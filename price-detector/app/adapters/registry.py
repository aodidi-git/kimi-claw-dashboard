"""Adapter registry: map an event URL to the right SiteAdapter."""
from __future__ import annotations

from .base import SiteAdapter
from .seatgeek import SeatGeekAdapter
from .stubhub import StubHubAdapter

ADAPTERS: list[type[SiteAdapter]] = [StubHubAdapter, SeatGeekAdapter]


def get_adapter_for_url(url: str) -> SiteAdapter | None:
    for cls in ADAPTERS:
        if cls.matches(url):
            return cls()
    return None


def site_for_url(url: str) -> str | None:
    adapter = get_adapter_for_url(url)
    return adapter.site_name if adapter else None
