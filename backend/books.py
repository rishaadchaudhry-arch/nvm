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
    """What to search for, or None if the name is too generic or too short to search safely.

    Usually the name's skeleton. A short name ("Lal Kuan", "Bara Dari") has too short a skeleton to
    trust, so it is matched by its exact words instead, marked with a leading "=".
    """
    words = re.findall(r"[A-Za-z]+", name)
    if not words or not any(w.lower() not in _GENERIC and len(w) >= 3 for w in words):
        return None
    key = "".join(_skel(w) for w in words)
    if len(key) >= 5 or (len(words) == 1 and len(key) >= 4 and len(words[0]) >= 7):
        return key
    if (len(words) >= 2 and sum(len(w) for w in words) >= 6) or (len(words) == 1 and len(words[0]) >= 6):
        return "=" + " ".join(w.lower() for w in words)
    return None


_QUALIFIERS = {"kalan", "khurd", "khas", "bazar", "bazaar", "road", "marg", "gali", "kucha", "mohalla", "muhalla"}


def variants(name: str) -> list[str]:
    """A name and its core: books write "the Dariba" for Dariba Kalan, "Ballimaran" for Muhalla Balli Maran."""
    words = re.findall(r"[A-Za-z]+", name)
    core = [w for w in words if w.lower() not in _QUALIFIERS]
    out = [name]
    if core and len(core) < len(words):
        out.append(" ".join(core))
    return out


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


def _index(text: str) -> tuple[str, set[int], str]:
    """The passage as one string of word skeletons, where each word starts and ends in it, and its plain words."""
    s, bounds = "", {0}
    words = re.findall(r"[A-Za-z]+", text)
    for w in words:
        k = _skel(w)
        if k:
            s += k
            bounds.add(len(s))
    return s, bounds, " " + " ".join(w.lower() for w in words) + " "


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
            r["skel"], r["bounds"], r["plain"] = _index(r["text"])
        _memory = rows
    return _memory


def _count(p: dict, key: str) -> int:
    """How many times a passage mentions a name."""
    if key.startswith("="):
        return p["plain"].count(f" {key[1:]} ")
    s, bounds, n = p["skel"], p["bounds"], 0
    i = s.find(key)
    while i != -1:
        if i in bounds and (i + len(key)) in bounds:
            n += 1
        i = s.find(key, i + 1)
    return n


def _mentions(p: dict, key: str) -> bool:
    return _count(p, key) > 0


async def find(db, names: Iterable[tuple[str, int]], limit: int = 6, per_name: int = 3) -> list[dict]:
    """Passages that mention any of `names` - (name, weight) pairs, the place's own name weighing most.

    Ranked by the total weight of the distinct names a passage mentions, so one that mentions this
    street and two of its landmarks beats one that only mentions a famous building down the road.
    """
    wanted: dict[str, tuple[str, int]] = {}
    for full, weight in names:
        for name in variants(full):
            key = _name_key(name)
            if key and (key not in wanted or wanted[key][1] < weight):
                wanted[key] = (full, weight)
    if not wanted:
        return []
    scored = []
    for p in await _passages(db):
        hits = [(name, w, c) for key, (name, w) in wanted.items() if (c := _count(p, key))]
        if hits:
            # Distinct names first (a passage naming the street and its landmarks is about here), then
            # how often it names them (a passage about the Dariba says "Dariba" more than once).
            weight = sum(w for _, w, _ in {n: (n, w, c) for n, w, c in hits}.values())
            mentions = sum(min(c, 4) * w for _, w, c in hits)
            scored.append((weight, mentions, p, [n for n, _, _ in hits]))
    scored.sort(key=lambda t: (-t[0], -t[1], t[2]["year"], t[2]["n"]))
    scored = [(w, p, names) for w, _, p, names in scored]
    out, used = [], {}
    for score, p, hit_names in scored:
        weight_of = {n: w for n, w in wanted.values()}
        hit_names = list(dict.fromkeys(hit_names))
        lead = max(hit_names, key=lambda n: weight_of.get(n, 0))
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
