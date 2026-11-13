# NVM iteration 7: admin history rebuild/edit (+ Hindi Wikipedia sources) and per-account photo attach/replace
import io
import re
import datetime as dt
import pytest
import requests

from nvm_test_env import ADMIN_EMAIL, ADMIN_PW, BASE_URL
KEY = "nai-sarak-1017b307"
DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def tiny_jpeg(color=(200, 80, 40)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def H(s):
    r = s.post(f"{BASE_URL}/api/auth/token", data={"username": ADMIN_EMAIL, "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def era_payload(hist, **over):
    eras = [{"key": e["key"], "heading": e.get("heading", ""), "text": e.get("text", ""), "scope": e.get("scope", "none"), "sources": e.get("sources", [])} for e in hist["eras"]]
    body = {"summary": hist.get("summary", ""), "then_now": hist.get("then_now", ""), "eras": eras, "new_sources": []}
    body.update(over)
    return body


def citable_ids(hist):
    return [x["id"] for x in hist["sources"] if x["type"] != "openstreetmap"]


# ---------- Rebuild + Hindi Wikipedia ----------
class TestRebuild:
    def test_rebuild_no_token(self, s):
        assert s.post(f"{BASE_URL}/api/admin/history/{KEY}/rebuild").status_code == 401

    def test_rebuild_unknown_key(self, s, H):
        r = s.post(f"{BASE_URL}/api/admin/history/zzz-nowhere-00000000/rebuild", headers=H, timeout=60)
        assert r.status_code == 404, r.text

    def test_rebuild_ok_with_hindi(self, s, H):
        r = s.post(f"{BASE_URL}/api/admin/history/{KEY}/rebuild", headers=H, timeout=180)
        assert r.status_code == 200, r.text
        h = r.json()
        assert h["has_records"] is True
        assert not h.get("edited_at")
        langs = {x.get("lang") for x in h["sources"] if x["type"] == "wikipedia"}
        print("wiki langs:", langs, [x["title"] for x in h["sources"]])
        assert "en" in langs and "hi" in langs
        hi = [x for x in h["sources"] if x.get("lang") == "hi"]
        assert all(DEVANAGARI.search(x["title"]) for x in hi)
        assert all("hi.wikipedia.org" in x["url"] for x in hi)
        ids = {x["id"] for x in h["sources"]}
        for e in h["eras"]:
            assert set(e["sources"]) <= ids, e
            if e["text"]:
                assert e["sources"], e


# ---------- Edit (PUT) ----------
class TestEdit:
    @pytest.fixture(scope="class")
    def hist(self, s):
        r = s.get(f"{BASE_URL}/api/history/{KEY}", timeout=180)
        assert r.status_code == 200
        return r.json()

    def test_no_token(self, s, hist):
        assert s.put(f"{BASE_URL}/api/admin/history/{KEY}", json=era_payload(hist)).status_code == 401

    def test_unbuilt_key_404(self, s, H, hist):
        r = s.put(f"{BASE_URL}/api/admin/history/never-built-key-1234abcd", headers=H, json=era_payload(hist))
        assert r.status_code == 404, r.text

    def test_valid_edit(self, s, H, hist):
        body = era_payload(hist)
        cid = citable_ids(hist)[0]
        for e in body["eras"]:
            if e["key"] == "1800s":
                e["text"] = "TEST_ edited 1800s text by testing agent."
                e["heading"] = e["heading"] or "TEST heading"
                e["scope"] = e["scope"] if e["scope"] != "none" else "street"
                e["sources"] = e["sources"] or [cid]
        r = s.put(f"{BASE_URL}/api/admin/history/{KEY}", headers=H, json=body)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["edited_by"] == ADMIN_EMAIL and d["edited_at"]
        g = s.get(f"{BASE_URL}/api/history/{KEY}").json()
        assert next(e for e in g["eras"] if e["key"] == "1800s")["text"].startswith("TEST_ edited")
        assert g["edited_at"]

    def _with_era(self, hist, sources):
        body = era_payload(hist)
        for e in body["eras"]:
            if e["key"] == "1800s":
                e["text"] = "TEST_ text"
                e["scope"] = "street"
                e["sources"] = sources
        return body

    def test_empty_sources_422(self, s, H, hist):
        r = s.put(f"{BASE_URL}/api/admin/history/{KEY}", headers=H, json=self._with_era(hist, []))
        assert r.status_code == 422 and "1800s" in r.text, r.text

    def test_osm_only_422(self, s, H, hist):
        osm = [x["id"] for x in hist["sources"] if x["type"] == "openstreetmap"]
        if not osm:
            pytest.skip("no osm source")
        r = s.put(f"{BASE_URL}/api/admin/history/{KEY}", headers=H, json=self._with_era(hist, osm))
        assert r.status_code == 422, r.text

    def test_new_source_manual(self, s, H):
        cur = s.get(f"{BASE_URL}/api/history/{KEY}").json()
        nid = max(x["id"] for x in cur["sources"]) + 1
        body = self._with_era(cur, [nid])
        body["new_sources"] = [{"title": "TEST_ manual source", "url": "https://example.org/x", "scope": "street"}]
        r = s.put(f"{BASE_URL}/api/admin/history/{KEY}", headers=H, json=body)
        assert r.status_code == 200, r.text
        man = [x for x in r.json()["sources"] if x["type"] == "manual"]
        assert any(x["id"] == nid and x["url"] == "https://example.org/x" for x in man)

    def test_bad_url_422(self, s, H, hist):
        body = era_payload(hist)
        body["new_sources"] = [{"title": "TEST bad", "url": "ftp://example.org/x", "scope": "street"}]
        assert s.put(f"{BASE_URL}/api/admin/history/{KEY}", headers=H, json=body).status_code == 422

    def test_missing_era_422(self, s, H, hist):
        body = era_payload(hist)
        body["eras"] = body["eras"][:-1]
        r = s.put(f"{BASE_URL}/api/admin/history/{KEY}", headers=H, json=body)
        assert r.status_code == 422 and "Today" in r.text, r.text

    def test_summary_without_eras_422(self, s, H, hist):
        body = era_payload(hist, summary="TEST summary")
        for e in body["eras"]:
            e["text"] = ""
        assert s.put(f"{BASE_URL}/api/admin/history/{KEY}", headers=H, json=body).status_code == 422


# ---------- Regression ----------
class TestRegression:
    def test_history_get_consistent(self, s):
        h = s.get(f"{BASE_URL}/api/history/{KEY}", timeout=180).json()
        ids = {x["id"] for x in h["sources"]}
        for e in h["eras"]:
            assert set(e["sources"]) <= ids

    def test_look(self, s):
        r = s.get(f"{BASE_URL}/api/look", params={"lat": 28.6506, "lng": 77.2303}, timeout=60)
        assert r.status_code == 200, r.text
        assert "key" in r.json() or "place" in r.json()


# ---------- Photo attach / replace ----------
class TestPhoto:
    @pytest.fixture(scope="class")
    def acct(self, s, H):
        r = s.post(f"{BASE_URL}/api/admin/local-accounts", headers=H, data={
            "place_key": KEY, "era": "today", "body": "TEST_ photo attach account body", "told_by": "TEST_ teller",
            "village": "TEST_ village", "collected_on": dt.date.today().isoformat()})
        assert r.status_code == 200, r.text
        a = r.json()
        assert not a.get("photo_url")
        yield a
        s.delete(f"{BASE_URL}/api/admin/local-accounts/{a['id']}", headers=H)

    def test_no_token(self, s, acct):
        r = s.post(f"{BASE_URL}/api/admin/local-accounts/{acct['id']}/photo", files={"photo": ("a.jpg", tiny_jpeg(), "image/jpeg")})
        assert r.status_code == 401

    def test_unknown_id(self, s, H):
        r = s.post(f"{BASE_URL}/api/admin/local-accounts/nope-000/photo", headers=H, files={"photo": ("a.jpg", tiny_jpeg(), "image/jpeg")})
        assert r.status_code == 404

    def test_non_image(self, s, H, acct):
        r = s.post(f"{BASE_URL}/api/admin/local-accounts/{acct['id']}/photo", headers=H, files={"photo": ("a.txt", b"hello", "text/plain")})
        assert r.status_code == 422

    def test_attach_then_replace(self, s, H, acct):
        r1 = s.post(f"{BASE_URL}/api/admin/local-accounts/{acct['id']}/photo", headers=H, files={"photo": ("a.jpg", tiny_jpeg(), "image/jpeg")}, timeout=60)
        assert r1.status_code == 200, r1.text
        u1 = r1.json()["photo_url"]
        assert "?v=" in u1
        g = s.get(f"{BASE_URL}{u1}", timeout=60)
        assert g.status_code == 200 and g.headers["content-type"].startswith("image/") and g.content[:2] == b"\xff\xd8"
        r2 = s.post(f"{BASE_URL}/api/admin/local-accounts/{acct['id']}/photo", headers=H, files={"photo": ("b.jpg", tiny_jpeg((10, 200, 10)), "image/jpeg")}, timeout=60)
        assert r2.status_code == 200
        u2 = r2.json()["photo_url"]
        assert u2 != u1
        lst = s.get(f"{BASE_URL}/api/local-accounts", params={"place_key": KEY}).json()
        assert next(x for x in lst if x["id"] == acct["id"])["photo_url"] == u2
