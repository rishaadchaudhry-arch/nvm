"""Reading present-day OpenStreetMap features into short, readable kinds."""
import sys
import types

sys.modules.setdefault("httpx", types.SimpleNamespace(AsyncClient=object, Timeout=lambda **k: None))
import osm_today  # noqa: E402


def test_kinds_read_like_a_person_would_say_them():
    k = osm_today.kind_of
    assert k({"shop": "jewelry"}) == "jewellery shop"
    assert k({"shop": "confectionery"}) == "sweet shop"
    assert k({"amenity": "place_of_worship", "religion": "sikh"}) == "gurdwara"
    assert k({"amenity": "restaurant", "cuisine": "mughlai;indian"}) == "mughlai restaurant"
    assert k({"amenity": "fast_food"}) == "eatery"
    assert k({"railway": "station", "station": "subway"}) == "metro station"
    assert k({"highway": "residential"}) is None


def test_record_needs_a_place_and_a_kind():
    el = {"type": "node", "id": 1, "lat": 28.65, "lon": 77.23, "tags": {"shop": "jewelry", "name": "Gulab Singh Johri Mal", "phone": "x"}}
    rec = osm_today.to_record(el)
    assert rec["kind"] == "jewellery shop" and rec["name"] == "Gulab Singh Johri Mal" and "phone" not in rec["tags"]
    assert osm_today.to_record({"type": "node", "id": 2, "tags": {"shop": "books"}}) is None
