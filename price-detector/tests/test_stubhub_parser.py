import json
from pathlib import Path

from app.adapters.stubhub import (
    extract_event_id,
    is_block_html,
    parse_api_payloads,
    parse_embedded_state,
)

FIX = Path(__file__).parent / "fixtures"


def test_parse_api_payloads_extracts_listings_with_fees():
    data = json.loads((FIX / "stubhub_listings_api.json").read_text())
    listings = parse_api_payloads([data])
    assert len(listings) == 3
    by_id = {l.external_id: l for l in listings}

    l1 = by_id["900001"]
    assert l1.section == "Floor 1"
    assert l1.row == "5"
    assert l1.quantity == 2
    assert l1.list_price == 250.0
    assert l1.fees == 62.5
    assert l1.all_in_price == 312.5

    # all_in computed from list + fees when not provided
    l2 = by_id["900002"]
    assert l2.all_in_price == 175.0

    # money object form
    l3 = by_id["900003"]
    assert l3.list_price == 65.0


def test_parse_embedded_state_reads_next_data():
    payload = {"props": {"listings": [
        {"listingId": "5", "sectionName": "X", "row": "1", "quantity": 2, "listPrice": 10.0}
    ]}}
    html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script></html>'
    listings = parse_embedded_state(html)
    assert len(listings) == 1
    assert listings[0].external_id == "5"
    assert listings[0].list_price == 10.0


def test_block_detection():
    html = (FIX / "datadome_block.html").read_text()
    assert is_block_html(html) is True
    assert is_block_html("<html>normal page</html>") is False


def test_extract_event_id():
    assert extract_event_id("https://www.stubhub.com/foo/event/123456/") == "123456"
    assert extract_event_id("https://www.stubhub.com/foo-bar-tickets-7654321/") == "7654321"
