"""What a Delhi street is now: its shops, eateries, markets, places of worship and nearest metro.

The history sources stop at "today" with whatever Wikipedia happens to say. OpenStreetMap knows the
present street in detail - that the Dariba is still lined with jewellers, that a lane is all paper
merchants, where the nearest metro is. Like the heritage features, it is imported once into our own
database, tile by tile, so a lookup is a local geo query.

What the history needs from it is not a directory but a character: what the street is known for
(counted by trade), a few named places worth knowing, and how to get there.
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from typing import Optional

import httpx

from osm_heritage import TIMEOUT, UA, fetch_tile, tile_bboxes

logger = logging.getLogger(__name__)

TILE_STEP = 0.04  # Delhi's markets are dense; bigger tiles time out on the public servers
AMENITIES = "restaurant|cafe|fast_food|marketplace|place_of_worship|cinema|theatre|library|college|university|hospital|arts_centre"
TOURISM = "attraction|museum|gallery|hotel|guest_house|viewpoint"
KEEP_TAGS = (
    "name", "name:en", "shop", "amenity", "cuisine", "tourism", "religion", "railway", "station", "subway",
    "leisure", "wikidata", "wikipedia", "start_date", "brand", "operator", "network", "line", "colour",
)
NOTABLE_RADIUS_M = 150
METRO_RADIUS_M = 2500


def _query(tile: tuple[float, float, float, float]) -> str:
    s, w, n, e = tile
    box = f"{s},{w},{n},{e}"
    parts = [
        f'nwr["shop"]["name"]({box});',
        f'nwr["amenity"~"^({AMENITIES})$"]["name"]({box});',
        f'nwr["tourism"~"^({TOURISM})$"]["name"]({box});',
        f'nwr["railway"="station"]["name"]({box});',
        f'nwr["leisure"="park"]["name"]({box});',
    ]
    return f"[out:json][timeout:120];({''.join(parts)});out center tags;"


def kind_of(tags: dict) -> Optional[str]:
    """A short, readable kind: 'jewellery shop', 'sweet shop', 'Mughlai restaurant', 'metro station'."""
    if tags.get("railway") == "station":
        return "metro station" if tags.get("station") == "subway" or "metro" in (tags.get("network", "") + tags.get("operator", "")).lower() else "railway station"
    if tags.get("shop"):
        shop = tags["shop"].replace("_", " ")
        shop = {"jewelry": "jewellery", "confectionery": "sweet", "clothes": "clothes", "yes": "general", "convenience": "general"}.get(shop, shop)
        return f"{shop} shop"
    if tags.get("amenity"):
        a = tags["amenity"].replace("_", " ")
        if a == "place of worship":
            return {"muslim": "mosque", "hindu": "temple", "sikh": "gurdwara", "christian": "church", "jain": "Jain temple"}.get(tags.get("religion", ""), "place of worship")
        if a in ("restaurant", "fast food", "cafe") and tags.get("cuisine"):
            return f"{tags['cuisine'].split(';')[0].replace('_', ' ')} {('eatery' if a == 'fast food' else a)}"
        return {"fast food": "eatery", "marketplace": "market"}.get(a, a)
    if tags.get("tourism"):
        return tags["tourism"].replace("_", " ")
    if tags.get("leisure") == "park":
        return "park"
    return None


def to_record(el: dict) -> Optional[dict]:
    tags = {k: v for k, v in (el.get("tags") or {}).items() if k in KEEP_TAGS}
    kind = kind_of(tags)
    centre = el if el.get("lat") is not None else (el.get("center") or {})
    lat, lng = centre.get("lat"), centre.get("lon")
    if not kind or lat is None or lng is None:
        return None
    return {
        "osm_id": f"{el.get('type')}/{el.get('id')}",
        "kind": kind,
        "name": tags.get("name:en") or tags.get("name"),
        "tags": tags,
        "location": {"type": "Point", "coordinates": [float(lng), float(lat)]},
    }


async def import_bbox(db, bbox: tuple[float, float, float, float], progress: Optional[dict] = None) -> dict:
    tiles = tile_bboxes(bbox, step=TILE_STEP)
    if progress is not None:
        progress.update({"state": "running", "tiles_total": len(tiles), "tiles_done": 0, "features": 0, "failed_tiles": 0})
    stored, failed = 0, 0
    async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=TIMEOUT) as client:
        for i, tile in enumerate(tiles, start=1):
            try:
                elements = await fetch_tile(client, tile, _query)
            except Exception as exc:
                failed += 1
                logger.error("today tile %s/%s gave up: %s", i, len(tiles), exc)
                elements = []
            for rec in (r for r in (to_record(e) for e in elements) if r):
                await db.osm_today.update_one({"osm_id": rec["osm_id"]}, {"$set": rec}, upsert=True)
                stored += 1
            if progress is not None:
                progress.update({"tiles_done": i, "features": stored, "failed_tiles": failed})
            await asyncio.sleep(1)
    result = {"state": "done", "tiles_total": len(tiles), "tiles_done": len(tiles), "features": stored,
              "failed_tiles": failed, "total_in_db": await db.osm_today.count_documents({})}
    if progress is not None:
        progress.update(result)
    return result


# ---- from a downloaded map file -----------------------------------------------------------------
# The public Overpass servers are often overloaded (504s, minutes per tile). Geofabrik publishes the
# whole of OpenStreetMap by region every day; the Northern Zone file holds Delhi, and reading it
# locally takes minutes, whatever the servers are doing.

GEOFABRIK_URL = "https://download.geofabrik.de/asia/india/northern-zone-latest.osm.pbf"
_AMENITY_SET = set(AMENITIES.split("|"))
_TOURISM_SET = set(TOURISM.split("|"))


def wanted(tags: dict) -> bool:
    """The same features the Overpass query asks for: named shops, eateries, worship, stations..."""
    if not (tags.get("name") or tags.get("name:en")):
        return False
    return bool(
        tags.get("shop")
        or tags.get("amenity") in _AMENITY_SET
        or tags.get("tourism") in _TOURISM_SET
        or tags.get("railway") == "station"
        or tags.get("leisure") == "park"
    )


def read_pbf(path: str, bbox: tuple[float, float, float, float]) -> list[dict]:
    """Every wanted feature inside bbox (min_lng, min_lat, max_lng, max_lat), as stored records."""
    import osmium  # imported here so the rest of the app runs without it

    min_lng, min_lat, max_lng, max_lat = bbox
    keys = ("shop", "amenity", "tourism", "railway", "leisure")
    out: list[dict] = []
    fp = osmium.FileProcessor(path, osmium.osm.NODE | osmium.osm.WAY).with_locations().with_filter(osmium.filter.KeyFilter(*keys))
    for obj in fp:
        tags = dict(obj.tags)
        if not wanted(tags):
            continue
        if obj.is_node():
            if not obj.location.valid():
                continue
            lat, lng, typ = obj.location.lat, obj.location.lon, "node"
        else:
            locs = [n.location for n in obj.nodes if n.location.valid()]
            if not locs:
                continue
            lat, lng, typ = sum(l.lat for l in locs) / len(locs), sum(l.lon for l in locs) / len(locs), "way"
        if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
            continue
        rec = to_record({"type": typ, "id": obj.id, "lat": lat, "lon": lng, "tags": tags})
        if rec:
            out.append(rec)
    return out


async def import_geofabrik(db, bbox: tuple[float, float, float, float], progress: Optional[dict] = None, url: str = GEOFABRIK_URL) -> dict:
    from pathlib import Path

    from pymongo import UpdateOne

    cache = Path(__file__).resolve().parent / "gazetteer_cache" / url.rsplit("/", 1)[-1]
    cache.parent.mkdir(exist_ok=True)
    if progress is not None:
        progress.update({"state": "downloading", "source": url, "mb": 0})
    if not cache.exists() or cache.stat().st_size < 10_000_000:
        tmp = cache.with_suffix(".part")
        async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=httpx.Timeout(30.0, read=120.0), follow_redirects=True) as client:
            async with client.stream("GET", url) as r:
                r.raise_for_status()
                done = 0
                with open(tmp, "wb") as fh:
                    async for chunk in r.aiter_bytes(1 << 20):
                        fh.write(chunk)
                        done += len(chunk)
                        if progress is not None:
                            progress["mb"] = round(done / 1e6)
        tmp.replace(cache)
    if progress is not None:
        progress.update({"state": "reading the map file"})
    records = await asyncio.to_thread(read_pbf, str(cache), bbox)
    if progress is not None:
        progress.update({"state": "storing", "features": len(records)})
    for i in range(0, len(records), 1000):
        await db.osm_today.bulk_write([UpdateOne({"osm_id": r["osm_id"]}, {"$set": r}, upsert=True) for r in records[i:i + 1000]], ordered=False)
    result = {"state": "done", "source": url, "features": len(records), "total_in_db": await db.osm_today.count_documents({})}
    if progress is not None:
        progress.update(result)
    return result


async def _near(db, lat: float, lng: float, radius_m: int, query: Optional[dict] = None, limit: int = 400) -> list[dict]:
    geo = {"near": {"type": "Point", "coordinates": [lng, lat]}, "distanceField": "dist_m", "maxDistance": radius_m, "spherical": True}
    if query:
        geo["query"] = query
    cursor = db.osm_today.aggregate([{"$geoNear": geo}, {"$limit": limit}, {"$project": {"_id": 0, "location": 0}}])
    return [d async for d in cursor]


async def describe(db, lat: float, lng: float) -> list[str]:
    """Lines for the model: what the street is known for now, named places worth knowing, nearest metro."""
    near = await _near(db, lat, lng, NOTABLE_RADIUS_M)
    lines: list[str] = []
    if near:
        counts = Counter(f["kind"] for f in near)
        top = [f"{n} {k}{'s' if n > 1 else ''}" for k, n in counts.most_common(8) if n >= 2]
        if top:
            lines.append(f"- Within {NOTABLE_RADIUS_M} m today: " + ", ".join(top))
        # Named places a reader might know: anything Wikipedia/Wikidata knows, attractions and
        # worship, then the nearest eateries and markets.
        def rank(f: dict) -> tuple:
            t = f.get("tags") or {}
            known = bool(t.get("wikidata") or t.get("wikipedia"))
            landmark = f["kind"] in ("attraction", "museum", "gallery", "market", "mosque", "temple", "gurdwara", "church", "Jain temple", "park")
            return (not known, not landmark, f["dist_m"])
        for f in sorted(near, key=rank)[:10]:
            if not f.get("name"):
                continue
            t = f.get("tags") or {}
            since = f", since {t['start_date']}" if t.get("start_date") else ""
            lines.append(f"- {f['name']} ({f['kind']}{since}), {round(f['dist_m'])} m away")
    metro = await _near(db, lat, lng, METRO_RADIUS_M, {"kind": "metro station"}, limit=1)
    if metro:
        m = metro[0]
        line = (m.get("tags") or {}).get("line") or (m.get("tags") or {}).get("colour")
        lines.append(f"- Nearest metro: {m['name']} station{f' ({line} line)' if line else ''}, about {round(m['dist_m'], -1):.0f} m away")
    return lines
