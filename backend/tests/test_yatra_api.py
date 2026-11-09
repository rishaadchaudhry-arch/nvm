# Yatra API regression tests: places, nearby, search, detail, timeline (LLM), trivia, narration (TTS)
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SLUGS = {"taj-mahal", "hampi", "red-fort", "mysore-palace", "konark-sun-temple",
         "khajuraho", "qutub-minar", "golden-temple"}


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# Places list
def test_list_places(s):
    r = s.get(f"{API}/places", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert SLUGS.issubset({p["slug"] for p in data})
    assert all("_id" not in p for p in data)
    names = [p["name"] for p in data]
    assert names == sorted(names)


# Nearby sorted by distance
def test_nearby_sorted(s):
    r = s.get(f"{API}/places/nearby", params={"lat": 28.6, "lng": 77.2}, timeout=30)
    assert r.status_code == 200
    data = r.json()
    d = [p["distance_km"] for p in data]
    assert d == sorted(d)
    assert data[0]["slug"] in ("red-fort", "qutub-minar")
    assert "_id" not in data[0]


def test_nearby_missing_params(s):
    assert s.get(f"{API}/places/nearby", timeout=30).status_code == 422


# Search
def test_search_delhi(s):
    r = s.get(f"{API}/places/search", params={"q": "delhi"}, timeout=30)
    assert r.status_code == 200
    assert {p["slug"] for p in r.json()} == {"red-fort", "qutub-minar"}


def test_search_agra(s):
    r = s.get(f"{API}/places/search", params={"q": "Agra"}, timeout=30)
    assert [p["slug"] for p in r.json()] == ["taj-mahal"]


def test_search_regex_safe(s):
    r = s.get(f"{API}/places/search", params={"q": ".*"}, timeout=30)
    assert r.status_code == 200 and r.json() == []


def test_search_empty_q(s):
    assert s.get(f"{API}/places/search", params={"q": ""}, timeout=30).status_code == 422


# Detail
def test_place_detail(s):
    r = s.get(f"{API}/places/taj-mahal", timeout=30)
    assert r.status_code == 200
    p = r.json()
    assert p["name"] == "Taj Mahal" and p["city"] == "Agra"


def test_place_404(s):
    assert s.get(f"{API}/places/nope-xyz", timeout=30).status_code == 404
    assert s.get(f"{API}/places/nope-xyz/timeline", timeout=30).status_code == 404
    assert s.get(f"{API}/places/nope-xyz/trivia", timeout=30).status_code == 404


# Timeline (LLM, cached)
def test_timeline_structure_and_cache(s):
    r = s.get(f"{API}/places/taj-mahal/timeline", timeout=120)
    assert r.status_code == 200
    t = r.json()
    assert len(t["summary"]) > 20
    assert len(t["events"]) >= 3, f"Looks like fallback timeline: {t}"
    assert t["did_you_know"] != "Fun fact coming soon."
    assert isinstance(t["hotspots"], list) and len(t["hotspots"]) >= 1
    for e in t["events"]:
        assert e["year"] and e["title"] and e["description"]
    r2 = s.get(f"{API}/places/taj-mahal/timeline", timeout=15)
    assert r2.status_code == 200 and r2.json() == t
    assert r2.elapsed.total_seconds() < 5


# Trivia create -> list
def test_trivia_create_and_list(s):
    payload = {"place_id": "x", "author": "TEST_author", "title": "TEST_title",
               "body": "TEST_body local tradition text"}
    r = s.post(f"{API}/places/hampi/trivia", json=payload, timeout=30)
    assert r.status_code == 200
    created = r.json()
    assert created["author"] == "TEST_author" and created["id"]
    lst = s.get(f"{API}/places/hampi/trivia", timeout=30).json()
    assert lst[0]["id"] == created["id"]


def test_trivia_missing_fields(s):
    r = s.post(f"{API}/places/hampi/trivia", json={"author": "TEST_a"}, timeout=30)
    assert r.status_code == 422


def test_trivia_empty_strings_rejected(s):
    # Expected: blank author/title/body should be rejected with 422
    r = s.post(f"{API}/places/hampi/trivia",
               json={"place_id": "x", "author": "", "title": "", "body": ""}, timeout=30)
    assert r.status_code == 422, f"Blank trivia accepted: {r.status_code}"


def test_trivia_unknown_place(s):
    r = s.post(f"{API}/places/nope-xyz/trivia",
               json={"place_id": "x", "author": "a", "title": "b", "body": "cccccccccc"}, timeout=30)
    assert r.status_code == 404


# Narration (TTS)
def test_narrate_and_audio(s):
    r = s.post(f"{API}/places/taj-mahal/narrate", timeout=180)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["audio_url"].startswith("/api/tts/") and data["text"]
    a = s.get(f"{BASE_URL}{data['audio_url']}", timeout=60)
    assert a.status_code == 200
    assert a.headers["content-type"].startswith("audio/mpeg")
    assert len(a.content) > 10000


def test_narrate_404(s):
    assert s.post(f"{API}/places/nope-xyz/narrate", timeout=30).status_code == 404


def test_tts_missing(s):
    assert s.get(f"{API}/tts/doesnotexist.mp3", timeout=30).status_code == 404
