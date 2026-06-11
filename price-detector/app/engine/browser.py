"""Browser management: one shared Chromium, per-profile contexts.

Each profile becomes an isolated browser context (own cookies/storage/proxy).
Device emulation, proxy, auth (storage_state) and persistence ('returning' =>
persistent context with a user_data_dir) are all derived from the Profile.
"""
from __future__ import annotations

import contextlib
from pathlib import Path
from typing import AsyncIterator, Optional

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from ..config import settings
from ..models import Profile
from ..profiles.devices import device_context_kwargs

# Light init script to smooth the most obvious automation tell. This reduces but
# does NOT eliminate fingerprint-based bot detection (see README).
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || { runtime: {} };
"""


def _proxy_kwargs(profile: Profile) -> Optional[dict]:
    if not profile.proxy_server:
        return None
    proxy = {"server": profile.proxy_server}
    if profile.proxy_username:
        proxy["username"] = profile.proxy_username
    if profile.proxy_password:
        proxy["password"] = profile.proxy_password
    return proxy


def _locale_for(profile: Profile) -> dict:
    # Align locale/timezone loosely with proxy geo when hinted.
    geo = (profile.proxy_geo_hint or "").lower()
    if "uk" in geo or "london" in geo:
        return {"locale": "en-GB", "timezone_id": "Europe/London"}
    if "eu" in geo or "berlin" in geo or "paris" in geo:
        return {"locale": "en-US", "timezone_id": "Europe/Berlin"}
    return {"locale": "en-US", "timezone_id": "America/New_York"}


def context_kwargs(profile: Profile) -> dict:
    kwargs = device_context_kwargs(profile.device)
    kwargs.update(_locale_for(profile))
    proxy = _proxy_kwargs(profile)
    if proxy:
        kwargs["proxy"] = proxy
    if profile.auth == "logged_in" and profile.storage_state_path:
        if Path(profile.storage_state_path).exists():
            kwargs["storage_state"] = profile.storage_state_path
    return kwargs


class BrowserManager:
    """Owns one Playwright + one shared Chromium for a server lifetime."""

    def __init__(self) -> None:
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

    async def start(self) -> None:
        if self._pw is None:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=not settings.headed)

    async def stop(self) -> None:
        with contextlib.suppress(Exception):
            if self._browser:
                await self._browser.close()
        with contextlib.suppress(Exception):
            if self._pw:
                await self._pw.stop()
        self._browser = None
        self._pw = None

    @contextlib.asynccontextmanager
    async def context_for(
        self, profile: Profile, headed_override: bool | None = None
    ) -> AsyncIterator[BrowserContext]:
        """Yield a context configured for the profile, cleaned up on exit."""
        kwargs = context_kwargs(profile)
        if profile.persistence == "returning" and profile.user_data_dir:
            Path(profile.user_data_dir).mkdir(parents=True, exist_ok=True)
            # Persistent contexts need their own browser launch.
            headless = not (headed_override if headed_override is not None else settings.headed)
            ctx = await self._pw.chromium.launch_persistent_context(
                profile.user_data_dir, headless=headless, **kwargs
            )
            try:
                await ctx.add_init_script(_STEALTH_JS)
                yield ctx
            finally:
                with contextlib.suppress(Exception):
                    await ctx.close()
        else:
            await self.start()
            ctx = await self._browser.new_context(**kwargs)
            try:
                await ctx.add_init_script(_STEALTH_JS)
                yield ctx
            finally:
                with contextlib.suppress(Exception):
                    await ctx.close()
