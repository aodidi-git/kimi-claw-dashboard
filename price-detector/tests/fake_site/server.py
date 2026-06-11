"""A tiny fake ticketing site for deterministic end-to-end engine tests.

Serves an event page that fetches /api/listings via XHR. The listings endpoint
deliberately *discriminates*: mobile user-agents and requests carrying a
"returning" cookie get marked-up prices. This lets the runner/matching/stats
pipeline be tested fully offline, without ever touching StubHub.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI()

_PAGE = """<!doctype html><html><head><title>Fake Event</title></head>
<body><div id="grid">loading</div>
<script>
fetch('/api/listings').then(r=>r.json()).then(d=>{
  document.getElementById('grid').textContent = JSON.stringify(d).slice(0,40);
});
</script></body></html>"""

# Base listings; prices are per-ticket list prices.
_BASE = [
    {"listingId": "L1", "sectionName": "100", "row": "A", "quantity": 2, "listPrice": 100.0, "fees": 20.0},
    {"listingId": "L2", "sectionName": "200", "row": "B", "quantity": 2, "listPrice": 80.0, "fees": 16.0},
    {"listingId": "L3", "sectionName": "300", "row": "C", "quantity": 4, "listPrice": 50.0, "fees": 10.0},
]


@app.get("/event/{event_id}", response_class=HTMLResponse)
async def event_page(event_id: str):
    return _PAGE


@app.get("/api/listings")
async def listings(request: Request):
    ua = request.headers.get("user-agent", "").lower()
    is_mobile = "iphone" in ua or "mobile" in ua or "android" in ua
    is_returning = "returning" in request.cookies or request.cookies.get("visits", "0") != "0"

    markup = 1.0
    if is_mobile:
        markup *= 1.15        # mobile shoppers see 15% higher list prices
    if is_returning:
        markup *= 1.10        # returning shoppers see a further 10% "urgency" bump

    out = []
    for item in _BASE:
        lp = round(item["listPrice"] * markup, 2)
        fees = round(item["fees"] * markup, 2)
        out.append({
            **item,
            "listPrice": lp,
            "fees": fees,
            "totalPrice": round(lp + fees, 2),
        })
    return JSONResponse({"items": out})
