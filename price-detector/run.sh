#!/usr/bin/env bash
# Launch the price-discrimination detector locally.
#
# First time only:
#   python -m venv .venv && source .venv/bin/activate
#   pip install -r requirements.txt
#   playwright install chromium
#
set -euo pipefail
cd "$(dirname "$0")"
exec uvicorn app.main:app --reload --port "${PORT:-8400}"
