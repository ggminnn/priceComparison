import logging
from fastapi import FastAPI, Query
from services.searchService import searchProducts

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")

app = FastAPI(title="Price Comparison API")


@app.get("/search")
async def search(query: str = Query(..., min_length=1, description="검색어")):
    results = await searchProducts(query)
    return {"query": query, "results": results}
