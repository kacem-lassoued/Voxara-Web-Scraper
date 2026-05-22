"""
╔══════════════════════════════════════════════════════════════════╗
║           PRODUCT NORMALIZER — normalizer.py                     ║
║                                                                  ║
║  Extracts structured specs from raw product titles/descriptions. ║
║  Strategy: rule-based first, Claude API fallback for hard cases. ║
║                                                                  ║
║  Usage (standalone):                                             ║
║      python normalizer.py output/mytek_results.json              ║
║                                                                  ║
║  Usage (in your scraper):                                        ║
║      from normalizer import normalize_items                      ║
║      enriched = await normalize_items(raw_items)                 ║
╚══════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────

# Set to "claude" to use Claude API, "gemini" to use Gemini API, or "rules" for rules-only
AI_BACKEND = os.getenv("AI_BACKEND", "gemini")


GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))

# How many products to send per AI batch (keeps prompts short, avoids timeouts)
BATCH_SIZE = 20

# Max concurrent AI requests
AI_CONCURRENCY = 5

# ─────────────────────────────────────────────────────────────
#  NORMALIZED SPEC MODEL
# ─────────────────────────────────────────────────────────────

SPEC_FIELDS = [
    "brand",        # Asus, HP, Lenovo, Dell, Apple …
    "model",        # VivoBook 15, Pavilion 15, ThinkPad E15 …
    "cpu",          # Intel Core i5-1235U, AMD Ryzen 5 5500U …
    "cpu_gen",      # 12th Gen, 13th Gen … (derived)
    "ram_gb",       # 8, 16, 32 (integer GB)
    "storage_gb",   # 256, 512, 1000 (integer GB; 1TB → 1000)
    "storage_type", # SSD, HDD, SSD+HDD
    "gpu",          # NVIDIA RTX 3050, AMD Radeon, Intel Iris Xe …
    "screen_inch",  # 13.3, 15.6, 17.3 (float)
    "screen_res",   # 1920x1080, 2560x1440 …
    "os",           # Windows 11, Windows 11 Pro, FreeDOS, Linux …
    "color",        # Silver, Black, Blue …
]

# ─────────────────────────────────────────────────────────────
#  RULE-BASED PARSER
# ─────────────────────────────────────────────────────────────

# Brand list (order matters — longer matches first to avoid "HP" matching "HPC")
BRANDS = [
    "Apple", "MacBook",
    "Lenovo", "ThinkPad", "IdeaPad", "Legion",
    "HP", "Hewlett",
    "Dell", "Latitude", "Inspiron", "XPS", "Vostro", "Alienware",
    "Asus", "ASUS", "VivoBook", "ZenBook", "ProArt", "ROG", "TUF",
    "Acer", "Aspire", "Nitro", "Swift", "Predator",
    "MSI", "Razer",
    "Samsung", "Huawei", "Honor", "Xiaomi",
    "Toshiba", "Fujitsu", "Panasonic",
    "Gigabyte", "GIGABYTE",
]

# Map brand aliases to canonical names
BRAND_ALIASES = {
    "ASUS": "Asus", "Hewlett": "HP",
    "MacBook": "Apple", "ThinkPad": "Lenovo",
    "IdeaPad": "Lenovo", "Legion": "Lenovo",
    "VivoBook": "Asus", "ZenBook": "Asus", "ProArt": "Asus",
    "ROG": "Asus", "TUF": "Asus",
    "Aspire": "Acer", "Nitro": "Acer", "Swift": "Acer", "Predator": "Acer",
    "Latitude": "Dell", "Inspiron": "Dell", "XPS": "Dell",
    "Vostro": "Dell", "Alienware": "Dell",
    "GIGABYTE": "Gigabyte",
}

_RAM_RE = re.compile(
    r"(\d+)\s*[- ]?Go\b"              # French: "16 Go", "16Go", "16-Go"
    r"|(\d+)\s*GB\b"                  # English: "16GB", "16 GB"
    r"|(\d+)\s*Go\s+RAM"              # "16 Go RAM"
    r"|RAM\s*[:\-]?\s*(\d+)",         # "RAM: 16"
    re.IGNORECASE,
)

_STORAGE_RE = re.compile(
    r"(\d+)\s*[- ]?Go\s+SSD"         # "512 Go SSD"
    r"|(\d+)\s*GB\s+SSD"             # "512GB SSD"
    r"|SSD\s*[:\-]?\s*(\d+)\s*[GT]"  # "SSD: 512G"
    r"|(\d+)\s*[- ]?To\b"            # French TB: "1 To"
    r"|(\d+)\s*TB\b"                  # English TB: "1TB"
    r"|(\d+)\s*[- ]?Go\s+HDD"        # "1000 Go HDD"
    r"|(\d+)\s*GB\s+HDD"             # "1000GB HDD"
    r"|(\d+)\s*[- ]?Go\b"            # last resort plain Go (picks up RAM too; filtered later)
    r"|(\d+)\s*GB\b",
    re.IGNORECASE,
)

_SCREEN_RE = re.compile(
    r'(\d{1,2}(?:[.,]\d)?)\s*(?:"|pouces?|inches?|")',
    re.IGNORECASE,
)

_CPU_RE = re.compile(
    r"(Intel\s+Core\s+[iI]\d[\w\-]+)"     # Intel Core i5-1235U
    r"|(Intel\s+Celeron[\w\s\-]*)"
    r"|(Intel\s+Pentium[\w\s\-]*)"
    r"|(AMD\s+Ryzen\s+\d[\w\s\-]+)"       # AMD Ryzen 5 5500U
    r"|(AMD\s+Athlon[\w\s\-]*)"
    r"|(Apple\s+M\d[\w\s]*)",             # Apple M1 / M2 Pro
    re.IGNORECASE,
)

_GPU_RE = re.compile(
    r"(NVIDIA\s+(?:GeForce\s+)?(?:RTX|GTX)\s*[\w\s]+?(?=,|\s+\d+Go|\s+\d+GB|$))"
    r"|(AMD\s+Radeon[\w\s]+?(?=,|$))"
    r"|(Intel\s+(?:Iris\s+Xe|UHD|HD)\s+Graphics[\w\s]*?(?=,|$))"
    r"|(NVIDIA\s+MX\d+)",
    re.IGNORECASE,
)

_OS_RE = re.compile(
    r"(Windows\s+11\s+(?:Pro|Home|S)?)"
    r"|(Windows\s+10\s+(?:Pro|Home)?)"
    r"|(FreeDOS)"
    r"|(Linux)"
    r"|(macOS[\w\s]*)",
    re.IGNORECASE,
)

_COLOR_RE = re.compile(
    r"\b(Silver|Black|White|Blue|Red|Gold|Grey|Gray|Rose\s+Gold|Space\s+Gray|Midnight|Starlight|Bleu|Noir|Gris|Argent)\b",
    re.IGNORECASE,
)


def _first_group(m) -> str | None:
    """Return the first non-None capturing group from a match object."""
    if not m:
        return None
    for g in m.groups():
        if g:
            return g.strip()
    return None


def rule_parse(text: str) -> dict[str, Any]:
    """
    Extract structured specs from a product title or description string.
    Returns a dict with only the fields that were found.
    """
    specs: dict[str, Any] = {}

    if not text:
        return specs

    combined = text  # parse across full text

    # ── Brand ─────────────────────────────────────────────────
    for b in BRANDS:
        if re.search(r"\b" + re.escape(b) + r"\b", combined, re.IGNORECASE):
            canonical = BRAND_ALIASES.get(b, b)
            # Normalise casing: title-case the canonical
            specs["brand"] = canonical
            break

    # ── CPU ───────────────────────────────────────────────────
    cpu_m = _CPU_RE.search(combined)
    if cpu_m:
        specs["cpu"] = _first_group(cpu_m)
        # Derive generation hint
        gen_m = re.search(r"(\d{2})th Gen", combined, re.IGNORECASE)
        if gen_m:
            specs["cpu_gen"] = f"{gen_m.group(1)}th Gen"

    # ── RAM ───────────────────────────────────────────────────
    # Find all Go/GB occurrences; pick the smallest that's a power-of-2 ≤ 64
    # (storage is usually larger)
    ram_candidates = []
    for m in re.finditer(r"(\d+)\s*(?:Go|GB)\b", combined, re.IGNORECASE):
        v = int(m.group(1))
        if v in (2, 4, 6, 8, 12, 16, 24, 32, 48, 64):
            ram_candidates.append(v)
    if ram_candidates:
        specs["ram_gb"] = min(ram_candidates)  # smallest common-RAM value

    # ── Storage ───────────────────────────────────────────────
    storage_gb = None
    storage_type = None

    # Prefer explicit SSD / HDD mentions
    ssd_m = re.search(
        r"(\d+)\s*(?:Go|GB)\s*SSD|SSD\s*[:\-]?\s*(\d+)\s*[GT]",
        combined, re.IGNORECASE
    )
    hdd_m = re.search(r"(\d+)\s*(?:Go|GB)\s*HDD", combined, re.IGNORECASE)
    tb_m  = re.search(r"(\d+)\s*(?:To|TB)\b", combined, re.IGNORECASE)

    if ssd_m:
        storage_gb   = int(ssd_m.group(1) or ssd_m.group(2))
        storage_type = "SSD"
        if hdd_m:
            storage_type = "SSD+HDD"
    elif tb_m:
        storage_gb   = int(tb_m.group(1)) * 1000  # 1 To → 1000 GB
        storage_type = "SSD"  # modern TB drives are typically NVMe
    elif hdd_m:
        storage_gb   = int(hdd_m.group(1))
        storage_type = "HDD"

    # Fall back: largest Go/GB value that's not the RAM
    if storage_gb is None:
        all_go = [int(m.group(1)) for m in re.finditer(r"(\d+)\s*(?:Go|GB)\b", combined, re.IGNORECASE)]
        ram = specs.get("ram_gb")
        candidates = [v for v in all_go if v != ram and v >= 128]
        if candidates:
            storage_gb = max(candidates)

    if storage_gb:
        specs["storage_gb"] = storage_gb
    if storage_type:
        specs["storage_type"] = storage_type

    # ── GPU ───────────────────────────────────────────────────
    gpu_m = _GPU_RE.search(combined)
    if gpu_m:
        specs["gpu"] = _first_group(gpu_m).strip(", ")

    # ── Screen size ───────────────────────────────────────────
    screen_m = _SCREEN_RE.search(combined)
    if screen_m:
        specs["screen_inch"] = float(screen_m.group(1).replace(",", "."))

    # ── Resolution ────────────────────────────────────────────
    res_m = re.search(r"(\d{3,4})[xX×](\d{3,4})", combined)
    if res_m:
        specs["screen_res"] = f"{res_m.group(1)}x{res_m.group(2)}"

    # ── OS ────────────────────────────────────────────────────
    os_m = _OS_RE.search(combined)
    if os_m:
        specs["os"] = _first_group(os_m)

    # ── Color ─────────────────────────────────────────────────
    color_m = _COLOR_RE.search(combined)
    if color_m:
        specs["color"] = color_m.group(1).title()

    return specs


# ─────────────────────────────────────────────────────────────
#  AI FALLBACK — CLAUDE
# ─────────────────────────────────────────────────────────────

AI_SYSTEM_PROMPT = """You are a product data extraction engine.
Given a list of product titles/descriptions (mostly laptops from Tunisian e-commerce),
extract structured specs and return ONLY a JSON array — no markdown, no explanation.

Each element must be a JSON object with these keys (omit keys you cannot determine):
brand, model, cpu, ram_gb (integer), storage_gb (integer), storage_type (SSD/HDD/SSD+HDD),
gpu, screen_inch (float), screen_res (e.g. "1920x1080"), os, color

Rules:
- 1 To / 1 TB = 1000 GB
- If description is in French, still return values in English
- brand should be the manufacturer (Asus, HP, Dell, Lenovo, Apple, Acer, MSI…)
- Return one JSON object per input product, in the same order
- If a field cannot be extracted confidently, omit it (do not guess)
"""


def _build_ai_prompt(items: list[dict]) -> str:
    lines = []
    for i, item in enumerate(items):
        title = item.get("title", "")
        desc  = item.get("description", "")
        text  = f"{title}. {desc}".strip(". ")
        lines.append(f"{i+1}. {text}")
    return "\n".join(lines)


async def _call_claude(texts_prompt: str, client: httpx.AsyncClient) -> list[dict]:
    resp = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key":         ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        json={
            "model":      "claude-haiku-4-5-20251001",  # fastest + cheapest
            "max_tokens": 2048,
            "system":     AI_SYSTEM_PROMPT,
            "messages":   [{"role": "user", "content": texts_prompt}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    raw = resp.json()["content"][0]["text"]
    # Strip accidental markdown fences
    raw = re.sub(r"^```[a-z]*\n?", "", raw.strip())
    raw = re.sub(r"\n?```$", "", raw.strip())
    return json.loads(raw)


async def _call_gemini(texts_prompt: str, client: httpx.AsyncClient) -> list[dict]:
    full_prompt = AI_SYSTEM_PROMPT + "\n\n" + texts_prompt
    resp = await client.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
        json={"contents": [{"parts": [{"text": full_prompt}]}]},
        timeout=60,
    )
    resp.raise_for_status()
    raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    raw = re.sub(r"^```[a-z]*\n?", "", raw.strip())
    raw = re.sub(r"\n?```$", "", raw.strip())
    return json.loads(raw)


async def _ai_extract_batch(
    batch: list[dict],
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
) -> list[dict]:
    async with sem:
        prompt = _build_ai_prompt(batch)
        try:
            if AI_BACKEND == "gemini":
                results = await _call_gemini(prompt, client)
            else:
                results = await _call_claude(prompt, client)
            # Align lengths defensively
            if len(results) != len(batch):
                print(f"  ⚠  AI returned {len(results)} results for {len(batch)} items — padding")
                while len(results) < len(batch):
                    results.append({})
            return results
        except Exception as e:
            print(f"  ✘ AI batch failed: {e} — falling back to empty specs")
            return [{} for _ in batch]


# ─────────────────────────────────────────────────────────────
#  MAIN NORMALIZER
# ─────────────────────────────────────────────────────────────

def _needs_ai(specs: dict) -> bool:
    """True if rule-based parsing left too many key fields blank."""
    required = {"brand", "cpu", "ram_gb", "storage_gb"}
    found    = set(specs.keys()) & required
    return len(found) < 2   # fewer than 2 of the 4 key fields found


async def normalize_items(
    items: list[dict],
    use_ai_fallback: bool = True,
) -> list[dict]:
    """
    Normalize a list of raw scraped product dicts.
    Adds a 'specs' sub-dict and a 'specs_source' field ('rules'/'ai'/'partial').
    """
    # Step 1 — rule-based pass
    results   = []
    ai_needed = []   # (index_in_results, item)

    for item in items:
        text  = f"{item.get('title', '')} {item.get('description', '')}"
        specs = rule_parse(text)

        enriched = {**item, "specs": specs, "specs_source": "rules"}
        results.append(enriched)

        if use_ai_fallback and _needs_ai(specs):
            ai_needed.append((len(results) - 1, item))

    print(f"Rule-based: {len(results) - len(ai_needed)}/{len(results)} fully parsed, "
          f"{len(ai_needed)} sent to AI fallback")

    if not ai_needed or not use_ai_fallback:
        return results

    # Step 2 — AI fallback for hard cases
    api_key = GEMINI_API_KEY if AI_BACKEND == "gemini" else ANTHROPIC_API_KEY
    if not api_key:
        print(f"  ⚠  {AI_BACKEND.upper()} key not set — skipping AI fallback")
        return results

    sem = asyncio.Semaphore(AI_CONCURRENCY)
    async with httpx.AsyncClient() as client:
        # Chunk into batches
        indices    = [idx  for idx, _   in ai_needed]
        raw_items  = [item for _,   item in ai_needed]
        batches    = [raw_items[i:i+BATCH_SIZE] for i in range(0, len(raw_items), BATCH_SIZE)]
        idx_batches = [indices[i:i+BATCH_SIZE]  for i in range(0, len(indices),  BATCH_SIZE)]

        tasks = [_ai_extract_batch(b, client, sem) for b in batches]
        batch_results = await asyncio.gather(*tasks)

        # Merge AI results back
        for idx_batch, ai_specs_batch in zip(idx_batches, batch_results):
            for result_idx, ai_specs in zip(idx_batch, ai_specs_batch):
                merged = {**results[result_idx]["specs"], **ai_specs}
                results[result_idx]["specs"] = merged
                results[result_idx]["specs_source"] = "ai" if ai_specs else "partial"

    ai_filled = sum(1 for r in results if r["specs_source"] == "ai")
    print(f"AI fallback: filled {ai_filled} items")
    return results


# ─────────────────────────────────────────────────────────────
#  COVERAGE REPORT
# ─────────────────────────────────────────────────────────────

def print_coverage_report(normalized: list[dict]) -> None:
    total = len(normalized)
    if total == 0:
        return

    print(f"\n{'─'*55}")
    print(f"  NORMALIZATION REPORT  ({total} products)")
    print(f"{'─'*55}")

    field_counts: dict[str, int] = {}
    for item in normalized:
        for f in SPEC_FIELDS:
            if item.get("specs", {}).get(f) is not None:
                field_counts[f] = field_counts.get(f, 0) + 1

    for f in SPEC_FIELDS:
        count = field_counts.get(f, 0)
        pct   = count / total * 100
        bar   = "█" * int(pct / 5)
        print(f"  {f:<14} {bar:<20} {count:>4}/{total}  ({pct:.0f}%)")

    src_counts = {}
    for item in normalized:
        src = item.get("specs_source", "unknown")
        src_counts[src] = src_counts.get(src, 0) + 1
    print(f"\n  Sources: {src_counts}")
    print(f"{'─'*55}\n")


# ─────────────────────────────────────────────────────────────
#  STANDALONE CLI
# ─────────────────────────────────────────────────────────────

async def _cli(input_path: str) -> None:
    raw = json.loads(Path(input_path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("items", list(raw.values())[0] if raw else [])

    print(f"Loaded {len(raw)} items from {input_path}")
    normalized = await normalize_items(raw)

    out_path = input_path.replace(".json", "_normalized.json")
    Path(out_path).write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print_coverage_report(normalized)
    print(f"✔  Saved → {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python normalizer.py <path/to/scraped.json>")
        sys.exit(1)
    asyncio.run(_cli(sys.argv[1]))
