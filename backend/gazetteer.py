"""Zafar Hasan's survey of Delhi's monuments (1916-1922), as a source this app can read.

Maulvi Zafar Hasan and the Archaeological Survey walked Delhi and wrote down every monument they
found, filed under the lane it stood in: more than 1,200 of them across four volumes, the famous and
the forgotten alike. For most of Delhi's older lanes it is the only description that was ever
written, which makes it the single richest thing we can give this app.

It is out of copyright and scanned on the Internet Archive, so we read its OCR text, split it back
into entries, and place each entry at its lane.

What this is honest about: the book gives lanes, not coordinates. An entry is placed where its lane
geocodes to, so it is street-level evidence, never a pin on a building. Entries carry the lane name
so the model can say "in Kucha Chelan" rather than implying it stands on this exact spot.
"""

import asyncio
import logging
import re
from typing import Iterable, Optional

import httpx

logger = logging.getLogger(__name__)

UA = "NVM-app/1.0 (street history lookup; contact: dev@nvm.app)"
ARCHIVE = "https://archive.org"

VOLUMES: dict[int, dict] = {
    1: {"archive_id": "in.gov.ignca.22805", "area": "Shahjahanabad", "year": 1916},
    2: {"archive_id": "in.gov.ignca.12006", "area": "Delhi Zail", "year": 1919},
    3: {"archive_id": "in.ernet.dli.2015.69531", "area": "Mahrauli Zail", "year": 1922},
    4: {"archive_id": "in.ernet.dli.2015.69532", "area": "Outer zails", "year": 1922},
}
TITLE = "Zafar Hasan, List of Muhammadan and Hindu Monuments"

# Running headers and page furniture that look like locality headings but are not.
_NOISE = re.compile(
    r"^(?:[IVXLC]+|\d+|LIST\s*OF.*|.*MON[UOIEXTS]{3,}.*|.*MONUMENTS?.*|PLATE.*|INDEX|CONTENTS|APPENDIX|PREFACE|DELHI PROVINCE|CHAPTER.*)$",
    re.I,
)
# A lane heading: a short all-caps line. OCR turns some letters into digits, so a few are allowed.
_HEADING = re.compile(r"^[A-Z][A-Z0-9'’‘\-.,& ]{4,45}$")
# Entry start. OCR mangles "No." in several ways, so be generous but anchored on the number.
_ENTRY = re.compile(r"^\s*(?:No|N0|Xo|No\.|ISTo)\s*\.?\s*(\d{1,4})\s*[.,]", re.I)
# Field markers: (a) name ... (e) period ... (j) the description. OCR substitutes freely.
_FIELD_A = re.compile(r"\(\s*[ao0@]\s*\)\s*(.+?)(?=\(\s*[b6]\s*\)|$)", re.S)
_FIELD_E = re.compile(r"\(\s*[e&]\s*\)\s*(.+?)(?=\(\s*[f/(]\s*\)|$)", re.S)
_FIELD_J = re.compile(r"\(\s*[j;iJ1]\s*\)\s*(.+)", re.S)


def _clean(s: str) -> str:
    s = re.sub(r"[ \t]*\n[ \t]*", " ", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" .,;:-—")


def _looks_like_heading(line: str) -> bool:
    line = line.strip().rstrip(".")
    if not (4 < len(line) <= 45) or not _HEADING.match(line):
        return False
    if _NOISE.match(line):
        return False
    return sum(c.isalpha() for c in line) >= len(line) * 0.6


# OCR leaves behind fragments and the book itself lists things it could say nothing about. An entry
# earns its place only if it can tell a reader something: a real name, or a description worth reading.
_JUNK_NAME = re.compile(r"^(?:unnamed|none|do|ditto|nil|n/?a|[^a-z]*)$", re.I)


def _worth_keeping(entry: dict) -> bool:
    name = entry.get("name", "")
    desc = entry.get("description", "")
    named = bool(name) and not _JUNK_NAME.match(name.strip()) and sum(c.isalpha() for c in name) >= 4
    informative = len(desc) >= 60 and sum(c.isalpha() for c in desc) >= 40
    return named or informative


def parse(text: str) -> list[dict]:
    """Split a volume's OCR text into monument entries, each tagged with the lane it is filed under."""
    entries: list[dict] = []
    locality: Optional[str] = None
    current: Optional[dict] = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal current, buffer
        if current is None:
            return
        body = _clean(" ".join(buffer))
        name = _FIELD_A.search(body)
        period = _FIELD_E.search(body)
        desc = _FIELD_J.search(body)
        current["name"] = _clean(name.group(1))[:160] if name else ""
        current["period"] = _clean(period.group(1))[:80] if period else ""
        current["description"] = _clean(desc.group(1))[:1500] if desc else ""
        if _worth_keeping(current):
            entries.append(current)
        current, buffer = None, []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _ENTRY.match(line)
        if m:
            flush()
            current = {"number": int(m.group(1)), "locality": locality or ""}
            buffer = [line[m.end() :]]
            continue
        if _looks_like_heading(line):
            flush()
            locality = line.strip().rstrip(".")
            continue
        if current is not None:
            buffer.append(line)
    flush()
    return entries


async def fetch_volume_text(client: httpx.AsyncClient, archive_id: str) -> str:
    """The OCR text of an Internet Archive item, whatever its text file happens to be called."""
    meta = (await client.get(f"{ARCHIVE}/metadata/{archive_id}", timeout=60)).json()
    names = [f["name"] for f in meta.get("files", []) if f.get("name", "").endswith("_djvu.txt")]
    if not names:
        raise RuntimeError(f"{archive_id} has no OCR text file")
    r = await client.get(f"{ARCHIVE}/download/{archive_id}/{names[0]}", timeout=180, follow_redirects=True)
    r.raise_for_status()
    return r.text


# ---- placing entries on the map -------------------------------------------------------------

_nominatim_lock = asyncio.Lock()
_nominatim_last = 0.0


async def _geocode(client: httpx.AsyncClient, query: str, viewbox: Optional[str]) -> Optional[tuple[float, float, str]]:
    """Public Nominatim allows about one request a second; hold the whole process to that."""
    global _nominatim_last
    async with _nominatim_lock:
        wait = 1.1 - (asyncio.get_event_loop().time() - _nominatim_last)
        if wait > 0:
            await asyncio.sleep(wait)
        _nominatim_last = asyncio.get_event_loop().time()
    params = {"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "in", "addressdetails": 1}
    if viewbox:
        params |= {"viewbox": viewbox, "bounded": 1}
    r = await client.get("https://nominatim.openstreetmap.org/search", params=params, timeout=30)
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return None
    return float(rows[0]["lat"]), float(rows[0]["lon"]), rows[0].get("display_name", "")


def _locality_queries(locality: str) -> list[str]:
    """A 1916 lane name, spelled a few ways modern maps might know it."""
    base = re.sub(r"\s{2,}", " ", locality.title().replace("’", "'")).strip()
    out = [f"{base}, Delhi"]
    swapped = base.replace("Kuncha-I-", "Kucha ").replace("Kuncha-i-", "Kucha ").replace("Muhalla ", "Mohalla ")
    if swapped != base:
        out.append(f"{swapped}, Delhi")
    bare = re.sub(r"^(Muhalla|Mohalla|Kuncha-I-|Kucha|Gali|Katra|Haveli)\s*", "", swapped, flags=re.I).strip()
    if bare and bare != swapped:
        out.append(f"{bare}, Old Delhi, Delhi")
    return out


async def geocode_localities(localities: Iterable[str], viewbox: Optional[str], progress: Optional[dict] = None) -> dict[str, dict]:
    """Resolve each lane name once. Lanes that no longer exist on the map simply get no entry."""
    names = list(dict.fromkeys(localities))
    found: dict[str, dict] = {}
    async with httpx.AsyncClient(headers={"User-Agent": UA}) as client:
        for i, name in enumerate(names, start=1):
            for query in _locality_queries(name):
                try:
                    hit = await _geocode(client, query, viewbox)
                except Exception as exc:
                    logger.warning("geocode %r failed: %s", query, exc)
                    hit = None
                if hit:
                    lat, lng, display = hit
                    found[name] = {"lat": lat, "lng": lng, "matched": query, "display_name": display}
                    break
            if progress is not None:
                progress.update({"localities_done": i, "localities_total": len(names), "localities_found": len(found)})
    return found


async def import_volumes(db, volumes: list[int], viewbox: Optional[str], progress: Optional[dict] = None, dry_run: bool = False) -> dict:
    """Download, parse, place and store. dry_run parses only, and reports what it found."""
    if progress is not None:
        progress.update({"state": "downloading", "volumes": volumes, "entries": 0})
    parsed: list[dict] = []
    async with httpx.AsyncClient(headers={"User-Agent": UA}) as client:
        for vol in volumes:
            spec = VOLUMES[vol]
            text = await fetch_volume_text(client, spec["archive_id"])
            got = parse(text)
            for e in got:
                e |= {"volume": vol, "area": spec["area"], "year": spec["year"], "archive_id": spec["archive_id"]}
            parsed += got
            logger.info("gazetteer: volume %s -> %s entries from %s chars", vol, len(got), len(text))
            if progress is not None:
                progress.update({"entries": len(parsed)})

    localities = [e["locality"] for e in parsed if e["locality"]]
    stats = {
        "entries_parsed": len(parsed),
        "with_description": sum(1 for e in parsed if e["description"]),
        "unique_localities": len(set(localities)),
    }
    if dry_run:
        stats |= {
            "state": "dry run",
            "sample_localities": sorted(set(localities))[:40],
            "sample_entries": [{k: e[k] for k in ("volume", "number", "locality", "name", "period", "description")} for e in parsed[:5]],
        }
        if progress is not None:
            progress.update(stats)
        return stats

    if progress is not None:
        progress.update({"state": "placing lanes on the map", **stats})
    placed = await geocode_localities(localities, viewbox, progress)

    if progress is not None:
        progress.update({"state": "storing"})
    stored = 0
    for e in parsed:
        where = placed.get(e["locality"])
        if not where:
            continue
        doc = {
            **e,
            "lat": where["lat"],
            "lng": where["lng"],
            "location": {"type": "Point", "coordinates": [where["lng"], where["lat"]]},
            "geocoded_from": where["matched"],
        }
        await db.gazetteer.update_one({"volume": e["volume"], "number": e["number"], "locality": e["locality"]}, {"$set": doc}, upsert=True)
        stored += 1

    result = {
        "state": "done",
        **stats,
        "localities_placed": len(placed),
        "entries_stored": stored,
        "entries_unplaced": len(parsed) - stored,
        "total_in_db": await db.gazetteer.count_documents({}),
    }
    if progress is not None:
        progress.update(result)
    return result


async def nearby(db, lat: float, lng: float, radius_m: int = 400, limit: int = 12) -> list[dict]:
    cursor = db.gazetteer.aggregate(
        [
            {"$geoNear": {"near": {"type": "Point", "coordinates": [lng, lat]}, "distanceField": "dist_m", "maxDistance": radius_m, "spherical": True}},
            {"$limit": limit},
            {"$project": {"_id": 0, "locality": 1, "name": 1, "period": 1, "description": 1, "number": 1, "volume": 1, "year": 1, "dist_m": 1}},
        ]
    )
    return [doc async for doc in cursor]


def as_lines(entries: Iterable[dict]) -> list[str]:
    out = []
    for e in entries:
        if not _worth_keeping(e):
            continue
        name = (e.get("name") or "").strip()
        head = name if name and not _JUNK_NAME.match(name) else "a monument"
        where = f" in {e['locality'].title()}" if e.get("locality") else ""
        period = f" ({e['period']})" if e.get("period") else ""
        dist = f", about {round(e['dist_m'])} m away" if e.get("dist_m") is not None else ""
        body = f" {e['description']}" if e.get("description") else ""
        out.append(f"- {head}{period}{where}{dist}, surveyed {e.get('year', '')}:{body}")
    return out
