# 요청 처리 흐름 — 파일별 상세 분석

> `GET /search?query=에어팟` 요청이 들어왔을 때 어떤 파일이, 어떤 순서로, 무엇을 하는지 추적한다.

---

## 전체 흐름 한눈에 보기

```
클라이언트
    │
    │  GET /search?query=에어팟
    ▼
① main.py              — 요청 수신, 파라미터 검증
    │
    ▼
② searchService.py     — 두 크롤러를 asyncio.gather로 동시 실행
    │
    ├──────────────────────────────────────┐
    ▼                                      ▼
③ naverCrawler.py              ④ elevenCrawler.py
  (네이버 쇼핑 API, httpx)        (11번가, Playwright)
  ~1초                            ~5~10초
    │                                      │
    └──────────────┬───────────────────────┘
                   ▼
② searchService.py     — 두 결과 합산, price 오름차순 정렬
    │
    ▼
① main.py              — JSON 응답 반환
    │
    ▼
클라이언트
```

> 핵심: ③과 ④는 **동시에 실행**된다.  
> 전체 응답 시간 ≈ max(네이버 시간, 11번가 시간) — 두 시간의 합이 아님.

---

## ① main.py — 진입점

```python
import logging
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from services.searchService import searchProducts

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")

app = FastAPI(title="Price Comparison API")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", include_in_schema=False)
async def index():
    return FileResponse("static/index.html")   # 웹 UI 서빙

@app.get("/search")
async def search(query: str = Query(..., min_length=1, description="검색어")):
    results = await searchProducts(query)
    return {"query": query, "results": results}
```

**하는 일**
- `GET /` — `static/index.html`을 반환. 브라우저에서 바로 검색 UI 사용 가능
- `GET /search?query=...` — 검색 API. `Query(..., min_length=1)`으로 빈 문자열 차단 (400 반환)
- `app.mount("/static", ...)` — CSS·JS 등 정적 자산 서빙 경로 등록
- `await searchProducts(query)` — 실제 처리를 서비스 레이어에 위임

**설계 포인트**  
라우터는 HTTP 입출력만 담당. 비즈니스 로직(검색, 정렬)은 서비스 레이어로 분리.  
웹 UI와 API가 같은 서버에서 동작하므로 별도 프론트엔드 서버 불필요.

---

## ② searchService.py — 병렬 처리 + 정렬

```python
import asyncio
from crawlers.naverCrawler import crawlNaver
from crawlers.elevenCrawler import crawlEleven

async def searchProducts(searchQuery: str) -> list[dict]:
    naverResults, elevenResults = await asyncio.gather(
        crawlNaver(searchQuery),   # 동시 시작
        crawlEleven(searchQuery),  # 동시 시작
    )

    combined = naverResults + elevenResults
    combined.sort(key=lambda item: item["price"])
    return combined
```

**하는 일**
- `asyncio.gather()` — 두 크롤러를 **동시에** 시작하고 둘 다 끝날 때까지 기다림
- 각 크롤러가 반환한 리스트를 합산 후 `price` 기준 오름차순 정렬
- 한쪽 크롤러가 실패해도 다른 쪽 결과는 그대로 반환됨 (빈 리스트로 처리)

**asyncio.gather 타임라인**

```
시간 →   0s          3s          8s
         │           │           │
네이버   [══════════]            (완료)
11번가   [══════════════════════](완료)
                                 │
                         gather 완료 → 정렬 → 반환
```

> `gather` 없이 순차 실행이면 3s + 8s = **11초**.  
> `gather` 사용 시 max(3s, 8s) = **8초**. 응답 시간 27% 단축.

---

## ③ naverCrawler.py — 네이버 쇼핑 API (httpx)

```python
import httpx, re, os, logging
from dotenv import load_dotenv

load_dotenv()
_CLIENT_ID     = os.getenv("NAVER_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
_API_URL = "https://openapi.naver.com/v1/search/shop.json"

async def crawlNaver(searchQuery: str) -> list[dict]:
    if not _CLIENT_ID or not _CLIENT_SECRET:
        logger.error("Naver: API 키가 .env에 없습니다")
        return []

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            _API_URL,
            params={"query": searchQuery, "display": 20, "sort": "sim"},
            headers={
                "X-Naver-Client-Id": _CLIENT_ID,
                "X-Naver-Client-Secret": _CLIENT_SECRET,
            },
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])

        for item in items:
            productName = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
            price = int(item.get("lprice") or 0)

            if productName and price >= 100:   # 어뷰징 상품 필터
                results.append({
                    "productName": productName,
                    "price": price,
                    "reviewCount": None,       # API가 제공하지 않음
                    "link": item.get("link", ""),
                    "mall": "naver",
                })
```

**하는 일**
1. `.env`에서 API 키 로드 — 키 없으면 즉시 `[]` 반환 (서버 전체 죽지 않음)
2. `httpx.AsyncClient`로 네이버 쇼핑 검색 API 비동기 호출
3. `sort=sim` (관련도순) — API 단에서 가격순 정렬 안 함, 정렬은 서비스 레이어에서
4. 응답 JSON `title` 필드에 `<b>에어팟</b>` 같은 HTML 태그가 섞여 있어 `re.sub`으로 제거
5. `price >= 100` 필터 — 어뷰징 10원·20원짜리 상품 제거

**왜 Playwright가 아닌 API인가?**

```
처음 시도: Playwright로 search.shopping.naver.com 접근
결과:      "쇼핑 서비스 접속이 일시적으로 제한되었습니다" (CAPTCHA)

원인:      네이버가 IP + 브라우저 핑거프린트 수준에서 봇 감지
           User-Agent 스푸핑, navigator.webdriver 숨기기로도 우회 불가

해결:      공식 쇼핑 검색 API 전환
           → 안정적, CAPTCHA 없음, 응답 속도도 빠름 (~1초)
```

---

## ④ elevenCrawler.py — 11번가 Playwright 크롤링

```python
import asyncio
from playwright.sync_api import sync_playwright

# CSS 셀렉터 (실제 DOM 확인 기반, 2025-05)
ITEM_SEL   = "li.c-search-list__item"
NAME_SEL   = "div.c-card-item__name dd"
PRICE_SEL  = ".c-card-item__price .value"   # div가 아닌 dd 태그 — 태그 제거
REVIEW_SEL = "dd.c-starrate__review .value"

def _crawlElevenSync(searchQuery: str) -> list[dict]:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],  # Linux/WSL2 필수
        )
        page = browser.new_page()
        page.goto(f"https://search.11st.co.kr/Search.tmall?kwd={searchQuery}")
        page.wait_for_selector(ITEM_SEL)          # JS 렌더링 완료까지 대기
        items = page.query_selector_all(ITEM_SEL) # 상품 카드 전체 선택

        for item in items[:20]:
            anchorEl = item.query_selector("a.c-card-item__anchor")
            name   = item.query_selector(NAME_SEL).inner_text()
            price  = int(re.sub(r"[^0-9]", "", item.query_selector(PRICE_SEL).inner_text()))
            review = int(re.sub(r"[^0-9]", "", item.query_selector(REVIEW_SEL).inner_text()))
            link   = anchorEl.get_attribute("href") if anchorEl else ""
            results.append({"productName": name, "price": price,
                            "reviewCount": review, "link": link, "mall": "11번가"})

async def crawlEleven(searchQuery: str) -> list[dict]:
    return await asyncio.to_thread(_crawlElevenSync, searchQuery)
    #            ↑ 동기 함수를 스레드 풀에서 실행
```

**하는 일 (단계별)**

```
1. asyncio.to_thread() 호출
   → _crawlElevenSync를 별도 스레드에서 실행
   → uvicorn 이벤트 루프와 완전히 분리

2. Chromium 브라우저 실행 (headless)
   → --no-sandbox: Linux/WSL2 환경 필수 플래그

3. 11번가 검색 페이지 이동
   → page.wait_for_selector(ITEM_SEL)
   → JavaScript 렌더링이 완료되어 상품 카드가 DOM에 나타날 때까지 대기

4. 상품 카드(li.c-search-list__item) 전체 선택
   → 각 카드에서 이름, 가격, 리뷰 수 추출

5. 숫자 추출: re.sub(r"[^0-9]", "", "335,790원") → 335790

6. 브라우저 종료 후 결과 반환
```

**왜 sync_playwright + asyncio.to_thread인가?**

```
처음 시도: async_playwright() — uvicorn 이벤트 루프 안에서 실행
결과:      11번가 결과 0개, 에러 로그 없음 (조용한 실패)

원인:      Playwright 내부가 자체 이벤트 루프를 관리
           uvicorn의 asyncio 루프와 충돌 → 크롤러 실행 실패

해결:      sync_playwright(동기 API) + asyncio.to_thread()
           → Playwright는 별도 스레드에서 독립 실행
           → asyncio.gather는 스레드 완료를 기다림
           → 이벤트 루프 간섭 없음
```

**11번가 DOM 구조 (실제 확인)**

```html
<li class="c-search-list__item">                          ← ITEM_SEL
  <a class="c-card-item__anchor" href="https://...">      ← link (href 추출)
  </a>
  <div class="c-card-item__name">
    <dd>에어팟 프로 3세대</dd>                             ← NAME_SEL
  </div>
  <dd class="c-card-item__price">                         ← PRICE_SEL (dd, div 아님)
    <span class="value">335,790</span>
  </dd>
  <dd class="c-starrate__review">
    <span class="value">(746)</span>                      ← REVIEW_SEL
  </dd>
</li>
```

> `c-card-item__price`는 `dd` 태그. 처음에 `div.c-card-item__price`로 작성해  
> 111개 요소를 찾고도 가격을 하나도 파싱 못 하는 버그 발생.  
> 태그명을 제거하고 `.c-card-item__price .value`로 수정해 해결.

---

## 데이터 모델 — 크롤러 출력 형식

두 크롤러 모두 동일한 dict 구조를 반환한다. 서비스 레이어가 `price` 키만 보고 정렬하면 되기 때문.

```python
{
    "productName": str,        # 상품명
    "price":       int,        # 판매가 (원)
    "reviewCount": int | None, # 리뷰 수 (네이버는 None — API 미제공)
    "link":        str,        # 상품 페이지 URL
    "mall":        str,        # "naver" | "11번가"
}
```

| 필드 | 네이버 | 11번가 |
|------|--------|--------|
| productName | API `title` 필드 (HTML 태그 제거) | DOM `div.c-card-item__name dd` |
| price | API `lprice` 필드 | DOM `.c-card-item__price .value` (숫자만 추출) |
| reviewCount | `None` (API 미제공) | DOM `dd.c-starrate__review .value` (숫자만 추출) |
| link | API `link` 필드 | DOM `a.c-card-item__anchor`의 `href` 속성 |

---

## 환경변수 (.env)

```env
HEADLESS=true                  # false 로 바꾸면 브라우저 창이 실제로 열림
REQUEST_TIMEOUT_MS=15000       # Playwright 페이지 로드 타임아웃
MAX_RESULTS_PER_MALL=20        # 쇼핑몰당 최대 수집 개수
NAVER_CLIENT_ID=...            # 네이버 개발자센터 발급
NAVER_CLIENT_SECRET=...        # 네이버 개발자센터 발급
```

각 크롤러는 모듈 로드 시점에 `os.getenv()`로 읽어서 상수로 저장한다.  
서버 재시작 없이 `.env`만 바꿔도 다음 재시작 시 반영됨.

---

## 예외 처리 전략

```
크롤러 내부 예외
    │
    ├── 아이템 단위 에러 → logger.warning + continue (해당 상품만 건너뜀)
    │
    └── 크롤러 전체 에러 → logger.error + return []
                                              ↑
                           빈 리스트 반환 → searchService가 다른 쪽 결과는 유지
```

네이버 API 장애 시에도 11번가 결과는 정상 반환되고, 그 반대도 마찬가지.  
두 크롤러는 `asyncio.gather`로 독립적으로 실행되기 때문에 한쪽 실패가 다른 쪽에 영향을 주지 않는다.
