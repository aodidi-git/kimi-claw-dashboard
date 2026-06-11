"""Site adapter interface + a reusable intercept-based implementation.

A SiteAdapter knows how to (a) recognize an event URL, (b) fetch the listings
for that event under whatever profile a given Playwright ``page`` already
embodies, and (c) build a deep link to the checkout step for a listing.

Most modern ticketing sites load listings via an internal JSON API and protect
pages with an anti-bot system. ``InterceptAdapter`` captures that flow once;
concrete sites (StubHub, SeatGeek) only declare their URL/cookie specifics and a
checkout-link builder.

Adding a new ticketing site = subclass ``InterceptAdapter`` (or ``SiteAdapter``
directly) and register it in registry.py.
"""
from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..models import FetchResult, RawListing
from . import extract


class BlockedError(RuntimeError):
    """Raised when an anti-bot system (e.g. DataDome) blocks the fetch."""


class SiteAdapter(ABC):
    site_name: str = "base"

    @classmethod
    @abstractmethod
    def matches(cls, url: str) -> bool:
        """Return True if this adapter handles ``url``."""

    @abstractmethod
    async def fetch_listings(
        self, page, event_url: str, capture_dir: Path
    ) -> FetchResult:
        """Navigate ``page`` to ``event_url`` and return the listings.

        ``page`` is already configured for the active profile (device/proxy/auth).
        Raw network captures should be written under ``capture_dir`` so parsers
        can be developed/tested offline.
        """

    @abstractmethod
    def checkout_url(self, listing: RawListing, event_url: str) -> str:
        """Build a deep link to the listing/checkout step for assisted handoff."""


class InterceptAdapter(SiteAdapter):
    """Generic 'intercept the listings JSON API' adapter.

    Subclasses set the class attributes below and implement ``matches`` and
    ``checkout_url``. The fetch flow (response interception, block detection,
    fallbacks) is shared.
    """

    # URL substrings that mark a response as listings-related.
    url_tokens: tuple[str, ...] = ("browse", "listing", "inventory", "grid", "/event")
    # Body substrings used as a secondary signal when content-type isn't JSON.
    body_keys: tuple[str, ...] = ("listingId", "sectionName", "items", "listings", "grid")
    # Optional cookie to request all-in/estimated-fee pricing; (name, value, domain).
    all_in_cookie: tuple[str, str, str] | None = None

    async def fetch_listings(self, page, event_url: str, capture_dir: Path) -> FetchResult:
        capture_dir.mkdir(parents=True, exist_ok=True)
        captured: list[Any] = []
        blocked = {"hit": False, "reason": None}
        counter = {"n": 0}

        async def _maybe_capture(response):
            try:
                url = response.url
                ctype = (response.headers or {}).get("content-type", "")
                if "captcha-delivery.com" in url or "px-captcha" in url:
                    blocked["hit"] = True
                    blocked["reason"] = "anti-bot captcha resource"
                    return
                url_match = any(t in url.lower() for t in self.url_tokens)
                if "json" not in ctype and not url_match:
                    return
                body = await response.body()
                text = body.decode("utf-8", "replace")
                if "json" in ctype or any(k in text for k in self.body_keys):
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        return
                    counter["n"] += 1
                    (capture_dir / f"resp_{counter['n']:03d}.json").write_text(text)
                    captured.append(data)
            except Exception:
                pass  # capturing must never crash the fetch

        page.on("response", _maybe_capture)

        if self.all_in_cookie:
            name, value, domain = self.all_in_cookie
            try:
                await page.context.add_cookies(
                    [{"name": name, "value": value, "domain": domain, "path": "/"}]
                )
            except Exception:
                pass

        try:
            resp = await page.goto(event_url, wait_until="domcontentloaded", timeout=25_000)
        except Exception as exc:
            return FetchResult(extraction_method="none",
                               event_meta={"error": f"navigation: {exc}"})

        if resp is not None and resp.status in (403, 429):
            blocked["hit"] = True
            blocked["reason"] = f"HTTP {resp.status}"

        for _ in range(20):
            if captured or blocked["hit"]:
                break
            await asyncio.sleep(0.5)

        html = ""
        try:
            html = await page.content()
        except Exception:
            pass

        if blocked["hit"] or extract.is_block_html(html):
            try:
                await page.screenshot(path=str(capture_dir / "screenshot.png"))
            except Exception:
                pass
            (capture_dir / "page.html").write_text(html or "")
            return FetchResult(blocked=True,
                               block_reason=blocked["reason"] or "block markers in page",
                               extraction_method="none")

        (capture_dir / "page.html").write_text(html or "")

        listings = extract.parse_api_payloads(captured)
        method = "api_intercept"
        if not listings and html:
            listings = extract.parse_embedded_state(html)
            method = "embedded_json"
        if not listings:
            listings = extract.parse_dom_text(await self._scrape_dom(page))
            method = "dom"

        for rl in listings:
            if rl.listing_url is None:
                rl.listing_url = self.checkout_url(rl, event_url)
        if not listings:
            method = "none"

        return FetchResult(
            listings=listings,
            extraction_method=method,
            event_meta={"external_event_id": extract.extract_event_id(event_url)},
        )

    async def _scrape_dom(self, page) -> list[dict]:
        """Last-resort DOM scrape; returns row dicts for extract.parse_dom_text."""
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
