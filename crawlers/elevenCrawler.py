import asyncio
import logging
import os
import re
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

headless = os.getenv("HEADLESS", "true").lower() == "true"
timeoutMs = int(os.getenv("REQUEST_TIMEOUT_MS", "15000"))
maxResults = int(os.getenv("MAX_RESULTS_PER_MALL", "20"))

# DOM 확인 기반 정확한 셀렉터 (2025-05 기준)
ITEM_SEL = "li.c-search-list__item"
NAME_SEL = "div.c-card-item__name dd"
PRICE_SEL = ".c-card-item__price .value"
REVIEW_SEL = "dd.c-starrate__review .value"


def _crawlElevenSync(searchQuery: str) -> list[dict]:
    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = browser.new_page()
            encodedQuery = searchQuery.replace(" ", "+")
            page.goto(
                f"https://search.11st.co.kr/Search.tmall?kwd={encodedQuery}",
                timeout=timeoutMs,
            )
            page.wait_for_selector(ITEM_SEL, timeout=timeoutMs)
            items = page.query_selector_all(ITEM_SEL)
            logger.info(f"11번가: {len(items)} items found")

            for item in items[:maxResults]:
                try:
                    nameEl   = item.query_selector(NAME_SEL)
                    priceEl  = item.query_selector(PRICE_SEL)
                    reviewEl = item.query_selector(REVIEW_SEL)
                    anchorEl = item.query_selector("a.c-card-item__anchor")

                    productName = nameEl.inner_text() if nameEl else ""
                    rawPrice    = priceEl.inner_text() if priceEl else "0"
                    rawReview   = reviewEl.inner_text() if reviewEl else "0"
                    link        = anchorEl.get_attribute("href") if anchorEl else ""

                    price       = int(re.sub(r"[^0-9]", "", rawPrice) or 0)
                    reviewCount = int(re.sub(r"[^0-9]", "", rawReview) or 0)

                    if productName and price > 0:
                        results.append({
                            "productName": productName.strip(),
                            "price": price,
                            "reviewCount": reviewCount,
                            "link": link,
                            "mall": "11번가",
                        })
                    else:
                        logger.debug(f"11번가: skipped — name={repr(productName)}, price={price}")
                except Exception as e:
                    logger.warning(f"11번가: item parse error — {e}")
                    continue

            browser.close()
    except Exception as e:
        logger.error(f"11번가: crawl failed — {e}")

    return results


async def crawlEleven(searchQuery: str) -> list[dict]:
    # sync_playwright를 별도 스레드에서 실행 — uvicorn 이벤트 루프 충돌 방지
    return await asyncio.to_thread(_crawlElevenSync, searchQuery)
