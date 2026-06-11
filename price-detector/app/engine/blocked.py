"""Heuristics for detecting anti-bot blocks (DataDome etc.)."""
from __future__ import annotations

BLOCK_MARKERS = (
    "captcha-delivery.com",
    "datadome",
    "verify you are a human",
    "unusual traffic",
    "access denied",
    "pardon our interruption",
)


def is_datadome_block(html: str | None, status: int | None = None) -> bool:
    if status in (403, 429):
        return True
    if not html:
        return False
    low = html.lower()
    return any(m in low for m in BLOCK_MARKERS)
