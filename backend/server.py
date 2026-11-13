import asyncio
import csv
import hashlib
import io
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, List, Literal, Optional

import emoji
import httpx
import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorClient
from pwdlib import PasswordHash
from pydantic import BaseModel, Field, field_validator
from pymongo import ASCENDING, DESCENDING, IndexModel
from starlette.middleware.cors import CORSMiddleware

import history_engine as he
import openai_voice
import osm_heritage
import photo_storage
import share_card

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

def _required(name: str) -> str:
    """Fail at startup with a readable message instead of a bare KeyError traceback."""
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set. Copy backend/.env.example to backend/.env and fill it in.")
    return value


MONGO_URL = _required("MONGO_URL")
DB_NAME = _required("DB_NAME")
OPENAI_API_KEY = _required("OPENAI_API_KEY")  # history writing + narration
ADMIN_EMAIL = _required("ADMIN_EMAIL").lower()
ADMIN_PASSWORD = _required("ADMIN_PASSWORD")
JWT_SECRET = _required("JWT_SECRET")
if len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET is too short to sign tokens safely. Use at least 32 characters: python -c \"import secrets; print(secrets.token_urlsafe(48))\"")
# Which patch of the world the app covers. Delhi NCT by default: the sources that make a street
# history worth reading (ASI listings, Shahjahanabad gazetteers, Urdu Wikipedia) are deep here and
# thin elsewhere, so the app is honest about its scope rather than pretending to cover India.
# Set SCOPE_BBOX to "" to lift the limit, or to "minLng,minLat,maxLng,maxLat" for somewhere else.
SCOPE_NAME = os.environ.get("SCOPE_NAME", "Delhi")
SCOPE_BBOX = os.environ.get("SCOPE_BBOX", "76.8382,28.4041,77.3485,28.8835")
# The box is a rectangle, so its corners catch Gurugram, Noida and Faridabad. The state the map
# actually reports is the exact test; the box only saves a lookup for points obviously far away.
SCOPE_STATE = os.environ.get("SCOPE_STATE", SCOPE_NAME)


def _parse_bbox(raw: str) -> Optional[tuple[float, float, float, float]]:
    try:
        min_lng, min_lat, max_lng, max_lat = (float(x) for x in raw.split(","))
    except (ValueError, AttributeError):
        if raw.strip():
            raise RuntimeError(f'SCOPE_BBOX must be "minLng,minLat,maxLng,maxLat" or empty, not {raw!r}')
        return None
    return min_lng, min_lat, max_lng, max_lat


SCOPE = _parse_bbox(SCOPE_BBOX)


def in_scope(lat: float, lng: float) -> bool:
    if not SCOPE:
        return True
    min_lng, min_lat, max_lng, max_lat = SCOPE
    return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng


UPVOTE_THRESHOLD = int(os.environ.get("UPVOTE_THRESHOLD") or 5)
TRUSTED_PROXY_HOPS = int(os.environ.get("TRUSTED_PROXY_HOPS") or 0)
BUILDS_PER_IP_PER_HOUR = int(os.environ.get("BUILDS_PER_IP_PER_HOUR") or 40)
JWT_ALG = "HS256"
TOKEN_MINUTES = 60 * 12
FACING_DISTANCE_M = 35  # how far ahead of the phone we look when the camera points somewhere
STORY_RADIUS_M = 150  # a verified story shows as "Did you know?" within this distance
DEVICES_PER_IP_PER_HOUR = 20
VOTES_PER_IP_PER_TRADITION = 3
PHOTO_MAX_BYTES = 8 * 1024 * 1024
ERA_LABELS = dict(he.ERAS)
IMPORT_MAX_ROWS = 200
IMPORT_MAX_BYTES = 2 * 1024 * 1024
# CSV header → field. Several spellings are accepted so a spreadsheet exported from elsewhere still imports.
IMPORT_ALIASES = {
    "street": {"street", "place", "place_key", "location", "address"},
    "era": {"era", "period", "century"},
    "body": {"body", "story", "text", "account", "story_text"},
    "told_by": {"told_by", "who", "who_told_it", "narrator", "source", "name"},
    "village": {"village", "town", "village_or_town", "village_town", "their_village_or_town", "from"},
    "collected_on": {"collected_on", "date", "date_collected", "collected"},
}
IMPORT_TEMPLATE = (
    "street,era,story,told_by,village,collected_on\n"
    'Nai Sarak Delhi,1900-1947,"My grandfather said the lane flooded every monsoon and the shops stood on stilts.","Shanti Devi, 82","Ballimaran, Old Delhi",2026-05-20\n'
)
EXPORT_COLUMNS = ["type", "id", "place_key", "place_title", "era", "era_label", "title", "body", "told_by", "village", "collected_on", "author", "status", "verified_by", "upvotes", "photo_url", "added_by", "created_at"]

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
photos = photo_storage.make_store(db)
logger = logging.getLogger(__name__)

TTS_CACHE_DIR = ROOT_DIR / "tts_cache"
TTS_CACHE_DIR.mkdir(exist_ok=True)
CARD_CACHE_DIR = ROOT_DIR / "card_cache"
CARD_CACHE_DIR.mkdir(exist_ok=True)

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummy-password-to-even-out-timing")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

INDEXES: dict[str, list[IndexModel]] = {
    "places": [IndexModel([("key", ASCENDING)], name="key", unique=True)],
    "histories": [IndexModel([("key", ASCENDING)], name="key", unique=True)],
    "geocode_cache": [IndexModel([("cell", ASCENDING)], name="cell", unique=True)],
    "traditions": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("location", "2dsphere")], name="location_2dsphere"),
        IndexModel([("place_key", ASCENDING), ("status", ASCENDING)], name="place_status"),
        IndexModel([("status", ASCENDING), ("created_at", DESCENDING)], name="status_created"),
    ],
    "osm_heritage": [
        IndexModel([("osm_id", ASCENDING)], name="osm_id", unique=True),
        IndexModel([("location", "2dsphere")], name="location_2dsphere"),
    ],
    "admins": [IndexModel([("email", ASCENDING)], name="email", unique=True)],
    "photos": [IndexModel([("id", ASCENDING)], name="id", unique=True)],
    "local_accounts": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("place_key", ASCENDING), ("deleted", ASCENDING), ("created_at", DESCENDING)], name="place_deleted_created"),
    ],
    "device_issues": [
        IndexModel([("created_at", ASCENDING)], name="ttl", expireAfterSeconds=3600),
        IndexModel([("ip", ASCENDING)], name="ip"),
    ],
    "build_log": [
        IndexModel([("created_at", ASCENDING)], name="ttl", expireAfterSeconds=3600),
        IndexModel([("ip", ASCENDING)], name="ip"),
    ],
}


async def ensure_indexes() -> None:
    for collection, models in INDEXES.items():
        for model in models:
            try:
                await db[collection].create_indexes([model])
            except Exception as exc:
                logger.error("ensure_indexes(%s.%s): %s", collection, model.document["name"], exc)


# ------------------------------- MODELS -------------------------------------


class Place(BaseModel):
    key: str
    title: str
    subtitle: str = ""
    lat: float
    lng: float
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    display_name: str = ""
    osm_url: Optional[str] = None


class EraEntry(BaseModel):
    key: str
    label: str
    heading: str = ""
    text: str = ""
    scope: str = "none"
    sources: List[int] = []


class Source(BaseModel):
    id: int
    type: str
    title: str
    url: str
    scope: str
    lang: Optional[str] = None


class FactOut(BaseModel):
    text: str
    sources: List[int] = []


class History(BaseModel):
    key: str
    summary: str = ""
    eras: List[EraEntry]
    then_now: str = ""
    did_you_know: List[FactOut] = []
    sources: List[Source] = []
    has_records: bool
    built_at: datetime
    edited_at: Optional[datetime] = None
    edited_by: Optional[str] = None


class EraEdit(BaseModel):
    key: str
    heading: str = Field("", max_length=80)
    text: str = Field("", max_length=1200)
    scope: str = "none"
    sources: List[int] = []

    @field_validator("heading", "text", mode="before")
    @classmethod
    def strip_text(cls, v):
        return v.strip() if isinstance(v, str) else v


class NewSource(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    url: str = Field(min_length=8, max_length=600, pattern=r"^https?://")
    scope: str = "street"


class HistoryEdit(BaseModel):
    summary: str = Field("", max_length=400)
    then_now: str = Field("", max_length=400)
    eras: List[EraEdit]
    new_sources: List[NewSource] = []


class Tradition(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    place_key: str
    place_title: str
    lat: float
    lng: float
    author: str
    title: str
    body: str
    status: Literal["pending", "verified", "rejected"] = "pending"
    verified_by: Optional[Literal["community", "admin"]] = None
    upvotes: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TraditionOut(Tradition):
    has_voted: bool = False


class TraditionCreate(BaseModel):
    place_key: str = Field(min_length=3, max_length=80)
    author: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=10, max_length=800)

    @field_validator("author", "title", "body", mode="before")
    @classmethod
    def strip_text(cls, v):
        return v.strip() if isinstance(v, str) else v


class VoteIn(BaseModel):
    device_token: str = Field(min_length=10, max_length=600)


class ModerateIn(BaseModel):
    action: Literal["verify", "reject"]


class LocalAccount(BaseModel):
    """A first-hand account collected by the NVM team, shown in the timeline apart from sourced history."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    place_key: str
    place_title: str
    era: str
    era_label: str
    body: str
    told_by: str
    village: str
    collected_on: str  # YYYY-MM-DD
    photo_url: Optional[str] = None
    added_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


TRADITION_PROJECTION = {"_id": 0, "voters": 0, "voter_ips": 0, "location": 0}
LOCAL_ACCOUNT_PROJECTION = {"_id": 0, "photo_path": 0, "deleted": 0}

# ------------------------------ AUTH / HELPERS ------------------------------


async def seed_admin() -> None:
    await db.admins.update_one(
        {"email": ADMIN_EMAIL},
        {"$set": {"email": ADMIN_EMAIL, "password_hash": password_hash.hash(ADMIN_PASSWORD), "role": "admin", "enabled": True}},
        upsert=True,
    )


def issue_token(email: str) -> str:
    now = datetime.now(timezone.utc)
    claims = {"sub": email, "role": "admin", "iat": now, "exp": now + timedelta(minutes=TOKEN_MINUTES)}
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALG)


async def require_admin(token: Annotated[str, Depends(oauth2_scheme)]):
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.InvalidTokenError:
        raise unauthorized
    email = payload.get("sub")
    if payload.get("role") != "admin" or not email:
        raise unauthorized
    admin = await db.admins.find_one({"email": email, "enabled": True}, {"_id": 0, "password_hash": 0})
    if not admin:
        raise unauthorized
    return admin


async def require_admin_link(request: Request, token: Optional[str] = Query(None)):
    """File downloads opened in a browser tab can't send a header, so the admin token may come as ?token=."""
    bearer = request.headers.get("authorization", "")
    tok = bearer[7:] if bearer.lower().startswith("bearer ") else token
    if not tok:
        raise HTTPException(status_code=401, detail="Sign in first", headers={"WWW-Authenticate": "Bearer"})
    return await require_admin(tok)


def parse_era(value: str) -> Optional[str]:
    norm = lambda s: re.sub(r"[\s_–—-]+", "", s.strip().lower())  # noqa: E731
    v = norm(value)
    for key, label in he.ERAS:
        if v in {norm(key), norm(label)}:
            return key
    return {"before1500": "pre1500", "190047": "1900_1947", "1947now": "today", "now": "today", "present": "today"}.get(v)


def parse_collected_on(value: str) -> Optional[str]:
    v = value.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def client_ip(request: Request) -> str:
    """Client IP as seen by our own proxies. Entries left of the trusted hops are client-supplied and ignored."""
    parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    idx = len(parts) - 1 - TRUSTED_PROXY_HOPS
    if idx >= 0:
        return parts[idx]
    return parts[0] if parts else (request.client.host if request.client else "unknown")


def device_from_token(token: Optional[str]) -> Optional[str]:
    """Device ids are issued and signed by the server, so a client can't invent new voters."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.InvalidTokenError:
        return None
    return payload.get("sub") if payload.get("typ") == "device" else None


def clean_for_tts(text: str) -> str:
    text = emoji.replace_emoji(text, replace="")
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#>~|]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def openai_error_detail(exc: Exception, fallback: str) -> str:
    """Turn the two OpenAI failures a user can actually fix into plain words; everything else stays generic."""
    msg = str(exc).lower()
    if "credits" in msg or "quota" in msg or "billing" in msg:
        return "The OpenAI account behind NVM has no credits left. Add billing at platform.openai.com and try again."
    if "incorrect api key" in msg or "invalid_api_key" in msg or "401" in msg:
        return "The OpenAI key is not valid. Update it and try again."
    return fallback


async def list_traditions(query: dict, device_token: Optional[str], limit: int = 100) -> List[TraditionOut]:
    device_id = device_from_token(device_token)
    docs = await db.traditions.find(query, {"_id": 0, "voter_ips": 0, "location": 0}).sort("created_at", -1).to_list(limit)
    return [TraditionOut(**{k: v for k, v in d.items() if k != "voters"}, has_voted=bool(device_id and device_id in d.get("voters", []))) for d in docs]


async def get_place(key: str) -> Place:
    doc = await db.places.find_one({"key": key}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Place not found")
    return Place(**doc)


async def resolve_place(lat: float, lng: float) -> Place:
    """Reverse-geocode with a ~11 m cache cell so a crowd on one street costs one lookup."""
    if not in_scope(lat, lng):
        raise HTTPException(status_code=404, detail=f"NVM only covers {SCOPE_NAME} for now. Point it at a street in {SCOPE_NAME}, or search for one.")
    cell = f"{round(lat, 4)},{round(lng, 4)}"
    cached = await db.geocode_cache.find_one({"cell": cell}, {"_id": 0})
    if cached:
        return await get_place(cached["key"])
    try:
        rev = await he.reverse_geocode(lat, lng)
    except Exception as exc:
        logger.error("reverse geocode failed: %s", exc)
        raise HTTPException(status_code=502, detail="Couldn't work out where this is right now. Try again in a moment.") from exc
    if not rev:
        raise HTTPException(status_code=404, detail="No mapped place here")
    p = he.place_from_reverse(rev)
    if SCOPE and SCOPE_STATE and SCOPE_STATE.lower() not in (p.get("state") or "").lower():
        raise HTTPException(status_code=404, detail=f"That's in {p.get('state') or 'another state'}. NVM only covers {SCOPE_NAME} for now.")
    existing = await db.places.find_one({"key": p["key"]}, {"_id": 0})
    if existing:
        place = Place(**existing)
    else:
        place = Place(**{k: p[k] for k in ("key", "title", "subtitle", "city", "state", "country", "display_name", "osm_url")}, lat=lat, lng=lng)
        # levels and osm_tags are kept on the record but off the API model: they feed history building.
        await db.places.update_one({"key": place.key}, {"$setOnInsert": {**place.model_dump(), "levels": p["levels"], "osm_tags": p.get("osm_tags") or {}}}, upsert=True)
    await db.geocode_cache.update_one({"cell": cell}, {"$set": {"cell": cell, "key": place.key}}, upsert=True)
    return place


_building: dict[str, asyncio.Task] = {}


async def _build_history(key: str) -> dict:
    place_doc = await db.places.find_one({"key": key}, {"_id": 0})
    try:
        heritage = osm_heritage.as_lines(await osm_heritage.nearby(db, place_doc["lat"], place_doc["lng"]))
    except Exception as exc:  # never let a geo query sink a build; the other sources still stand
        logger.warning("heritage lookup failed for %s: %s", key, exc)
        heritage = []
    sources = await he.gather_sources(place_doc, place_doc["lat"], place_doc["lng"], heritage)
    has_text_sources = any(s["type"] != "openstreetmap" for s in sources)
    body = he.empty_history()
    if has_text_sources:
        try:
            body = await asyncio.wait_for(he.compose_history(OPENAI_API_KEY, place_doc, sources), timeout=120)
        except Exception as exc:
            logger.error("compose failed for %s: %s", key, exc)
            raise HTTPException(status_code=502, detail=openai_error_detail(exc, "Couldn't put this history together right now. Try again.")) from exc
    used = {i for e in body["eras"] for i in e["sources"]} | {i for d in body["did_you_know"] for i in d["sources"]}
    history = {
        "key": key,
        **body,
        "sources": [{**{k: s[k] for k in ("id", "type", "title", "url", "scope")}, "lang": s.get("lang")} for s in sources if s["id"] in used or s["type"] == "openstreetmap"],
        "has_records": any(e["text"] for e in body["eras"]),
        "built_at": datetime.now(timezone.utc),
    }
    await db.histories.update_one({"key": key}, {"$set": history}, upsert=True)
    return history


# ------------------------------ APP / ROUTES --------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Index building runs in the background; the admin has to exist before the first login."""
    index_task = asyncio.create_task(ensure_indexes())
    await seed_admin()
    try:
        yield
    finally:
        index_task.cancel()
        with suppress(asyncio.CancelledError):
            await index_task
        client.close()


app = FastAPI(lifespan=lifespan)


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"message": "NVM API"}


@api.get("/eras")
async def eras():
    return [{"key": k, "label": v} for k, v in he.ERAS]


@api.get("/look")
async def look(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    heading: Optional[float] = Query(None, ge=0, le=360),
):
    """What is the phone looking at? With a heading, we look a few metres ahead along it."""
    t_lat, t_lng = he.offset_point(lat, lng, heading, FACING_DISTANCE_M) if heading is not None else (lat, lng)
    place = await resolve_place(t_lat, t_lng)
    cached = await db.histories.find_one({"key": place.key}, {"_id": 0})
    return {"place": place, "facing": {"lat": t_lat, "lng": t_lng}, "history": History(**cached) if cached else None}


@api.get("/history/{key}", response_model=History)
async def history(key: str, request: Request):
    cached = await db.histories.find_one({"key": key}, {"_id": 0})
    if cached:
        return History(**cached)
    await get_place(key)
    task = _building.get(key)
    if not task:
        ip = client_ip(request)
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        if await db.build_log.count_documents({"ip": ip, "created_at": {"$gte": since}}) >= BUILDS_PER_IP_PER_HOUR:
            raise HTTPException(status_code=429, detail="You've explored a lot of new places this hour. Try again a little later.")
        log_id = (await db.build_log.insert_one({"ip": ip, "key": key, "created_at": datetime.now(timezone.utc)})).inserted_id

        async def build_and_uncount_failures():
            try:
                return await _build_history(key)
            except Exception:
                await db.build_log.delete_one({"_id": log_id})  # a failed build shouldn't use up someone's allowance
                raise

        task = asyncio.create_task(build_and_uncount_failures())
        _building[key] = task
        task.add_done_callback(lambda _t, k=key: _building.pop(k, None))
    return History(**await asyncio.shield(task))


@api.get("/places")
async def places_by_key(keys: str = Query("", max_length=4000)):
    wanted = [k for k in keys.split(",") if k][:100]
    docs = await db.places.find({"key": {"$in": wanted}}, {"_id": 0, "levels": 0}).to_list(100) if wanted else []
    return [Place(**d) for d in docs]


@api.get("/places/{key}", response_model=Place)
async def place_detail(key: str):
    return await get_place(key)


@api.get("/search")
async def search(q: str = Query(..., min_length=2, max_length=120)):
    try:
        return await he.search_places(q, viewbox=SCOPE_BBOX or None)
    except Exception as exc:
        logger.error("search failed: %s", exc)
        raise HTTPException(status_code=502, detail="Search is unavailable right now. Try again.") from exc


# ---- Oral traditions (community) ----


@api.get("/traditions", response_model=List[TraditionOut])
async def traditions(
    status_: Literal["pending", "verified"] = Query("pending", alias="status"),
    place_key: Optional[str] = None,
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lng: Optional[float] = Query(None, ge=-180, le=180),
    radius_m: int = Query(STORY_RADIUS_M, ge=10, le=5000),
    device_token: Optional[str] = None,
):
    q: dict = {"status": status_}
    if place_key:
        q["place_key"] = place_key
    elif lat is not None and lng is not None:
        q["location"] = {"$geoWithin": {"$centerSphere": [[lng, lat], radius_m / 6378100]}}
    return await list_traditions(q, device_token)


@api.post("/traditions", response_model=Tradition)
async def create_tradition(body: TraditionCreate):
    place = await get_place(body.place_key)
    t = Tradition(**body.model_dump(), place_title=place.title, lat=place.lat, lng=place.lng)
    await db.traditions.insert_one({**t.model_dump(), "location": {"type": "Point", "coordinates": [place.lng, place.lat]}, "voters": [], "voter_ips": []})
    return t


@api.post("/devices")
async def register_device(request: Request):
    ip = client_ip(request)
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    if await db.device_issues.count_documents({"ip": ip, "created_at": {"$gte": since}}) >= DEVICES_PER_IP_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many new devices from this network. Try again later.")
    await db.device_issues.insert_one({"ip": ip, "created_at": datetime.now(timezone.utc)})
    token = jwt.encode({"sub": str(uuid.uuid4()), "typ": "device", "iat": datetime.now(timezone.utc)}, JWT_SECRET, algorithm=JWT_ALG)
    return {"device_token": token}


@api.post("/traditions/{tid}/upvote", response_model=TraditionOut)
async def upvote(tid: str, body: VoteIn, request: Request):
    device_id = device_from_token(body.device_token)
    if not device_id:
        raise HTTPException(status_code=401, detail="Unrecognised device. Please reopen the app.")
    ip = client_ip(request)
    existing = await db.traditions.find_one({"id": tid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Story not found")
    if existing["status"] != "pending":
        raise HTTPException(status_code=409, detail="Voting is closed for this story")
    if device_id in existing.get("voters", []):
        raise HTTPException(status_code=409, detail="You have already upvoted this")
    if existing.get("voter_ips", []).count(ip) >= VOTES_PER_IP_PER_TRADITION:
        raise HTTPException(status_code=429, detail="Too many votes from this network for this story")
    doc = await db.traditions.find_one_and_update(
        {
            "id": tid,
            "status": "pending",
            "voters": {"$ne": device_id},
            # Re-checked atomically so parallel requests can't slip past the per-network cap.
            "$expr": {"$lt": [{"$size": {"$filter": {"input": {"$ifNull": ["$voter_ips", []]}, "cond": {"$eq": ["$$this", ip]}}}}, VOTES_PER_IP_PER_TRADITION]},
        },
        {"$addToSet": {"voters": device_id}, "$push": {"voter_ips": ip}, "$inc": {"upvotes": 1}},
        projection={"_id": 0, "voter_ips": 0, "location": 0},
        return_document=True,
    )
    if not doc:
        raise HTTPException(status_code=409, detail="Could not record your vote. Refresh and try again.")
    if doc["upvotes"] >= UPVOTE_THRESHOLD:
        await db.traditions.update_one({"id": tid, "status": "pending"}, {"$set": {"status": "verified", "verified_by": "community"}})
        doc.update(status="verified", verified_by="community")
    return TraditionOut(**{k: v for k, v in doc.items() if k != "voters"}, has_voted=True)


@api.get("/config")
async def config():
    return {"upvote_threshold": UPVOTE_THRESHOLD, "story_radius_m": STORY_RADIUS_M, "scope_name": SCOPE_NAME if SCOPE else None, "scope_bbox": list(SCOPE) if SCOPE else None}


# ---- Admin ----


@api.post("/auth/token")
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    admin = await db.admins.find_one({"email": form.username.strip().lower(), "enabled": True})
    if not admin:
        password_hash.verify(form.password, DUMMY_HASH)
        ok = False
    else:
        ok = password_hash.verify(form.password, admin["password_hash"])
    if not ok:
        raise HTTPException(status_code=401, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})
    return {"access_token": issue_token(admin["email"]), "token_type": "bearer"}


@api.get("/admin/me")
async def admin_me(admin=Depends(require_admin)):
    return {"email": admin["email"], "role": admin["role"]}


@api.get("/admin/traditions", response_model=List[Tradition])
async def admin_queue(status_: Literal["pending", "verified", "rejected"] = Query("pending", alias="status"), admin=Depends(require_admin)):
    docs = await db.traditions.find({"status": status_}, TRADITION_PROJECTION).sort("created_at", 1).to_list(200)
    return [Tradition(**d) for d in docs]


@api.post("/admin/traditions/{tid}/moderate", response_model=Tradition)
async def moderate(tid: str, body: ModerateIn, admin=Depends(require_admin)):
    update = {"status": "verified", "verified_by": "admin"} if body.action == "verify" else {"status": "rejected", "verified_by": None}
    doc = await db.traditions.find_one_and_update({"id": tid}, {"$set": update}, projection=TRADITION_PROJECTION, return_document=True)
    if not doc:
        raise HTTPException(status_code=404, detail="Story not found")
    return Tradition(**doc)


@api.delete("/admin/history/{key}")
async def rebuild_history(key: str, admin=Depends(require_admin)):
    """Drop a cached history so the next visit rebuilds it from fresh sources."""
    res = await db.histories.delete_one({"key": key})
    return {"deleted": res.deleted_count}


@api.post("/admin/history/{key}/rebuild", response_model=History)
async def rebuild_history_now(key: str, admin=Depends(require_admin)):
    """Throw away the current text (including edits) and compose it again from fresh sources."""
    await get_place(key)
    task = _building.get(key)
    if not task:
        await db.histories.delete_one({"key": key})
        task = asyncio.create_task(_build_history(key))
        _building[key] = task
        task.add_done_callback(lambda _t, k=key: _building.pop(k, None))
    return History(**await asyncio.shield(task))


# ---- OpenStreetMap heritage import ----

_heritage_import: dict = {"state": "never run"}
_heritage_task: Optional[asyncio.Task] = None


@api.post("/admin/osm-heritage/import")
async def start_heritage_import(admin=Depends(require_admin)):
    """Pull every historic and heritage-listed feature in the covered area into our own database.

    Takes a few minutes and runs in the background: poll /admin/osm-heritage for progress. Re-running
    is safe, and so is interrupting it, because each feature is upserted by its OpenStreetMap id.
    """
    global _heritage_task
    if not SCOPE:
        raise HTTPException(status_code=400, detail="Set SCOPE_BBOX before importing; importing the whole world is not supported.")
    if _heritage_task and not _heritage_task.done():
        return {"started": False, "reason": "already running", **_heritage_import}
    _heritage_task = asyncio.create_task(osm_heritage.import_bbox(db, SCOPE, _heritage_import))
    return {"started": True, "area": SCOPE_NAME, **_heritage_import}


@api.get("/admin/osm-heritage")
async def heritage_status(admin=Depends(require_admin)):
    stored = await db.osm_heritage.count_documents({})
    running = bool(_heritage_task and not _heritage_task.done())
    failed = None
    if _heritage_task and _heritage_task.done() and _heritage_task.exception():
        failed = str(_heritage_task.exception())
    return {"stored": stored, "running": running, "error": failed, **_heritage_import}


@api.get("/admin/sources/{key}")
async def preview_sources(key: str, admin=Depends(require_admin)):
    """Everything the app has gathered about a place, before any model touches it.

    This is the honest answer to "why does this street's history say so little": if the sources here
    are thin, no amount of prompting will fix it, and the gap has to be filled with real data.
    """
    place_doc = await db.places.find_one({"key": key}, {"_id": 0})
    if not place_doc:
        raise HTTPException(status_code=404, detail="Unknown place")
    heritage = osm_heritage.as_lines(await osm_heritage.nearby(db, place_doc["lat"], place_doc["lng"]))
    sources = await he.gather_sources(place_doc, place_doc["lat"], place_doc["lng"], heritage)
    return {
        "place": {k: place_doc.get(k) for k in ("key", "title", "subtitle", "lat", "lng")},
        "heritage_features_nearby": len(heritage),
        "sources": [
            {**{k: s.get(k) for k in ("id", "type", "lang", "title", "url", "scope")}, "chars": len(s.get("text", "")), "text": s.get("text", "")}
            for s in sources
        ],
    }


@api.put("/admin/history/{key}", response_model=History)
async def edit_history(key: str, body: HistoryEdit, admin=Depends(require_admin)):
    """Hand-correct a street's history. Every era that has text must still cite at least one source."""
    doc = await db.histories.find_one({"key": key}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Build the history first, then edit it")
    sources = [s for s in doc["sources"]]
    next_id = max((s["id"] for s in sources), default=0) + 1
    for ns in body.new_sources:
        if ns.scope not in he.SCOPES:
            raise HTTPException(status_code=422, detail="Unknown source scope")
        sources.append({"id": next_id, "type": "manual", "title": ns.title.strip(), "url": ns.url.strip(), "scope": ns.scope, "lang": None})
        next_id += 1
    citable = {s["id"] for s in sources if s["type"] != "openstreetmap"}
    by_key = {e.key: e for e in body.eras}
    eras = []
    for era_key, label in he.ERAS:
        e = by_key.get(era_key)
        if e is None:
            raise HTTPException(status_code=422, detail=f"Missing era {label}")
        ids = sorted({i for i in e.sources if i in citable})
        if e.text and not ids:
            raise HTTPException(status_code=422, detail=f"{label}: add at least one source for this text, or clear the text")
        if e.text and e.scope not in he.SCOPES:
            raise HTTPException(status_code=422, detail=f"{label}: pick how close this fact is to the spot")
        eras.append({"key": era_key, "label": label, "heading": e.heading if e.text else "", "text": e.text, "scope": e.scope if e.text else "none", "sources": ids if e.text else []})
    has_records = any(e["text"] for e in eras)
    if not has_records:
        raise HTTPException(status_code=422, detail="This would clear every era. Use Rebuild instead, or leave at least one era with sourced text.")
    if len({e.key for e in body.eras}) != len(body.eras) or any(e.key not in ERA_LABELS for e in body.eras):
        raise HTTPException(status_code=422, detail="Unknown or repeated era")
    update = {
        "summary": body.summary.strip(),
        "then_now": body.then_now.strip(),
        "eras": eras,
        "sources": sources,  # keep every source, cited or not, so an editor can re-cite it later
        "has_records": has_records,
        "edited_at": datetime.now(timezone.utc),
        "edited_by": admin["email"],
    }
    await db.histories.update_one({"key": key}, {"$set": update})
    return History(**{**doc, **update})


# ---- Local accounts (admin-collected, shown inside the timeline) ----


def _clean_field(value: str, name: str, lo: int, hi: int) -> str:
    v = value.strip()
    if not lo <= len(v) <= hi:
        raise HTTPException(status_code=422, detail=f"{name} must be {lo}–{hi} characters")
    return v


@api.get("/local-accounts", response_model=List[LocalAccount])
async def local_accounts(place_key: str = Query(..., min_length=3, max_length=80)):
    docs = await db.local_accounts.find({"place_key": place_key, "deleted": False}, LOCAL_ACCOUNT_PROJECTION).sort("created_at", -1).to_list(200)
    return [LocalAccount(**d) for d in docs]


@api.get("/local-accounts/{aid}/photo")
async def local_account_photo(aid: str):
    doc = await db.local_accounts.find_one({"id": aid, "deleted": False}, {"_id": 0, "photo_path": 1})
    if not doc or not doc.get("photo_path"):
        raise HTTPException(status_code=404, detail="Photo not found")
    try:
        data, content_type = await photos.get(doc["photo_path"])
    except KeyError:
        raise HTTPException(status_code=404, detail="Photo not found")
    except Exception as exc:
        logger.error("photo fetch failed for %s: %s", aid, exc)
        raise HTTPException(status_code=502, detail="Photo unavailable right now") from exc
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "public, max-age=31536000"})


@api.get("/admin/local-accounts", response_model=List[LocalAccount])
async def admin_local_accounts(admin=Depends(require_admin)):
    docs = await db.local_accounts.find({"deleted": False}, LOCAL_ACCOUNT_PROJECTION).sort("created_at", -1).to_list(200)
    return [LocalAccount(**d) for d in docs]


@api.post("/admin/local-accounts", response_model=LocalAccount)
async def create_local_account(
    place_key: str = Form(..., min_length=3, max_length=80),
    era: str = Form(...),
    body: str = Form(...),
    told_by: str = Form(...),
    village: str = Form(...),
    collected_on: str = Form(...),
    photo: Optional[UploadFile] = File(None),
    admin=Depends(require_admin),
):
    if era not in ERA_LABELS:
        raise HTTPException(status_code=422, detail="Unknown era")
    try:
        collected = datetime.strptime(collected_on.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=422, detail="Date collected must be YYYY-MM-DD")
    # Admins collect in India; allow a day of slack so a local date is never rejected as "future".
    if collected > (datetime.now(timezone.utc) + timedelta(days=1)).date():
        raise HTTPException(status_code=422, detail="Date collected can't be in the future")
    place = await get_place(place_key)
    account = LocalAccount(
        place_key=place.key,
        place_title=place.title,
        era=era,
        era_label=ERA_LABELS[era],
        body=_clean_field(body, "Story", 10, 2000),
        told_by=_clean_field(told_by, "Who told it", 1, 80),
        village=_clean_field(village, "Village or town", 1, 80),
        collected_on=collected.isoformat(),
        added_by=admin["email"],
    )
    photo_path = None
    if photo is not None and photo.filename:
        photo_path = await store_photo(account.id, photo)
        account.photo_url = f"/api/local-accounts/{account.id}/photo"
    await db.local_accounts.insert_one({**account.model_dump(), "photo_path": photo_path, "deleted": False})
    return account


@api.delete("/admin/local-accounts/{aid}")
async def delete_local_account(aid: str, admin=Depends(require_admin)):
    res = await db.local_accounts.update_one({"id": aid, "deleted": False}, {"$set": {"deleted": True}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Local account not found")
    return {"deleted": 1}


async def store_photo(account_id: str, photo: UploadFile) -> str:
    content_type = (photo.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="Photo must be an image")
    data = await photo.read(PHOTO_MAX_BYTES + 1)
    if len(data) > PHOTO_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Photo must be under 8 MB")
    try:
        prepared, prepared_type = await asyncio.to_thread(photo_storage.prepare_image, data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="That file isn't an image we can read") from exc
    try:
        return await photos.put(prepared, prepared_type)
    except Exception as exc:
        logger.error("photo upload failed for %s: %s", account_id, exc)
        raise HTTPException(status_code=502, detail="Couldn't store the photo right now") from exc


@api.post("/admin/local-accounts/{aid}/photo", response_model=LocalAccount)
async def set_local_account_photo(aid: str, photo: UploadFile = File(...), admin=Depends(require_admin)):
    """Attach (or replace) the photo of an existing local account, e.g. one that came in through a CSV."""
    doc = await db.local_accounts.find_one({"id": aid, "deleted": False}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Local account not found")
    path = await store_photo(aid, photo)
    # A fresh ?v= each time so a replaced photo is never served from an old cache entry.
    photo_url = f"/api/local-accounts/{aid}/photo?v={path.split(':', 1)[-1][:8]}"
    await db.local_accounts.update_one({"id": aid}, {"$set": {"photo_path": path, "photo_url": photo_url}})
    old_path = doc.get("photo_path")
    if old_path and old_path != path:
        with suppress(Exception):  # the replacement is already saved; an orphan left behind is not worth a 500
            await photos.delete(old_path)
    return LocalAccount(**{**doc, "photo_url": photo_url})


# ---- Bulk import / export ----


@api.get("/admin/local-accounts/template.csv", include_in_schema=False)
async def import_template():
    return PlainTextResponse(IMPORT_TEMPLATE, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="nvm-local-accounts-template.csv"'})


@api.post("/admin/local-accounts/import")
async def import_local_accounts(file: UploadFile = File(...), admin=Depends(require_admin)):
    """Add many local accounts from a CSV. Good rows are saved, bad rows are reported, nothing is half-saved."""
    raw = await file.read(IMPORT_MAX_BYTES + 1)
    if len(raw) > IMPORT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="CSV must be under 2 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=422, detail="The file is empty or has no header row")
    col_for: dict[str, str] = {}
    for header in reader.fieldnames:
        norm = re.sub(r"[^a-z0-9]+", "_", (header or "").strip().lower()).strip("_")
        for field, aliases in IMPORT_ALIASES.items():
            if norm in aliases and field not in col_for:
                col_for[field] = header
    missing = [f for f in IMPORT_ALIASES if f not in col_for]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing columns: {', '.join(missing)}. Download the template to see the expected headers.")

    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=422, detail="No rows under the header")
    if len(rows) > IMPORT_MAX_ROWS:
        raise HTTPException(status_code=422, detail=f"Import at most {IMPORT_MAX_ROWS} rows at a time")

    place_cache: dict[str, Place] = {}

    async def resolve_street(value: str) -> Place:
        if value in place_cache:
            return place_cache[value]
        existing = await db.places.find_one({"key": value}, {"_id": 0})
        if existing:
            place = Place(**existing)
        else:
            hits = await he.search_places(value)
            if not hits:
                raise ValueError("Street not found on the map")
            place = await resolve_place(hits[0]["lat"], hits[0]["lng"])
        place_cache[value] = place
        return place

    created: list[dict] = []
    failed: list[dict] = []
    max_date = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        get = lambda f: (row.get(col_for[f]) or "").strip()  # noqa: E731
        street = get("street")
        try:
            if not any(get(f) for f in IMPORT_ALIASES):
                continue  # blank line
            if not street:
                raise ValueError("Street is empty")
            era = parse_era(get("era"))
            if not era:
                raise ValueError(f"Unknown era '{get('era')}'. Use one of: {', '.join(l for _, l in he.ERAS)}")
            body = get("body")
            if not 10 <= len(body) <= 2000:
                raise ValueError("Story must be 10–2000 characters")
            told_by, village = get("told_by"), get("village")
            if not 1 <= len(told_by) <= 80 or not 1 <= len(village) <= 80:
                raise ValueError("Who told it and village/town must each be 1–80 characters")
            collected = parse_collected_on(get("collected_on"))
            if not collected:
                raise ValueError("Date collected must look like 2026-05-20")
            if collected > max_date:
                raise ValueError("Date collected can't be in the future")
            try:
                place = await resolve_street(street)
            except HTTPException as exc:
                raise ValueError(exc.detail) from exc
            account = LocalAccount(place_key=place.key, place_title=place.title, era=era, era_label=ERA_LABELS[era], body=body, told_by=told_by, village=village, collected_on=collected, added_by=admin["email"])
            await db.local_accounts.insert_one({**account.model_dump(), "photo_path": None, "deleted": False})
            created.append({"row": i, "id": account.id, "place_title": place.title, "era_label": account.era_label})
        except ValueError as exc:
            failed.append({"row": i, "street": street, "reason": str(exc)})
        except Exception as exc:
            logger.error("import row %s failed: %s", i, exc)
            failed.append({"row": i, "street": street, "reason": "Couldn't look up this street right now"})
    return {"created": len(created), "failed": failed, "rows": len(rows), "created_rows": created}


@api.get("/admin/export.csv", include_in_schema=False)
async def export_csv(admin=Depends(require_admin_link)):
    """Everything people have contributed, as one spreadsheet: community stories and local accounts."""
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    w.writeheader()
    async for d in db.local_accounts.find({"deleted": False}, LOCAL_ACCOUNT_PROJECTION).sort("created_at", 1):
        w.writerow({**d, "type": "local_account", "created_at": d["created_at"].isoformat()})
    async for d in db.traditions.find({}, TRADITION_PROJECTION).sort("created_at", 1):
        w.writerow({**d, "type": "community_story", "created_at": d["created_at"].isoformat()})
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return PlainTextResponse(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="nvm-backup-{stamp}.csv"'})


# ---- Narration ----


@api.post("/history/{key}/narrate")
async def narrate(key: str, voice: Literal["marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"] = openai_voice.DEFAULT_VOICE):
    doc = await db.histories.find_one({"key": key}, {"_id": 0})
    if not doc or not doc.get("has_records"):
        raise HTTPException(status_code=404, detail="No story to narrate yet")
    place = await get_place(key)
    parts = [f"{place.title}."] + [f"{e['label']}. {e['text']}" for e in doc["eras"] if e["text"]]
    text = clean_for_tts(" ".join(parts))[:3800]
    audio_key = hashlib.sha256(f"{voice}|{openai_voice.VOICE_MODEL}|mp3|{text}".encode()).hexdigest()
    path = TTS_CACHE_DIR / f"{audio_key}.mp3"
    if not path.exists():
        try:
            audio = await asyncio.wait_for(openai_voice.synthesize_mp3(OPENAI_API_KEY, text, voice), timeout=240)
        except Exception as exc:
            logger.error("tts failed for %s: %s", key, exc)
            raise HTTPException(status_code=502, detail=openai_error_detail(exc, "Narration unavailable right now")) from exc
        tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(audio)
        tmp.replace(path)
    return {"audio_url": f"/api/tts/{audio_key}.mp3"}


@api.get("/tts/{key}.mp3")
async def get_tts(key: str):
    path = TTS_CACHE_DIR / f"{key}.mp3"
    if not re.fullmatch(r"[0-9a-f]{64}", key) or not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=31536000"})


# ---- Share card ----


def card_facts(doc: dict) -> list[dict]:
    """The facts worth putting on a card, most surprising first: did-you-knows, then dated eras, then the summary."""
    facts = [{"label": "Did you know?", "text": d["text"]} for d in doc.get("did_you_know", []) if d.get("text")]
    facts += [{"label": e["label"], "text": e["text"]} for e in doc.get("eras", []) if e.get("text")]
    if doc.get("summary"):
        facts.append({"label": "In short", "text": doc["summary"]})
    return facts


@api.get("/history/{key}/card-facts")
async def history_card_facts(key: str):
    doc = await db.histories.find_one({"key": key}, {"_id": 0})
    if not doc or not doc.get("has_records"):
        raise HTTPException(status_code=404, detail="No story to share yet")
    return card_facts(doc)


@api.get("/history/{key}/card.png")
async def history_card(key: str, fact: int = Query(0, ge=0)):
    doc = await db.histories.find_one({"key": key}, {"_id": 0})
    facts = card_facts(doc) if doc and doc.get("has_records") else []
    if not facts:
        raise HTTPException(status_code=404, detail="No story to share yet")
    chosen = facts[fact % len(facts)]
    place = await get_place(key)
    langs = {s.get("lang") for s in doc.get("sources", []) if s["type"] == "wikipedia"}
    source_note = "From Wikipedia" + (" (English and Hindi)" if "hi" in langs and "en" in langs else " (Hindi)" if "hi" in langs else "") + (" and the NVM team" if any(s["type"] == "manual" for s in doc.get("sources", [])) else "")
    digest = hashlib.sha256(f"v2|{place.title}|{place.subtitle}|{chosen['label']}|{chosen['text']}|{source_note}".encode()).hexdigest()
    path = CARD_CACHE_DIR / f"{digest}.png"
    if not path.exists():
        png = await asyncio.to_thread(share_card.render_card, place.title, place.subtitle, chosen["label"], chosen["text"], source_note)
        tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(png)
        tmp.replace(path)  # atomic, so a parallel request never reads a half-written file
    safe_name = re.sub(r"[^a-z0-9]+", "-", place.title.lower()).strip("-") or "street"
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400", "Content-Disposition": f'inline; filename="nvm-{safe_name}.png"'})


app.include_router(api)

app.add_middleware(CORSMiddleware, allow_credentials=False, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
