"""
Probes Tunisianet and Spacenet to find:
  - Whether products are static HTML or loaded via JS/API
  - Correct CSS selectors
  - Pagination mechanism

Run:  python debug_all_sites.py
"""

import asyncio
import json
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

SITES = [
    {
        "name": "Tunisianet",
        "url":  "https://www.tunisianet.com.tn/301-pc-portable-tunisie",
    },
    {
        "name": "Spacenet",
        "url":  "https://www.spacenet.tn/pc-portables/",
    },
]

ITEM_SELECTORS = [
    "article.product-miniature",
    "div.product-miniature",
    ".js-product-miniature",
    ".product-container",
    ".product-item",
    ".product_item",
    ".product-card",
    "li.ajax_block_product",
    ".type-product",
    ".wc-block-grid__product",
]

PAGINATION_SELECTORS = [
    "a[rel='next']",
    ".next a",
    "li.next a",
    ".pagination a",
    ".page-item a",
    "[class*='pagination'] a",
    "[class*='page-next']",
    "a[class*='next']",
    "button[class*='next']",
]


async def probe_site(playwright, site: dict):
    name = site["name"]
    url  = site["url"]
    print(f"\n{'='*60}")
    print(f"  {name}  —  {url}")
    print(f"{'='*60}")

    api_calls = []
    browser   = await playwright.chromium.launch(headless=True)
    page      = await browser.new_page(
        extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9"}
    )

    async def on_response(response):
        ct  = response.headers.get("content-type", "")
        ru  = response.url
        if "json" in ct or any(k in ru for k in ["product", "api", "ajax", "search", "catalog", "listing"]):
            try:
                body = await response.body()
                if len(body) > 300:
                    api_calls.append({"url": ru, "size": len(body), "ct": ct,
                                      "body": body[:500].decode("utf-8", errors="replace")})
            except Exception:
                pass

    page.on("response", on_response)
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(6000)

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    # --- API calls? ---
    json_calls = [c for c in api_calls if "json" in c["ct"]]
    if json_calls:
        print(f"\n  ⚡ {len(json_calls)} JSON API call(s) detected — may be JS-rendered like Mytek")
        for c in json_calls[:3]:
            print(f"     {c['url'][:100]}  ({c['size']:,} bytes)")
            try:
                data = json.loads(c['body'])
                if isinstance(data, list):
                    print(f"     → array of {len(data)}, first keys: {list(data[0].keys())[:6] if data else '?'}")
                elif isinstance(data, dict):
                    print(f"     → object keys: {list(data.keys())[:8]}")
            except Exception:
                pass
    else:
        print(f"\n  ✔ No JSON API calls — products are likely in static HTML")

    # --- item selectors ---
    print(f"\n  Item selectors:")
    best = None
    for sel in ITEM_SELECTORS:
        els = soup.select(sel)
        if els:
            # check if they have real content (not skeleton)
            first_text = els[0].get_text(strip=True)
            is_skeleton = len(first_text) < 5
            status = f"✔  {len(els)} elements" + (" [SKELETON - JS needed]" if is_skeleton else " [HAS CONTENT ✔]")
            print(f"    {sel:<40} {status}")
            if not best and not is_skeleton:
                best = (sel, els)
        else:
            print(f"    {sel:<40} ✘")

    # --- field selectors on best item ---
    if best:
        sel, els = best
        el = els[0]
        print(f"\n  Fields inside '{sel}':")
        for fsel, label in [
            ("h2.product-title a",        "title"),
            ("h3.product-title a",        "title h3"),
            (".product-title a",          "title generic"),
            ("h2 a",                      "title h2>a"),
            (".woocommerce-loop-product__title", "title woo"),
            ("span.price",                "price"),
            (".price",                    "price generic"),
            (".woocommerce-Price-amount", "price woo"),
            ("span.regular-price",        "old price"),
            ("del .woocommerce-Price-amount", "old price woo"),
            ("span.product-availability", "availability"),
            (".stock",                    "stock woo"),
            ("a[href]",                   "link"),
            ("img",                       "image"),
        ]:
            node = el.select_one(fsel)
            if node:
                if node.name == "img":
                    src = node.get("src") or node.get("data-src") or node.get("data-lazy-src") or "?"
                    print(f"    ✔ {label:<25} → {src[:70]}")
                elif node.get("href"):
                    print(f"    ✔ {label:<25} → '{node.get_text(strip=True)[:35]}'  {node['href'][:55]}")
                else:
                    print(f"    ✔ {label:<25} → '{node.get_text(strip=True)[:60]}'")

    # --- pagination ---
    print(f"\n  Pagination:")
    for psel in PAGINATION_SELECTORS:
        node = soup.select_one(psel)
        if node:
            href = node.get("href", "")
            txt  = node.get_text(strip=True)[:20]
            print(f"    ✔ '{psel}' → text='{txt}'  href='{href[:70]}'")

    # --- scroll test ---
    api_before = len(api_calls)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(3000)
    if len(api_calls) > api_before:
        print(f"\n  ✔ Infinite scroll triggers new API calls!")
    else:
        print(f"\n  ✘ No infinite scroll detected")

    await browser.close()


async def main():
    async with async_playwright() as pw:
        for site in SITES:
            await probe_site(pw, site)
    print("\n\nDone. Paste this output to get the scrapers built.")


asyncio.run(main())
