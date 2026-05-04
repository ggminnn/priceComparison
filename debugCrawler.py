import asyncio
import re
from playwright.async_api import async_playwright

NAVER_URL = "https://search.shopping.naver.com/search/all?query=에어팟"
ELEVEN_URL = "https://search.11st.co.kr/Search.tmall?kwd=에어팟"
DEBUG_TIMEOUT = 30_000

NAVER_CANDIDATES = [
    "li[class*='basicList_item']",
    "ul[class*='basicList'] > li",
    "li[class*='product_item']",
]
ELEVEN_CANDIDATES = [
    "li.c-search-list__item",
    "ul[class*='c-product-list'] > li",
    "li[class*='c-product']",
]

_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
window.chrome = {runtime: {}};
"""

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


async def inspectSite(page, label, candidates, fullHtmlPath):
    fullHtml = await page.content()
    with open(fullHtmlPath, "w", encoding="utf-8") as f:
        f.write(fullHtml)
    print(f"[{label}] full page HTML → {fullHtmlPath} ({len(fullHtml)} chars)")

    liClasses = await page.evaluate("""() => {
        const counts = {};
        document.querySelectorAll('li, ul, ol').forEach(el => {
            el.className.split(' ').forEach(c => {
                if (c) counts[c] = (counts[c] || 0) + 1;
            });
        });
        return Object.entries(counts)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 40)
            .map(([cls, n]) => `${n}x  .${cls}`);
    }""")
    print(f"\n[{label}] Top li/ul/ol classes:")
    for line in liClasses:
        print(f"  {line}")

    matched, items = None, []
    for sel in candidates:
        try:
            await page.wait_for_selector(sel, timeout=3000)
            items = await page.query_selector_all(sel)
            if items:
                matched = sel
                break
        except Exception:
            continue

    print(f"\n[{label}] matched={matched}, count={len(items)}")
    for i, item in enumerate(items[:2]):
        html = await item.evaluate("el => el.outerHTML")
        classes = sorted({c for m in re.findall(r'class="([^"]+)"', html) for c in m.split()})
        print(f"\n  item{i+1} classes: {classes}")
        print(f"  item{i+1} html[:1000]:\n{html[:1000]}")


async def main():
    async with async_playwright() as p:
        # --- Naver (스텔스 적용) ---
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=_USER_AGENT,
            locale="ko-KR",
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9",
                "Referer": "https://www.naver.com/",
            },
        )
        page = await context.new_page()
        await page.add_init_script(_STEALTH_SCRIPT)
        print(f"\n[Naver] opening {NAVER_URL}")
        await page.goto(NAVER_URL, timeout=DEBUG_TIMEOUT)
        await page.wait_for_timeout(4000)
        await inspectSite(page, "Naver", NAVER_CANDIDATES, "debug_naver.html")
        await browser.close()

        # --- 11번가 ---
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        print(f"\n[11번가] opening {ELEVEN_URL}")
        await page.goto(ELEVEN_URL, timeout=DEBUG_TIMEOUT)
        await page.wait_for_timeout(4000)
        await inspectSite(page, "11번가", ELEVEN_CANDIDATES, "debug_eleven.html")
        await browser.close()


asyncio.run(main())
