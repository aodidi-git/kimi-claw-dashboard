from app import db
from app.engine import stats
from app.profiles import manager


def _setup_run(trials=2):
    event_id = db.upsert_event("stubhub", "https://www.stubhub.com/event/1/")
    run_id = db.create_run(event_id, trials)
    profs = {p.name: p for p in manager.all_profiles()}
    return event_id, run_id, profs


def _add_price(event_id, run_id, profile_id, trial, ext_id, section, qty, all_in):
    snap = db.create_snapshot(run_id, profile_id, trial)
    lid = db.upsert_listing(event_id, f"id:{ext_id}", ext_id, section, "A", qty)
    db.insert_price(snap, lid, all_in, 0.0, all_in, "USD", "http://x", {})
    db.finish_snapshot(snap, "ok", "api_intercept")


def test_significant_delta_above_noise(fresh_db):
    event_id, run_id, profs = _setup_run(trials=2)
    base = profs["desktop-fresh"].id
    mobile = profs["mobile-fresh"].id

    # Baseline stable at 100 across trials; mobile clearly higher (115) -> significant.
    for trial in (1, 2):
        _add_price(event_id, run_id, base, trial, "L1", "100", 2, 100.0)
        _add_price(event_id, run_id, mobile, trial, "L1", "100", 2, 115.0)

    summary = stats.build_summary(run_id)
    assert len(summary.rows) == 1
    cells = summary.rows[0]["cells"]
    mobile_cell = cells[mobile]
    assert mobile_cell["delta_abs"] == 15.0
    assert mobile_cell["significant"] is True
    assert summary.cheapest_profile_name == "desktop-fresh"
    assert summary.max_savings_abs == 15.0


def test_noise_swamps_small_delta(fresh_db):
    event_id, run_id, profs = _setup_run(trials=2)
    base = profs["desktop-fresh"].id
    mobile = profs["mobile-fresh"].id

    # Both profiles swing wildly across trials (noise ~40); a 5-unit gap is noise.
    _add_price(event_id, run_id, base, 1, "L1", "100", 2, 100.0)
    _add_price(event_id, run_id, base, 2, "L1", "100", 2, 140.0)
    _add_price(event_id, run_id, mobile, 1, "L1", "100", 2, 105.0)
    _add_price(event_id, run_id, mobile, 2, "L1", "100", 2, 145.0)

    summary = stats.build_summary(run_id)
    mobile_cell = summary.rows[0]["cells"][mobile]
    # best (lowest) prices: base 100, mobile 105 -> delta 5, below k*noise.
    assert mobile_cell["significant"] is False


def test_unmatched_listing_separated(fresh_db):
    event_id, run_id, profs = _setup_run(trials=1)
    base = profs["desktop-fresh"].id
    mobile = profs["mobile-fresh"].id
    _add_price(event_id, run_id, base, 1, "SHARED", "100", 2, 100.0)
    _add_price(event_id, run_id, mobile, 1, "SHARED", "100", 2, 110.0)
    _add_price(event_id, run_id, base, 1, "ONLYBASE", "999", 2, 50.0)

    summary = stats.build_summary(run_id)
    assert len(summary.rows) == 1          # only SHARED matched across 2 profiles
    assert len(summary.unmatched) == 1     # ONLYBASE shown to one profile
