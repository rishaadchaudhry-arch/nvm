"""Builds an era-by-era history for any spot from open data.

Pipeline (all sources are public and global, so this works for any street in India and later anywhere):
1. OpenStreetMap / Nominatim reverse-geocode -> street, neighbourhood, city, district, state.
2. Wikipedia: articles geotagged near the spot + the articles for each named level (street, neighbourhood, city ...).
3. Wikidata: items within a few hundred metres with founding / dissolution dates.
4. The LLM may ONLY arrange those fetched facts into eras. Every era carries a scope (how close the fact is to
   the exact spot) and the ids of the sources it came from. Eras with no supporting source stay empty.
"""

import asyncio
import hashlib
import json
import logging
import math
import re
import time
import uuid
from typing import Optional
from urllib.parse import quote

import httpx
from emergentintegrations.llm.chat import LlmChat, StreamDone, TextDelta, UserMessage

logger = logging.getLogger(__name__)

UA = "NVM-app/1.0 (street history lookup; contact: dev@nvm.app)"
WIKI_API = "https://en.wikipedia.org/w/api.php"
NOMINATIM = "https://nominatim.openstreetmap.org"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
LLM_PROVIDER, LLM_MODEL = "openai", "gpt-5.6-terra"

ERAS = [
    ("pre1500", "Before 1500"),
    ("1500s", "1500s"),
    ("1600s", "1600s"),
    ("1700s", "1700s"),
    ("1800s", "1800s"),
    ("1900_1947", "1900–1947"),
    ("1947_2000", "1947–2000"),
    ("today", "Today"),
]
ERA_KEYS = [k for k, _ in ERAS]
SCOPES = ["spot", "street", "neighbourhood", "city", "region"]
MAX_SOURCE_CHARS = 2600


# ------------------------------ geometry ------------------------------------


def offset_point(lat: float, lng: float, bearing: float, dist_m: float) -> tuple[float, float]:
    r = 6371000.0
    br, la, lo = math.radians(bearing), math.radians(lat), math.radians(lng)
    la2 = math.asin(math.sin(la) * math.cos(dist_m / r) + math.cos(la) * math.sin(dist_m / r) * math.cos(br))
    lo2 = lo + math.atan2(math.sin(br) * math.sin(dist_m / r) * math.cos(la), math.cos(dist_m / r) - math.sin(la) * math.sin(la2))
    return math.degrees(la2), math.degrees(lo2)


# ------------------------------ OpenStreetMap -------------------------------

_nominatim_lock = asyncio.Lock()
_nominatim_last = 0.0


async def _nominatim(client: httpx.AsyncClient, path: str, params: dict):
    """Public Nominatim allows ~1 request/second; space calls out across the whole process."""
    global _nominatim_last
    async with _nominatim_lock:
        wait = 1.05 - (time.monotonic() - _nominatim_last)
        if wait > 0:
            await asyncio.sleep(wait)
        _nominatim_last = time.monotonic()
    r = await client.get(f"{NOMINATIM}/{path}", params={**params, "format": "jsonv2", "accept-language": "en"}, timeout=12)
    r.raise_for_status()
    return r.json()


async def reverse_geocode(lat: float, lng: float) -> Optional[dict]:
    async with httpx.AsyncClient(headers={"User-Agent": UA}) as c:
        data = await _nominatim(c, "reverse", {"lat": lat, "lon": lng, "zoom": 17, "addressdetails": 1})
    return None if not data or "error" in data else data


async def search_places(q: str, country: str = "in") -> list[dict]:
    async with httpx.AsyncClient(headers={"User-Agent": UA}) as c:
        rows = await _nominatim(c, "search", {"q": q, "countrycodes": country, "limit": 8, "addressdetails": 1})
    out = []
    for r in rows:
        p = place_from_reverse(r)
        out.append({"title": p["title"], "subtitle": p["subtitle"], "lat": float(r["lat"]), "lng": float(r["lon"]), "type": r.get("type", "")})
    return out


def _first(a: dict, *keys: str) -> Optional[str]:
    for k in keys:
        if a.get(k):
            return a[k]
    return None


def place_from_reverse(rev: dict) -> dict:
    a = rev.get("address", {}) or {}
    road = _first(a, "road", "pedestrian", "footway", "path", "square")
    locality = _first(a, "neighbourhood", "quarter", "suburb", "hamlet", "village")
    suburb = a.get("suburb") if a.get("suburb") and a.get("suburb") != locality else None
    city = _first(a, "city", "town", "village", "municipality", "county")
    district = _first(a, "state_district", "county")
    state = a.get("state")
    name = rev.get("name") or ""
    is_road = rev.get("category") == "highway" or rev.get("addresstype") == "road"
    spot = name if name and not is_road and name != road else None

    title = spot or road or locality or city or "Unnamed spot"
    subtitle_parts: list[str] = []
    for part in ([road] if spot else []) + [locality, suburb, city, state]:
        if part and part != title and part not in subtitle_parts:
            subtitle_parts.append(part)

    levels: list[tuple[str, str]] = []
    for scope, value in (("spot", spot), ("street", road), ("neighbourhood", locality), ("neighbourhood", suburb), ("city", city), ("district", district), ("region", state)):
        if value and value not in [v for _, v in levels]:
            levels.append((scope, value))

    raw_key = "|".join([title, locality or "", city or "", state or ""]).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "spot"
    key = f"{slug}-{hashlib.sha1(raw_key.encode()).hexdigest()[:8]}"
    return {
        "key": key,
        "title": title,
        "subtitle": ", ".join(subtitle_parts[:3]),
        "levels": levels,
        "city": city,
        "state": state,
        "country": a.get("country"),
        "country_code": a.get("country_code"),
        "display_name": rev.get("display_name", ""),
        "osm_url": f"https://www.openstreetmap.org/{rev['osm_type']}/{rev['osm_id']}" if rev.get("osm_type") and rev.get("osm_id") else None,
    }


# ------------------------------ Wikipedia / Wikidata ------------------------


async def _wiki(client: httpx.AsyncClient, params: dict) -> dict:
    r = await client.get(WIKI_API, params={**params, "format": "json", "formatversion": 2}, timeout=12)
    r.raise_for_status()
    return r.json()


async def wiki_geosearch(client: httpx.AsyncClient, lat: float, lng: float) -> list[tuple[str, float]]:
    d = await _wiki(client, {"action": "query", "list": "geosearch", "gscoord": f"{lat}|{lng}", "gsradius": 600, "gslimit": 8})
    return [(g["title"], float(g["dist"])) for g in d.get("query", {}).get("geosearch", [])]


async def wiki_find(client: httpx.AsyncClient, name: str, context: str) -> Optional[str]:
    if name.lower().endswith(" district") is False and context == "district":
        hit = await wiki_find(client, f"{name} district", "")
        if hit:
            return hit
        context = ""
    d = await _wiki(client, {"action": "query", "list": "search", "srsearch": f"{name} {context}".strip(), "srlimit": 3})
    for hit in d.get("query", {}).get("search", []):
        # Only accept an article that is actually about this name, never a loosely related one.
        if name.lower() in hit["title"].lower():
            return hit["title"]
    return None


def _trim_extract(text: str) -> str:
    """Keep the intro plus any history section; drop the rest."""
    parts = re.split(r"\n(==+)\s*(.+?)\s*\1\n", text)
    intro = parts[0].strip()
    history = []
    for i in range(1, len(parts) - 2, 3):
        heading, body = parts[i + 1], parts[i + 2]
        if re.search(r"histor|etymolog|origin|name|founding|partition|colonial|mughal|ancient|medieval", heading, re.I):
            history.append(f"{heading}: {body.strip()}")
    out = (intro + "\n" + "\n".join(history)).strip()
    return out[:MAX_SOURCE_CHARS]


async def wiki_extract(client: httpx.AsyncClient, title: str) -> Optional[tuple[str, str]]:
    d = await _wiki(client, {"action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "wiki", "redirects": 1, "titles": title})
    pages = d.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None
    text = _trim_extract(pages[0].get("extract", ""))
    return (pages[0]["title"], text) if len(text) > 80 else None


async def wikidata_nearby(client: httpx.AsyncClient, lat: float, lng: float) -> list[str]:
    q = f"""SELECT ?itemLabel ?itemDescription ?dist ?inception ?dissolved WHERE {{
      SERVICE wikibase:around {{ ?item wdt:P625 ?loc . bd:serviceParam wikibase:center "Point({lng} {lat})"^^geo:wktLiteral .
        bd:serviceParam wikibase:radius "0.4" . bd:serviceParam wikibase:distance ?dist . }}
      OPTIONAL {{ ?item wdt:P571 ?inception }} OPTIONAL {{ ?item wdt:P576 ?dissolved }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }} ORDER BY ?dist LIMIT 25"""
    r = await client.get(WIKIDATA_SPARQL, params={"query": q}, headers={"Accept": "application/sparql-results+json"}, timeout=15)
    r.raise_for_status()
    lines = []
    for b in r.json()["results"]["bindings"]:
        label = b.get("itemLabel", {}).get("value", "")
        if not label or re.fullmatch(r"Q\d+", label):
            continue
        desc = b.get("itemDescription", {}).get("value", "")
        dist = round(float(b["dist"]["value"]) * 1000)
        dates = []
        if b.get("inception"):
            dates.append(f"founded/built {b['inception']['value'][:4]}")
        if b.get("dissolved"):
            dates.append(f"ended {b['dissolved']['value'][:4]}")
        lines.append(f"- {label} ({desc}) {dist} m away" + (f", {', '.join(dates)}" if dates else ""))
    return lines


async def _safe(coro, label: str):
    try:
        return await coro
    except Exception as exc:  # one failing source must never sink the whole lookup
        logger.warning("source %s failed: %s", label, exc)
        return None


async def gather_sources(place: dict, lat: float, lng: float) -> list[dict]:
    context = " ".join(x for x in [place.get("city"), place.get("state")] if x)
    async with httpx.AsyncClient(headers={"User-Agent": UA}) as c:
        geo, wd, *level_titles = await asyncio.gather(
            _safe(wiki_geosearch(c, lat, lng), "geosearch"),
            _safe(wikidata_nearby(c, lat, lng), "wikidata"),
            *[
                _safe(wiki_find(c, name, context if scope in ("spot", "street", "neighbourhood") else ("district" if scope == "district" else "")), f"find:{name}")
                for scope, name in place["levels"]
            ],
        )
        candidates: list[tuple[str, str]] = []
        spot_name = (place["levels"][0][1] if place["levels"] and place["levels"][0][0] in ("spot", "street") else "").lower()
        for title, dist in (geo or [])[:5]:
            # Only an article named after this very spot is "about this spot"; other nearby articles are context.
            candidates.append(("spot" if spot_name and spot_name in title.lower() else "neighbourhood", title))
        for (scope, _), title in zip(place["levels"], level_titles):
            if title:
                candidates.append(("region" if scope == "district" else scope, title))
        seen, unique = set(), []
        for scope, title in candidates:
            if title not in seen:
                seen.add(title)
                unique.append((scope, title))
        extracts = await asyncio.gather(*[_safe(wiki_extract(c, t), f"extract:{t}") for _, t in unique[:9]])

    sources: list[dict] = []
    for (scope, _), ext in zip(unique[:9], extracts):
        if ext:
            title, text = ext
            sources.append({"type": "wikipedia", "title": title, "url": f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}", "scope": scope, "text": text})
    if wd:
        sources.append({"type": "wikidata", "title": "Wikidata: mapped places within 400 m", "url": f"https://www.wikidata.org/wiki/Special:Nearby#/coord/{lat},{lng}", "scope": "spot", "text": "\n".join(wd)[:MAX_SOURCE_CHARS]})
    sources.append({"type": "openstreetmap", "title": "OpenStreetMap address", "url": place.get("osm_url") or "https://www.openstreetmap.org", "scope": "street", "text": place.get("display_name", "")})
    for i, s in enumerate(sources, start=1):
        s["id"] = i
    return sources


# ------------------------------ composition ---------------------------------

SYSTEM = """You write the history of a precise spot for a camera app, using ONLY the numbered sources given.
Rules:
- Never use outside knowledge. Every sentence must be supported by the cited sources.
- For each era give what is known about THIS spot. If sources only describe the wider area, write about the
  wider area and set scope accordingly: spot (this building/site), street, neighbourhood, city, region.
  Prefer the narrowest scope the sources support.
- If sources say the area was farmland, forest, a village, a river bed, outside the city etc. in an era, say so.
- If nothing in the sources covers an era, return text "" and scope "none". Do not guess.
- Never fill an era by just restating the place's name or address; that is not history.
- Write plain narrative. Never mention "scope", "sources", "the sources do not..." or "this site/spot is not
  described" in the text; the app shows scope and citations separately.
- 1-3 short sentences per era, plain English, concrete dates and names. No hedging filler.
- Put a fact in an era only if the source dates it to that era. Do not repeat the same fact or the same
  generic city sentence across several eras; if an era would only repeat something, leave it empty.
- A nearby landmark's article describes that landmark, not this street. Refer to it as nearby ("the nearby X")
  and never describe it as if it were this spot.
- then_now: one sentence contrasting the earliest known state of this spot with today (or "" if unsupported).
- did_you_know: up to 3 surprising, specific facts from the sources about this spot or street (each <= 25 words).
Return ONLY JSON:
{"summary": str, "summary_sources": [int], "eras": [{"key": one of %s, "heading": str (<= 8 words), "text": str, "scope": one of %s or "none", "sources": [int]}], "then_now": str, "then_now_sources": [int], "did_you_know": [{"text": str, "sources": [int]}]}
Include all 8 era keys in order.""" % (ERA_KEYS, SCOPES)


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    start, end = raw.find("{"), raw.rfind("}")
    return json.loads(raw[start : end + 1])


async def compose_history(api_key: str, place: dict, sources: list[dict]) -> dict:
    src_block = "\n\n".join(f"[{s['id']}] ({s['type']}, about the {s['scope']}) {s['title']}\n{s['text']}" for s in sources if s["type"] != "openstreetmap")
    prompt = f"Spot: {place['title']} — {place['display_name']}\n\nSOURCES:\n{src_block}"
    chat = LlmChat(api_key=api_key, session_id=f"nvm-{uuid.uuid4()}", system_message=SYSTEM).with_model(LLM_PROVIDER, LLM_MODEL)
    chunks: list[str] = []
    async for ev in chat.stream_message(UserMessage(text=prompt)):
        if isinstance(ev, TextDelta):
            chunks.append(ev.content)
        elif isinstance(ev, StreamDone):
            break
    data = _parse_json("".join(chunks))

    valid_ids = {s["id"] for s in sources if s["type"] != "openstreetmap"}  # the map address is never a history citation

    def cited(text_key: str, ids_key: str, limit: int) -> str:
        ids = [i for i in data.get(ids_key, []) if i in valid_ids]
        return str(data.get(text_key, "")).strip()[:limit] if ids else ""
    by_key = {e.get("key"): e for e in data.get("eras", []) if isinstance(e, dict)}
    eras = []
    for key, label in ERAS:
        e = by_key.get(key, {})
        ids = [i for i in e.get("sources", []) if i in valid_ids]
        text = str(e.get("text", "")).strip()
        scope = e.get("scope") if e.get("scope") in SCOPES else "none"
        if not text or not ids:  # an era without a cited source is dropped, never shown as fact
            text, scope, ids = "", "none", []
        eras.append({"key": key, "label": label, "heading": str(e.get("heading", "")).strip()[:80] if text else "", "text": text[:600], "scope": scope, "sources": ids})
    dyk = [
        {"text": str(d.get("text", "")).strip()[:220], "sources": [i for i in d.get("sources", []) if i in valid_ids]}
        for d in data.get("did_you_know", [])[:3]
        if isinstance(d, dict) and d.get("text")
    ]
    return {
        "summary": cited("summary", "summary_sources", 300),
        "eras": eras,
        "then_now": cited("then_now", "then_now_sources", 300),
        "did_you_know": [d for d in dyk if d["sources"]],
    }


def empty_history() -> dict:
    return {
        "summary": "",
        "eras": [{"key": k, "label": label, "heading": "", "text": "", "scope": "none", "sources": []} for k, label in ERAS],
        "then_now": "",
        "did_you_know": [],
    }
