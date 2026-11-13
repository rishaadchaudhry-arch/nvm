"""Builds an era-by-era history for any spot from open data.

Pipeline (every source is public and global, so widening beyond the configured area needs no new code):
1. OpenStreetMap / Nominatim reverse-geocode -> street, neighbourhood, city, district, state, plus any
   historic/heritage/start_date tags on the address itself.
2. Wikipedia in English, Hindi and Urdu: articles geotagged near the spot, the other-language versions of
   those, and the article for each named level (street, neighbourhood, city ...).
3. Wikidata: items within 800 m with founding / dissolution dates and any official heritage protection,
   which is what surfaces an ASI Monument of National Importance.
4. Overpass: everything OpenStreetMap records nearby as historic, heritage-listed or dated.
5. The LLM may ONLY arrange those fetched facts into eras. Every era carries a scope (how close the fact is to
   the exact spot) and the ids of the sources it came from. Eras with no supporting source stay empty.
"""

import asyncio
import hashlib
import json
import logging
import math
import re
import time
from typing import Optional
from urllib.parse import quote

import httpx

import openai_voice

logger = logging.getLogger(__name__)

UA = "NVM-app/1.0 (street history lookup; contact: dev@nvm.app)"
# Hindi and Urdu Wikipedia both carry lanes and mohallas that English misses; for Shahjahanabad in
# particular, Urdu is often the only encyclopaedia with an article at all.
OTHER_LANGS = ("hi", "ur")
LANG_NAMES = {"hi": "Hindi", "ur": "Urdu"}
NOMINATIM = "https://nominatim.openstreetmap.org"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

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


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


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
        data = await _nominatim(c, "reverse", {"lat": lat, "lon": lng, "zoom": 17, "addressdetails": 1, "extratags": 1})
    return None if not data or "error" in data else data


async def search_places(q: str, country: str = "in", viewbox: Optional[str] = None) -> list[dict]:
    params = {"q": q, "countrycodes": country, "limit": 8, "addressdetails": 1}
    if viewbox:
        params |= {"viewbox": viewbox, "bounded": 1}  # bounded=1 discards hits outside the box entirely
    async with httpx.AsyncClient(headers={"User-Agent": UA}) as c:
        rows = await _nominatim(c, "search", params)
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
        "osm_tags": rev.get("extratags") or {},
        "osm_url": f"https://www.openstreetmap.org/{rev['osm_type']}/{rev['osm_id']}" if rev.get("osm_type") and rev.get("osm_id") else None,
    }


# ------------------------------ Wikipedia / Wikidata ------------------------


async def _wiki(client: httpx.AsyncClient, params: dict, lang: str = "en") -> dict:
    r = await client.get(f"https://{lang}.wikipedia.org/w/api.php", params={**params, "format": "json", "formatversion": 2}, timeout=12)
    r.raise_for_status()
    return r.json()


async def wiki_geosearch(client: httpx.AsyncClient, lat: float, lng: float, lang: str = "en") -> list[tuple[str, float]]:
    d = await _wiki(client, {"action": "query", "list": "geosearch", "gscoord": f"{lat}|{lng}", "gsradius": 600, "gslimit": 8}, lang)
    return [(g["title"], float(g["dist"])) for g in d.get("query", {}).get("geosearch", [])]


async def wiki_langlink(client: httpx.AsyncClient, title: str, lang: str) -> Optional[str]:
    """The same article in another language, via Wikipedia's own interlanguage links."""
    d = await _wiki(client, {"action": "query", "prop": "langlinks", "lllang": lang, "redirects": 1, "titles": title})
    for p in d.get("query", {}).get("pages", []):
        for ll in p.get("langlinks", []):
            if ll.get("lang") == lang and ll.get("title"):
                return ll["title"]
    return None


async def hi_wiki_find(client: httpx.AsyncClient, name: str, context: str) -> Optional[str]:
    """Hindi article for an English place name: accept a hit only if its intro mentions that name."""
    d = await _wiki(client, {"action": "query", "list": "search", "srsearch": f"{name} {context}".strip(), "srlimit": 3}, "hi")
    hits = [h["title"] for h in d.get("query", {}).get("search", [])]
    if not hits:
        return None
    intros = await asyncio.gather(*[_safe(wiki_extract(client, t, "hi"), f"hi-intro:{t}") for t in hits])
    for title, ext in zip(hits, intros):
        if ext and name.lower() in ext[1][:600].lower():
            return title
    return None


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
        if re.search(r"histor|etymolog|origin|name|founding|partition|colonial|mughal|ancient|medieval|इतिहास|नाम|उत्पत्ति|स्थापना|प्राचीन|मध्यकाल|मुग़ल|मुगल|विभाजन|औपनिवेशिक|ब्रिटिश", heading, re.I):
            history.append(f"{heading}: {body.strip()}")
    out = (intro + "\n" + "\n".join(history)).strip()
    return out[:MAX_SOURCE_CHARS]


async def wiki_extract(client: httpx.AsyncClient, title: str, lang: str = "en") -> Optional[tuple[str, str]]:
    d = await _wiki(client, {"action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "wiki", "redirects": 1, "titles": title}, lang)
    pages = d.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None
    text = _trim_extract(pages[0].get("extract", ""))
    return (pages[0]["title"], text) if len(text) > 80 else None


WIKIDATA_RADIUS_KM = 0.8


async def wikidata_nearby(client: httpx.AsyncClient, lat: float, lng: float) -> list[str]:
    """Mapped items near the spot, with their dates and any official heritage protection.

    The heritage designation (P1435) is what surfaces an ASI Monument of National Importance or a
    state-protected monument, which for Delhi is the difference between "an old building" and a
    dated, officially recorded one.
    """
    q = f"""SELECT ?itemLabel ?itemDescription ?dist ?inception ?dissolved ?heritageLabel WHERE {{
      SERVICE wikibase:around {{ ?item wdt:P625 ?loc . bd:serviceParam wikibase:center "Point({lng} {lat})"^^geo:wktLiteral .
        bd:serviceParam wikibase:radius "{WIKIDATA_RADIUS_KM}" . bd:serviceParam wikibase:distance ?dist . }}
      OPTIONAL {{ ?item wdt:P571 ?inception }} OPTIONAL {{ ?item wdt:P576 ?dissolved }}
      OPTIONAL {{ ?item wdt:P1435 ?heritage }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }} ORDER BY ?dist LIMIT 60"""
    r = await client.get(WIKIDATA_SPARQL, params={"query": q}, headers={"Accept": "application/sparql-results+json"}, timeout=20)
    r.raise_for_status()
    rows: dict[str, str] = {}  # one line per item; a second heritage designation repeats the row
    for b in r.json()["results"]["bindings"]:
        label = b.get("itemLabel", {}).get("value", "")
        if not label or re.fullmatch(r"Q\d+", label) or label in rows:
            continue
        desc = b.get("itemDescription", {}).get("value", "")
        dist = round(float(b["dist"]["value"]) * 1000)
        bits = []
        if b.get("inception"):
            bits.append(f"founded/built {b['inception']['value'][:4]}")
        if b.get("dissolved"):
            bits.append(f"ended {b['dissolved']['value'][:4]}")
        heritage = b.get("heritageLabel", {}).get("value", "")
        if heritage and not re.fullmatch(r"Q\d+", heritage):
            bits.append(f"officially protected as: {heritage}")
        rows[label] = f"- {label} ({desc}) {dist} m away" + (f", {', '.join(bits)}" if bits else "")
    return list(rows.values())


# Tags that carry history. Nominatim gives them for the matched address; Overpass finds everything
# standing nearby, which is what catches an unnamed tomb or gateway in the middle of a lane.
_OSM_TAG_LABELS = {
    "historic": "historic",
    "heritage": "heritage listing level",
    "heritage:operator": "listed by",
    "ref:asi": "ASI reference",
    "start_date": "built",
    "building": "building",
    "inscription": "inscription",
    "architect": "architect",
    "religion": "religion",
    "wikipedia": "wikipedia",
}


def _osm_feature_line(tags: dict, dist: Optional[int]) -> Optional[str]:
    name = tags.get("name:en") or tags.get("name") or tags.get("name:hi") or tags.get("name:ur")
    bits = []
    for key, label in _OSM_TAG_LABELS.items():
        val = tags.get(key)
        if val and key != "building":
            bits.append(f"{label} {val}")
        elif val and key == "building" and val not in ("yes", "house"):
            bits.append(f"{label} {val}")
    if not bits:
        return None
    head = name or "unnamed feature"
    where = f", {dist} m away" if dist is not None else ""
    return f"- {head}: {'; '.join(bits)}{where}"


# Heritage features nearby no longer come from Overpass at build time: they are imported into our own
# database once (see osm_heritage.py) and passed into gather_sources by the caller.


async def _safe(coro, label: str):
    try:
        return await coro
    except Exception as exc:  # one failing source must never sink the whole lookup
        logger.warning("source %s failed: %s", label, exc)
        return None


async def gather_sources(place: dict, lat: float, lng: float, heritage_lines: Optional[list[str]] = None) -> list[dict]:
    context = " ".join(x for x in [place.get("city"), place.get("state")] if x)
    levels: list[tuple[str, str]] = [(s, n) for s, n in (place.get("levels") or [])]
    async with httpx.AsyncClient(headers={"User-Agent": UA}) as c:
        fixed, *level_titles = await asyncio.gather(
            asyncio.gather(
                _safe(wiki_geosearch(c, lat, lng), "geosearch"),
                _safe(wikidata_nearby(c, lat, lng), "wikidata"),
                *[_safe(wiki_geosearch(c, lat, lng, lang), f"geosearch:{lang}") for lang in OTHER_LANGS],
            ),
            *[
                _safe(wiki_find(c, name, context if scope in ("spot", "street", "neighbourhood") else ("district" if scope == "district" else "")), f"find:{name}")
                for scope, name in levels
            ],
        )
        geo, wd = fixed[0], fixed[1]
        geo_other = dict(zip(OTHER_LANGS, fixed[2:]))
        candidates: list[tuple[str, str]] = []
        spot_name = (levels[0][1] if levels and levels[0][0] in ("spot", "street") else "").lower()
        for title, dist in (geo or [])[:5]:
            # Only an article named after this very spot is "about this spot"; other nearby articles are context.
            candidates.append(("spot" if spot_name and spot_name in title.lower() else "neighbourhood", title))
        for (scope, _), title in zip(levels, level_titles):
            if title:
                candidates.append(("region" if scope == "district" else scope, title))
        seen, unique = set(), []
        for scope, title in candidates:
            if title not in seen:
                seen.add(title)
                unique.append((scope, title))
        unique = unique[:9]

        # Other-language Wikipedias: that language's version of each English article, plus its own
        # geotagged articles nearby. For Hindi we also search by name, which works because an English
        # place name usually survives into the Hindi text; in Urdu script it does not, so that search
        # would match on nothing but noise and is skipped.
        narrow_levels = [(s, n) for s, n in levels if s in ("spot", "street", "neighbourhood", "city")]

        async def lang_candidates(lang: str) -> list[tuple[str, str]]:
            links, *found = await asyncio.gather(
                asyncio.gather(*[_safe(wiki_langlink(c, t, lang), f"langlink:{lang}:{t}") for _, t in unique]),
                *(
                    [_safe(hi_wiki_find(c, name, context if scope != "city" else place.get("state") or ""), f"hi-find:{name}") for scope, name in narrow_levels]
                    if lang == "hi"
                    else []
                ),
            )
            out: list[tuple[str, str]] = []
            for (scope, _), title in zip(unique, links):
                if title:
                    out.append((scope, title))
            for title, _dist in (geo_other.get(lang) or [])[:4]:
                out.append(("neighbourhood", title))
            for (scope, _), title in zip(narrow_levels, found):
                if title:
                    out.append((scope, title))
            seen_l, uniq_l = set(), []
            for scope, title in out:
                if title not in seen_l:
                    seen_l.add(title)
                    uniq_l.append((scope, title))
            return uniq_l[:6]

        per_lang = dict(zip(OTHER_LANGS, await asyncio.gather(*[lang_candidates(lang) for lang in OTHER_LANGS])))

        extracts, *other_extracts = await asyncio.gather(
            asyncio.gather(*[_safe(wiki_extract(c, t), f"extract:{t}") for _, t in unique]),
            *[asyncio.gather(*[_safe(wiki_extract(c, t, lang), f"extract:{lang}:{t}") for _, t in per_lang[lang]]) for lang in OTHER_LANGS],
        )

    sources: list[dict] = []
    for lang, items, exts in [("en", unique, extracts)] + [(lang, per_lang[lang], other_extracts[i]) for i, lang in enumerate(OTHER_LANGS)]:
        for (scope, _), ext in zip(items, exts):
            if ext:
                title, text = ext
                sources.append({"type": "wikipedia", "lang": lang, "title": title, "url": f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}", "scope": scope, "text": text})
    if wd:
        sources.append({"type": "wikidata", "title": f"Wikidata: mapped places within {round(WIKIDATA_RADIUS_KM * 1000)} m", "url": f"https://www.wikidata.org/wiki/Special:Nearby#/coord/{lat},{lng}", "scope": "spot", "text": "\n".join(wd)[:MAX_SOURCE_CHARS]})
    # "openstreetmap_heritage" is citable; plain "openstreetmap" stays the bare address, which never is.
    if heritage_lines:
        sources.append({"type": "openstreetmap_heritage", "title": "OpenStreetMap: historic and heritage-listed features nearby", "url": f"https://www.openstreetmap.org/#map=18/{lat}/{lng}", "scope": "spot", "text": "\n".join(heritage_lines)[:MAX_SOURCE_CHARS]})
    osm_tags = _osm_feature_line(place.get("osm_tags") or {}, None)
    if osm_tags:
        sources.append({"type": "openstreetmap_heritage", "title": "OpenStreetMap: tags on this address itself", "url": place.get("osm_url") or "https://www.openstreetmap.org", "scope": "spot", "text": osm_tags})
    sources.append({"type": "openstreetmap", "title": "OpenStreetMap address", "url": place.get("osm_url") or "https://www.openstreetmap.org", "scope": "street", "text": place.get("display_name", "")})
    for i, s in enumerate(sources, start=1):
        s["id"] = i
    return sources


# ------------------------------ composition ---------------------------------

SYSTEM = """You write the history of a precise spot for a camera app, using ONLY the numbered sources given.
Rules:
- Never use outside knowledge. Every sentence must be supported by the cited sources.
- Some sources are in Hindi or Urdu (from Hindi and Urdu Wikipedia). Read them like any other source, translate
  the facts you use into English, and cite them by number. Keep Indian names and terms as they are commonly
  written in English.
- The openstreetmap_heritage source is a list of what physically stands near this spot, each item with its
  distance in metres and, where recorded, what it is, when it was built and how it is protected. It is the most
  precise source you have about this spot's immediate surroundings, so use it: name what stands close by and
  how far, and use its dates. Never state a distance or date it does not give, and do not list features for
  their own sake - only where they tell you something about an era.
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
    src_block = "\n\n".join(
        f"[{s['id']}] ({s['type']}{' in ' + LANG_NAMES[s['lang']] if LANG_NAMES.get(s.get('lang')) else ''}, about the {s['scope']}) {s['title']}\n{s['text']}"
        for s in sources
        if s["type"] != "openstreetmap"
    )
    prompt = f"Spot: {place['title']} — {place['display_name']}\n\nSOURCES:\n{src_block}"
    data = _parse_json(await openai_voice.generate_text(api_key, SYSTEM, prompt))

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
