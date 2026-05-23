# Voxara — Price Intelligence Scraper

> Scrapes **Mytek.tn** and **Tunisianet.com.tn**, normalizes product data, and exports to JSON, CSV, and SQLite.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
  - [Mytek — API Interception](#mytek--api-interception)
  - [Tunisianet — HTML Parsing](#tunisianet--html-parsing)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Scrapers](#running-the-scrapers)
- [Running the Normalizer](#running-the-normalizer)
- [Output Files](#output-files)
- [Data Schema](#data-schema)
- [Normalizer Spec Extraction](#normalizer-spec-extraction)
- [Adding Categories](#adding-categories)

---

## Overview

Voxara solves a simple problem: no Tunisian price comparison tool exists. Consumers visit Mytek, Tunisianet, and other stores one by one to compare prices. Voxara automates this by scraping both stores, merging the data into a unified schema, and computing discounts automatically.

| Source | Method | Categories | Products |
|---|---|---|---|
| mytek.tn | API interception (Playwright) | 29 | ~15,000 |
| tunisianet.com.tn | HTML parsing (aiohttp + BS4) | 70+ | ~9,000 |

---

## Project Structure

```
Voxara-Extended/
├── scraper/
│   ├── mytek/
│   │   ├── scrape_mytek.py        # Mytek entry point
│   │   └── output/                # Per-category JSON + CSV files
│   ├── tunisianet/
│   │   ├── scrape_tunisianet.py   # Tunisianet entry point
│   │   └── output/                # Aggregated JSON + CSV + SQLite DB
│   ├── core.py                    # MarketplaceScraper base class
│   ├── helpers.py                 # RateLimiter, parse_price, extract_field, random UA
│   ├── models.py                  # ScrapedItem dataclass (unified product schema)
│   └── exporters.py               # JSON + CSV export helpers
├── normalizer.py                  # Post-scrape spec extraction + deduplication
├── requirements.txt
└── .env
```

---

## How It Works

### Mytek — API Interception

Mytek is a JavaScript Single-Page Application. The product listing HTML contains no data — products are loaded dynamically via an internal XHR call to `/api/products/volatile`. A plain HTTP scraper would see an empty page.

Voxara uses **Playwright** to launch a real headless Chromium browser and intercepts the XHR response directly, getting clean structured JSON without any HTML parsing.

```
Browser opens category URL
  └─▶ page.on("response") fires on every network call
        └─▶ filter: URL contains /api/products/volatile
              └─▶ response.json() → list of products
                    └─▶ paginate via ?p=N until last page
```

**What the API returns per product:**
- `id`, `name`, `final_price`, `price` (original), `erpstock.label` (stock), `images_gallery`

**Advantages of this approach:**
- No CSS selectors to maintain — immune to frontend redesigns
- Prices, discounts, and stock all arrive in one clean JSON payload
- Pagination is reliable — total pages read from `.custom-pagination` DOM element

---

### Tunisianet — HTML Parsing

Tunisianet runs on PrestaShop, which is server-rendered PHP. The full product listing is present in the first HTTP response — no JavaScript execution needed.

Voxara uses **aiohttp** for async HTTP requests and **BeautifulSoup** to extract product fields from the HTML.

```
aiohttp GET category URL (with random User-Agent)
  └─▶ BeautifulSoup selects article.product-miniature (every product card)
        └─▶ extract_field() reads each CSS-targeted field
              └─▶ paginate via ?page=N until 0 cards returned
                    └─▶ asyncio Semaphore(5) — 5 categories scraped in parallel
```

**CSS selector map:**

| Field | Selector |
|---|---|
| Title | `h2.product-title a` → text |
| Price | `span.price` → text |
| Original price | `span.regular-price` → text |
| Image | `img.product-thumbnail` → `[src]` |
| Item URL | `h2.product-title a` → `[href]` |
| Availability | `span.product-availability` → text |

**Advantages of this approach:**
- No browser overhead — significantly faster than Playwright
- Built-in rate limiter (1.5 req/s, burst 3) prevents IP bans
- Exponential backoff retry (4 attempts: 1s, 2s, 4s, 8s) handles transient errors
- Results deduplicated by SHA-256 hash of item URL

---

## Installation

**Requirements:** Python 3.10+

```bash
# 1. Clone the repo
git clone https://github.com/your-org/voxara.git
cd Voxara-Extended

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Playwright's Chromium browser (needed for Mytek only)
playwright install chromium
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

**.env options:**

```env
# AI backend for the normalizer (optional — rules-only mode works without a key)
# Options: "gemini" | "claude" | "rules"
AI_BACKEND=gemini

# Gemini API key (free at aistudio.google.com)
GEMINI_API_KEY=your_key_here

# Anthropic API key (if using AI_BACKEND=claude)
ANTHROPIC_API_KEY=your_key_here
```

All other settings (max pages, request timeouts, output paths) are hardcoded in the top of each scraper file under the `# ▼▼▼ CONFIGURE HERE ▼▼▼` section.

---

## Running the Scrapers

### Mytek

```bash
cd scraper/mytek
python scrape_mytek.py
```

This scrapes all 29 configured categories. Per-category files are written to `scraper/mytek/output/` as the run progresses. Expect ~20–40 minutes depending on your connection speed (Playwright launches a browser per category).

### Tunisianet

```bash
cd scraper/tunisianet
python scrape_tunisianet.py
```

Scrapes all configured categories concurrently (5 at a time). Results are written to `scraper/tunisianet/output/`. Significantly faster than Mytek due to async HTTP — expect ~5–15 minutes for a full run.

---

## Running the Normalizer

The normalizer enriches raw scraped data with structured spec fields (brand, CPU, RAM, storage, screen size, resolution, OS, etc.).

### Rules-only mode (no API key required)

```bash
# Mytek
AI_BACKEND=rules python normalizer.py scraper/mytek/output/mytek_ordinateurs_portables.json

# Tunisianet
AI_BACKEND=rules python normalizer.py scraper/tunisianet/output/tunisianet_results.json
```

### With AI fallback (higher coverage)

Set `AI_BACKEND=gemini` in your `.env` and run without the override:

```bash
python normalizer.py scraper/mytek/output/mytek_ordinateurs_portables.json
```

Products where the rules engine extracts fewer than 2 of 4 key fields are automatically sent to the AI fallback for richer extraction.

### From Python

```python
import asyncio, json
from normalizer import normalize_items

items = json.loads(open("scraper/mytek/output/mytek_ordinateurs_portables.json").read())
results = asyncio.run(normalize_items(items[:10], use_ai_fallback=False))

for r in results:
    print(r["title"], r["specs"])
```

### Output

A `*_normalized.json` file is written alongside the input file. The terminal prints a coverage report:

```
───────────────────────────────────────────────────────
  NORMALIZATION REPORT  (526 products)
───────────────────────────────────────────────────────
  brand          ███████████████████   524/526  (100%)
  cpu            ███████████           308/526  (59%)
  ram_gb         ███████████████████   525/526  (100%)
  storage_gb     ████████████████████  526/526  (100%)
  screen_res     ██████████████████    493/526  (94%)
  os             ███████████████████   525/526  (100%)
───────────────────────────────────────────────────────
```

---

## Output Files

After a full run, the following files are produced:

| File | Size | Description |
|---|---|---|
| `mytek/output/mytek_results.json` | ~6.6 MB | All Mytek products aggregated |
| `mytek/output/mytek_results.csv` | ~4.7 MB | Same data in flat CSV format |
| `mytek/output/mytek_<category>.json` | varies | Per-category JSON files |
| `tunisianet/output/tunisianet_results.json` | ~4.5 MB | All Tunisianet products |
| `tunisianet/output/tunisianet_results.csv` | ~3.0 MB | Same data in flat CSV format |
| `tunisianet/output/results_<timestamp>.db` | ~5.3 MB | SQLite database (deduplication + querying) |
| `*_normalized.json` | varies | Enriched version with `specs` field added |

---

## Data Schema

Every product — regardless of source — is stored as a `ScrapedItem` with the following fields:

| Field | Type | Description |
|---|---|---|
| `item_id` | `str` | SHA-256 hash of `item_url` — globally unique |
| `title` | `str` | Product name |
| `price` | `float \| None` | Current price in TND |
| `original_price` | `float \| None` | Pre-discount price (if on sale) |
| `discount_pct` | `float \| None` | Computed: `(1 - price/original_price) × 100` |
| `currency` | `str` | Always `"TND"` |
| `availability` | `str` | Stock status string |
| `image_url` | `str \| None` | Product image URL |
| `item_url` | `str \| None` | Direct link to product page |
| `category` | `str` | Category name as scraped |
| `source` | `str` | `"mytek"` or `"tunisianet"` |
| `description` | `str \| None` | Full product description |
| `timestamp` | `datetime` | UTC time of scrape |

---

## Normalizer Spec Extraction

After scraping, `normalizer.py` adds a `specs` dict to each product. Fields extracted:

| Spec field | Coverage (Mytek laptops) | Notes |
|---|---|---|
| `brand` | 100% | Detects 30+ brands including BMAX, Chuwi, Infinix |
| `ram_gb` | 100% | Parses "8Go", "16GB", "8 Go RAM" |
| `storage_gb` | 100% | Parses SSD/HDD/NVMe values |
| `storage_type` | 100% | SSD, HDD, NVMe |
| `os` | 100% | Windows 11, FreeDOS, Linux, etc. |
| `screen_inch` | 94% | Parses `15.6"`, `15,6 pouces` |
| `screen_res` | 94% | Exact (`1920x1080`) or keyword (`Full HD`, `4K`) |
| `cpu` | 59% | Intel Core i/N-series, AMD Ryzen, Apple M |
| `color` | 49% | When mentioned in description |
| `gpu` | 7% | Dedicated GPU only (RTX, RX, etc.) |

Each product also gets a `specs_source` field: `"rules"` (regex), `"ai"` (AI fallback), or `"partial"`.

---

## Adding Categories

### Mytek

Open `scraper/mytek/scrape_mytek.py` and add an entry to the `CATEGORIES` list:

```python
CATEGORIES = [
    {
        "name": "Imprimantes",
        "url":  "https://www.mytek.tn/informatique/imprimantes.html",
    },
    # add here ↓
    {
        "name": "Drones",
        "url":  "https://www.mytek.tn/categorie/drones.html",
    },
]
```

### Tunisianet

Open `scraper/tunisianet/scrape_tunisianet.py` and add to the `CATEGORIES` list. Category URLs follow the pattern `https://www.tunisianet.com.tn/<ID>-<slug>` — copy directly from the browser address bar:

```python
CATEGORIES = [
    {
        "name": "Ordinateurs Portables",
        "url":  "https://www.tunisianet.com.tn/702-ordinateur-portable-tunisie",
    },
    # add here ↓
    {
        "name": "Drones",
        "url":  "https://www.tunisianet.com.tn/843-drones",
    },
]
```
