import csv
import io

from app.web.routes import _run_to_csv

# Cells keyed by *string* profile ids, mimicking a JSON round-trip of summary_json.
SUMMARY = {
    "profiles": [
        {"id": 1, "name": "desktop-fresh", "is_baseline": True},
        {"id": 2, "name": "mobile-fresh", "is_baseline": False},
    ],
    "rows": [
        {
            "section": "100", "row": "A", "quantity": 2,
            "cells": {
                "1": {"profile_id": 1, "all_in_price": 100.0, "delta_pct": None},
                "2": {"profile_id": 2, "all_in_price": 115.0, "delta_pct": 15.0},
            },
            "cheapest_profile_id": 1, "cheapest_price": 100.0,
        }
    ],
}


def test_run_to_csv_has_header_and_values():
    text = _run_to_csv(SUMMARY)
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == [
        "section", "row", "quantity",
        "desktop-fresh all_in", "desktop-fresh delta_pct",
        "mobile-fresh all_in", "mobile-fresh delta_pct",
        "cheapest_profile", "cheapest_price",
    ]
    data = rows[1]
    assert data[0:3] == ["100", "A", "2"]
    assert data[3] == "100.00"        # baseline all-in
    assert data[5] == "115.00"        # mobile all-in
    assert data[6] == "15.0"          # mobile delta_pct
    assert data[7] == "desktop-fresh"
    assert data[8] == "100.00"


def test_run_to_csv_handles_missing_cell():
    summary = {
        "profiles": [{"id": 1, "name": "p1"}, {"id": 9, "name": "blocked"}],
        "rows": [{
            "section": "S", "row": "R", "quantity": 1,
            "cells": {"1": {"profile_id": 1, "all_in_price": 50.0, "delta_pct": None}},
            "cheapest_profile_id": 1, "cheapest_price": 50.0,
        }],
    }
    rows = list(csv.reader(io.StringIO(_run_to_csv(summary))))
    # blocked profile with no cell -> empty all_in/delta columns
    assert rows[1][5] == "" and rows[1][6] == ""
