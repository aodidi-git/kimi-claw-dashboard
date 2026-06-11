#!/usr/bin/env python3
"""Seed realistic demo data so the UI can be previewed without Playwright.

This inserts an event plus several completed runs whose prices are fed through
the *real* matching + stats engine (no hand-faked summaries), so the comparison
matrix, significance flags, noise floor, history and trend sparklines all reflect
genuine engine output. Useful for a local preview:

    python scripts/demo_seed.py
    ./run.sh        # then browse http://127.0.0.1:8400

Re-running is idempotent-ish: it adds a fresh batch of runs each time.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.config import settings  # noqa: E402
from app.engine import stats  # noqa: E402
from app.profiles import manager  # noqa: E402

# Per-profile pricing behaviour relative to the baseline list price.
# (name -> multiplier applied to each listing's base list price)
PROFILE_MULTIPLIER = {
    "desktop-fresh": 1.00,    # baseline
    "mobile-fresh": 1.15,     # mobile shoppers marked up ~15%
    "desktop-returning": 1.09,  # returning-visitor "urgency" bump
    "desktop-logged-in": 0.97,  # small loyalty discount
}

# Base listings for the demo event (per-ticket list price, fee).
BASE_LISTINGS = [
    ("100", "5", 2, 220.0, 0.25),
    ("Lower 110", "12", 4, 145.0, 0.25),
    ("Upper 320", "G", 2, 78.0, 0.25),
    ("Floor GA", "GA", 2, 410.0, 0.25),
]


def _seed_one_run(event_id: int, trials: int, drift: float) -> int:
    run_id = db.create_run(event_id, trials)
    profiles = manager.enabled_profiles()
    for trial in range(1, trials + 1):
        for p in profiles:
            snap = db.create_snapshot(run_id, p.id, trial)
            mult = PROFILE_MULTIPLIER.get(p.name, 1.0)
            for ext, section, qty_row, base_price, fee_rate in _listings():
                # small per-trial volatility so the noise floor is realistic
                noise = random.uniform(-drift, drift)
                list_price = round(base_price * mult * (1 + noise), 2)
                fees = round(list_price * fee_rate, 2)
                all_in = round(list_price + fees, 2)
                lid = db.upsert_listing(event_id, f"id:{ext}", ext, section, qty_row[0], qty_row[1])
                db.insert_price(snap, lid, list_price, fees, all_in, "USD",
                                f"https://www.stubhub.com/event/9001/?listingId={ext}", {})
            db.finish_snapshot(snap, "ok", "api_intercept")
    summary = stats.build_summary(run_id)
    db.set_run_status(run_id, "done", summary.to_dict())
    return run_id


def _listings():
    for i, (section, row, qty, base_price, fee_rate) in enumerate(BASE_LISTINGS):
        yield f"L{i+1}", section, (row, qty), base_price, fee_rate


def main() -> None:
    settings.ensure_dirs()
    db.init_db()
    manager.seed_defaults()

    event_id = db.upsert_event(
        "stubhub",
        "https://www.stubhub.com/taylor-swift-tickets/event/9001/",
        name="Demo Headliner — Arena Tour",
        venue="Demo Arena",
        event_date="2026-08-15",
    )

    # Three runs over time with slightly different volatility -> a real trend.
    for drift in (0.015, 0.02, 0.012):
        rid = _seed_one_run(event_id, trials=2, drift=drift)
        run = db.query_one("SELECT * FROM runs WHERE id=?", (rid,))
        print(f"seeded run #{rid} ({run['status']})")

    print(f"\nDone. Start the app and open http://127.0.0.1:8400")
    print("  ./run.sh")


if __name__ == "__main__":
    main()
