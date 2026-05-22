from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import sqlite3
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from .helpers import (
    RateLimiter,
    extract_field,
    next_url_next_button,
    next_url_offset_param,
    next_url_page_param,
    parse_price,
    random_headers,
)
from .models import ScrapedItem

logger = logging.getLogger(__name__)

# Fields that map directly onto ScrapedItem attributes
_KNOWN_FIELDS = {
    "title", "rating", "review_count", "seller", "location",
    "condition", "category", "description", "image_url",
    "item_url", "availability", "original_price",
}


def _make_id(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


class MarketplaceScraper:
    """
    Async marketplace scraper with pagination, rate-limiting, and deduplication.

    Usage
    -----
    async with MarketplaceScraper(db_path="output/results.db") as s:
        items = await s.scrape_source(source_config)
    """

    def __init__(
        self,
        *,
        concurrency: int = 5,
        requests_per_second: float = 1.5,
        burst: int = 3,
        timeout: int = 20,
        max_retries: int = 4,
        proxies: list[str] | None = None,
        db_path: str | None = None,
    ):
        self.concurrency = concurrency
        self.timeout = timeout
        self.max_retries = max_retries
        self.proxies = proxies or []
        self.db_path = db_path
        self._rate = RateLimiter(requests_per_second, burst)
        self._seen: set[str] = set()
        self._session: aiohttp.ClientSession | None = None
        self._sem: asyncio.Semaphore | None = None
        self._stats: dict[str, int] = {}

        if db_path:
            self._init_db(db_path)

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def __aenter__(self) -> MarketplaceScraper:
        connector = aiohttp.TCPConnector(ssl=False, limit=self.concurrency)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )
        self._sem = asyncio.Semaphore(self.concurrency)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._session:
            await self._session.close()

    # ── SQLite ─────────────────────────────────────────────────────────────

    def _init_db(self, path: str) -> None:
        con = sqlite3.connect(path)
        con.execute(
            """CREATE TABLE IF NOT EXISTS items (
                item_id    TEXT PRIMARY KEY,
                source_url TEXT,
                timestamp  TEXT,
                data       TEXT
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_src ON items(source_url)")
        con.commit()
        rows = con.execute("SELECT item_id FROM items").fetchall()
        self._seen.update(r[0] for r in rows)
        con.close()
        logger.info("DB: %d previously-scraped items loaded", len(self._seen))

    def _save_to_db(self, items: list[ScrapedItem]) -> None:
        if not self.db_path or not items:
            return
        con = sqlite3.connect(self.db_path)
        con.executemany(
            "INSERT OR REPLACE INTO items VALUES (?,?,?,?)",
            [(it.item_id, it.source_url, it.timestamp, json.dumps(it.to_dict())) for it in items],
        )
        con.commit()
        con.close()

    # ── HTTP ───────────────────────────────────────────────────────────────

    async def _fetch(
        self,
        url: str,
        extra_headers: dict | None = None,
        cookies: dict | None = None,
    ) -> str | None:
        assert self._session and self._sem
        headers = random_headers(extra_headers)
        proxy = random.choice(self.proxies) if self.proxies else None
        backoff = 1.0

        async with self._sem:
            await self._rate.wait(url)
            for attempt in range(self.max_retries):
                try:
                    async with self._session.get(
                        url,
                        headers=headers,
                        cookies=cookies or {},
                        proxy=proxy,
                        allow_redirects=True,
                    ) as resp:
                        if resp.status == 429:
                            wait = float(resp.headers.get("Retry-After", backoff * 2))
                            logger.warning("Rate-limited (%s) — waiting %.1fs", url, wait)
                            await asyncio.sleep(wait)
                            continue
                        if resp.status == 404:
                            logger.warning("404 — %s", url)
                            return None
                        resp.raise_for_status()
                        return await resp.text(errors="replace")
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    jitter = random.uniform(0, backoff * 0.3)
                    wait = backoff + jitter
                    logger.warning(
                        "Attempt %d/%d failed for %s: %s — retrying in %.1fs",
                        attempt + 1, self.max_retries, url, exc, wait,
                    )
                    await asyncio.sleep(wait)
                    backoff = min(backoff * 2, 60)

        logger.error("Giving up on %s after %d attempts", url, self.max_retries)
        return None

    async def _fetch_dynamic(self, url: str) -> str | None:
        """Playwright-based fetch for JavaScript-rendered pages."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error(
                "Playwright not installed.\n"
                "Run:  pip install playwright && playwright install chromium"
            )
            return None

        await self._rate.wait(url)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent=random_headers()["User-Agent"],
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            page = await ctx.new_page()
            try:
                await page.goto(url, timeout=self.timeout * 1000, wait_until="domcontentloaded")
                try:
                    await page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass
                html = await page.content()
            finally:
                await browser.close()
        return html

    # ── Parsing ────────────────────────────────────────────────────────────

    def _parse_page(self, html: str, base_url: str, source: dict[str, Any]) -> list[ScrapedItem]:
        soup = BeautifulSoup(html, "html.parser")
        item_sel = source.get("item_selector")
        elements = soup.select(item_sel) if item_sel else [soup]

        if not elements:
            logger.warning("item_selector '%s' matched 0 elements on %s", item_sel, base_url)

        fields_spec: dict[str, dict] = source.get("fields", {})
        items: list[ScrapedItem] = []

        for el in elements:
            raw: dict[str, Any] = {}
            for fname, spec in fields_spec.items():
                raw[fname] = extract_field(el, spec, base_url)  # type: ignore[arg-type]

            # --- price normalisation ---
            price_raw    = raw.pop("price", None)
            orig_raw     = raw.pop("original_price", None)
            price, cur   = parse_price(str(price_raw)) if price_raw else (None, None)
            orig_price,_ = parse_price(str(orig_raw))  if orig_raw  else (None, None)

            discount = None
            if price and orig_price and orig_price > 0:
                discount = round((orig_price - price) / orig_price * 100, 1)

            # --- item ID ---
            id_key = raw.get("item_url") or raw.get("title") or base_url
            item_id = _make_id(str(id_key))

            if item_id in self._seen:
                continue
            self._seen.add(item_id)

            # --- split known vs extra fields ---
            known_vals = {k: raw.pop(k) for k in list(raw) if k in _KNOWN_FIELDS}
            extra      = {k: v for k, v in raw.items() if v is not None}

            items.append(ScrapedItem(
                item_id=item_id,
                source_url=base_url,
                price=price,
                currency=cur,
                original_price=orig_price,
                discount_pct=discount,
                extra=extra,
                **known_vals,  # type: ignore[arg-type]
            ))

        return items

    # ── Pagination ─────────────────────────────────────────────────────────

    def _next_url(
        self,
        soup: BeautifulSoup,
        current_url: str,
        pagination: dict[str, Any],
        page: int,
        offset: int,
    ) -> str | None:
        strategy = pagination.get("strategy", "none")
        if strategy == "none":
            return None
        if strategy == "next_button":
            return next_url_next_button(soup, pagination.get("next_selector", "a[rel=next]"), current_url)
        if strategy == "page_param":
            return next_url_page_param(current_url, pagination["page_param"], page)
        if strategy == "offset_param":
            return next_url_offset_param(current_url, pagination["offset_param"], pagination.get("page_size", 20), offset)
        return None

    # ── Public API ─────────────────────────────────────────────────────────

    async def scrape_source(self, source: dict[str, Any]) -> list[ScrapedItem]:
        """Scrape all pages of a single source config dict."""
        url: str         = source["base_url"]
        mode: str        = source.get("mode", "static")
        pagination: dict = source.get("pagination", {"strategy": "none"})
        max_pages: int   = pagination.get("max_pages", 20)
        extra_hdrs: dict = source.get("extra_headers", {})
        cookies: dict    = source.get("cookies", {})

        all_items: list[ScrapedItem] = []
        page = 1
        offset = 0

        while url and page <= max_pages:
            logger.info("Page %d → %s", page, url)

            html = (
                await self._fetch_dynamic(url)
                if mode == "dynamic"
                else await self._fetch(url, extra_hdrs, cookies)
            )

            if not html:
                logger.warning("Empty response on page %d — stopping", page)
                break

            soup  = BeautifulSoup(html, "html.parser")
            items = self._parse_page(html, url, source)

            if not items:
                logger.info("No new items on page %d — stopping", page)
                break

            all_items.extend(items)
            logger.info("  → %d new items (running total: %d)", len(items), len(all_items))

            next_url = self._next_url(soup, url, pagination, page, offset)
            if not next_url or next_url == url:
                break

            url     = next_url
            page   += 1
            offset += pagination.get("page_size", len(items))
            await asyncio.sleep(random.uniform(0.5, 1.5))   # polite crawl delay

        self._save_to_db(all_items)
        self._stats[source["base_url"]] = self._stats.get(source["base_url"], 0) + len(all_items)
        return all_items

    def reset_seen(self) -> None:
        """Clear the deduplication set between categories.
        Without this, items from category 1 fill self._seen and category 2
        returns 0 new items on page 1, causing the loop to stop immediately."""
        self._seen.clear()

    async def scrape_many(self, sources: list[dict[str, Any]]) -> list[ScrapedItem]:
        """Scrape multiple source configs concurrently."""
        tasks = [self.scrape_source(s) for s in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_items: list[ScrapedItem] = []
        for src, res in zip(sources, results):
            if isinstance(res, Exception):
                logger.error("Source %s failed: %s", src["base_url"], res)
            else:
                all_items.extend(res)
        return all_items

    def print_stats(self) -> None:
        print("\n── Scrape Stats " + "─" * 45)
        for url, count in self._stats.items():
            print(f"  {url[:65]:<65}  {count:>5} items")
        print(f"  {'TOTAL':<65}  {sum(self._stats.values()):>5} items")
        print("─" * 62 + "\n")
