"""ComparisonRunner: orchestrate simultaneous per-profile fetches for a run.

All profiles in a trial fire together (gated by a semaphore) to minimize the
time skew between them -- this is the anti-confound mechanism that keeps temporal
price drift from masquerading as profile-based discrimination. Multiple trials
let stats.py estimate the noise floor.
"""
from __future__ import annotations

import asyncio
import random
import traceback
from pathlib import Path

from .. import db
from ..adapters.registry import get_adapter_for_url
from ..config import settings
from ..models import Profile
from ..profiles import manager
from . import stats
from .browser import BrowserManager
from .matching import match_key


class ComparisonRunner:
    def __init__(self, browser: BrowserManager) -> None:
        self.browser = browser
        self.semaphore = asyncio.Semaphore(settings.concurrency_cap)

    async def run(self, run_id: int) -> None:
        run = db.query_one("SELECT * FROM runs WHERE id=?", (run_id,))
        if run is None:
            return
        event = db.query_one("SELECT * FROM events WHERE id=?", (run["event_id"],))
        adapter = get_adapter_for_url(event["url"])
        db.set_run_status(run_id, "running")

        try:
            if adapter is None:
                raise RuntimeError(f"No adapter handles URL: {event['url']}")
            profiles = manager.enabled_profiles()
            if not profiles:
                raise RuntimeError("No enabled profiles to compare.")

            for trial in range(1, run["trials"] + 1):
                tasks = [
                    self._fetch_one(adapter, event, p, run_id, trial)
                    for p in profiles
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

            summary = stats.build_summary(run_id)
            db.set_run_status(run_id, "done", summary.to_dict())
        except Exception as exc:  # noqa: BLE001
            db.execute(
                "UPDATE runs SET status='failed', summary_json=?, finished_at=datetime('now') WHERE id=?",
                (f'{{"error": {exc!r}}}', run_id),
            )
            traceback.print_exc()

    async def _fetch_one(self, adapter, event, profile: Profile, run_id: int, trial: int) -> None:
        async with self.semaphore:
            # Small randomized jitter so contexts do not all hammer at the same ms.
            await asyncio.sleep(random.uniform(0, settings.jitter_ms / 1000.0))
            snap_id = db.create_snapshot(run_id, profile.id, trial)
            capture_dir = settings.captures_dir / str(snap_id)
            try:
                result = await self._do_fetch(adapter, event, profile, capture_dir)
                # Headed retry on block, if enabled and we were headless.
                if result.blocked and settings.headed_retry_on_block and not settings.headed:
                    result = await self._do_fetch(
                        adapter, event, profile, capture_dir, headed_override=True
                    )

                if result.blocked:
                    db.finish_snapshot(snap_id, "blocked", error=result.block_reason,
                                       capture_dir=str(capture_dir))
                    return

                self._persist_listings(event["id"], snap_id, result)
                status = "ok" if result.listings else "error"
                db.finish_snapshot(
                    snap_id, status, extraction_method=result.extraction_method,
                    error=None if result.listings else "no listings extracted",
                    capture_dir=str(capture_dir),
                )
            except Exception as exc:  # noqa: BLE001
                db.finish_snapshot(snap_id, "error", error=str(exc),
                                   capture_dir=str(capture_dir))
                traceback.print_exc()

    async def _do_fetch(self, adapter, event, profile, capture_dir: Path, headed_override=None):
        async with self.browser.context_for(profile, headed_override=headed_override) as ctx:
            page = await ctx.new_page()
            page.set_default_timeout(settings.nav_timeout_ms)
            return await adapter.fetch_listings(page, event["url"], capture_dir)

    def _persist_listings(self, event_id: int, snap_id: int, result) -> None:
        for rl in result.listings:
            key = match_key(rl)
            listing_id = db.upsert_listing(
                event_id, key, rl.external_id, rl.section, rl.row, rl.quantity
            )
            db.insert_price(
                snap_id, listing_id, rl.list_price, rl.fees, rl.all_in_price,
                rl.currency, rl.listing_url, rl.raw,
            )
