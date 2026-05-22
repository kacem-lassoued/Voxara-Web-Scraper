from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from .models import ScrapedItem

logger = logging.getLogger(__name__)


def export_json(items: list[ScrapedItem], path: str) -> None:
    """Save items to a pretty-printed JSON file."""
    Path(path).write_text(
        json.dumps([it.to_dict() for it in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("JSON saved → %s (%d items)", path, len(items))


def export_csv(items: list[ScrapedItem], path: str) -> None:
    """Save items to CSV, flattening the `extra` dict into top-level columns."""
    if not items:
        logger.warning("No items to export to CSV")
        return

    rows = [it.to_dict() for it in items]

    # Collect all unique column names while preserving insertion order
    all_keys: list[str] = []
    for row in rows:
        for k in row:
            if k not in all_keys:
                all_keys.append(k)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    logger.info("CSV saved → %s (%d items)", path, len(items))
