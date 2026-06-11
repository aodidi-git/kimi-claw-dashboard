from app.engine.matching import match_key
from app.models import RawListing


def _rl(**kw):
    base = dict(external_id=None, section=None, row=None, quantity=None,
               list_price=10.0, fees=None, all_in_price=10.0)
    base.update(kw)
    return RawListing(**base)


def test_external_id_preferred():
    a = _rl(external_id="L1", section="100", row="A", quantity=2)
    b = _rl(external_id="L1", section="DIFFERENT", row="Z", quantity=9)
    assert match_key(a) == match_key(b) == "id:L1"


def test_composite_key_normalizes():
    a = _rl(section="Floor  1", row="A", quantity=2)
    b = _rl(section="floor 1", row="a", quantity=2)
    assert match_key(a) == match_key(b)


def test_composite_key_distinguishes():
    a = _rl(section="100", row="A", quantity=2)
    b = _rl(section="100", row="B", quantity=2)
    assert match_key(a) != match_key(b)
