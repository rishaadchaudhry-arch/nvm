# Share card feature: /api/history/{key}/card-facts and /api/history/{key}/card.png
import io
import os
import time

import pytest
import requests
from PIL import Image, ImageStat

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
KEY = "nai-sarak-1017b307"
MISSING = "nope-00000000"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def facts(s):
    r = s.get(f"{BASE_URL}/api/history/{KEY}/card-facts", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# card-facts
class TestCardFacts:
    def test_facts_shape(self, facts):
        assert isinstance(facts, list) and len(facts) > 0
        for f in facts:
            assert set(f.keys()) == {"label", "text"}
            assert isinstance(f["label"], str) and f["label"]
            assert isinstance(f["text"], str) and f["text"]

    def test_facts_order(self, facts):
        labels = [f["label"] for f in facts]
        assert labels[0] == "Did you know?"
        assert labels[-1] == "In short"
        # once "Did you know?" stops, it never resumes; eras in between
        first_non_dyk = next(i for i, l in enumerate(labels) if l != "Did you know?")
        assert all(l != "Did you know?" for l in labels[first_non_dyk:])
        assert labels.count("In short") == 1

    def test_facts_unknown_key_404(self, s):
        r = s.get(f"{BASE_URL}/api/history/{MISSING}/card-facts", timeout=30)
        assert r.status_code == 404


# card.png
class TestCardPng:
    def _get(self, s, fact, key=KEY):
        return s.get(f"{BASE_URL}/api/history/{key}/card.png", params={"fact": fact}, timeout=60)

    def test_png_fact0(self, s):
        r = self._get(s, 0)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("image/png")
        assert r.headers.get("cache-control")
        cd = r.headers.get("content-disposition", "")
        assert cd.startswith("inline") and 'filename="nvm-nai-sarak.png"' in cd, cd
        img = Image.open(io.BytesIO(r.content))
        assert img.format == "PNG"
        assert img.size == (1080, 1350)
        # not blank
        stat = ImageStat.Stat(img.convert("L"))
        assert stat.stddev[0] > 5, stat.stddev

    def test_fact1_differs(self, s):
        a, b = self._get(s, 0), self._get(s, 1)
        assert a.status_code == b.status_code == 200
        assert a.content != b.content

    def test_fact_wrap_within_limit(self, s, facts):
        n = len(facts)
        a, b = self._get(s, 0), self._get(s, n)
        assert b.status_code == 200
        assert a.content == b.content

    def test_fact_999_wraps(self, s):
        r = self._get(s, 999)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"

    def test_fact_negative_422(self, s):
        assert self._get(s, -1).status_code == 422

    def test_unknown_key_404(self, s):
        assert self._get(s, 0, MISSING).status_code == 404

    def test_cached_second_call(self, s, facts):
        idx = len(facts) - 1
        first = self._get(s, idx)
        t = time.time()
        second = self._get(s, idx)
        dt = time.time() - t
        assert first.status_code == second.status_code == 200
        assert first.content == second.content
        assert dt < 3, dt
