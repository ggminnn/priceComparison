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
    return FileResponse("static/index.html")


@app.get("/search")
async def search(query: str = Query(..., min_length=1, description="검색어")):
    results = await searchProducts(query)
    return {"query": query, "results": results}
