# 🛒 PriceComparison — 쇼핑몰 최저가 비교 API

> 네이버쇼핑과 11번가를 **동시에** 검색해 가격 낮은 순으로 정렬된 결과를 반환하는 FastAPI 백엔드

---

## 프로젝트 소개

소비자가 동일 상품을 여러 쇼핑몰에서 직접 검색하는 번거로움을 없애기 위해 제작했습니다.  
검색어 하나로 네이버쇼핑(공식 API)과 11번가(Playwright 크롤링)를 **비동기 병렬 처리**로 동시에 조회하고,  
전체 결과를 가격 오름차순으로 정렬해 단일 엔드포인트에서 반환합니다.

### 핵심 특징

- **병렬 처리** — `asyncio.gather`로 두 쇼핑몰을 동시에 조회, 응답 시간 최소화
- **이기종 수집 전략** — 공식 API(네이버)와 Playwright 크롤링(11번가)을 상황에 맞게 혼용
- **실전 트러블슈팅** — CAPTCHA 차단, 이벤트 루프 충돌 등 실제 운영 이슈 해결 경험

---

## 기술 스택

| 역할 | 기술 |
|------|------|
| 백엔드 프레임워크 | FastAPI |
| 네이버쇼핑 수집 | 네이버 쇼핑 검색 API + httpx (비동기 HTTP) |
| 11번가 수집 | Playwright (Chromium 헤드리스 브라우저) |
| 병렬 처리 | asyncio.gather + asyncio.to_thread |
| 환경 변수 관리 | python-dotenv |
| 런타임 | Python 3.12 / uvicorn |

---

## 시스템 아키텍처

```
클라이언트
    │
    │  GET /search?query=에어팟
    ▼
┌─────────────────────────────────────┐
│            FastAPI (main.py)        │
│         GET /search endpoint        │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│       searchService.py              │
│   asyncio.gather(크롤러 A, 크롤러 B) │  ← 두 크롤러 동시 실행
│   결과 합산 후 price 오름차순 정렬   │
└──────┬──────────────────┬───────────┘
       │                  │
       ▼                  ▼
┌─────────────┐   ┌──────────────────────────┐
│ naverCrawler│   │     elevenCrawler         │
│             │   │                           │
│ 네이버 쇼핑  │   │ sync_playwright           │
│ 검색 API    │   │ + asyncio.to_thread()     │
│ (httpx)     │   │ (이벤트 루프 충돌 방지)    │
└──────┬──────┘   └──────────────┬────────────┘
       │                         │
       ▼                         ▼
 Naver Open API           11번가 검색 페이지
 (JSON 응답)              (Chromium 렌더링)
```

---

## 트러블슈팅 과정

실제 개발 중 맞닥뜨린 문제와 해결 과정입니다.

### 1. 네이버쇼핑 CAPTCHA 차단

**문제**  
Playwright로 `search.shopping.naver.com`에 접근하자 "*쇼핑 서비스 접속이 일시적으로 제한되었습니다*" 에러 페이지 반환.  
User-Agent 스푸핑, `navigator.webdriver` 숨기기 등 스텔스 기법을 적용해도 CAPTCHA 페이지로 리다이렉트됨.

**원인 분석**  
Playwright 자체의 브라우저 핑거프린트를 IP 수준에서 감지. 스텔스 기법으로는 우회 불가능한 단계.

**해결**  
네이버 개발자센터의 **쇼핑 검색 API** 로 전환.  
Playwright 없이 `httpx` 비동기 HTTP 클라이언트로 대체 → 안정성과 속도 모두 향상.

```python
# Before: Playwright (CAPTCHA 차단)
await page.goto("https://search.shopping.naver.com/...")

# After: 공식 API (안정적)
resp = await client.get("https://openapi.naver.com/v1/search/shop.json", ...)
```

---

### 2. 11번가 CSS 셀렉터 깨짐

**문제**  
`li.basicList_item__0T9YD` 같은 하드코딩된 셀렉터가 배포마다 빈 배열 반환.

**원인 분석**  
11번가(및 네이버)는 Next.js/CSS Modules를 사용해 클래스명 뒤에 해시 suffix(`__0T9YD`)를 붙임.  
사이트 재배포 시 해시가 변경되어 셀렉터가 무효화됨.

**해결**  
`[class*="partialName"]` 속성 포함 셀렉터로 전환 — 해시 suffix 변경에 내성 확보.  
실제 DOM을 Playwright로 열어 클래스명을 직접 덤프하는 `debugCrawler.py` 작성으로 빠른 재진단 가능.

```python
# Before: 해시 suffix 포함 (배포마다 깨짐)
"li.basicList_item__0T9YD"

# After: 부분 일치 (해시 변경에 내성)
"li[class*='basicList_item']"
"li.c-search-list__item"  # 11번가 실제 DOM 확인 후 적용
```

---

### 3. asyncio 이벤트 루프 충돌

**문제**  
`async_playwright()`를 FastAPI/uvicorn 내에서 사용하자 11번가 크롤러가 결과 0개 반환.  
서버 로그에는 에러 없음 → 조용한 실패.

**원인 분석**  
Playwright는 내부적으로 자체 이벤트 루프 관리 로직을 가짐.  
uvicorn의 asyncio 이벤트 루프 안에서 `async_playwright()`를 중첩 실행하면 충돌 발생.

**해결**  
`sync_playwright` + `asyncio.to_thread()` 조합으로 전환.  
Playwright를 별도 스레드에서 동기 실행 → 이벤트 루프 완전 분리.

```python
# Before: 이벤트 루프 충돌
async def crawlEleven(...):
    async with async_playwright() as p:  # uvicorn 루프와 충돌
        ...

# After: 스레드 분리
def _crawlElevenSync(...):          # 동기 함수
    with sync_playwright() as p:    # 자체 스레드에서 실행
        ...

async def crawlEleven(...):
    return await asyncio.to_thread(_crawlElevenSync, searchQuery)  # 스레드 풀 위임
```

---

### 4. 어뷰징 상품 필터링

**문제**  
네이버 API를 `sort=asc`(가격 오름차순)로 호출하니 10원, 20원짜리 어뷰징 상품이 상위 노출.

**해결**  
API 호출을 `sort=sim`(관련도순)으로 변경하고, 서비스 레이어에서 가격 정렬.  
`price >= 100` 최소 필터 추가.

---

## 실행 방법

### 1. 네이버 API 키 발급

1. [https://developers.naver.com](https://developers.naver.com) 로그인
2. **Application → 애플리케이션 등록**
3. 사용 API → **검색** 선택
4. Client ID / Client Secret 발급

### 2. 환경 설정

```bash
# 저장소 클론
git clone https://github.com/your-id/priceComparison.git
cd priceComparison

# 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# Playwright Chromium 브라우저 설치 (최초 1회)
playwright install chromium
```

### 3. .env 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 네이버 API 키 입력:

```env
HEADLESS=true
REQUEST_TIMEOUT_MS=15000
MAX_RESULTS_PER_MALL=20
NAVER_CLIENT_ID=발급받은_클라이언트_ID
NAVER_CLIENT_SECRET=발급받은_클라이언트_시크릿
```

### 4. 서버 실행

```bash
uvicorn main:app --reload --log-level info
```

---

## API 사용 예시

### `GET /search?query={검색어}`

두 쇼핑몰을 동시에 검색해 가격 낮은 순으로 정렬된 결과를 반환합니다.

**요청**
```bash
curl -G "http://localhost:8000/search" --data-urlencode "query=에어팟"
```

**응답**
```json
{
  "query": "에어팟",
  "results": [
    {
      "productName": "차이팟 프로 2세대 에어팟 오픈형 블루투스 무선 이어폰",
      "price": 34900,
      "reviewCount": null,
      "mall": "naver"
    },
    {
      "productName": "에어팟 프로 3 블루투스 이어폰 MFHP4KH/A",
      "price": 335790,
      "reviewCount": 746,
      "mall": "11번가"
    },
    {
      "productName": "Apple 에어팟 프로 2세대 (USB-C)",
      "price": 299000,
      "reviewCount": null,
      "mall": "naver"
    }
  ]
}
```

> **참고**: 네이버 쇼핑 API는 리뷰 수를 제공하지 않아 `reviewCount`가 `null`로 반환됩니다.  
> 11번가는 Playwright 크롤링으로 실제 리뷰 수를 수집합니다.

### 자동 문서 (Swagger UI)

서버 실행 후 브라우저에서 확인:

```
http://localhost:8000/docs
```

---

## 프로젝트 구조

```
priceComparison/
├── main.py                  # FastAPI 앱, GET /search 엔드포인트
├── crawlers/
│   ├── naverCrawler.py      # 네이버 쇼핑 API (httpx)
│   └── elevenCrawler.py     # 11번가 Playwright 크롤러
├── services/
│   └── searchService.py     # asyncio.gather 병렬 처리 + 가격 정렬
├── debugCrawler.py          # DOM 셀렉터 진단 도구 (headless=False)
├── .env.example
└── requirements.txt
```

---

## 상세 동작 흐름

파일별 코드 레벨 분석 → [flow.md](./flow.md)
