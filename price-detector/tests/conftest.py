import importlib

import pytest


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    """Point the app at an isolated temp data dir with a fresh schema."""
    from app.config import settings
    from app import db

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    # Force a new connection bound to the temp db.
    db._conn = None
    db.init_db()
    from app.profiles import manager
    manager.seed_defaults()
    yield db
    db._conn = None
