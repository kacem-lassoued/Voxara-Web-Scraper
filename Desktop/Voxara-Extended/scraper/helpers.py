from __future__ import annotations

import asyncio
import random
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse, urlencode, parse_qs, urlunparse

from bs4 import BeautifulSoup, Tag


# ── User-Agent pool ───────────────────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]


def random_headers(extra: dict | None = None) -> dict[str, str]:
    h = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    if extra:
        h.update(extra)
    return h


# ── Token-bucket rate limiter (per domain) ────────────────────────────────────

class _Bucket:
    def __init__(self, rate: float, capacity: float):
        self._rate = rate
        self._capacity = capacity
        self._tokens = capacity
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._tokens = min(
                self._capacity, self._tokens + (now - self._last) * self._rate
            )
            self._last = now
            if self._tokens < 1:
                await asyncio.sleep((1 - self._tokens) / self._rate)
                self._tokens = 0
            else:
                self._tokens -= 1


class RateLimiter:
    def __init__(self, rps: float = 1.5, burst: int = 3):
        self._rps = rps
        self._burst = burst
        self._buckets: dict[str, _Bucket] = {}

    def _bucket(self, url: str) -> _Bucket:
        domain = urlparse(url).netloc
        if domain not in self._buckets:
            self._buckets[domain] = _Bucket(self._rps, self._burst)
        return self._buckets[domain]

    async def wait(self, url: str) -> None:
        await self._bucket(url).acquire()


# ── Price parsing ─────────────────────────────────────────────────────────────

_CURRENCY_RE = re.compile(r"[$€£¥₹₩₽]|[A-Z]{3}")
_NUMBER_RE   = re.compile(r"[\d.,\s]+")


def parse_price(text: str | None) -> tuple[float | None, str | None]:
    """Return (amount_as_float, currency_symbol) from a raw price string."""
    if not text:
        return None, None
    cur = _CURRENCY_RE.search(text)
    currency = cur.group() if cur else None
    clean = re.sub(r"[^\d.,]", " ", text).strip()
    m = _NUMBER_RE.search(clean)
    if not m:
        return None, currency
    raw = m.group().strip().replace(" ", "")
    # Handle both "1,299.99" (US) and "1.299,99" (EU)
    if raw.count(",") == 1 and raw.count(".") == 0:
        raw = raw.replace(",", ".")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", "")
    try:
        return float(raw), currency
    except ValueError:
        return None, currency


def safe_int(text: str | None) -> int | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", text)
    return int(cleaned) if cleaned else None


def safe_float(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", "."))
    try:
        return float(cleaned)
    except ValueError:
        return None


# ── Field extraction ──────────────────────────────────────────────────────────

def extract_field(el: Tag, spec: dict[str, Any], base_url: str) -> Any:
    """
    Extract one value from a BeautifulSoup element according to a field spec.

    Spec keys
    ---------
    selector : CSS selector relative to `el`
    attr     : HTML attribute to read (e.g. "href", "src", "data-price")
    regex    : regex applied to the extracted string; returns first group
    type     : "text" | "href" | "src" | "price" | "int" | "float"
    absolute : bool — resolve relative URLs against base_url
    """
    sel  = spec.get("selector")
    node = el.select_one(sel) if sel else el
    if node is None:
        return None

    ftype = spec.get("type", "text")
    attr  = spec.get("attr")

    # --- raw value ---
    if ftype == "href":
        raw = node.get("href", "")
    elif ftype == "src":
        raw = node.get("src") or node.get("data-src") or node.get("data-lazy-src") or ""
    elif attr:
        raw = node.get(attr, "")
    else:
        raw = node.get_text(" ", strip=True)

    if raw is None:
        return None
    raw = str(raw).strip()

    # --- regex ---
    pattern = spec.get("regex")
    if pattern and raw:
        m = re.search(pattern, raw)
        if m:
            raw = m.group(1) if m.lastindex else m.group()
        else:
            return None

    if not raw:
        return None

    # --- type coercion ---
    if ftype == "int":
        return safe_int(raw)
    if ftype == "float":
        return safe_float(raw)
    if ftype == "price":
        return raw   # caller handles price parsing

    # --- make absolute URL ---
    if spec.get("absolute") and raw:
        raw = urljoin(base_url, raw)

    return raw or None


# ── Pagination helpers ────────────────────────────────────────────────────────

def next_url_next_button(soup: BeautifulSoup, selector: str, base_url: str) -> str | None:
    node = soup.select_one(selector)
    if not node:
        return None
    href = node.get("href")
    return urljoin(base_url, str(href)) if href else None


def next_url_page_param(current_url: str, param: str, current_page: int) -> str:
    parsed = urlparse(current_url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs[param] = [str(current_page + 1)]
    return urlunparse(parsed._replace(query=urlencode({k: v[0] for k, v in qs.items()})))


def next_url_offset_param(current_url: str, param: str, page_size: int, offset: int) -> str:
    parsed = urlparse(current_url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs[param] = [str(offset + page_size)]
    return urlunparse(parsed._replace(query=urlencode({k: v[0] for k, v in qs.items()})))
