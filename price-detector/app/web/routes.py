"""All HTTP routes, registered against the FastAPI app + shared state."""
from __future__ import annotations

import asyncio
import csv
import io
import json
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import db
from ..adapters.registry import get_adapter_for_url, site_for_url
from ..profiles import login_capture
from ..profiles import manager
from .sparkline import sparkline_svg

_HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))


def _cell(row: dict, pid: int) -> dict | None:
    """Cell lookup tolerant of int vs str profile-id keys (JSON round-trips them)."""
    cells = row.get("cells", {})
    return cells.get(pid) or cells.get(str(pid))


def _run_to_csv(summary: dict) -> str:
    """Flatten a run summary's comparison matrix into CSV text."""
    profiles = summary.get("profiles", [])
    buf = io.StringIO()
    w = csv.writer(buf)
    header = ["section", "row", "quantity"]
    for p in profiles:
        header += [f"{p['name']} all_in", f"{p['name']} delta_pct"]
    header += ["cheapest_profile", "cheapest_price"]
    w.writerow(header)

    prof_by_id = {p["id"]: p for p in profiles}
    for row in summary.get("rows", []):
        out = [row.get("section"), row.get("row"), row.get("quantity")]
        for p in profiles:
            c = _cell(row, p["id"])
            out.append("" if not c or c.get("all_in_price") is None else f"{c['all_in_price']:.2f}")
            out.append("" if not c or c.get("delta_pct") is None else f"{c['delta_pct']:.1f}")
        cheapest = prof_by_id.get(row.get("cheapest_profile_id"))
        out.append(cheapest["name"] if cheapest else "")
        cp = row.get("cheapest_price")
        out.append("" if cp is None else f"{cp:.2f}")
        w.writerow(out)
    return buf.getvalue()


def _build_trends(parsed_runs: list[dict]) -> list[dict]:
    """Per-event 'max savings %' trend across its completed runs.

    Shows whether an observed price gap is consistent over time (a stronger
    discrimination signal) or a one-off. Only events with >=2 completed runs
    are included.
    """
    by_event: dict[int, list[dict]] = {}
    for r in parsed_runs:
        if r.get("status") == "done" and r.get("summary") and "rows" in r["summary"]:
            by_event.setdefault(r["event_id"], []).append(r)

    trends = []
    for runs in by_event.values():
        runs = sorted(runs, key=lambda r: r["id"])  # chronological
        if len(runs) < 2:
            continue
        values = [float(r["summary"].get("max_savings_pct") or 0.0) for r in runs]
        label = runs[-1].get("event_name") or runs[-1].get("event_url") or "event"
        trends.append({
            "label": label[:55],
            "values": values,
            "latest": values[-1],
            "runs": len(runs),
            "svg": sparkline_svg(values),
        })
    return trends


def register(app: FastAPI, state) -> None:
    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        profiles = manager.all_profiles()
        recent = db.query(
            "SELECT r.*, e.url AS event_url, e.name AS event_name "
            "FROM runs r JOIN events e ON r.event_id=e.id ORDER BY r.id DESC LIMIT 10"
        )
        return templates.TemplateResponse(
            request, "index.html", {"profiles": profiles, "recent": recent}
        )

    @app.get("/profiles", response_class=HTMLResponse)
    async def profiles_page(request: Request):
        return templates.TemplateResponse(
            request,
            "profiles.html",
            {
                "profiles": manager.all_profiles(),
                "proxies": manager.all_proxies(),
                "capture_status": {
                    p.id: login_capture.status_for(p.id) for p in manager.all_profiles()
                },
            },
        )

    @app.post("/profiles/{profile_id}/toggle")
    async def toggle_profile(profile_id: int, enabled: str = Form("0")):
        manager.set_enabled(profile_id, enabled == "1")
        return RedirectResponse("/profiles", status_code=303)

    @app.post("/profiles/{profile_id}/baseline")
    async def baseline_profile(profile_id: int):
        manager.set_baseline(profile_id)
        return RedirectResponse("/profiles", status_code=303)

    @app.post("/profiles/{profile_id}/proxy")
    async def assign_proxy(profile_id: int, proxy_id: str = Form("")):
        manager.set_proxy(profile_id, int(proxy_id) if proxy_id else None)
        return RedirectResponse("/profiles", status_code=303)

    @app.post("/proxies")
    async def add_proxy(
        label: str = Form(...),
        server: str = Form(...),
        username: str = Form(""),
        password: str = Form(""),
        geo_hint: str = Form(""),
    ):
        manager.add_proxy(label, server, username, password, geo_hint)
        return RedirectResponse("/profiles", status_code=303)

    @app.post("/profiles/{profile_id}/capture-login")
    async def capture_login_route(profile_id: int, login_url: str = Form("")):
        profile = manager.get_profile(profile_id)
        site = "stubhub"
        url = login_url or login_capture.default_login_url(site)
        asyncio.create_task(login_capture.capture_login(profile_id, url))
        return RedirectResponse("/profiles", status_code=303)

    @app.post("/runs")
    async def create_run(event_url: str = Form(...), trials: int = Form(1)):
        site = site_for_url(event_url)
        if site is None:
            return JSONResponse(
                {"error": "No adapter handles this URL. Supported: StubHub, SeatGeek, Vivid Seats."},
                status_code=400,
            )
        event_id = db.upsert_event(site, event_url)
        run_id = _start_run(event_id, max(1, int(trials)))
        return RedirectResponse(f"/runs/{run_id}", status_code=303)

    def _start_run(event_id: int, trials: int) -> int:
        run_id = db.create_run(event_id, trials)
        state.tasks[run_id] = asyncio.create_task(state.runner.run(run_id))
        return run_id

    @app.post("/runs/{run_id}/rerun")
    async def rerun(run_id: int):
        old = db.query_one("SELECT * FROM runs WHERE id=?", (run_id,))
        if old is None:
            return HTMLResponse("Run not found", status_code=404)
        new_id = _start_run(old["event_id"], old["trials"])
        return RedirectResponse(f"/runs/{new_id}", status_code=303)

    @app.get("/runs/{run_id}/export.json")
    async def export_json(run_id: int):
        run = db.query_one("SELECT * FROM runs WHERE id=?", (run_id,))
        if run is None or not run["summary_json"]:
            return JSONResponse({"error": "no completed summary for this run"}, status_code=404)
        return JSONResponse(
            json.loads(run["summary_json"]),
            headers={"Content-Disposition": f'attachment; filename="run_{run_id}.json"'},
        )

    @app.get("/runs/{run_id}/export.csv")
    async def export_csv(run_id: int):
        run = db.query_one("SELECT * FROM runs WHERE id=?", (run_id,))
        if run is None or not run["summary_json"]:
            return PlainTextResponse("no completed summary for this run", status_code=404)
        csv_text = _run_to_csv(json.loads(run["summary_json"]))
        return PlainTextResponse(
            csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="run_{run_id}.csv"'},
        )

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    async def run_detail(request: Request, run_id: int):
        run = db.query_one("SELECT * FROM runs WHERE id=?", (run_id,))
        if run is None:
            return HTMLResponse("Run not found", status_code=404)
        event = db.query_one("SELECT * FROM events WHERE id=?", (run["event_id"],))
        return templates.TemplateResponse(
            request, "run_detail.html", {"run": run, "event": event}
        )

    @app.get("/runs/{run_id}/results", response_class=HTMLResponse)
    async def run_results(request: Request, run_id: int):
        run = db.query_one("SELECT * FROM runs WHERE id=?", (run_id,))
        if run is None:
            return HTMLResponse("Run not found", status_code=404)
        summary = None
        if run["summary_json"]:
            try:
                summary = json.loads(run["summary_json"])
            except json.JSONDecodeError:
                summary = None
        snapshots = db.query(
            "SELECT s.*, p.name AS profile_name FROM snapshots s "
            "JOIN profiles p ON s.profile_id=p.id WHERE s.run_id=? ORDER BY s.id",
            (run_id,),
        )
        return templates.TemplateResponse(
            request,
            "_run_results.html",
            {
                "run": run,
                "summary": summary,
                "snapshots": snapshots,
            },
        )

    @app.get("/history", response_class=HTMLResponse)
    async def history(request: Request):
        runs = db.query(
            "SELECT r.*, e.url AS event_url, e.name AS event_name "
            "FROM runs r JOIN events e ON r.event_id=e.id ORDER BY r.id DESC LIMIT 100"
        )
        parsed = []
        for r in runs:
            d = dict(r)
            if r["summary_json"]:
                try:
                    d["summary"] = json.loads(r["summary_json"])
                except json.JSONDecodeError:
                    d["summary"] = None
            parsed.append(d)
        return templates.TemplateResponse(
            request, "history.html", {"runs": parsed, "trends": _build_trends(parsed)}
        )

    @app.post("/handoff")
    async def handoff(profile_id: int = Form(...), listing_url: str = Form(...)):
        from ..purchase.handoff import launch_handoff

        try:
            info = await launch_handoff(profile_id, listing_url)
        except Exception as exc:  # noqa: BLE001
            return HTMLResponse(
                f'<p class="toast error">Handoff failed: {exc}</p>', status_code=500
            )
        return HTMLResponse(
            f'<p class="toast">Opened a {info["profile"]} browser at the listing. '
            f"Complete payment in that window.</p>"
        )
