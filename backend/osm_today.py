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
