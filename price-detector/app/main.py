"""FastAPI application entry point."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import db
from .config import settings
from .engine.browser import BrowserManager
from .engine.runner import ComparisonRunner
from .profiles import manager as profile_manager


class AppState:
    browser: BrowserManager
    runner: ComparisonRunner
    tasks: dict[int, asyncio.Task]


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    db.init_db()
    profile_manager.seed_defaults()
    state.browser = BrowserManager()
    state.runner = ComparisonRunner(state.browser)
    state.tasks = {}
    try:
        yield
    finally:
        # Cancel any in-flight runs and shut the browser down.
        for task in state.tasks.values():
            task.cancel()
        await state.browser.stop()


app = FastAPI(title="Ticket Price-Discrimination Detector", lifespan=lifespan)

from .web import routes  # noqa: E402  (import after app exists)

routes.register(app, state)
