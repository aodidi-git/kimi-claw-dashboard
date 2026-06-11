from app.adapters.registry import get_adapter_for_url, site_for_url
from app.adapters.vividseats import VividSeatsAdapter
from app.models import RawListing


def test_registry_routes_vividseats():
    assert site_for_url("https://www.vividseats.com/foo/event/123") == "vividseats"
    assert isinstance(get_adapter_for_url("https://vividseats.com/e/1"), VividSeatsAdapter)


def test_checkout_url():
    vs = VividSeatsAdapter()
    rl = RawListing(external_id="v9", section="A", row="1", quantity=2,
                    list_price=10.0, fees=None, all_in_price=10.0)
    assert "listingId=v9" in vs.checkout_url(rl, "https://vividseats.com/e/1")
