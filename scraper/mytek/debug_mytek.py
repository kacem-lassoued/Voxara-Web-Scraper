"""
Checks how Mytek pagination works — scroll vs buttons vs URL params.
    python debug_mytek.py
"""

import asyncio
from playwright.async_api import async_playwright

URL = "https://www.mytek.tn/informatique/ordinateurs-portables.html"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9"}
        )

        api_calls = []

        async def on_response(response):
            if "/api/products/volatile" in response.url:
                api_calls.append(response.url)
                print(f"  API call #{len(api_calls)}: {response.url[:120]}")

        page.on("response", on_response)

        print(f"Loading page ...\n")
        await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        # --- check what pagination elements exist ---
        print("\n── Pagination elements found ────────────────────────")
        selectors = [
            "a.page-item-next",
            "li.pages-item-next a",
            "[aria-label='Next']",
            ".pagination a",
            "a[rel='next']",
            ".page-item a",
            "[class*='pagination']",
            "[class*='page-next']",
            "[class*='next']",
            "button[class*='next']",
            "button[class*='load']",
            "[class*='load-more']",
        ]
        for sel in selectors:
            els = await page.query_selector_all(sel)
            if els:
                for el in els[:2]:
                    txt  = await el.inner_text()
                    href = await el.get_attribute("href")
                    cls  = await el.get_attribute("class")
                    print(f"  ✔ '{sel}' → text='{txt.strip()[:40]}'  href='{href}'  class='{cls}'")
            else:
                print(f"  ✘ '{sel}'")

        # --- scroll to bottom and see if more products load ---
        print("\n── Scroll test ──────────────────────────────────────")
        api_before = len(api_calls)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(5000)
        api_after = len(api_calls)
        if api_after > api_before:
            print(f"  ✔ Infinite scroll works! {api_after - api_before} new API call(s) after scrolling")
        else:
            print(f"  ✘ No new API calls after scrolling")

        # --- check URL pattern for page 2 ---
        print("\n── URL pattern test (page=2) ─────────────────────────")
        api_before = len(api_calls)
        await page.goto(URL + "?p=2", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        api_after = len(api_calls)
        if api_after > api_before:
            print(f"  ✔ ?p=2 works! Got {api_after - api_before} API call(s)")
        else:
            print(f"  ✘ ?p=2 did not trigger new API calls")

        # --- try ?page=2 ---
        print("\n── URL pattern test (page=2 param) ───────────────────")
        api_before = len(api_calls)
        await page.goto(URL + "?page=2", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        api_after = len(api_calls)
        if api_after > api_before:
            print(f"  ✔ ?page=2 works! Got {api_after - api_before} API call(s)")
        else:
            print(f"  ✘ ?page=2 did not trigger new API calls")

        await browser.close()

    print(f"\n── Summary ───────────────────────────────────────────")
    print(f"  Total API calls seen: {len(api_calls)}")
    for i, u in enumerate(api_calls):
        print(f"  [{i+1}] {u[:120]}")

asyncio.run(main())
