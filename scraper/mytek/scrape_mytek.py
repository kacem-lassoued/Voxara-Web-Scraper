"""
╔══════════════════════════════════════════════════════════════╗
║           MYTEK SCRAPER — scrape_mytek.py                    ║
║  Run:  python scrape_mytek.py                                ║
╚══════════════════════════════════════════════════════════════╝
"""

import asyncio
import csv
import json
import os
import re
from pathlib import Path
from playwright.async_api import async_playwright
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────
#  ▼▼▼  CONFIGURE HERE  ▼▼▼
# ─────────────────────────────────────────────────────────────

CATEGORIES = [
    # ── Informatique ──────────────────────────────────────────
    {
        "name": "Ordinateurs Portables",
        "url":  "https://www.mytek.tn/informatique/ordinateurs-portables.html",
    },
    {
        "name": "Ordinateurs de Bureau",
        "url":  "https://www.mytek.tn/informatique/ordinateur-de-bureau.html",
    },
    {
        "name": "Composants Informatique",
        "url":  "https://www.mytek.tn/informatique/composants-informatique.html",
    },
    {
        "name": "Périphériques & Accessoires",
        "url":  "https://www.mytek.tn/informatique/peripheriques-accessoires.html",
    },
    {
        "name": "Stockage",
        "url":  "https://www.mytek.tn/informatique/stockage.html",
    },
    {
        "name": "Tablettes Tactiles",
        "url":  "https://www.mytek.tn/informatique/tablettes-tactiles.html",
    },
    {
        "name": "Serveurs",
        "url":  "https://www.mytek.tn/informatique/serveurs.html",
    },

    # ── Impression ────────────────────────────────────────────
    {
        "name": "Imprimantes",
        "url":  "https://www.mytek.tn/impression/imprimantes.html",
    },
    {
        "name": "Photocopieurs",
        "url":  "https://www.mytek.tn/impression/photocopieurs.html",
    },
    {
        "name": "Scanners",
        "url":  "https://www.mytek.tn/impression/scanners.html",
    },
    {
        "name": "Consommables",
        "url":  "https://www.mytek.tn/impression/consommables.html",
    },

    # ── Téléphonie ────────────────────────────────────────────
    {
        "name": "Smartphones",
        "url":  "https://www.mytek.tn/telephonie-tunisie/smartphone-mobile-tunisie.html",
    },
    {
        "name": "Smartwatch",
        "url":  "https://www.mytek.tn/telephonie-tunisie/smartwatch.html",
    },
    {
        "name": "Accessoires Téléphonie",
        "url":  "https://www.mytek.tn/telephonie-tunisie/accessoires-telephonie.html",
    },
    {
        "name": "Téléphone Fixe",
        "url":  "https://www.mytek.tn/telephonie-tunisie/telephone-fixe.html",
    },

    # ── Image & Son ───────────────────────────────────────────
    {
        "name": "Téléviseurs",
        "url":  "https://www.mytek.tn/image-son/televiseurs.html",
    },
    {
        "name": "Home Cinéma",
        "url":  "https://www.mytek.tn/image-son/home-cinema.html",
    },
    {
        "name": "Son Numérique",
        "url":  "https://www.mytek.tn/image-son/son-numerique.html",
    },
    {
        "name": "Photos & Caméscopes",
        "url":  "https://www.mytek.tn/image-son/photos-camescopes.html",
    },
    {
        "name": "Projection",
        "url":  "https://www.mytek.tn/image-son/projection.html",
    },
    {
        "name": "Récepteurs Numériques & Box TV",
        "url":  "https://www.mytek.tn/image-son/recepteurs-numeriques-box-tv.html",
    },

    # ── Réseaux & Sécurité ────────────────────────────────────
    {
        "name": "Réseaux",
        "url":  "https://www.mytek.tn/reseaux-securite/reseaux.html",
    },
    {
        "name": "Onduleurs",
        "url":  "https://www.mytek.tn/reseaux-securite/onduleurs.html",
    },
    {
        "name": "Vidéosurveillance",
        "url":  "https://www.mytek.tn/reseaux-securite/videosurveillance.html",
    },
    {
        "name": "Câbles & Adaptateurs",
        "url":  "https://www.mytek.tn/reseaux-securite/cables-adaptateurs.html",
    },

    # ── Gaming ────────────────────────────────────────────────
    {
        "name": "Consoles de Jeux",
        "url":  "https://www.mytek.tn/gaming/console-de-jeux.html",
    },
    {
        "name": "Gaming PC",
        "url":  "https://www.mytek.tn/gaming/gaming-pc.html",
    },
    {
        "name": "Composants PC Gamer",
        "url":  "https://www.mytek.tn/gaming/composant-pc-gamer.html",
    },
    {
        "name": "Périphériques Gaming",
        "url":  "https://www.mytek.tn/gaming/peripheriques-et-accessoires-gamers.html",
    },
    {
        "name": "Accessoires de Jeux",
        "url":  "https://www.mytek.tn/gaming/accessoires-de-jeux.html",
    },
]

# Set to True to resume a run without re-scraping finished categories
SKIP_EXISTING = True

OUTPUT_DIR = "output"

# ─────────────────────────────────────────────────────────────
#  ▲▲▲  STOP EDITING HERE  ▲▲▲
# ─────────────────────────────────────────────────────────────

IMAGE_BASE   = "https://mk-media.mytek.tn/media/catalog/product/cache/4635b69058c0dccf0c8109f6ac6742cc"
PRODUCT_BASE = "https://www.mytek.tn"

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "changeme")


def parse_api_response(data: dict, category_name: str) -> list[dict]:
    items = []
    for p in data.get("items", []):
        pid       = p.get("id")
        price     = p.get("final_price")
        orig      = p.get("price")
        discount  = None
        if orig and price and orig > price:
            discount = round((orig - price) / orig * 100, 1)
        else:
            orig = None

        stock     = p.get("erpstock", {})
        avail     = stock.get("label")

        desc_html = p.get("short_description", "")
        desc      = re.sub(r"<[^>]+>", " ", desc_html).strip()
        desc      = re.sub(r"\s+", " ", desc)

        images    = p.get("images_gallery", [])
        image_url = (IMAGE_BASE + images[0]) if images else None
        item_url  = p.get("url") or f"{PRODUCT_BASE}/catalogsearch/result/?q={pid}"

        items.append({
            "item_id":        str(pid),
            "category":       category_name,
            "title":          p.get("name"),
            "price":          price,
            "currency":       "TND",
            "original_price": orig,
            "discount_pct":   discount,
            "availability":   avail,
            "description":    desc[:400] if desc else None,
            "image_url":      image_url,
            "item_url":       item_url,
            "source":         "mytek.tn",
        })
    return items


def get_total_pages(pagination_text: str) -> int:
    numbers = re.findall(r"\d+", pagination_text)
    return max(int(n) for n in numbers) if numbers else 1


def category_output_path(category_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", category_name.lower()).strip("_")
    return f"{OUTPUT_DIR}/mytek_{slug}.json"


async def scrape_category(playwright, category: dict) -> list[dict]:
    name     = category["name"]
    base_url = category["url"]
    all_items: list[dict] = []
    seen_ids: set[str]    = set()

    print(f"\n── {name} ──────────────────────────────────────────")

    out_path = category_output_path(name)
    if SKIP_EXISTING and Path(out_path).exists():
        print(f"   ↩  Skipping (already scraped: {out_path})")
        return json.loads(Path(out_path).read_text(encoding="utf-8"))

    browser = await playwright.chromium.launch(headless=True)

    page = await browser.new_page(
        extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9"}
    )

    page1_items: list[dict] = []

    async def on_page1_response(response):
        if "/api/products/volatile" in response.url:
            try:
                data  = await response.json()
                items = parse_api_response(data, name)
                page1_items.extend(items)
            except Exception:
                pass

    page.on("response", on_page1_response)
    await page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(6000)

    total_pages = 1
    try:
        pagination = await page.query_selector(".custom-pagination, .pagination-container")
        if pagination:
            text        = await pagination.inner_text()
            total_pages = get_total_pages(text)
    except Exception:
        pass

    print(f"   Total pages: {total_pages}")

    for it in page1_items:
        if it["item_id"] not in seen_ids:
            seen_ids.add(it["item_id"])
            all_items.append(it)
    print(f"   Page 1 → {len(page1_items)} products  (running total: {len(all_items)})")
    await page.close()

    for p_num in range(2, total_pages + 1):
        url = f"{base_url}?p={p_num}"
        page = await browser.new_page(
            extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9"}
        )

        page_items: list[dict] = []

        async def on_response(response, _items=page_items):
            if "/api/products/volatile" in response.url:
                try:
                    data  = await response.json()
                    items = parse_api_response(data, name)
                    _items.extend(items)
                except Exception:
                    pass

        page.on("response", on_response)
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(6000)
        await page.close()

        new = 0
        for it in page_items:
            if it["item_id"] not in seen_ids:
                seen_ids.add(it["item_id"])
                all_items.append(it)
                new += 1

        print(f"   Page {p_num} → {len(page_items)} products  ({new} new, running total: {len(all_items)})")

        if not page_items:
            print(f"   No products on page {p_num} — stopping early.")
            break

        await asyncio.sleep(1)

    await browser.close()
    print(f"   ✔ {name}: {len(all_items)} total products")

    if all_items:
        Path(out_path).write_text(
            json.dumps(all_items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"   ✔  saved → {out_path}")

    return all_items


async def main():
    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    all_items: list[dict] = []

    async with async_playwright() as pw:
        for cat in CATEGORIES:
            items = await scrape_category(pw, cat)
            all_items.extend(items)

    if not all_items:
        print("\n⚠  No items scraped.")
        return

    json_path = f"{OUTPUT_DIR}/mytek_results.json"
    Path(json_path).write_text(
        json.dumps(all_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    csv_path = f"{OUTPUT_DIR}/mytek_results.csv"
    keys = list(all_items[0].keys())
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_items)

    print(f"\n── Done ──────────────────────────────────────────────")
    print(f"   {len(all_items)} total products across {len(CATEGORIES)} categories")
    print(f"   ✔  {json_path}")
    print(f"   ✔  {csv_path}")

    by_cat = {}
    for it in all_items:
        by_cat.setdefault(it["category"], 0)
        by_cat[it["category"]] += 1
    print("\n   Products per category:")
    for cat_name, count in by_cat.items():
        print(f"      {cat_name}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
