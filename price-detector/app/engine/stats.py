"""Comparison engine: build the per-listing price matrix and summary stats.

Reads persisted snapshots/prices for a run and produces a RunSummary. The core
honest move is the *noise floor*: the same profile fetched across multiple trials
will show some price drift (inventory churn / temporal volatility). We treat a
profile's delta versus the baseline as "significant" only when it exceeds
``k * noise_floor``, so true profile-based discrimination is separated from mere
volatility.
"""
from __future__ import annotations

import statistics
from collections import defaultdict

from .. import db
from ..config import settings
from ..models import RunSummary
from ..profiles import manager


def _price_of(row) -> float | None:
    return row["all_in_price"] if row["all_in_price"] is not None else row["list_price"]


def compute_noise_floor(per_profile_listing_prices: dict) -> float:
    """Median within-profile spread across trials, in absolute currency units.

    ``per_profile_listing_prices`` maps (profile_id, listing_id) -> [prices...].
    The spread for a key is max-min across its trials; the noise floor is the
    median spread over all keys that had >=2 trials.
    """
    spreads = []
    for prices in per_profile_listing_prices.values():
        vals = [p for p in prices if p is not None]
        if len(vals) >= 2:
            spreads.append(max(vals) - min(vals))
    return statistics.median(spreads) if spreads else 0.0


def build_summary(run_id: int) -> RunSummary:
    run = db.query_one("SELECT * FROM runs WHERE id=?", (run_id,))
    profiles = manager.all_profiles()
    prof_by_id = {p.id: p for p in profiles}
    baseline = manager.baseline_profile()
    baseline_id = baseline.id if baseline else None

    # Which profiles actually participated in this run.
    snap_rows = db.query("SELECT * FROM snapshots WHERE run_id=?", (run_id,))
    participating_ids = []
    blocked_profiles: list[str] = []
    for s in snap_rows:
        pid = s["profile_id"]
        if pid not in participating_ids:
            participating_ids.append(pid)
        if s["status"] == "blocked":
            name = prof_by_id.get(pid)
            if name and name.name not in blocked_profiles:
                blocked_profiles.append(name.name)

    # Gather prices: (profile_id, listing_id) -> [prices], and best price per cell.
    trial_prices: dict[tuple[int, int], list[float]] = defaultdict(list)
    best_cell: dict[tuple[int, int], dict] = {}
    listing_meta: dict[int, dict] = {}

    rows = db.query(
        "SELECT pr.*, s.profile_id AS profile_id, l.section AS section, "
        "l.row AS row, l.quantity AS quantity, l.id AS lid "
        "FROM prices pr "
        "JOIN snapshots s ON pr.snapshot_id = s.id "
        "JOIN listings l ON pr.listing_id = l.id "
        "WHERE s.run_id=?",
        (run_id,),
    )
    for r in rows:
        pid = r["profile_id"]
        lid = r["lid"]
        price = _price_of(r)
        listing_meta[lid] = {
            "section": r["section"],
            "row": r["row"],
            "quantity": r["quantity"],
        }
        if price is not None:
            trial_prices[(pid, lid)].append(price)
        cell = best_cell.get((pid, lid))
        if cell is None or (price is not None and (cell["all_in_price"] is None or price < cell["all_in_price"])):
            best_cell[(pid, lid)] = {
                "all_in_price": price,
                "list_price": r["list_price"],
                "fees": r["fees"],
                "listing_url": r["listing_url"],
            }

    noise_floor = compute_noise_floor(trial_prices)
    threshold = settings.significance_k * noise_floor

    # Group listings: those seen by >=2 profiles are "matched", else "unmatched".
    profiles_per_listing: dict[int, set[int]] = defaultdict(set)
    for (pid, lid) in best_cell:
        profiles_per_listing[lid].add(pid)

    matched_rows = []
    unmatched_rows = []
    significant_count = 0
    max_savings_abs = 0.0
    max_savings_pct = 0.0
    overall_cheapest_counts: dict[int, int] = defaultdict(int)

    for lid, pids in profiles_per_listing.items():
        meta = listing_meta.get(lid, {})
        cells = {}
        base_cell = best_cell.get((baseline_id, lid)) if baseline_id is not None else None
        base_price = base_cell["all_in_price"] if base_cell else None
        cheapest_price = None
        cheapest_pid = None
        dearest_price = None
        for pid in pids:
            c = best_cell[(pid, lid)]
            price = c["all_in_price"]
            delta_abs = delta_pct = None
            significant = False
            if base_price is not None and price is not None and pid != baseline_id:
                delta_abs = price - base_price
                delta_pct = (delta_abs / base_price * 100.0) if base_price else None
                if abs(delta_abs) > threshold and abs(delta_abs) > 0.005:
                    significant = True
            if price is not None and (cheapest_price is None or price < cheapest_price):
                cheapest_price = price
                cheapest_pid = pid
            if price is not None and (dearest_price is None or price > dearest_price):
                dearest_price = price
            cells[pid] = {
                "profile_id": pid,
                "profile_name": prof_by_id.get(pid).name if pid in prof_by_id else str(pid),
                "all_in_price": price,
                "list_price": c["list_price"],
                "fees": c["fees"],
                "listing_url": c["listing_url"],
                "delta_abs": delta_abs,
                "delta_pct": delta_pct,
                "significant": significant,
            }
            if significant:
                significant_count += 1
        if cheapest_pid is not None:
            overall_cheapest_counts[cheapest_pid] += 1
        # savings: spread between the dearest and cheapest profile for this listing
        # (what you'd save by shopping as the cheapest profile instead of the worst).
        if dearest_price is not None and cheapest_price is not None:
            sv = dearest_price - cheapest_price
            if sv > max_savings_abs:
                max_savings_abs = sv
                max_savings_pct = (sv / dearest_price * 100.0) if dearest_price else 0.0

        row_obj = {
            "listing_id": lid,
            "section": meta.get("section"),
            "row": meta.get("row"),
            "quantity": meta.get("quantity"),
            "cells": cells,
            "cheapest_profile_id": cheapest_pid,
            "cheapest_price": cheapest_price,
        }
        if len(pids) >= 2:
            matched_rows.append(row_obj)
        else:
            unmatched_rows.append(row_obj)

    matched_rows.sort(key=lambda r: (r["cheapest_price"] is None, r["cheapest_price"] or 0))

    cheapest_profile_name = None
    if overall_cheapest_counts:
        top_pid = max(overall_cheapest_counts, key=overall_cheapest_counts.get)
        cheapest_profile_name = prof_by_id.get(top_pid).name if top_pid in prof_by_id else None

    notes = [
        f"Noise floor (median within-profile spread across trials): ${noise_floor:.2f}.",
        f"Significance threshold: |delta| > ${threshold:.2f} (k={settings.significance_k}).",
    ]
    if (run["trials"] if run else 1) < 2:
        notes.append(
            "Single trial: noise floor is 0, so all deltas appear significant. "
            "Run >=2 trials to separate discrimination from price volatility."
        )
    if blocked_profiles:
        notes.append(f"Blocked profiles (no data): {', '.join(blocked_profiles)}.")

    summary = RunSummary(
        run_id=run_id,
        baseline_profile_id=baseline_id,
        profiles=[
            {
                "id": prof_by_id[pid].id,
                "name": prof_by_id[pid].name,
                "device": prof_by_id[pid].device,
                "persistence": prof_by_id[pid].persistence,
                "auth": prof_by_id[pid].auth,
                "is_baseline": prof_by_id[pid].id == baseline_id,
            }
            for pid in participating_ids
            if pid in prof_by_id
        ],
        rows=matched_rows,
        unmatched=unmatched_rows,
        blocked_profiles=blocked_profiles,
        significant_count=significant_count,
        max_savings_abs=round(max_savings_abs, 2),
        max_savings_pct=round(max_savings_pct, 1),
        cheapest_profile_name=cheapest_profile_name,
        notes=notes,
    )
    return summary
