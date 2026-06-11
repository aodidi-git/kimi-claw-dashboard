# Ticket Price-Discrimination Detector

A local research tool that tests whether a ticketing site (StubHub first) shows
**different prices to different shoppers** — mobile vs desktop, logged-in vs
anonymous, returning vs first-time, and by geography/IP — quantifies the
discrepancy per listing, and helps you buy at the lowest observed price via an
**assisted handoff** (it opens a real browser configured as the cheapest profile;
you complete payment yourself).

> ⚠️ Run this locally, on your own machine, against your own sessions. It does
> not bypass CAPTCHAs and does not automate payment. See **Limitations**.

## How it works

For one event, the tool fetches the **same listings under several "profiles"**
at the same moment (to avoid temporal price drift confounding the result), then
matches identical listings across profiles and reports per-listing price deltas.

- **Profiles** = a shopper identity: device (desktop/mobile), persistence
  (fresh vs returning visitor with accumulated cookies), auth (anonymous vs your
  logged-in StubHub session), and an optional proxy (geo/IP).
- **Trials**: each profile is fetched several times so the tool can estimate a
  **noise floor** (how much prices wobble for the *same* profile across trials).
  A profile's delta vs the baseline counts as *significant* only when it exceeds
  `k × noise_floor` — this separates real discrimination from ordinary price
  volatility.
- **Extraction**: StubHub listings are read primarily by intercepting the site's
  internal listings JSON API (stable listing IDs + fee fields), falling back to
  embedded page JSON, then DOM scraping.

## Setup

```bash
cd price-detector
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
./run.sh                      # serves http://127.0.0.1:8400
```

## Usage

1. **Profiles page** — review the default matrix (`desktop-fresh` [baseline],
   `mobile-fresh`, `desktop-returning`, `desktop-logged-in`). Optionally add a
   proxy and assign it to a profile; for the logged-in profile click **Capture**
   to open a browser, log into StubHub, and save your session.
2. **New Run** — paste a StubHub event URL, pick a trial count (≥2 recommended),
   and run. The run page auto-refreshes with a comparison matrix.
3. **Buy here** — click on the cheapest cell to open a real browser configured as
   that profile at the listing; complete payment manually.

## Tests

```bash
pytest                        # offline unit tests always run
                              # the fake-site integration test runs only if
                              # chromium is installed, and never touches StubHub
```

The fake site (`tests/fake_site/`) deliberately marks prices up for mobile and
returning visitors, giving a deterministic end-to-end check of the
runner → matching → stats pipeline.

Use `python scripts/debug_fetch.py <url> --profile desktop-fresh --headed` to
fetch a real page once and dump raw captures under `data/captures/` for parser
development; sanitized copies become fixtures in `tests/fixtures/`.

## Limitations (read these)

- **Bot blocking**: StubHub uses DataDome. Headless fetches are often blocked.
  Realistic fingerprints, headed-mode auto-retry, and polite pacing reduce but do
  **not** eliminate blocks. No CAPTCHA bypass is attempted; blocked profiles are
  surfaced, not worked around. Heavy use risks IP/account bans.
- **Volatility vs discrimination**: prices and inventory change continuously. A
  single-trial difference can be pure noise. The noise-floor test mitigates this
  but the tool reports *observed, statistically-flagged* discrepancies — it does
  not prove causation or intent.
- **Matching**: without exposed listing IDs, section/row/quantity matching can
  mis-pair or miss listings shown to only some profiles (those are reported
  separately).
- **Fees**: listing-page all-in estimates may differ from the final checkout
  total, which we do not automate.
- **Secrets**: proxy credentials and saved session state live in plaintext under
  `data/` (gitignored, local only).
- **ToS/legal**: automated scraping likely violates StubHub's Terms of Service;
  proxies and account automation carry ban and potential legal risk. You are
  responsible for how you use this.

## Architecture

```
app/
  adapters/   site adapter interface + StubHub (registry maps URL -> adapter)
  profiles/   profile CRUD, device presets, login capture
  engine/     browser mgr, runner (concurrent fetches), matching, stats, block detection
  purchase/   assisted-handoff launcher
  web/        FastAPI routes, Jinja2 templates, vendored static assets
```

Adding a site = implement `SiteAdapter` (`app/adapters/base.py`) and register it
in `app/adapters/registry.py`.
