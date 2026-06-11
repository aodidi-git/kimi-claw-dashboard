"""StubHub adapter.

Extraction strategy lives in ``InterceptAdapter``: intercept the internal
listings JSON API (stable listing IDs + fee fields), falling back to embedded
page state then DOM scraping. This module only declares StubHub's specifics.

The parser functions are re-exported from ``extract`` so existing tests and the
debug tooling can import them from here.
"""
from __future__ import annotations

from ..models import RawListing
from .base import InterceptAdapter
from .extract import (  # noqa: F401  (re-exported for tests / tooling)
    extract_event_id,
    is_block_html,
    parse_api_payloads,
    parse_dom_text,
    parse_embedded_state,
)


class StubHubAdapter(InterceptAdapter):
    site_name = "stubhub"
    url_tokens = ("browse", "listing", "inventory", "grid", "/event")
    body_keys = ("listingId", "sectionName", "items", "listings", "grid")
    all_in_cookie = ("allInPricing", "true", ".stubhub.com")

    @classmethod
    def matches(cls, url: str) -> bool:
        return "stubhub." in url.lower()

    def checkout_url(self, listing: RawListing, event_url: str) -> str:
        if listing.external_id:
            sep = "&" if "?" in event_url else "?"
            return f"{event_url}{sep}listingId={listing.external_id}"
        return event_url
