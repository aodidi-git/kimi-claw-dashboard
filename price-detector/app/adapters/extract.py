"""Shared, pure extraction helpers used by all site adapters.

These functions operate on already-fetched bytes/dicts (no network, no
Playwright) so they are unit-testable from fixtures. Adapters differ only in how
they recognize URLs, toggle all-in pricing, and build checkout links -- the
parsing of listing JSON is common across StubHub/SeatGeek-style sites.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

from ..models import RawListing

# Field name groups, covering both verbose (StubHub) and compact (SeatGeek-map)
# JSON shapes. Order matters: earlier keys win.
ID_KEYS = ("listingId", "listingID", "sellerListingId", "id")
SECTION_KEYS = ("sectionName", "section", "zoneName", "zone", "s")
ROW_KEYS = ("row", "rowName", "r")
QTY_KEYS = ("quantity", "availableTickets", "ticketCount", "qty", "q")
LIST_PRICE_KEYS = ("listPrice", "price", "amount", "faceValue", "rawPrice", "p")
FEE_KEYS = ("fees", "serviceFee", "totalFees", "feeAmount", "fee", "f")
ALL_IN_KEYS = (
    "allInPrice", "totalPrice", "totalCost", "priceWithFees",
    "displayPrice", "display_price", "dp",
)

_TRAILING_ID_RE = re.compile(r"-(\d+)/?(?:\?|$)")
_EVENT_ID_RE = re.compile(r"/event[s]?/(\d+)", re.IGNORECASE)


def extract_event_id(url: str) -> str | None:
    m = _EVENT_ID_RE.search(url)
    if m:
        return m.group(1)
    m = _TRAILING_ID_RE.search(url)
    return m.group(1) if m else None


def as_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        for k in ("amount", "value", "total", "price"):
            if k in val:
                return as_float(val[k])
        return None
    if isinstance(val, str):
        cleaned = re.sub(r"[^0-9.]", "", val)
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
    return None


def first(d: dict, keys: Iterable[str]) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _matched_groups(item: dict) -> int:
    groups = (ID_KEYS, SECTION_KEYS, ROW_KEYS, QTY_KEYS, LIST_PRICE_KEYS + ALL_IN_KEYS, FEE_KEYS)
    return sum(1 for g in groups if any(k in item for k in g))


def looks_like_listing(item: dict) -> bool:
    """A dict is a listing if it carries a price plus >=3 distinct field groups.

    The group-count guard keeps compact single-letter keys (s/r/q/p) from
    triggering false positives on unrelated objects.
    """
    has_price = any(k in item for k in (LIST_PRICE_KEYS + ALL_IN_KEYS))
    has_section = any(k in item for k in SECTION_KEYS)
    return has_price and has_section and _matched_groups(item) >= 3


def listing_from_dict(item: dict) -> RawListing | None:
    if not isinstance(item, dict):
        return None
    ext = first(item, ID_KEYS)
    section = first(item, SECTION_KEYS)
    row = first(item, ROW_KEYS)
    qty = first(item, QTY_KEYS)
    list_price = as_float(first(item, LIST_PRICE_KEYS))
    fees = as_float(first(item, FEE_KEYS))
    all_in = as_float(first(item, ALL_IN_KEYS))
    if all_in is None and list_price is not None and fees is not None:
        all_in = list_price + fees
    if all_in is None and list_price is not None:
        all_in = list_price
    currency = first(item, ("currency", "currencyCode")) or "USD"
    if list_price is None and all_in is None:
        return None
    return RawListing(
        external_id=str(ext) if ext is not None else None,
        section=str(section) if section is not None else None,
        row=str(row) if row is not None else None,
        quantity=int(qty) if isinstance(qty, (int, float)) or (isinstance(qty, str) and qty.isdigit()) else None,
        list_price=list_price,
        fees=fees,
        all_in_price=all_in,
        currency=str(currency),
        listing_url=None,
        raw=item,
    )


def _walk(obj: Any) -> Iterable[dict]:
    if isinstance(obj, dict):
        if looks_like_listing(obj):
            yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def parse_api_payloads(payloads: list[Any]) -> list[RawListing]:
    out: list[RawListing] = []
    seen: set[str] = set()
    for payload in payloads:
        for item in _walk(payload):
            rl = listing_from_dict(item)
            if rl is None:
                continue
            key = rl.external_id or f"{rl.section}|{rl.row}|{rl.quantity}|{rl.list_price}"
            if key in seen:
                continue
            seen.add(key)
            out.append(rl)
    return out


def parse_embedded_state(html: str) -> list[RawListing]:
    """Pull listings out of embedded JSON blobs (__NEXT_DATA__, JSON-LD)."""
    payloads: list[Any] = []
    for pattern in (
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    ):
        for m in re.finditer(pattern, html, re.DOTALL):
            try:
                payloads.append(json.loads(m.group(1)))
            except json.JSONDecodeError:
                pass
    return parse_api_payloads(payloads)


def parse_dom_text(rows: list[dict]) -> list[RawListing]:
    """Map already-scraped DOM row dicts to listings (unit-testable)."""
    out: list[RawListing] = []
    for r in rows:
        list_price = as_float(r.get("price"))
        all_in = as_float(r.get("all_in"))
        out.append(
            RawListing(
                external_id=r.get("id"),
                section=r.get("section"),
                row=r.get("row"),
                quantity=int(r["quantity"]) if str(r.get("quantity", "")).isdigit() else None,
                list_price=list_price,
                fees=as_float(r.get("fees")),
                all_in_price=all_in or list_price,
                currency=r.get("currency", "USD"),
                raw=r,
            )
        )
    return out


# --- Anti-bot block detection --------------------------------------------

BLOCK_MARKERS = (
    "captcha-delivery.com",
    "datadome",
    "verify you are a human",
    "unusual traffic",
    "access denied",
    "pardon our interruption",
    "px-captcha",            # PerimeterX, used by some ticketing sites
)


def is_block_html(html: str | None) -> bool:
    if not html:
        return False
    low = html.lower()
    return any(m in low for m in BLOCK_MARKERS)
