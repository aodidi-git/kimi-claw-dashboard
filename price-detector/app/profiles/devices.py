"""Device presets used to build Playwright browser contexts.

These mirror Playwright's built-in device descriptors but are kept here so the
engine has no hard dependency on a specific Playwright version's device table.
"""
from __future__ import annotations

DEVICE_PRESETS: dict[str, dict] = {
    "desktop": {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1366, "height": 900},
        "device_scale_factor": 1,
        "is_mobile": False,
        "has_touch": False,
    },
    "mobile": {
        "user_agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
        ),
        "viewport": {"width": 390, "height": 844},
        "device_scale_factor": 3,
        "is_mobile": True,
        "has_touch": True,
    },
}


def device_context_kwargs(device: str) -> dict:
    preset = DEVICE_PRESETS.get(device, DEVICE_PRESETS["desktop"])
    return dict(preset)
