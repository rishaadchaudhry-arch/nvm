# NVM backend regression tests: look, history, search, places, traditions, devices/upvotes, admin, narration
import re
import time
import pytest
import requests

from nvm_test_env import ADMIN_EMAIL, ADMIN_PW, BASE_URL

LOCAL = "http://localhost:8001"  # only used to simulate distinct client IPs for the 5-upvote rule
META = re.compile(r"(the sources? (do|does) not|not mentioned in|no source|sources provided|according to the sources)", re.I)
ERA_KEYS = None
CREATED = []


def nom_sleep():
    time.sleep(1.3)


@pytest.fixture(scope="session")
def s():
    return requests.Session()


@pytest.fixture(scope="session")
def admin_token(s):
    r = s.post(f"{BASE_URL}/api/auth/token", data={"username": ADMIN_EMAIL, "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def lajpat(s):
    r = s.get(f"{BASE_URL}/api/look", params={"lat": 28.5677, "lng": 77.2433}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def validate_history(h):
    assert len(h["eras"]) == 8
    ids = {x["id"] for x in h["sources"]}
    problems = []
    for e in h["eras"]:
        assert e["scope"] in {"spot", "street", "neighbourhood", "city", "region", "none"}, e
        if e["text"]:
            if not e["sources"]:
                problems.append(f"{e['key']}: text without sources")
            if not set(e["sources"]) <= ids:
                problems.append(f"{e['key']}: unknown source ids {e['sources']}")
            if META.search(e["text"]):
                problems.append(f"{e['key']}: meta phrase: {e['text'][:120]}")
        else:
            if e["sources"]:
                problems.append(f"{e['key']}: empty text but sources")
    for f in h.get("did_you_know", []):
        if not f["sources"] or not set(f["sources"]) <= ids:
            problems.append(f"dyk uncited: {f['text'][:80]}")
    for t in (h["summary"], h["then_now"]):
        if t and META.search(t):
            problems.append(f"meta phrase in summary/then_now: {t[:120]}")
    return problems


# --- basics ---
class TestBasics:
    def test_eras(self, s):
        r = s.get(f"{BASE_URL}/api/eras")
        assert r.status_code == 200
        keys = [e["key"] for e in r.json()]
        assert len(keys) == 8, keys

    def test_config(self, s):
        r = s.get(f"{BASE_URL}/api/config")
        assert r.json() == {"upvote_threshold": 5, "story_radius_m": 150}


# --- look / places ---
class TestLook:
    def test_look_no_heading(self, lajpat):
        p = lajpat["place"]
        assert p["key"] and p["title"]
        assert abs(lajpat["facing"]["lat"] - 28.5677) < 1e-6
        print("LOOK lajpat:", p["title"], "|", p["subtitle"], "| history?", lajpat["history"] is not None)

    def test_look_with_heading_offsets(self, s):
        nom_sleep()
        r = s.get(f"{BASE_URL}/api/look", params={"lat": 28.6558, "lng": 77.2297, "heading": 90}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["facing"]["lng"] > 77.2297 and abs(d["facing"]["lat"] - 28.6558) < 1e-4
        print("LOOK old delhi:", d["place"]["title"], "|", d["place"]["subtitle"])

    def test_look_rural(self, s):
        nom_sleep()
        r = s.get(f"{BASE_URL}/api/look", params={"lat": 26.9520, "lng": 75.4980}, timeout=30)
        assert r.status_code == 200, r.text
        print("LOOK rural:", r.json()["place"]["title"], "|", r.json()["place"]["subtitle"])

    def test_look_invalid(self, s):
        assert s.get(f"{BASE_URL}/api/look", params={"lat": 200, "lng": 1}).status_code == 422

    def test_place_detail_and_bulk(self, s, lajpat):
        k = lajpat["place"]["key"]
        r = s.get(f"{BASE_URL}/api/places/{k}")
        assert r.status_code == 200 and r.json()["key"] == k
        r = s.get(f"{BASE_URL}/api/places", params={"keys": f"{k},nope-123"})
        assert [p["key"] for p in r.json()] == [k]
        assert s.get(f"{BASE_URL}/api/places/nope-xyz-123").status_code == 404


# --- search ---
class TestSearch:
    def test_search_ok(self, s):
        nom_sleep()
        r = s.get(f"{BASE_URL}/api/search", params={"q": "Nai Sarak Delhi"}, timeout=30)
        assert r.status_code == 200, r.text
        res = r.json()
        assert len(res) > 0
        print("SEARCH:", [(x.get("title"), x.get("country")) for x in res[:5]])
        assert all((x.get("country") or "India") == "India" for x in res)

    def test_search_short(self, s):
        assert s.get(f"{BASE_URL}/api/search", params={"q": "a"}).status_code == 422


# --- history ---
class TestHistory:
    def test_history_cached_valid(self, s, lajpat):
        k = lajpat["place"]["key"]
        t = time.time()
        r = s.get(f"{BASE_URL}/api/history/{k}", timeout=120)
        el = time.time() - t
        assert r.status_code == 200, r.text
        h = r.json()
        print(f"HISTORY {k} {el:.1f}s has_records={h['has_records']} sources={len(h['sources'])}")
        for e in h["eras"]:
            print("  ", e["key"], e["scope"], e["sources"], e["text"][:90])
        probs = validate_history(h)
        assert not probs, probs
        t = time.time()
        assert s.get(f"{BASE_URL}/api/history/{k}").status_code == 200
        assert time.time() - t < 3

    def test_history_unknown_404(self, s):
        assert s.get(f"{BASE_URL}/api/history/unknown-key-zz").status_code == 404

    def test_history_fresh_build_old_delhi(self, s):
        nom_sleep()
        d = s.get(f"{BASE_URL}/api/look", params={"lat": 28.6558, "lng": 77.2297}, timeout=30).json()
        k = d["place"]["key"]
        t = time.time()
        r = s.get(f"{BASE_URL}/api/history/{k}", timeout=180)
        el = time.time() - t
        assert r.status_code == 200, r.text
        h = r.json()
        print(f"BUILD {k} {el:.1f}s has_records={h['has_records']} summary={h['summary'][:150]}")
        for e in h["eras"]:
            print("  ", e["key"], e["scope"], e["sources"], e["text"][:120])
        probs = validate_history(h)
        assert not probs, probs


# --- traditions / devices / upvotes ---
class TestTraditions:
    def test_create_validation(self, s, lajpat):
        k = lajpat["place"]["key"]
        assert s.post(f"{BASE_URL}/api/traditions", json={"place_key": "nope-xyz-123", "author": "TEST_a", "title": "TEST_t", "body": "long enough body"}).status_code == 404
        assert s.post(f"{BASE_URL}/api/traditions", json={"place_key": k, "author": "   ", "title": "TEST_t", "body": "long enough body"}).status_code == 422
        assert s.post(f"{BASE_URL}/api/traditions", json={"place_key": k, "author": "TEST_a", "title": "TEST_t", "body": "short"}).status_code == 422

    def test_create_list_upvote_verify(self, s, lajpat):
        k = lajpat["place"]["key"]
        r = s.post(f"{BASE_URL}/api/traditions", json={"place_key": k, "author": "TEST_author", "title": "TEST_story", "body": "TEST_ an old banyan stood here once."})
        assert r.status_code == 200, r.text
        t = r.json()
        CREATED.append(t["id"])
        assert t["status"] == "pending" and t["lat"] == lajpat["place"]["lat"]
        for f in ("voters", "voter_ips", "location"):
            assert f not in t
        lst = s.get(f"{BASE_URL}/api/traditions", params={"place_key": k}).json()
        assert any(x["id"] == t["id"] for x in lst)
        assert all("voters" not in x and "location" not in x for x in lst)
        # upvote: bad token, then good token, duplicate
        assert s.post(f"{BASE_URL}/api/traditions/{t['id']}/upvote", json={"device_token": "garbage-token-123"}).status_code == 401
        dev = s.post(f"{BASE_URL}/api/devices").json()["device_token"]
        r = s.post(f"{BASE_URL}/api/traditions/{t['id']}/upvote", json={"device_token": dev})
        assert r.status_code == 200 and r.json()["upvotes"] == 1 and r.json()["has_voted"] is True
        assert "voters" not in r.json()
        assert s.post(f"{BASE_URL}/api/traditions/{t['id']}/upvote", json={"device_token": dev}).status_code == 409
        # 4 more votes from simulated distinct IPs (localhost, XFF client entry) -> community verified
        last = None
        for i in range(4):
            d2 = requests.post(f"{LOCAL}/api/devices", headers={"X-Forwarded-For": f"10.9.{i}.1, 10.0.0.1, 10.0.0.2"}).json()["device_token"]
            last = requests.post(f"{LOCAL}/api/traditions/{t['id']}/upvote", json={"device_token": d2},
                                 headers={"X-Forwarded-For": f"10.9.{i}.1, 10.0.0.1, 10.0.0.2"})
            assert last.status_code == 200, last.text
        assert last.json()["status"] == "verified" and last.json()["verified_by"] == "community"
        near = s.get(f"{BASE_URL}/api/traditions", params={"status": "verified", "lat": lajpat["place"]["lat"] + 0.0005, "lng": lajpat["place"]["lng"]}).json()
        assert any(x["id"] == t["id"] for x in near)
        far = s.get(f"{BASE_URL}/api/traditions", params={"status": "verified", "lat": lajpat["place"]["lat"] + 0.01, "lng": lajpat["place"]["lng"]}).json()
        assert not any(x["id"] == t["id"] for x in far)


# --- admin ---
class TestAdmin:
    def test_bad_login(self, s):
        assert s.post(f"{BASE_URL}/api/auth/token", data={"username": ADMIN_EMAIL, "password": "wrong"}).status_code == 401

    def test_admin_requires_auth(self, s):
        assert s.get(f"{BASE_URL}/api/admin/traditions").status_code == 401
        assert s.delete(f"{BASE_URL}/api/admin/history/unknown-key-zz").status_code == 401

    def test_moderate(self, s, admin_token, lajpat):
        h = {"Authorization": f"Bearer {admin_token}"}
        assert s.get(f"{BASE_URL}/api/admin/me", headers=h).json()["email"] == ADMIN_EMAIL
        r = s.post(f"{BASE_URL}/api/traditions", json={"place_key": lajpat["place"]["key"], "author": "TEST_admin", "title": "TEST_admin story", "body": "TEST_ body for admin verify"})
        tid = r.json()["id"]
        CREATED.append(tid)
        q = s.get(f"{BASE_URL}/api/admin/traditions", headers=h).json()
        assert any(x["id"] == tid for x in q)
        assert all("voters" not in x for x in q)
        r = s.post(f"{BASE_URL}/api/admin/traditions/{tid}/moderate", json={"action": "verify"}, headers=h)
        assert r.status_code == 200 and r.json()["status"] == "verified" and r.json()["verified_by"] == "admin"
        assert s.post(f"{BASE_URL}/api/admin/traditions/nope/moderate", json={"action": "verify"}, headers=h).status_code == 404
        assert s.delete(f"{BASE_URL}/api/admin/history/unknown-key-zz", headers=h).json() == {"deleted": 0}


# --- narration ---
class TestNarration:
    def test_narrate(self, s, lajpat):
        k = lajpat["place"]["key"]
        s.get(f"{BASE_URL}/api/history/{k}", timeout=120)  # ensure built (xdist may run this before TestHistory)
        r = s.post(f"{BASE_URL}/api/history/{k}/narrate", timeout=90)
        assert r.status_code == 200, r.text
        a = s.get(BASE_URL + r.json()["audio_url"], timeout=30)
        assert a.status_code == 200 and a.headers["content-type"].startswith("audio/mpeg") and len(a.content) > 5000

    def test_narrate_404(self, s):
        assert s.post(f"{BASE_URL}/api/history/unknown-key-zz/narrate").status_code == 404
        assert s.get(f"{BASE_URL}/api/tts/{'0'*64}.mp3").status_code == 404
