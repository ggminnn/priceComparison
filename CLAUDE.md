# priceComparison

쇼핑몰 별 최저가 검색 프로그램. 사용자가 검색어를 입력하면 네이버쇼핑과 11번가를 동시에 크롤링하여 가격 낮은 순으로 결과를 반환한다.

## 기술 스택

- **백엔드**: FastAPI`
- **크롤링**: Playwright (async)
- **동시 처리**: asyncio.gather
- **환경변수**: python-dotenv (.env)

## 프로젝트 구조

```
priceComparison/
├── main.py                  # FastAPI 앱 진입점, 라우터 정의
├── crawlers/
│   ├── naverCrawler.py      # 네이버쇼핑 크롤러
│   └── elevenCrawler.py     # 11번가 크롤러
├── services/
│   └── searchService.py     # 두 크롤러를 gather로 묶어 정렬 반환
├── .env                     # 환경변수 (git 제외)
├── .env.example             # 환경변수 템플릿
├── requirements.txt
└── CLAUDE.md
```

## 네이밍 컨벤션

- **변수명, 함수명**: camelCase (예: `searchQuery`, `getLowestPrice`)
- **클래스명**: PascalCase (예: `NaverCrawler`)
- **파일명**: camelCase (예: `naverCrawler.py`)

## 데이터 모델

각 크롤러는 아래 구조의 dict 리스트를 반환한다:

```python
{
    "productName": str,   # 상품명
    "price": int,         # 판매가 (원)
    "reviewCount": int,   # 리뷰 수
    "mall": str           # 쇼핑몰명 ("naver" | "11번가")
}
```

## API

### GET /search?query={검색어}

두 쇼핑몰을 동시에 검색하여 가격 낮은 순으로 정렬된 상품 리스트를 반환한다.

**응답 예시**:
```json
{
    "query": "에어팟",
    "results": [
        {
            "productName": "애플 에어팟 4세대",
            "price": 159000,
            "reviewCount": 1234,
            "mall": "11번가"
        }
    ]
}
```

## 개발 명령어

```bash
# 가상환경 활성화
source venv/bin/activate

# 서버 실행
uvicorn main:app --reload

# Playwright 브라우저 설치 (최초 1회)
playwright install chromium
```

## 주의사항

- 크롤러 각각은 독립적으로 실패해도 다른 쇼핑몰 결과는 반환한다 (빈 리스트로 처리).
- Playwright는 headless 모드로 실행한다.
- `.env`는 절대 커밋하지 않는다.
