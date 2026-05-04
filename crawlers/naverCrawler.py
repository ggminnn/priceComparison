import logging
import os
import re
import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
maxResults = int(os.getenv("MAX_RESULTS_PER_MALL", "20"))

_API_URL = "https://openapi.naver.com/v1/search/shop.json"


async def crawlNaver(searchQuery: str) -> list[dict]:
    if not _CLIENT_ID or not _CLIENT_SECRET:
        logger.error("Naver: NAVER_CLIENT_ID / NAVER_CLIENT_SECRET not set in .env")
        return []

    results = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _API_URL,
                params={"query": searchQuery, "display": maxResults, "sort": "sim"},
                headers={
                    "X-Naver-Client-Id": _CLIENT_ID,
                    "X-Naver-Client-Secret": _CLIENT_SECRET,
                },
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            logger.info(f"Naver: {len(items)} items found")

            for item in items:
                try:
                    productName = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
                    price = int(item.get("lprice") or 0)

                    if productName and price >= 100:
                        results.append({
                            "productName": productName,
                            "price": price,
                            "reviewCount": None,  # 네이버 쇼핑 API 미제공
                            "mall": "naver",
                        })
                except Exception as e:
                    logger.warning(f"Naver: item parse error — {e}")
                    continue
    except Exception as e:
        logger.error(f"Naver: API call failed — {e}")

    return results
