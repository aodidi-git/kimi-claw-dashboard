"""Profile CRUD and the default comparison matrix."""
from __future__ import annotations

from .. import db
from ..config import settings
from ..models import Profile

# The default matrix: a small, fast, sane set of profiles seeded on first boot.
DEFAULT_MATRIX = [
    # name, device, persistence, auth, is_baseline
    ("desktop-fresh", "desktop", "fresh", "anon", True),
    ("mobile-fresh", "mobile", "fresh", "anon", False),
    ("desktop-returning", "desktop", "returning", "anon", False),
    ("desktop-logged-in", "desktop", "fresh", "logged_in", False),
]


def _row_to_profile(row) -> Profile:
    return Profile(
        id=row["id"],
        name=row["name"],
        device=row["device"],
        persistence=row["persistence"],
        auth=row["auth"],
        proxy_id=row["proxy_id"],
        storage_state_path=row["storage_state_path"],
        user_data_dir=row["user_data_dir"],
        enabled=bool(row["enabled"]),
        is_baseline=bool(row["is_baseline"]),
        proxy_server=row["proxy_server"] if "proxy_server" in row.keys() else None,
        proxy_username=row["proxy_username"] if "proxy_username" in row.keys() else None,
        proxy_password=row["proxy_password"] if "proxy_password" in row.keys() else None,
        proxy_geo_hint=row["proxy_geo_hint"] if "proxy_geo_hint" in row.keys() else None,
    )


_JOIN = (
    "SELECT p.*, x.server AS proxy_server, x.username AS proxy_username, "
    "x.password AS proxy_password, x.geo_hint AS proxy_geo_hint "
    "FROM profiles p LEFT JOIN proxies x ON p.proxy_id = x.id "
)


def seed_defaults() -> None:
    if db.query_one("SELECT id FROM profiles LIMIT 1"):
        return
    for name, device, persistence, auth, baseline in DEFAULT_MATRIX:
        udir = None
        if persistence == "returning":
            udir = str(settings.user_data_root / name)
        db.execute(
            "INSERT INTO profiles (name, device, persistence, auth, user_data_dir, is_baseline) "
            "VALUES (?,?,?,?,?,?)",
            (name, device, persistence, auth, udir, 1 if baseline else 0),
        )


def all_profiles() -> list[Profile]:
    return [_row_to_profile(r) for r in db.query(_JOIN + "ORDER BY p.id")]


def enabled_profiles() -> list[Profile]:
    return [
        _row_to_profile(r)
        for r in db.query(_JOIN + "WHERE p.enabled=1 ORDER BY p.id")
    ]


def get_profile(profile_id: int) -> Profile | None:
    row = db.query_one(_JOIN + "WHERE p.id=?", (profile_id,))
    return _row_to_profile(row) if row else None


def baseline_profile() -> Profile | None:
    row = db.query_one(_JOIN + "WHERE p.is_baseline=1 LIMIT 1")
    if row:
        return _row_to_profile(row)
    row = db.query_one(_JOIN + "ORDER BY p.id LIMIT 1")
    return _row_to_profile(row) if row else None


def set_enabled(profile_id: int, enabled: bool) -> None:
    db.execute("UPDATE profiles SET enabled=? WHERE id=?", (1 if enabled else 0, profile_id))


def set_baseline(profile_id: int) -> None:
    db.execute("UPDATE profiles SET is_baseline=0")
    db.execute("UPDATE profiles SET is_baseline=1 WHERE id=?", (profile_id,))


def set_proxy(profile_id: int, proxy_id: int | None) -> None:
    db.execute("UPDATE profiles SET proxy_id=? WHERE id=?", (proxy_id, profile_id))


def set_storage_state(profile_id: int, path: str) -> None:
    db.execute("UPDATE profiles SET storage_state_path=? WHERE id=?", (path, profile_id))


def add_proxy(label: str, server: str, username: str | None, password: str | None,
              geo_hint: str | None) -> int:
    return db.execute(
        "INSERT INTO proxies (label, server, username, password, geo_hint) VALUES (?,?,?,?,?)",
        (label, server, username or None, password or None, geo_hint or None),
    )


def all_proxies() -> list[dict]:
    return [dict(r) for r in db.query("SELECT * FROM proxies ORDER BY id")]
