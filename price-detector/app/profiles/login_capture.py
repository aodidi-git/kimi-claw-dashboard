"""Headed login capture: open a real browser, let the human log in, save state.

This blocks on a human, so callers run it as a background task. We poll for an
auth cookie heuristic, then persist the Playwright storage_state to disk and
attach it to the profile.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from ..config import settings
from . import manager
from .devices import device_context_kwargs

# A login is considered complete when a plausible auth cookie appears.
_AUTH_COOKIE_HINTS = ("auth", "session", "login", "token", "sh_", "identity")

_status: dict[int, str] = {}


def status_for(profile_id: int) -> str:
    return _status.get(profile_id, "idle")


async def capture_login(profile_id: int, login_url: str, max_wait_s: int = 300) -> str:
    profile = manager.get_profile(profile_id)
    if profile is None:
        raise ValueError(f"unknown profile {profile_id}")
    _status[profile_id] = "running"
    settings.ensure_dirs()
    out_path = settings.storage_states_dir / f"{profile.name}.json"

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(**device_context_kwargs(profile.device))
        page = await ctx.new_page()
        await page.goto(login_url, wait_until="domcontentloaded")

        deadline = asyncio.get_event_loop().time() + max_wait_s
        logged_in = False
        while asyncio.get_event_loop().time() < deadline:
            cookies = await ctx.cookies()
            if any(
                any(h in (c.get("name", "").lower()) for h in _AUTH_COOKIE_HINTS)
                for c in cookies
            ):
                logged_in = True
                break
            if len(ctx.pages) == 0:  # user closed the window
                break
            await asyncio.sleep(2)

        await ctx.storage_state(path=str(out_path))
        await ctx.close()
        await browser.close()

        manager.set_storage_state(profile_id, str(out_path))
        _status[profile_id] = "captured" if logged_in else "saved (login unconfirmed)"
        return str(out_path)
    except Exception as exc:  # noqa: BLE001
        _status[profile_id] = f"error: {exc}"
        raise
    finally:
        await pw.stop()


def default_login_url(site: str) -> str:
    return {
        "stubhub": "https://www.stubhub.com/login",
    }.get(site, "https://www.stubhub.com/login")
