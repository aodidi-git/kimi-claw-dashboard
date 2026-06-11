#!/usr/bin/env python3
"""Detached headed browser for assisted purchase.

Invoked by app.purchase.handoff with a JSON spec describing the profile. Opens a
real Chromium window at the listing/checkout URL and stays open until the human
closes it. Never automates payment.

Usage: python scripts/handoff_browser.py '<json-spec>'
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Allow running as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.profiles.devices import device_context_kwargs  # noqa: E402


def _build_kwargs(spec: dict) -> dict:
    kwargs = device_context_kwargs(spec.get("device", "desktop"))
    geo = (spec.get("proxy_geo_hint") or "").lower()
    if "uk" in geo or "london" in geo:
        kwargs.update(locale="en-GB", timezone_id="Europe/London")
    else:
        kwargs.update(locale="en-US", timezone_id="America/New_York")
    if spec.get("proxy_server"):
        proxy = {"server": spec["proxy_server"]}
        if spec.get("proxy_username"):
            proxy["username"] = spec["proxy_username"]
        if spec.get("proxy_password"):
            proxy["password"] = spec["proxy_password"]
        kwargs["proxy"] = proxy
    if spec.get("auth") == "logged_in" and spec.get("storage_state_path"):
        if Path(spec["storage_state_path"]).exists():
            kwargs["storage_state"] = spec["storage_state_path"]
    return kwargs


async def main(spec: dict) -> None:
    from playwright.async_api import async_playwright

    kwargs = _build_kwargs(spec)
    pw = await async_playwright().start()
    try:
        if spec.get("persistence") == "returning" and spec.get("user_data_dir"):
            Path(spec["user_data_dir"]).mkdir(parents=True, exist_ok=True)
            ctx = await pw.chromium.launch_persistent_context(
                spec["user_data_dir"], headless=False, **kwargs
            )
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        else:
            browser = await pw.chromium.launch(headless=False)
            ctx = await browser.new_context(**kwargs)
            page = await ctx.new_page()
        await page.goto(spec["url"], wait_until="domcontentloaded")
        # Stay open until the human closes the context.
        closed = asyncio.Event()
        ctx.on("close", lambda: closed.set())
        await closed.wait()
    finally:
        await pw.stop()


if __name__ == "__main__":
    spec = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    asyncio.run(main(spec))
