#!/usr/bin/env python3
"""Fetch one event under one profile and dump captures — for parser dev.

Usage:
  python scripts/debug_fetch.py <event_url> [--profile desktop-fresh] [--headed]

Captures (raw JSON responses, page.html, screenshot on block) land under
data/captures/debug-<ts>/. Sanitized copies of those JSON files become
tests/fixtures/*.json so parsers can be developed offline.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.adapters.registry import get_adapter_for_url  # noqa: E402
from app.config import settings  # noqa: E402
from app.engine.browser import BrowserManager  # noqa: E402
from app.profiles import manager  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--profile", default="desktop-fresh")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    settings.ensure_dirs()
    db.init_db()
    manager.seed_defaults()
    if args.headed:
        settings.headed = True

    profile = next((p for p in manager.all_profiles() if p.name == args.profile), None)
    if profile is None:
        print(f"Unknown profile {args.profile}. Available: "
              f"{[p.name for p in manager.all_profiles()]}")
        return

    adapter = get_adapter_for_url(args.url)
    if adapter is None:
        print("No adapter handles that URL.")
        return

    import time
    capture_dir = settings.captures_dir / f"debug-{int(time.time())}"
    browser = BrowserManager()
    try:
        async with browser.context_for(profile) as ctx:
            page = await ctx.new_page()
            result = await adapter.fetch_listings(page, args.url, capture_dir)
    finally:
        await browser.stop()

    print(f"method={result.extraction_method} blocked={result.blocked} "
          f"reason={result.block_reason}")
    print(f"listings={len(result.listings)}  captures -> {capture_dir}")
    for l in result.listings[:10]:
        print(f"  {l.external_id} {l.section}/{l.row} x{l.quantity} "
              f"list=${l.list_price} all_in=${l.all_in_price}")


if __name__ == "__main__":
    asyncio.run(main())
