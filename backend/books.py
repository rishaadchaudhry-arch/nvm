"""Old books about Delhi, searched by the names of the places in them.

The gazetteer and OpenStreetMap say what stood where. These books say what happened there: who
built a street, who lived on it, what it looked like in 1876 or 1902, what happened in it in 1857.
They are not geotagged, so passages are found by name - the street's, its landmarks', and the lanes
the 1916 survey recorded nearby - and spelling is matched loosely, because a Victorian writer's
"Chandni Chauk" or "Kashmir Darwaza" is the same place as today's Chandni Chowk or Kashmere Gate.

All three books are public domain and are read from the Internet Archive's OCR text.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

import httpx

from gazetteer import UA, fetch_volume_text

logger = logging.getLogger(__name__)

BOOKS: dict[str, dict] = {
    "fanshawe": {
        "archive_id": "cu31924095603076",
        "title": "H. C. Fanshawe, Delhi Past and Present",
        "year": 1902,
    },
    "carr_stephen": {
        "archive_id": "b28709548",
        "title": "Carr Stephen, The Archaeology and Monumental Remains of Delhi",
        "year": 1876,
    },
    "hearn": {
        "archive_id": "dli.ernet.523979",
        "title": "Gordon Risley Hearn, The Seven Cities of Delhi",
        "year": 1906,
    },
}

PASSAGE_MIN, PASSAGE_MAX = 600, 1400

# Words that name a kind of place rather than a place. A name made only of these ("Old Delhi", "Main
# Road", "Masjid") would match half of every book, so it is not searched for.
_GENERIC = set(
    "the of and a an old new delhi shahjahanabad city road marg street lane gali kucha kuncha katra chhatta "
    "chatta mohalla muhalla bazar bazaar market chowk chauk gate darwaza masjid mosque mandir temple church "
    "gurdwara house haveli park garden bagh tomb maqbara well place area colony nagar village main north south "
    "east west upper lower near behind today then known survey monument building".split()
)


# ---- loose spelling ---------------------------------------------------------------------------

def _skel(word: str) -> str:
    """A word reduced to its consonants, so transliterations meet: Chauk/Chowk, Fatahpuri/Fatehpuri,
    Balli Maran/Ballimaran, Kutb/Qutb, Kashmir/Kashmere."""
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return ""
    w = w.replace("ph", "f").replace("q", "k").replace("z", "j").replace("ee", "i").replace("oo", "u")
    s = w[0] + re.sub(r"[aeiouyhw]", "", w[1:])
    return re.sub(r"(.)\1+", r"\1", s)


def _name_key(name: str) -> Optional[str]:
    """The skeleton to search for, or None if the name is too generic or too short to search safely."""
    words = re.findall(r"[A-Za-z]+", name)
    if not words or not any(w.lower() not in _GENERIC and len(w) >= 4 for w in words):
        return None
    key = "".join(_skel(w) for w in words)
    return key if len(key) >= 5 else None


# ---- passages -----------------------------------------------------------------------------------

def _clean(text: str) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"(\w)-\n\s*(\w)", r"\1\2", text)          # re-join words broken across lines
    lines = [ln.strip() for ln in text.split("\n")]
    keep = []
    for ln in lines:
        if re.fullmatch(r"[\divxlcIVXLC .,\-—]*", ln):          # page numbers
            keep.append("")
            continue
        if ln.isupper() and len(ln) < 60:                         # running heads
            continue
        keep.append(ln)
    return "\n".join(keep)


def _looks_like_prose(p: str) -> bool:
    if len(p) < 200:
        return False
    digits = sum(ch.isdigit() for ch in p) / len(p)
    return digits < 0.06 and p.count("—") < 8 and p.count("...") < 4 and len(re.findall(r"[a-z]{3,}", p)) > len(p) / 12


def split_passages(text: str) -> list[str]:
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", _clean(text))]
    out: list[str] = []
    buf = ""
    for p in paras:
        if not p:
            continue
        buf = f"{buf} {p}".strip() if buf else p
        if len(buf) >= PASSAGE_MIN:
            while len(buf) > PASSAGE_MAX:                         # cut long runs at a sentence end
                cut = buf.rfind(". ", PASSAGE_MIN, PASSAGE_MAX)
                cut = cut + 1 if cut > 0 else PASSAGE_MAX
                out.append(buf[:cut].strip())
                buf = buf[cut:].strip()
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return [p for p in out if _looks_like_prose(p)]


def _index(text: str) -> tuple[str, set[int]]:
    """The passage as one string of word skeletons, plus where each word starts and ends in it."""
    s, bounds = "", {0}
    for w in re.findall(r"[A-Za-z]+", text):
        k = _skel(w)
        if k:
            s += k
            bounds.add(len(s))
    return s, bounds


# ---- import and lookup --------------------------------------------------------------------------

_memory: Optional[list[dict]] = None


async def import_books(db, keys: Optional[list[str]] = None, progress: Optional[dict] = None) -> dict:
    global _memory
    keys = keys or list(BOOKS)
    stats: dict = {"state": "downloading", "books": {}}
    if progress is not None:
        progress.update(stats)
    async with httpx.AsyncClient(headers={"User-Agent": UA}) as client:
        for key in keys:
            spec = BOOKS[key]
            text = await fetch_volume_text(client, spec["archive_id"])
            passages = split_passages(text)
            await db.book_passages.delete_many({"book": key})
            if passages:
                await db.book_passages.insert_many(
                    [{"book": key, "n": i, "title": spec["title"], "year": spec["year"], "archive_id": spec["archive_id"], "text": p} for i, p in enumerate(passages)]
                )
            stats["books"][key] = {"chars": len(text), "passages": len(passages)}
            if progress is not None:
                progress.update(stats)
    _memory = None
    stats["state"] = "done"
    stats["total_passages"] = await db.book_passages.count_documents({})
    if progress is not None:
        progress.update(stats)
    return stats


async def _passages(db) -> list[dict]:
    global _memory
    if _memory is None:
        rows = [r async for r in db.book_passages.find({}, {"_id": 0})]
        for r in rows:
            r["skel"], r["bounds"] = _index(r["text"])
        _memory = rows
    return _memory


def _mentions(p: dict, key: str) -> bool:
    s, bounds = p["skel"], p["bounds"]
    i = s.find(key)
    while i != -1:
        if i in bounds and (i + len(key)) in bounds:
            return True
        i = s.find(key, i + 1)
    return False


async def find(db, names: Iterable[tuple[str, int]], limit: int = 6, per_name: int = 2) -> list[dict]:
    """Passages that mention any of `names` - (name, weight) pairs, the place's own name weighing most.

    Ranked by the total weight of the distinct names a passage mentions, so one that mentions this
    street and two of its landmarks beats one that only mentions a famous building down the road.
    """
    wanted: dict[str, tuple[str, int]] = {}
    for name, weight in names:
        key = _name_key(name)
        if key and (key not in wanted or wanted[key][1] < weight):
            wanted[key] = (name, weight)
    if not wanted:
        return []
    scored = []
    for p in await _passages(db):
        hits = [(name, w) for key, (name, w) in wanted.items() if _mentions(p, key)]
        if hits:
            scored.append((sum(w for _, w in hits), p, [n for n, _ in hits]))
    scored.sort(key=lambda t: (-t[0], t[1]["year"], t[1]["n"]))
    out, used = [], {}
    for score, p, hit_names in scored:
        lead = max(hit_names, key=lambda n: wanted[_name_key(n)][1])
        if used.get(lead, 0) >= per_name:
            continue
        used[lead] = used.get(lead, 0) + 1
        out.append({**{k: p[k] for k in ("book", "title", "year", "archive_id", "text", "n")}, "names": hit_names})
        if len(out) >= limit:
            break
    return out


def as_sources(passages: list[dict]) -> list[dict]:
    """One source per book, so the reader's citation names the book."""
    by_book: dict[str, dict] = {}
    for p in passages:
        src = by_book.setdefault(p["book"], {
            "type": "book",
            "title": f"{p['title']} ({p['year']})",
            "url": f"https://archive.org/details/{p['archive_id']}",
            "scope": "street",
            "text": "",
        })
        src["text"] += f"[Passage mentioning {', '.join(p['names'])}]\n{p['text']}\n\n"
    return list(by_book.values())
