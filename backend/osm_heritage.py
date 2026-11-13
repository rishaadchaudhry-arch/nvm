"""Delhi's historic and heritage-listed features, held in our own database.

OpenStreetMap knows a great deal that Wikipedia does not: the baoli behind the fort, the unnamed
tomb in a lane, the gateway with a date carved on it. The public Overpass service that serves it is
free and often overloaded — 50 seconds one minute, HTTP 502 the next — so it is no good at the
moment a person points their camera at a street.

So we fetch it once, tile by tile, and keep it. Lookups then cost a local geo query, every street
gets the same answer every time, and Overpass being down stops mattering.

Re-run the import when you want fresher data; it upserts, so nothing is lost if it stops halfway.
"""

import asyncio
import logging
from typing import Iterable, Optional

import httpx

logger = logging.getLogger(__name__)

# Several hosts run the same API. The main one is the most often overloaded, so it goes last.
OVERPASS_HOSTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
UA = "NVM-app/1.0 (street history lookup; contact: dev@nvm.app)"

# Tags that say something about a feature's history. Anything carrying one of these is worth keeping.
HERITAGE_FILTERS = ['["historic"]', '["heritage"]', '["start_date"]', '["inscription"]', '["ruins"]']

# Tags we keep on each feature. Everything else is noise for our purpose.
KEEP_TAGS = (
    "name", "name:en", "name:hi", "name:ur", "alt_name", "old_name",
    "historic", "heritage", "heritage:operator", "ref:asi", "ruins",
    "start_date", "inscription", "architect", "building", "amenity",
    "religion", "denomination", "tourism", "wikipedia", "wikidata", "description",
)


def tile_bboxes(bbox: tuple[float, float, float, float], step: float = 0.08) -> list[tuple[float, float, float, float]]:
    """Split a bounding box into Overpass-sized tiles (min_lat, min_lng, max_lat, max_lng)."""
    min_lng, min_lat, max_lng, max_lat = bbox
    tiles = []
    lat = min_lat
    while lat < max_lat:
        lng = min_lng
        while lng < max_lng:
            tiles.append((lat, lng, min(lat + step, max_lat), min(lng + step, max_lng)))
            lng += step
        lat += step
    return tiles


def _query(tile: tuple[float, float, float, float]) -> str:
    s, w, n, e = tile
    box = f"{s},{w},{n},{e}"
    parts = "".join(f"nwr{f}({box});" for f in HERITAGE_FILTERS)
    return f"[out:json][timeout:90];({parts});out center tags;"


async def fetch_tile(client: httpx.AsyncClient, tile: tuple[float, float, float, float]) -> list[dict]:
    """One tile, trying each host in turn. Raises only if every host failed."""
    last: Optional[Exception] = None
    for host in OVERPASS_HOSTS:
        try:
            r = await client.post(host, data={"data": _query(tile)}, timeout=120)
            r.raise_for_status()
            return r.json().get("elements", [])
        except Exception as exc:
            last = exc
            logger.warning("overpass tile %s failed on %s: %s", tile, host.split("/")[2], exc)
            await asyncio.sleep(2)
    raise RuntimeError(f"every Overpass host failed for tile {tile}: {last}")


def to_record(el: dict) -> Optional[dict]:
    """An Overpass element as a document we can store, or None if it carries nothing useful."""
    tags = el.get("tags") or {}
    kept = {k: v for k, v in tags.items() if k in KEEP_TAGS}
    if not any(k in kept for k in ("historic", "heritage", "start_date", "inscription", "ruins")):
        return None
    centre = el if el.get("lat") is not None else (el.get("center") or {})
    lat, lng = centre.get("lat"), centre.get("lon")
    if lat is None or lng is None:
        return None
    return {
        "osm_id": f"{el.get('type')}/{el.get('id')}",
        "tags": kept,
        "location": {"type": "Point", "coordinates": [float(lng), float(lat)]},
        "lat": float(lat),
        "lng": float(lng),
    }


async def import_bbox(db, bbox: tuple[float, float, float, float], progress: Optional[dict] = None) -> dict:
    """Fetch every heritage feature in the box and upsert it. Safe to re-run and to interrupt."""
    tiles = tile_bboxes(bbox)
    if progress is not None:
        progress.update({"state": "running", "tiles_total": len(tiles), "tiles_done": 0, "features": 0, "failed_tiles": 0})
    stored, failed = 0, 0
    async with httpx.AsyncClient(headers={"User-Agent": UA}) as client:
        for i, tile in enumerate(tiles, start=1):
            try:
                elements = await fetch_tile(client, tile)
            except Exception as exc:
                failed += 1
                logger.error("tile %s/%s gave up: %s", i, len(tiles), exc)
                elements = []
            records = [r for r in (to_record(e) for e in elements) if r]
            for rec in records:
                await db.osm_heritage.update_one({"osm_id": rec["osm_id"]}, {"$set": rec}, upsert=True)
            stored += len(records)
            if progress is not None:
                progress.update({"tiles_done": i, "features": stored, "failed_tiles": failed})
            logger.info("osm heritage: tile %s/%s -> %s features (%s stored so far)", i, len(tiles), len(records), stored)
            await asyncio.sleep(1)  # the public instances are shared; do not hammer them
    total = await db.osm_heritage.count_documents({})
    result = {"state": "done", "tiles_total": len(tiles), "tiles_done": len(tiles), "features": stored, "failed_tiles": failed, "total_in_db": total}
    if progress is not None:
        progress.update(result)
    return result


async def nearby(db, lat: float, lng: float, radius_m: int = 350, limit: int = 40) -> list[dict]:
    """Stored features near a point, nearest first, each with its distance in metres."""
    cursor = db.osm_heritage.aggregate(
        [
            {
                "$geoNear": {
                    "near": {"type": "Point", "coordinates": [lng, lat]},
                    "distanceField": "dist_m",
                    "maxDistance": radius_m,
                    "spherical": True,
                }
            },
            {"$limit": limit},
            {"$project": {"_id": 0, "tags": 1, "dist_m": 1, "osm_id": 1}},
        ]
    )
    return [doc async for doc in cursor]


def as_lines(features: Iterable[dict]) -> list[str]:
    """One readable line per feature, for the model to cite."""
    labels = {
        "historic": "historic",
        "ruins": "ruins",
        "heritage": "heritage listing level",
        "heritage:operator": "listed by",
        "ref:asi": "ASI reference",
        "start_date": "built",
        "inscription": "inscription",
        "architect": "architect",
        "religion": "religion",
        "denomination": "denomination",
        "description": "described as",
    }
    out = []
    for f in features:
        tags = f.get("tags") or {}
        name = tags.get("name:en") or tags.get("name") or tags.get("name:hi") or tags.get("name:ur")
        bits = [f"{label} {tags[key]}" for key, label in labels.items() if tags.get(key)]
        if tags.get("old_name"):
            bits.append(f"formerly called {tags['old_name']}")
        if not bits:
            continue
        dist = f", {round(f['dist_m'])} m away" if f.get("dist_m") is not None else ""
        out.append(f"- {name or 'unnamed feature'}: {'; '.join(bits)}{dist}")
    return out
