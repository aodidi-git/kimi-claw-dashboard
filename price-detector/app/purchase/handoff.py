"""Assisted-purchase handoff.

Launches a *detached* headed browser configured exactly like the chosen profile
(device + proxy + storage_state / persistent user_data_dir) navigated to the
listing/checkout page, then leaves it open for the human to complete payment.
We never automate payment.

The browser runs in a separate process (``scripts/handoff_browser.py``) so it
outlives the HTTP request and is independent of the run's shared browser.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from ..models import Profile
from ..profiles import manager

_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "handoff_browser.py"


async def launch_handoff(profile_id: int, listing_url: str) -> dict:
    profile = manager.get_profile(profile_id)
    if profile is None:
        raise ValueError(f"unknown profile {profile_id}")

    spec = {
        "device": profile.device,
        "persistence": profile.persistence,
        "auth": profile.auth,
        "user_data_dir": profile.user_data_dir,
        "storage_state_path": profile.storage_state_path,
        "proxy_server": profile.proxy_server,
        "proxy_username": profile.proxy_username,
        "proxy_password": profile.proxy_password,
        "proxy_geo_hint": profile.proxy_geo_hint,
        "url": listing_url,
    }
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(_SCRIPT), json.dumps(spec),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return {"pid": proc.pid, "profile": profile.name, "url": listing_url}
