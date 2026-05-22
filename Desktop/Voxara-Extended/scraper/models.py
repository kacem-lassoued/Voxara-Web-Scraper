from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ScrapedItem:
    item_id: str
    source_url: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Common marketplace fields (all optional)
    title: str | None = None
    price: float | None = None
    currency: str | None = None
    original_price: float | None = None
    discount_pct: float | None = None
    rating: float | None = None
    review_count: int | None = None
    seller: str | None = None
    location: str | None = None
    condition: str | None = None
    category: str | None = None
    description: str | None = None
    image_url: str | None = None
    item_url: str | None = None
    availability: str | None = None

    # Catch-all for any custom fields defined in the source config
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        extra = d.pop("extra", {})
        d.update(extra)
        # Drop None values for cleaner output
        return {k: v for k, v in d.items() if v is not None}
