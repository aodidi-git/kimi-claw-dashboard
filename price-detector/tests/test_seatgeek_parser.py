import json
from pathlib import Path

from app.adapters.extract import parse_api_payloads
from app.adapters.registry import get_adapter_for_url, site_for_url
from app.adapters.seatgeek import SeatGeekAdapter
from app.models import RawListing

FIX = Path(__file__).parent / "fixtures"


def test_registry_routes_seatgeek_and_stubhub():
    assert site_for_url("https://www.seatgeek.com/foo/event/123") == "seatgeek"
    assert site_for_url("https://www.stubhub.com/foo/event/123") == "stubhub"
    assert site_for_url("https://example.com/x") is None
    assert isinstance(get_adapter_for_url("https://seatgeek.com/e/1"), SeatGeekAdapter)


def test_parse_seatgeek_verbose_and_compact():
    data = json.loads((FIX / "seatgeek_listings_api.json").read_text())
    listings = parse_api_payloads([data])
    assert len(listings) == 3
    by_id = {l.external_id: l for l in listings}

    # verbose form, explicit display_price = all-in
    a = by_id["sg-1001"]
    assert a.section == "Lower 102" and a.row == "8" and a.quantity == 2
    assert a.list_price == 120.0 and a.fees == 30.0 and a.all_in_price == 150.0

    # compact single-letter form
    b = by_id["sg-1002"]
    assert b.section == "Upper 305" and b.row == "C" and b.quantity == 4
    assert b.list_price == 45.0 and b.all_in_price == 56.0

    # only display_price present -> all_in set, list_price falls back to None
    c = by_id["sg-1003"]
    assert c.all_in_price == 310.0


def test_checkout_url_format():
    sg = SeatGeekAdapter()
    rl = RawListing(external_id="sg-1", section="A", row="1", quantity=2,
                    list_price=10.0, fees=None, all_in_price=10.0)
    assert "listing_id=sg-1" in sg.checkout_url(rl, "https://seatgeek.com/e/1")
