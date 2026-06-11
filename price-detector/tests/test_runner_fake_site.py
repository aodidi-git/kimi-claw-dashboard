"""Full-stack engine test against the local fake site.

Skipped automatically if Playwright's Chromium isn't installed, so the offline
unit suite still runs everywhere. This test never touches StubHub.
"""
import asyncio
import socket
import threading
import time

import pytest

playwright = pytest.importorskip("playwright")
from playwright.async_api import async_playwright  # noqa: E402

import uvicorn  # noqa: E402

from app import db  # noqa: E402
from app.adapters import registry  # noqa: E402
from app.adapters.stubhub import StubHubAdapter  # noqa: E402
from app.engine.browser import BrowserManager  # noqa: E402
from app.engine.runner import ComparisonRunner  # noqa: E402
from app.engine import stats  # noqa: E402
from app.profiles import manager  # noqa: E402


class FakeSiteAdapter(StubHubAdapter):
    site_name = "fakesite"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "127.0.0.1" in url or "localhost" in url


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def fake_server():
    from tests.fake_site.server import app as fake_app

    port = _free_port()
    config = uvicorn.Config(fake_app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def _chromium_available() -> bool:
    try:
        async def _check():
            pw = await async_playwright().start()
            try:
                b = await pw.chromium.launch(headless=True)
                await b.close()
                return True
            finally:
                await pw.stop()
        return asyncio.get_event_loop().run_until_complete(_check())
    except Exception:
        return False


def test_runner_detects_mobile_markup(fresh_db, fake_server, monkeypatch):
    if not _chromium_available():
        pytest.skip("Chromium not installed (run: playwright install chromium)")

    monkeypatch.setattr(registry, "ADAPTERS", [FakeSiteAdapter])

    event_url = f"{fake_server}/event/1"
    event_id = db.upsert_event("fakesite", event_url)
    run_id = db.create_run(event_id, trials=2)

    browser = BrowserManager()
    runner = ComparisonRunner(browser)

    async def _go():
        await runner.run(run_id)
        await browser.stop()

    asyncio.get_event_loop().run_until_complete(_go())

    run = db.query_one("SELECT * FROM runs WHERE id=?", (run_id,))
    assert run["status"] == "done"

    summary = stats.build_summary(run_id)
    assert summary.rows, "expected matched listings"
    # The fake site marks mobile up 15%; desktop-fresh is baseline & cheapest.
    profs = {p.name: p for p in manager.all_profiles()}
    mobile_id = profs["mobile-fresh"].id
    found_sig = any(
        row["cells"].get(mobile_id, {}).get("significant") for row in summary.rows
    )
    assert found_sig, "expected a significant mobile markup to be detected"
