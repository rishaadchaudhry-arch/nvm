# Yatra v3 API regression (device_token upvote contract): regions/areas/pois, nearby, traditions (community + upvotes), admin auth/moderation/upsert, narration
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@yatra.app"
ADMIN_PASSWORD = "Yatra-a20d244dfc16"
CREATED = []
IPS = []


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def token(s):
    r = s.post(f"{API}/auth/token", data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    if r.status_code != 200:
        pytest.skip("admin login failed")
    return r.json()["access_token"]


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    if CREATED or IPS:
        mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        mc["test_database"].traditions.delete_many({"id": {"$in": CREATED}})
    MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))["test_database"].device_issues.delete_many({"ip": {"$in": IPS}})


def make(s, **kw):
    payload = {"area_slug": "chandni-chowk", "author": "TEST_bot", "title": "TEST story", "body": "A long enough test story body."}
    payload.update(kw)
    r = s.post(f"{API}/traditions", json=payload, timeout=20)
    if r.status_code == 200:
        CREATED.append(r.json()["id"])
    return r


# Content: regions/areas/pois
def test_regions(s):
    d = s.get(f"{API}/regions", timeout=20).json()
    assert len(d) == 6
    assert [r["slug"] for r in d if r["has_stories"]] == ["delhi"]


def test_region_detail(s):
    d = s.get(f"{API}/regions/delhi", timeout=20).json()
    assert d["region"]["slug"] == "delhi"
    assert "chandni-chowk" in {a["slug"] for a in d["areas"]}


def test_area_chandni(s):
    d = s.get(f"{API}/areas/chandni-chowk", timeout=20).json()
    assert len(d["pois"]) == 12
    assert len(d["eras"]) == 7
    assert isinstance(d["did_you_know"], list)
    assert all("voters" not in t for t in d["did_you_know"])


def test_area_taj_empty(s):
    d = s.get(f"{API}/areas/taj-mahal", timeout=20).json()
    assert d["eras"] == [] or d["area"]["eras"] == []


def test_poi_detail(s):
    d = s.get(f"{API}/pois/gurudwara-sis-ganj", timeout=20).json()
    assert d["poi"]["slug"] == "gurudwara-sis-ganj"
    assert d["area"]["slug"] == "chandni-chowk"
    assert d["upvote_threshold"] == 5
    assert len(d["poi"]["eras"]) > 0


def test_pois_by_slugs(s):
    d = s.get(f"{API}/pois", params={"slugs": "gurudwara-sis-ganj,nope-x"}, timeout=20).json()
    assert [p["slug"] for p in d] == ["gurudwara-sis-ganj"]


@pytest.mark.parametrize("path", ["regions/zzz", "areas/zzz", "pois/zzz"])
def test_404s(s, path):
    assert s.get(f"{API}/{path}", timeout=20).status_code == 404


# Nearby
def test_nearby_inside(s):
    d = s.get(f"{API}/nearby", params={"lat": 28.6560, "lng": 77.2312}, timeout=20).json()
    assert d["inside"]["area"]["name"] == "Chandni Chowk"
    dist = [p["distance_m"] for p in d["inside"]["pois"]]
    assert dist == sorted(dist) and len(dist) == 12


def test_nearby_mumbai(s):
    d = s.get(f"{API}/nearby", params={"lat": 19.07, "lng": 72.87}, timeout=20).json()
    assert d["inside"] is None
    assert d["nearest"]["slug"] == "chandni-chowk"


# Traditions validation
def test_tradition_validation(s):
    assert make(s, body="   ").status_code == 422
    assert make(s, body="short").status_code == 422
    assert make(s, author="  ").status_code == 422


def test_tradition_wrong_area_poi(s):
    # find a poi of a different area, if any
    r = make(s, area_slug="taj-mahal", poi_slug="gurudwara-sis-ganj")
    assert r.status_code == 400


# Device tokens + upvote contract (FIX 2). Each test uses its own spoofed X-Forwarded-For so the
# real container IP's 20/hour device quota is not used up (spoofing works: see test_xff_spoof_bypass).
def ip():
    x = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
    IPS.append(x)
    return x


def dev(s, xip):
    r = s.post(f"{API}/devices", headers={"X-Forwarded-For": xip}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["device_token"]


def vote(s, tid, tok, xip):
    return s.post(f"{API}/traditions/{tid}/upvote", json={"device_token": tok}, headers={"X-Forwarded-For": xip}, timeout=20)


def no_voter_fields(items):
    return all("voters" not in t and "voter_ips" not in t for t in items)


def test_device_issue(s):
    tok = dev(s, ip())
    assert isinstance(tok, str) and tok.count(".") == 2


def test_device_rate_limit(s):
    xip = ip()
    codes = [s.post(f"{API}/devices", headers={"X-Forwarded-For": xip}, timeout=20).status_code for _ in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429


def test_upvote_fake_token(s):
    tid = make(s, title="TEST fake tok").json()["id"]
    assert vote(s, tid, "not-a-real-token-xxxxxxxx", ip()).status_code == 401
    assert vote(s, tid, "x", ip()).status_code == 422
    assert s.post(f"{API}/traditions/{tid}/upvote", json={"device_id": "dev-1234567890"}, timeout=20).status_code == 422


def test_upvote_same_device_twice(s):
    tid = make(s, title="TEST dup").json()["id"]
    xip = ip()
    tok = dev(s, xip)
    r1 = vote(s, tid, tok, xip)
    assert r1.status_code == 200 and r1.json()["upvotes"] == 1 and r1.json()["has_voted"] is True
    assert no_voter_fields([r1.json()])
    assert vote(s, tid, tok, xip).status_code == 409


def test_upvote_ip_limit(s):
    tid = make(s, title="TEST ip limit").json()["id"]
    xip = ip()
    for _ in range(3):
        assert vote(s, tid, dev(s, ip()), xip).status_code == 200
    r = vote(s, tid, dev(s, ip()), xip)
    assert r.status_code == 429


def test_upvote_flow_to_verified(s):
    r = make(s, poi_slug="gurudwara-sis-ganj", title="TEST upvote")
    tid = r.json()["id"]
    xa, xb = ip(), ip()
    toks = [dev(s, ip()) for _ in range(6)]
    for i in range(5):
        rr = vote(s, tid, toks[i], xa if i < 3 else xb)
        assert rr.status_code == 200, rr.text
    assert rr.json()["status"] == "verified" and rr.json()["verified_by"] == "community"
    assert vote(s, tid, toks[5], ip()).status_code == 409
    ver = s.get(f"{API}/traditions", params={"status": "verified", "device_token": toks[0]}, timeout=20).json()
    item = next(t for t in ver if t["id"] == tid)
    assert item["has_voted"] is True and no_voter_fields(ver)
    other = s.get(f"{API}/traditions", params={"status": "verified", "device_token": toks[5]}, timeout=20).json()
    assert next(t for t in other if t["id"] == tid)["has_voted"] is False
    poi = s.get(f"{API}/pois/gurudwara-sis-ganj", params={"device_token": toks[0]}, timeout=20).json()
    dyk = next(t for t in poi["did_you_know"] if t["id"] == tid)
    assert dyk["has_voted"] is True and no_voter_fields(poi["did_you_know"] + poi["community"])
    area = s.get(f"{API}/areas/chandni-chowk", params={"device_token": toks[0]}, timeout=20).json()
    assert no_voter_fields(area["did_you_know"])
    near = s.get(f"{API}/nearby", params={"lat": 28.6560, "lng": 77.2312}, timeout=20).json()
    assert no_voter_fields(near["inside"]["did_you_know"])


def test_xff_spoof_bypass(s):
    """SECURITY: a client can choose its own IP via X-Forwarded-For, so one machine reaches 5 votes alone."""
    tid = make(s, title="TEST spoof").json()["id"]
    last = None
    for _ in range(5):
        x = ip()
        last = vote(s, tid, dev(s, x), x)
    assert last.status_code == 409 or last.json()["status"] != "verified", "single client verified a story by spoofing X-Forwarded-For"


def test_upvote_bad(s):
    assert vote(s, "nope", dev(s, ip()), ip()).status_code == 404


def test_pending_list_no_voters(s):
    d = s.get(f"{API}/traditions", params={"status": "pending"}, timeout=20).json()
    assert no_voter_fields(d) and all(t["status"] == "pending" for t in d)


# POI images (FIX 3): distinct per POI, Bhagirath Palace intentionally empty
def test_poi_images(s):
    pois = s.get(f"{API}/areas/chandni-chowk", timeout=20).json()["pois"]
    imgs = {p["slug"]: p["image"] for p in pois}
    bp = [k for k in imgs if "bhagirath" in k]
    assert bp and imgs[bp[0]] == ""
    rest = [v for k, v in imgs.items() if k not in bp]
    assert all(rest) and len(set(rest)) == len(rest)


# Admin
def test_login_wrong(s):
    assert s.post(f"{API}/auth/token", data={"username": ADMIN_EMAIL, "password": "bad"}, timeout=20).status_code == 401


def test_admin_requires_token(s):
    assert s.get(f"{API}/admin/traditions", timeout=20).status_code == 401
    assert s.get(f"{API}/admin/traditions", headers={"Authorization": "Bearer junk"}, timeout=20).status_code == 401


def test_admin_moderate(s, token):
    h = {"Authorization": f"Bearer {token}"}
    tid = make(s, title="TEST mod").json()["id"]
    q = s.get(f"{API}/admin/traditions", headers=h, timeout=20).json()
    assert tid in {t["id"] for t in q} and all("voters" not in t for t in q)
    r = s.post(f"{API}/admin/traditions/{tid}/moderate", json={"action": "verify"}, headers=h, timeout=20)
    assert r.status_code == 200 and r.json()["status"] == "verified" and r.json()["verified_by"] == "admin"
    tid2 = make(s, title="TEST rej").json()["id"]
    r2 = s.post(f"{API}/admin/traditions/{tid2}/moderate", json={"action": "reject"}, headers=h, timeout=20)
    assert r2.json()["status"] == "rejected"
    assert s.post(f"{API}/admin/traditions/{tid2}/moderate", json={"action": "bogus"}, headers=h, timeout=20).status_code == 422
    assert s.post(f"{API}/admin/traditions/nope/moderate", json={"action": "verify"}, headers=h, timeout=20).status_code == 404


def test_admin_upsert_poi(s, token):
    h = {"Authorization": f"Bearer {token}"}
    cur = s.get(f"{API}/pois/gurudwara-sis-ganj", timeout=20).json()["poi"]
    assert s.put(f"{API}/admin/pois/gurudwara-sis-ganj", json=cur, timeout=20).status_code == 401
    r = s.put(f"{API}/admin/pois/gurudwara-sis-ganj", json=cur, headers=h, timeout=20)
    assert r.status_code == 200 and r.json()["slug"] == "gurudwara-sis-ganj"
    bad = {**cur, "area_slug": "nowhere"}
    assert s.put(f"{API}/admin/pois/gurudwara-sis-ganj", json=bad, headers=h, timeout=20).status_code == 404


# Narration
def test_narrate(s):
    r = s.post(f"{API}/pois/gurudwara-sis-ganj/narrate", timeout=90)
    assert r.status_code == 200
    url = r.json()["audio_url"]
    a = s.get(f"{BASE_URL}{url}", timeout=30)
    assert a.status_code == 200 and a.headers["content-type"].startswith("audio/mpeg") and len(a.content) > 1000


def test_tts_404(s):
    assert s.get(f"{API}/tts/{'0'*64}.mp3", timeout=20).status_code == 404
