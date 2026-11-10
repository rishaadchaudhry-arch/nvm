# NVM Local accounts feature tests (admin create/list/delete, public list, photo route) + light regression
import io
import os
import datetime as dt
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@yatra.app"
ADMIN_PW = "Yatra-a20d244dfc16"
PLACE = "lajpat-nagar-ii-1a9b6fe7"


def tiny_jpeg() -> bytes:
    try:
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), (200, 80, 40)).save(buf, "JPEG")
        return buf.getvalue()
    except Exception:
        pytest.skip("PIL not available")


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def token(s):
    r = s.post(f"{BASE_URL}/api/auth/token", data={"username": ADMIN_EMAIL, "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}"}


def form(**over):
    base = {"place_key": PLACE, "era": "1800s", "body": "TEST_ an account of the old well near the bazaar",
            "told_by": "TEST_ Teller", "village": "TEST_ Village", "collected_on": dt.date.today().isoformat()}
    base.update(over)
    return base


@pytest.fixture(scope="module")
def created(s, H):
    ids = []
    yield ids
    for i in ids:
        s.delete(f"{BASE_URL}/api/admin/local-accounts/{i}", headers=H)


class TestLocalAccounts:
    def test_auth_token(self, token):
        assert isinstance(token, str) and len(token) > 20

    def test_create_requires_auth(self, s):
        r = s.post(f"{BASE_URL}/api/admin/local-accounts", data=form())
        assert r.status_code == 401, r.text

    @pytest.mark.parametrize("over,code", [
        ({"era": "1999s"}, 422),
        ({"body": "short"}, 422),
        ({"collected_on": "12-01-2025"}, 422),
        ({"collected_on": (dt.date.today() + dt.timedelta(days=3)).isoformat()}, 422),
        ({"told_by": "   "}, 422),
        ({"place_key": "no-such-place-zzz"}, 404),
    ])
    def test_create_validation(self, s, H, over, code):
        r = s.post(f"{BASE_URL}/api/admin/local-accounts", data=form(**over), headers=H)
        assert r.status_code == code, f"{over}: {r.status_code} {r.text}"

    def test_non_image_photo_rejected(self, s, H):
        r = s.post(f"{BASE_URL}/api/admin/local-accounts", data=form(), headers=H,
                   files={"photo": ("x.txt", b"hello world", "text/plain")})
        assert r.status_code == 422, r.text
        # ensure nothing was persisted
        lst = s.get(f"{BASE_URL}/api/admin/local-accounts", headers=H).json()
        assert not any(a["body"] == form()["body"] and a["photo_url"] is None and a["created_at"] > (dt.datetime.utcnow() - dt.timedelta(seconds=10)).isoformat() for a in lst)

    def test_create_without_photo_and_lifecycle(self, s, H, created):
        r = s.post(f"{BASE_URL}/api/admin/local-accounts", data=form(), headers=H)
        assert r.status_code == 200, r.text
        a = r.json()
        created.append(a["id"])
        assert a["place_key"] == PLACE and a["era"] == "1800s" and a["era_label"]
        assert a["photo_url"] is None and a["added_by"] == ADMIN_EMAIL
        assert "_id" not in a and "photo_path" not in a and "deleted" not in a
        # public list
        pub = s.get(f"{BASE_URL}/api/local-accounts", params={"place_key": PLACE})
        assert pub.status_code == 200
        assert any(x["id"] == a["id"] for x in pub.json())
        assert all(x["place_key"] == PLACE for x in pub.json())
        # admin list
        adm = s.get(f"{BASE_URL}/api/admin/local-accounts", headers=H)
        assert adm.status_code == 200 and any(x["id"] == a["id"] for x in adm.json())
        # photo 404 when none
        assert s.get(f"{BASE_URL}/api/local-accounts/{a['id']}/photo").status_code == 404
        # delete
        d = s.delete(f"{BASE_URL}/api/admin/local-accounts/{a['id']}", headers=H)
        assert d.status_code == 200, d.text
        assert not any(x["id"] == a["id"] for x in s.get(f"{BASE_URL}/api/local-accounts", params={"place_key": PLACE}).json())
        assert not any(x["id"] == a["id"] for x in s.get(f"{BASE_URL}/api/admin/local-accounts", headers=H).json())
        assert s.delete(f"{BASE_URL}/api/admin/local-accounts/{a['id']}", headers=H).status_code == 404

    def test_create_with_photo_and_delete(self, s, H, created):
        r = s.post(f"{BASE_URL}/api/admin/local-accounts", data=form(era="1900_1947"), headers=H,
                   files={"photo": ("t.jpg", tiny_jpeg(), "image/jpeg")}, timeout=120)
        assert r.status_code == 200, r.text
        a = r.json()
        created.append(a["id"])
        assert a["photo_url"] == f"/api/local-accounts/{a['id']}/photo"
        p = s.get(f"{BASE_URL}{a['photo_url']}", timeout=60)
        assert p.status_code == 200, p.text
        assert p.headers["content-type"].startswith("image/")
        assert p.content[:2] == b"\xff\xd8"
        assert s.delete(f"{BASE_URL}/api/admin/local-accounts/{a['id']}", headers=H).status_code == 200
        assert s.get(f"{BASE_URL}{a['photo_url']}").status_code == 404

    def test_admin_list_requires_auth(self, s):
        assert s.get(f"{BASE_URL}/api/admin/local-accounts").status_code == 401
        assert s.delete(f"{BASE_URL}/api/admin/local-accounts/whatever").status_code == 401

    def test_unknown_photo_404(self, s):
        assert s.get(f"{BASE_URL}/api/local-accounts/does-not-exist/photo").status_code == 404

    def test_public_list_missing_param(self, s):
        assert s.get(f"{BASE_URL}/api/local-accounts").status_code == 422

    def test_preseeded_account_has_photo(self, s):
        lst = s.get(f"{BASE_URL}/api/local-accounts", params={"place_key": PLACE}).json()
        seeded = [x for x in lst if x["era"] == "1900_1947" and x["photo_url"] and not x["body"].startswith("TEST_")]
        assert seeded, lst
        p = s.get(f"{BASE_URL}{seeded[0]['photo_url']}", timeout=60)
        assert p.status_code == 200 and p.headers["content-type"].startswith("image/")


class TestRegression:
    def test_place(self, s):
        r = s.get(f"{BASE_URL}/api/places/{PLACE}")
        assert r.status_code == 200 and r.json()["key"] == PLACE

    def test_history_cached(self, s):
        r = s.get(f"{BASE_URL}/api/history/{PLACE}", timeout=90)
        assert r.status_code == 200 and len(r.json()["eras"]) == 8

    def test_traditions_pending(self, s):
        r = s.get(f"{BASE_URL}/api/traditions", params={"status": "pending"})
        assert r.status_code == 200 and isinstance(r.json(), list)

    def test_admin_traditions(self, s, H):
        r = s.get(f"{BASE_URL}/api/admin/traditions", headers=H)
        assert r.status_code == 200 and isinstance(r.json(), list)
