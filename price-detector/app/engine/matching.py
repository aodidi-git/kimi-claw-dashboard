"""Match identical listings across profiles/trials.

Prefer the site's external listing id when present (exact match); otherwise fall
back to a normalized composite key of section + row + quantity.
"""
from __future__ import annotations

import re

from ..models import RawListing

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9 ]")


def _norm(s: str | None) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    s = _PUNCT.sub("", s)
    s = _WS.sub(" ", s)
    return s.strip()


def match_key(listing: RawListing) -> str:
    """Stable identity for a listing within an event.

    External id wins when available; composite key otherwise.
    """
    if listing.external_id:
        return f"id:{listing.external_id}"
    qty = listing.quantity if listing.quantity is not None else "?"
    return f"sec:{_norm(listing.section)}|row:{_norm(listing.row)}|qty:{qty}"
