"""Runtime settings for the price-discrimination detector."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PDD_", env_file=".env", extra="ignore")

    # Where all mutable runtime state lives (db, captures, storage states).
    data_dir: Path = BASE_DIR / "data"

    # Browser behaviour.
    headed: bool = False  # default comparison runs are headless
    headed_retry_on_block: bool = True  # re-fetch a blocked profile in headed mode
    concurrency_cap: int = 4  # max simultaneous profile fetches per trial
    nav_timeout_ms: int = 25_000
    jitter_ms: int = 400  # randomized pause between context creations

    # Significance: a profile delta counts only if |delta| > k * noise_floor.
    significance_k: float = 2.0

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def storage_states_dir(self) -> Path:
        return self.data_dir / "storage_states"

    @property
    def user_data_root(self) -> Path:
        return self.data_dir / "user_data"

    @property
    def captures_dir(self) -> Path:
        return self.data_dir / "captures"

    def ensure_dirs(self) -> None:
        for d in (
            self.data_dir,
            self.storage_states_dir,
            self.user_data_root,
            self.captures_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
