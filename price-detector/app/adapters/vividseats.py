"""Vivid Seats adapter.

Another thin ``InterceptAdapter`` subclass: Vivid Seats loads its listings from
an internal JSON API ("production" / listings endpoints) and exposes an all-in
pricing preference. Only the site-specific tokens and checkout link differ.
"""
from __future__ import annotations

from ..models import RawListing
from .base import InterceptAdapter


class VividSeatsAdapter(InterceptAdapter):
    site_name = "vividseats"
    url_tokens = ("listings", "production", "/event", "tickets", "inventory")
    body_keys = ("listings", "section", "ticketPrice", "listPrice", "tickets")
    # Vivid Seats' all-in toggle preference.
    all_in_cookie = ("all_in_pricing", "true", ".vividseats.com")

    @classmethod
    def matches(cls, url: str) -> bool:
        return "vividseats." in url.lower()

    def checkout_url(self, listing: RawListing, event_url: str) -> str:
        if listing.external_id:
            sep = "&" if "?" in event_url else "?"
            return f"{event_url}{sep}listingId={listing.external_id}"
        return event_url
