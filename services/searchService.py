import asyncio
from crawlers.naverCrawler import crawlNaver
from crawlers.elevenCrawler import crawlEleven


async def searchProducts(searchQuery: str) -> list[dict]:
    naverResults, elevenResults = await asyncio.gather(
        crawlNaver(searchQuery),
        crawlEleven(searchQuery),
    )

    combined = naverResults + elevenResults
    combined.sort(key=lambda item: item["price"])
    return combined
