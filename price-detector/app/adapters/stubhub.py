"""StubHub adapter.

Primary extraction strategy: intercept the internal listings JSON API responses
(stable listing IDs, section/row/qty, list price + fee fields). Fallbacks:
embedded page state (Next.js ``__NEXT_DATA__`` / JSON-LD) then DOM scraping.

The parsers (``parse_api_payloads``, ``parse_embedded_state``, ``parse_dom``) are
pure functions over already-fetched bytes/dicts so they can be unit-tested from
fixtures with no network.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Iterable

from ..models import FetchResult, RawListing
from .base import SiteAdapter

# Tokens that mark a network response as "listings-like".
_URL_TOKENS = ("browse", "listing", "inventory", "grid", "/event")
_BODY_KEYS = ("listingId", "sectionName", "items", "listings", "grid")

_EVENT_ID_RE = re.compile(r"/(?:event)/(\d+)", re.IGNORECASE)
_TRAILING_ID_RE = re.compile(r"-(\d+)/?(?:\?|$)")


def extract_event_id(url: str) -> str | None:
    m = _EVENT_ID_RE.search(url)
    if m:
        return m.group(1)
    m = _TRAILING_ID_RE.search(url)
    return m.group(1) if m else None


def _as_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        # money objects like {"amount": 123.0, "currency": "USD"}
        for k in ("amount", "value", "total", "price"):
            if k in val:
                return _as_float(val[k])
        return None
    if isinstance(val, str):
        cleaned = re.sub(r"[^0-9.]", "", val)
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
    return None


def _first(d: dict, *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _listing_from_dict(item: dict) -> RawListing | None:
    """Best-effort map one StubHub listing dict to a RawListing."""
    if not isinstance(item, dict):
        return None
    ext = _first(item, "listingId", "id", "listingID", "sellerListingId")
    section = _first(item, "sectionName", "section", "zoneName", "zone")
    row = _first(item, "row", "rowName")
    qty = _first(item, "quantity", "availableTickets", "ticketCount", "qty")
    list_price = _as_float(
        _first(item, "listPrice", "price", "amount", "faceValue", "rawPrice")
    )
    fees = _as_float(_first(item, "fees", "serviceFee", "totalFees", "feeAmount"))
    all_in = _as_float(
        _first(item, "allInPrice", "totalPrice", "totalCost", "priceWithFees")
    )
    if all_in is None and list_price is not None and fees is not None:
        all_in = list_price + fees
    currency = _first(item, "currency", "currencyCode") or "USD"
    if list_price is None and all_in is None:
        return None
    return RawListing(
        external_id=str(ext) if ext is not None else None,
        section=str(section) if section is not None else None,
        row=str(row) if row is not None else None,
        quantity=int(qty) if isinstance(qty, (int, float, str)) and str(qty).isdigit() else None,
        list_price=list_price,
        fees=fees,
        all_in_price=all_in,
        currency=str(currency),
        listing_url=None,
        raw=item,
    )


def _walk_for_listings(obj: Any) -> Iterable[dict]:
    """Yield dicts that look like individual listings, recursively."""
    if isinstance(obj, dict):
        looks_like = any(k in obj for k in ("listingId", "sectionName", "sellerListingId"))
        if looks_like and (
            "price" in obj or "listPrice" in obj or "totalPrice" in obj or "amount" in obj
        ):
            yield obj
        for v in obj.values():
            yield from _walk_for_listings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_for_listings(v)


def parse_api_payloads(payloads: list[Any]) -> list[RawListing]:
    out: list[RawListing] = []
    seen: set[str] = set()
    for payload in payloads:
        for item in _walk_for_listings(payload):
            rl = _listing_from_dict(item)
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
    for m in re.finditer(
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
    ):
        try:
            payloads.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            pass
    for m in re.finditer(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL
    ):
        try:
            payloads.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            pass
    return parse_api_payloads(payloads)


def parse_dom_text(rows: list[dict]) -> list[RawListing]:
    """Map already-scraped DOM row dicts (section/row/qty/price text) to listings.

    Kept separate from Playwright so it is unit-testable; the live DOM scrape in
    ``fetch_listings`` produces these dicts.
    """
    out: list[RawListing] = []
    for r in rows:
        list_price = _as_float(r.get("price"))
        all_in = _as_float(r.get("all_in"))
        out.append(
            RawListing(
                external_id=r.get("id"),
                section=r.get("section"),
                row=r.get("row"),
                quantity=int(r["quantity"]) if str(r.get("quantity", "")).isdigit() else None,
                list_price=list_price,
                fees=_as_float(r.get("fees")),
                all_in_price=all_in or list_price,
                currency=r.get("currency", "USD"),
                raw=r,
            )
        )
    return out


# --- DataDome / block detection ------------------------------------------

_BLOCK_MARKERS = (
    "captcha-delivery.com",
    "datadome",
    "verify you are a human",
    "unusual traffic",
    "access denied",
)


def is_block_html(html: str) -> bool:
    low = html.lower()
    return any(m in low for m in _BLOCK_MARKERS)


class StubHubAdapter(SiteAdapter):
    site_name = "stubhub"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "stubhub." in url.lower()

    async def fetch_listings(self, page, event_url: str, capture_dir: Path) -> FetchResult:
        capture_dir.mkdir(parents=True, exist_ok=True)
        captured: list[Any] = []
        blocked_signal = {"hit": False, "reason": None}
        counter = {"n": 0}

        async def _maybe_capture(response):
            try:
                url = response.url
                ctype = (response.headers or {}).get("content-type", "")
                if "captcha-delivery.com" in url:
                    blocked_signal["hit"] = True
                    blocked_signal["reason"] = "DataDome captcha resource"
                    return
                url_match = any(t in url.lower() for t in _URL_TOKENS)
                if "json" not in ctype and not url_match:
                    return
                body = await response.body()
                text = body.decode("utf-8", "replace")
                if "json" in ctype or any(k in text for k in _BODY_KEYS):
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        return
                    counter["n"] += 1
                    (capture_dir / f"resp_{counter['n']:03d}.json").write_text(text)
                    captured.append(data)
            except Exception:
                # Capturing must never crash the fetch.
                pass

        page.on("response", _maybe_capture)
        # Prefer the site's all-in pricing display where supported.
        try:
            await page.context.add_cookies(
                [{
                    "name": "allInPricing",
                    "value": "true",
                    "domain": ".stubhub.com",
                    "path": "/",
                }]
            )
        except Exception:
            pass

        try:
            resp = await page.goto(
                event_url, wait_until="domcontentloaded", timeout=25_000
            )
        except Exception as exc:
            return FetchResult(blocked=False, block_reason=None, extraction_method="none",
                               event_meta={"error": f"navigation: {exc}"})

        if resp is not None and resp.status in (403, 429):
            blocked_signal["hit"] = True
            blocked_signal["reason"] = f"HTTP {resp.status}"

        # Give XHRs a moment to land (or a block to surface).
        for _ in range(20):
            if captured or blocked_signal["hit"]:
                break
            await asyncio.sleep(0.5)

        html = ""
        try:
            html = await page.content()
        except Exception:
            pass

        if blocked_signal["hit"] or is_block_html(html):
            try:
                await page.screenshot(path=str(capture_dir / "screenshot.png"))
            except Exception:
                pass
            (capture_dir / "page.html").write_text(html or "")
            return FetchResult(
                blocked=True,
                block_reason=blocked_signal["reason"] or "block markers in page",
                extraction_method="none",
            )

        (capture_dir / "page.html").write_text(html or "")

        # 1) intercepted API JSON
        listings = parse_api_payloads(captured)
        method = "api_intercept"
        # 2) embedded state
        if not listings and html:
            listings = parse_embedded_state(html)
            method = "embedded_json"
        # 3) DOM scrape
        if not listings:
            dom_rows = await self._scrape_dom(page)
            listings = parse_dom_text(dom_rows)
            method = "dom"

        for rl in listings:
            if rl.listing_url is None:
                rl.listing_url = self.checkout_url(rl, event_url)

        if not listings:
            method = "none"

        return FetchResult(
            listings=listings,
            extraction_method=method,
            blocked=False,
            event_meta={"external_event_id": extract_event_id(event_url)},
        )

    async def _scrape_dom(self, page) -> list[dict]:
        """Last-resort DOM scrape; returns row dicts for parse_dom_text."""
        try:
            return await page.evaluate(
                """() => {
                    const rows = [];
                    const cards = document.querySelectorAll(
                      '[data-listing-id], [data-testid*="listing"], li[class*="listing"]'
                    );
                    cards.forEach(c => {
                      const text = c.textContent || '';
                      const priceMatch = text.match(/\\$([0-9,]+(?:\\.[0-9]{2})?)/);
                      rows.push({
                        id: c.getAttribute('data-listing-id'),
                        section: (c.querySelector('[class*="section"],[data-testid*="section"]')||{}).textContent || null,
                        row: (c.querySelector('[class*="row"],[data-testid*="row"]')||{}).textContent || null,
                        quantity: null,
                        price: priceMatch ? priceMatch[1] : null,
                      });
                    });
                    return rows;
                }"""
            )
        except Exception:
            return []

    def checkout_url(self, listing: RawListing, event_url: str) -> str:
        if listing.external_id:
            sep = "&" if "?" in event_url else "?"
            return f"{event_url}{sep}listingId={listing.external_id}"
        return event_url
