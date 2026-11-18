"""The old-books source: splitting a scanned book into passages, and finding them by loose spelling."""
import asyncio
import sys
import types

sys.modules.setdefault("httpx", types.SimpleNamespace(AsyncClient=object))
import books  # noqa: E402

PAGE = """DELHI PAST AND PRESENT

The Dariba, the street of the incomparable pearl, leads
from the Chandni Chauk to the Jama Masjid. It was the
street of the jewellers, and in 1857 the mutineers plun-
dered several of its houses before the siege began, and
the shops of the bankers were closed for many weeks.

42

Beyond it lies the Kucha Chelan, where many families of
the old nobility lived, in houses built round courtyards,
some of which still had their painted ceilings at the time
of writing; the lane takes its name from the disciples
(chelas) of a saint who settled there in the reign of Shah Jahan.
"""


def test_split_rejoins_hyphenation_and_drops_page_furniture():
    passages = books.split_passages(PAGE * 2)
    assert passages
    assert all("DELHI PAST AND PRESENT" not in p for p in passages)
    assert any("plundered" in p for p in passages)


def test_spelling_variants_meet():
    for a, b in [("Chandni Chowk", "Chandni Chauk"), ("Ballimaran", "Balli Maran"), ("Fatehpuri", "Fatahpuri"),
                 ("Qutb Minar", "Kutb Minar"), ("Kucha Chelan", "Kuchah Chelan")]:
        assert books._name_key(a) == books._name_key(b), (a, b)


def test_generic_names_are_not_searched():
    for n in ["Old Delhi", "Main Road", "Masjid", "Gali", "Delhi"]:
        assert books._name_key(n) is None, n


def test_find_ranks_the_place_itself_first():
    class FakeColl:
        def find(self, *a, **k):
            async def gen():
                for i, p in enumerate(books.split_passages(PAGE)):
                    yield {"book": "fanshawe", "n": i, "title": "Fanshawe", "year": 1902, "archive_id": "x", "text": p}
            return gen()

    db = types.SimpleNamespace(book_passages=FakeColl())
    books._memory = None
    found = asyncio.run(books.find(db, [("Kucha Chelan", 3), ("Chandni Chowk", 1)]))
    books._memory = None
    assert found and "Kucha Chelan" in found[0]["names"]
    assert not asyncio.run(books.find(db, [("Ballimaran", 3)]))
    books._memory = None
