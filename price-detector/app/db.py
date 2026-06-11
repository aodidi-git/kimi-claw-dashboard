"""SQLite data-access layer (no ORM).

A single module-level connection in WAL mode. All callers run inside one asyncio
event loop; write transactions are short. Heavy/blocking calls in async code
should be wrapped with ``asyncio.to_thread`` by the caller if needed, but in
practice these queries are tiny.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

from .config import settings

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

_conn: Optional[sqlite3.Connection] = None
_lock = threading.RLock()


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        settings.ensure_dirs()
        _conn = sqlite3.connect(settings.db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def init_db() -> None:
    conn = get_conn()
    with _lock:
        conn.executescript(_SCHEMA_PATH.read_text())
        conn.commit()


def query(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    with _lock:
        cur = get_conn().execute(sql, tuple(params))
        return cur.fetchall()


def query_one(sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Run a write statement, return lastrowid."""
    with _lock:
        conn = get_conn()
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return cur.lastrowid


# --- Higher-level helpers -------------------------------------------------

def upsert_event(site: str, url: str, **meta: Any) -> int:
    row = query_one("SELECT id FROM events WHERE site=? AND url=?", (site, url))
    if row:
        return row["id"]
    return execute(
        "INSERT INTO events (site, url, external_event_id, name, venue, event_date) "
        "VALUES (?,?,?,?,?,?)",
        (
            site,
            url,
            meta.get("external_event_id"),
            meta.get("name"),
            meta.get("venue"),
            meta.get("event_date"),
        ),
    )


def create_run(event_id: int, trials: int) -> int:
    return execute(
        "INSERT INTO runs (event_id, trials, status, started_at) "
        "VALUES (?,?,'pending', datetime('now'))",
        (event_id, trials),
    )


def set_run_status(run_id: int, status: str, summary: Any = None) -> None:
    if summary is not None:
        execute(
            "UPDATE runs SET status=?, summary_json=?, finished_at=datetime('now') WHERE id=?",
            (status, json.dumps(summary), run_id),
        )
    elif status in ("done", "failed"):
        execute(
            "UPDATE runs SET status=?, finished_at=datetime('now') WHERE id=?",
            (status, run_id),
        )
    else:
        execute("UPDATE runs SET status=? WHERE id=?", (status, run_id))


def create_snapshot(run_id: int, profile_id: int, trial: int) -> int:
    return execute(
        "INSERT INTO snapshots (run_id, profile_id, trial, status, started_at) "
        "VALUES (?,?,?,'pending', datetime('now'))",
        (run_id, profile_id, trial),
    )


def finish_snapshot(
    snapshot_id: int,
    status: str,
    extraction_method: str | None = None,
    error: str | None = None,
    capture_dir: str | None = None,
) -> None:
    execute(
        "UPDATE snapshots SET status=?, extraction_method=?, error=?, capture_dir=?, "
        "finished_at=datetime('now') WHERE id=?",
        (status, extraction_method, error, capture_dir, snapshot_id),
    )


def upsert_listing(
    event_id: int,
    match_key: str,
    external_listing_id: str | None,
    section: str | None,
    row: str | None,
    quantity: int | None,
) -> int:
    existing = query_one(
        "SELECT id FROM listings WHERE event_id=? AND match_key=?", (event_id, match_key)
    )
    if existing:
        return existing["id"]
    return execute(
        "INSERT INTO listings (event_id, external_listing_id, section, row, quantity, match_key) "
        "VALUES (?,?,?,?,?,?)",
        (event_id, external_listing_id, section, row, quantity, match_key),
    )


def insert_price(
    snapshot_id: int,
    listing_id: int,
    list_price: float | None,
    fees: float | None,
    all_in_price: float | None,
    currency: str,
    listing_url: str | None,
    raw: Any,
) -> None:
    execute(
        "INSERT OR REPLACE INTO prices "
        "(snapshot_id, listing_id, list_price, fees, all_in_price, currency, listing_url, raw_json) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            snapshot_id,
            listing_id,
            list_price,
            fees,
            all_in_price,
            currency,
            listing_url,
            json.dumps(raw) if raw is not None else None,
        ),
    )
