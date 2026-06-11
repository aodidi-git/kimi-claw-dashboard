"""Site adapter interface.

A SiteAdapter knows how to (a) recognize an event URL, (b) fetch the listings
for that event under whatever profile a given Playwright ``page`` already
embodies, and (c) build a deep link to the checkout step for a listing.

Adding a new ticketing site = implement this ABC + register it in registry.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import FetchResult, RawListing


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
