"""Shared data-transfer objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Profile:
    id: int
    name: str
    device: str = "desktop"          # 'desktop' | 'mobile'
    persistence: str = "fresh"       # 'fresh' | 'returning'
    auth: str = "anon"               # 'anon' | 'logged_in'
    proxy_id: Optional[int] = None
    storage_state_path: Optional[str] = None
    user_data_dir: Optional[str] = None
    enabled: bool = True
    is_baseline: bool = False
    # Hydrated from the proxies table when present:
    proxy_server: Optional[str] = None
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None
    proxy_geo_hint: Optional[str] = None


@dataclass
class RawListing:
    external_id: Optional[str]
    section: Optional[str]
    row: Optional[str]
    quantity: Optional[int]
    list_price: Optional[float]
    fees: Optional[float]
    all_in_price: Optional[float]
    currency: str = "USD"
    listing_url: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class FetchResult:
    listings: list[RawListing] = field(default_factory=list)
    extraction_method: str = "none"   # 'api_intercept'|'embedded_json'|'dom'|'none'
    blocked: bool = False
    block_reason: Optional[str] = None
    event_meta: Optional[dict] = None


@dataclass
class PriceCell:
    """A profile's best (lowest all-in) price for one listing in a run."""
    profile_id: int
    profile_name: str
    all_in_price: Optional[float]
    list_price: Optional[float]
    fees: Optional[float]
    listing_url: Optional[str]
    delta_abs: Optional[float] = None
    delta_pct: Optional[float] = None
    significant: bool = False


@dataclass
class ListingRow:
    listing_id: int
    section: Optional[str]
    row: Optional[str]
    quantity: Optional[int]
    cells: dict[int, PriceCell]                 # profile_id -> cell
    cheapest_profile_id: Optional[int] = None
    cheapest_price: Optional[float] = None


@dataclass
class RunSummary:
    run_id: int
    baseline_profile_id: Optional[int]
    profiles: list[dict] = field(default_factory=list)   # id/name/device/auth/...
    rows: list[dict] = field(default_factory=list)       # serialized ListingRow
    unmatched: list[dict] = field(default_factory=list)
    blocked_profiles: list[str] = field(default_factory=list)
    significant_count: int = 0
    max_savings_abs: float = 0.0
    max_savings_pct: float = 0.0
    cheapest_profile_name: Optional[str] = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "baseline_profile_id": self.baseline_profile_id,
            "profiles": self.profiles,
            "rows": self.rows,
            "unmatched": self.unmatched,
            "blocked_profiles": self.blocked_profiles,
            "significant_count": self.significant_count,
            "max_savings_abs": self.max_savings_abs,
            "max_savings_pct": self.max_savings_pct,
            "cheapest_profile_name": self.cheapest_profile_name,
            "notes": self.notes,
        }
