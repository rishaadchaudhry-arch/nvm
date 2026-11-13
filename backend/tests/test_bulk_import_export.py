# NVM bulk CSV import of local accounts + CSV export/backup (admin) tests
import csv
import io
import os
import re
import datetime as dt

import pytest
import requests

from nvm_test_env import ADMIN_EMAIL, ADMIN_PW, BASE_URL
PLACE = "lajpat-nagar-ii-1a9b6fe7"
EXPORT_COLS = "type,id,place_key,place_title,era,era_label,title,body,told_by,village,collected_on,author,status,verified_by,upvotes,photo_url,added_by,created_at".split(",")


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def token(s):
    r = s.post(f"{BASE_URL}/api/auth/token", data={"username": ADMIN_EMAIL, "password": ADMIN_PW})
    if r.status_code != 200:
        pytest.skip(f"auth failed {r.status_code}")
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def created_ids(s, H):
    ids = []
    yield ids
    for i in ids:
        s.delete(f"{BASE_URL}/api/admin/local-accounts/{i}", headers=H)


def upload(s, H, text, name="t.csv"):
    return s.post(f"{BASE_URL}/api/admin/local-accounts/import", headers=H,
                  files={"file": (name, text.encode("utf-8"), "text/csv")}, timeout=120)


MIXED = (
    "street,era,story,told_by,village,collected_on\n"
    f"{PLACE},1800s,TEST_ bulk A the old well near the market,TEST_ Teller A,TEST_ Village A,20/05/2026\n"   # row2 ok
    f"{PLACE},1900–1947,TEST_ bulk B the tram line ran here once,TEST_ Teller B,TEST_ Village B,2026-02-02\n"  # row3 ok (label era)
    f"{PLACE},1800s,short,TEST_ T,TEST_ V,2026-01-01\n"                                                         # row4 short
    f"{PLACE},Mughal,TEST_ bulk D unknown era here yes,TEST_ T,TEST_ V,2026-01-01\n"                            # row5 era
    f"{PLACE},1800s,TEST_ bulk E future date row text,TEST_ T,TEST_ V,2031-01-01\n"                             # row6 future
    ",1800s,TEST_ bulk F blank street row text,TEST_ T,TEST_ V,2026-01-01\n"                                    # row7 blank street
    "Connaught Place Delhi,today,TEST_ bulk G geocoded by name row,TEST_ Teller G,TEST_ Village G,2026-01-05\n"  # row8 ok geocoded
    ",,,,,\n"                                                                                                   # row9 blank
)


class TestTemplate:
    def test_template_csv(self, s):
        r = s.get(f"{BASE_URL}/api/admin/local-accounts/template.csv")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        lines = r.text.strip().splitlines()
        assert lines[0] == "street,era,story,told_by,village,collected_on"
        assert len(lines) == 2


class TestImport:
    def test_import_requires_auth(self, s):
        r = s.post(f"{BASE_URL}/api/admin/local-accounts/import", files={"file": ("t.csv", MIXED.encode(), "text/csv")})
        assert r.status_code == 401

    def test_import_mixed(self, s, H, created_ids):
        r = upload(s, H, MIXED)
        assert r.status_code == 200, r.text
        d = r.json()
        print(d)
        for cr in d["created_rows"]:
            created_ids.append(cr["id"])
        assert d["rows"] == 8  # DictReader skips truly empty lines; ',,,,,' counts as a row
        failed_rows = {f["row"]: f for f in d["failed"]}
        assert set(failed_rows) == {4, 5, 6, 7}, d["failed"]
        assert "10" in failed_rows[4]["reason"]
        assert "Mughal" in failed_rows[5]["reason"]
        assert "future" in failed_rows[6]["reason"]
        assert "empty" in failed_rows[7]["reason"].lower()
        assert d["created"] == 3, d
        rows = {c["row"]: c for c in d["created_rows"]}
        assert rows[2]["era_label"] == "1800s"
        assert rows[3]["era_label"] == "1900–1947"
        assert 8 in rows
        # persistence
        lst = s.get(f"{BASE_URL}/api/local-accounts", params={"place_key": PLACE}).json()
        by_id = {a["id"]: a for a in lst}
        assert rows[2]["id"] in by_id and by_id[rows[2]["id"]]["collected_on"] == "2026-05-20"
        assert rows[3]["id"] in by_id and by_id[rows[3]["id"]]["era"] == "1900_1947"
        adm = s.get(f"{BASE_URL}/api/admin/local-accounts", headers=H).json()
        g = [a for a in adm if a["id"] == rows[8]["id"]]
        assert g and g[0]["place_key"] != PLACE, g
        print("geocoded place:", g[0]["place_key"], g[0]["place_title"])

    def test_missing_column_422(self, s, H):
        r = upload(s, H, "street,era,story,village,collected_on\nx,1800s,TEST_ long story here,v,2026-01-01\n")
        assert r.status_code == 422 and "told_by" in r.text

    def test_header_only_422(self, s, H):
        r = upload(s, H, "street,era,story,told_by,village,collected_on\n")
        assert r.status_code == 422

    def test_empty_file_422(self, s, H):
        r = upload(s, H, "")
        assert r.status_code == 422

    def test_header_aliases(self, s, H, created_ids):
        text = f"Street,Period,Story text,Who,Town,Date\n{PLACE},1947–2000,TEST_ alias header row story,TEST_ Alias,TEST_ Town,02-02-2026\n"
        r = upload(s, H, text)
        assert r.status_code == 200, r.text
        d = r.json()
        for cr in d["created_rows"]:
            created_ids.append(cr["id"])
        assert d["created"] == 1 and d["rows"] == 1 and d["failed"] == []

    def test_bom_and_crlf(self, s, H, created_ids):
        text = "\ufeffstreet,era,story,told_by,village,collected_on\r\n" + f"{PLACE},today,TEST_ bom crlf row story,TEST_ Bom,TEST_ V,2026-01-03\r\n"
        r = upload(s, H, text)
        assert r.status_code == 200, r.text
        d = r.json()
        for cr in d["created_rows"]:
            created_ids.append(cr["id"])
        assert d["created"] == 1


class TestExport:
    def test_export_no_auth(self, s):
        assert s.get(f"{BASE_URL}/api/admin/export.csv").status_code == 401

    def test_export_bad_token(self, s):
        assert s.get(f"{BASE_URL}/api/admin/export.csv", params={"token": "nope"}).status_code == 401

    def test_export_bearer_and_contents(self, s, H, created_ids):
        r = s.get(f"{BASE_URL}/api/admin/export.csv", headers=H)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        assert re.search(rf'attachment; filename="nvm-backup-{stamp}\.csv"', r.headers["content-disposition"])
        rows = list(csv.DictReader(io.StringIO(r.text)))
        assert list(csv.reader(io.StringIO(r.text)))[0] == EXPORT_COLS
        types = {x["type"] for x in rows}
        assert types <= {"local_account", "community_story"}
        la_ids = {x["id"] for x in rows if x["type"] == "local_account"}
        adm = s.get(f"{BASE_URL}/api/admin/local-accounts", headers=H).json()
        assert la_ids == {a["id"] for a in adm} or len(adm) == 200
        statuses = {x["status"] for x in rows if x["type"] == "community_story"}
        print("story statuses in export:", statuses, "local:", len(la_ids), "stories:", len(rows) - len(la_ids))
        for st in ("pending", "verified", "rejected"):
            q = s.get(f"{BASE_URL}/api/admin/traditions", params={"status": st}, headers=H).json()
            if q:
                assert st in statuses
                assert {t["id"] for t in q} <= {x["id"] for x in rows}

    def test_export_query_token(self, s, token):
        r = s.get(f"{BASE_URL}/api/admin/export.csv", params={"token": token})
        assert r.status_code == 200 and r.text.startswith("type,id,")

    def test_soft_deleted_excluded(self, s, H, created_ids):
        assert created_ids
        victim = created_ids.pop()
        assert s.delete(f"{BASE_URL}/api/admin/local-accounts/{victim}", headers=H).status_code == 200
        r = s.get(f"{BASE_URL}/api/admin/export.csv", headers=H)
        assert victim not in r.text


# Export must include community stories of every status (pending/verified/rejected)
class TestExportStories:
    @pytest.fixture(scope="class")
    def story_ids(self, s, H):
        ids = {}
        for st in ("pending", "verify", "reject"):
            r = s.post(f"{BASE_URL}/api/traditions", json={"place_key": PLACE, "author": "TEST_ bot", "title": f"TEST_ export {st}", "body": "TEST_ story body for export check"})
            assert r.status_code == 200, r.text
            tid = r.json()["id"]
            if st != "pending":
                m = s.post(f"{BASE_URL}/api/admin/traditions/{tid}/moderate", json={"action": st}, headers=H)
                assert m.status_code == 200, m.text
            ids[st] = tid
        yield ids
        import asyncio
        from pathlib import Path

        from dotenv import load_dotenv
        from motor.motor_asyncio import AsyncIOMotorClient

        load_dotenv(Path(__file__).resolve().parents[1] / ".env")

        async def rm():
            db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
            for tid in ids.values():
                await db.traditions.delete_one({"id": tid})
        asyncio.run(rm())

    def test_all_statuses_exported(self, s, H, story_ids):
        r = s.get(f"{BASE_URL}/api/admin/export.csv", headers=H)
        assert r.status_code == 200
        rows = {x["id"]: x for x in csv.DictReader(io.StringIO(r.text))}
        assert rows[story_ids["pending"]]["status"] == "pending"
        assert rows[story_ids["verify"]]["status"] == "verified"
        assert rows[story_ids["reject"]]["status"] == "rejected"
        for tid in story_ids.values():
            assert rows[tid]["type"] == "community_story"
            assert rows[tid]["title"].startswith("TEST_ export")
            assert rows[tid]["place_key"] == PLACE
