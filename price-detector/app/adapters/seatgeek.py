"""SeatGeek adapter.

Demonstrates the pluggable design: SeatGeek loads its seat-map listings from an
internal JSON API and protects pages with an anti-bot layer, so it reuses the
same ``InterceptAdapter`` flow as StubHub -- only the URL tokens, all-in pricing
preference, and checkout-link format differ.
"""
from __future__ import annotations

from ..models import RawListing
from .base import InterceptAdapter


class SeatGeekAdapter(InterceptAdapter):
    site_name = "seatgeek"
    # SeatGeek's listing/map endpoints contain these tokens.
    url_tokens = ("listings", "seatmap", "/event", "performers", "inventory")
    body_keys = ("listings", "section", "display_price", "seat_view", "dp")
    # SeatGeek shows all-in ("Prices include fees") via this preference cookie.
    all_in_cookie = ("allin_pricing", "1", ".seatgeek.com")

    @classmethod
    def matches(cls, url: str) -> bool:
        return "seatgeek." in url.lower()

    def checkout_url(self, listing: RawListing, event_url: str) -> str:
        if listing.external_id:
            sep = "&" if "?" in event_url else "?"
            return f"{event_url}{sep}listing_id={listing.external_id}"
        return event_url
