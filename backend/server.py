import asyncio
import hashlib
import logging
import os
import re
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, List, Literal, Optional

import emoji
import httpx
import jwt
from dotenv import load_dotenv
from emergentintegrations.llm.openai import OpenAITextToSpeech
from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorClient
from pwdlib import PasswordHash
from pydantic import BaseModel, Field, field_validator
from pymongo import ASCENDING, DESCENDING, IndexModel
from starlette.middleware.cors import CORSMiddleware

import history_engine as he
import object_storage as store

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"].lower()
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
JWT_SECRET = os.environ["JWT_SECRET"]
UPVOTE_THRESHOLD = int(os.environ["UPVOTE_THRESHOLD"])
TRUSTED_PROXY_HOPS = int(os.environ["TRUSTED_PROXY_HOPS"])
BUILDS_PER_IP_PER_HOUR = int(os.environ["BUILDS_PER_IP_PER_HOUR"])
JWT_ALG = "HS256"
TOKEN_MINUTES = 60 * 12
FACING_DISTANCE_M = 35  # how far ahead of the phone we look when the camera points somewhere
STORY_RADIUS_M = 150  # a verified story shows as "Did you know?" within this distance
DEVICES_PER_IP_PER_HOUR = 20
VOTES_PER_IP_PER_TRADITION = 3
PHOTO_MAX_BYTES = 8 * 1024 * 1024
ERA_LABELS = dict(he.ERAS)

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
logger = logging.getLogger(__name__)

TTS_CACHE_DIR = ROOT_DIR / "tts_cache"
TTS_CACHE_DIR.mkdir(exist_ok=True)

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
    "admins": [IndexModel([("email", ASCENDING)], name="email", unique=True)],
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
    existing = await db.places.find_one({"key": p["key"]}, {"_id": 0})
    if existing:
        place = Place(**existing)
    else:
        place = Place(**{k: p[k] for k in ("key", "title", "subtitle", "city", "state", "country", "display_name", "osm_url")}, lat=lat, lng=lng)
        await db.places.update_one({"key": place.key}, {"$setOnInsert": {**place.model_dump(), "levels": p["levels"]}}, upsert=True)
    await db.geocode_cache.update_one({"cell": cell}, {"$set": {"cell": cell, "key": place.key}}, upsert=True)
    return place


_building: dict[str, asyncio.Task] = {}


async def _build_history(key: str) -> dict:
    place_doc = await db.places.find_one({"key": key}, {"_id": 0})
    sources = await he.gather_sources(place_doc, place_doc["lat"], place_doc["lng"])
    has_text_sources = any(s["type"] != "openstreetmap" for s in sources)
    body = he.empty_history()
    if has_text_sources:
        try:
            body = await asyncio.wait_for(he.compose_history(EMERGENT_LLM_KEY, place_doc, sources), timeout=90)
        except Exception as exc:
            logger.error("compose failed for %s: %s", key, exc)
            raise HTTPException(status_code=502, detail="Couldn't put this history together right now. Try again.") from exc
    used = {i for e in body["eras"] for i in e["sources"]} | {i for d in body["did_you_know"] for i in d["sources"]}
    history = {
        "key": key,
        **body,
        "sources": [{k: s[k] for k in ("id", "type", "title", "url", "scope")} for s in sources if s["id"] in used or s["type"] == "openstreetmap"],
        "has_records": any(e["text"] for e in body["eras"]),
        "built_at": datetime.now(timezone.utc),
    }
    await db.histories.update_one({"key": key}, {"$set": history}, upsert=True)
    return history


# ------------------------------ APP / ROUTES --------------------------------

app = FastAPI()


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
        return await he.search_places(q)
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
    return {"upvote_threshold": UPVOTE_THRESHOLD, "story_radius_m": STORY_RADIUS_M}


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
        data, content_type = await store.get_object(EMERGENT_LLM_KEY, doc["photo_path"])
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
        content_type = (photo.content_type or "").lower()
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=422, detail="Photo must be an image")
        data = await photo.read(PHOTO_MAX_BYTES + 1)
        if len(data) > PHOTO_MAX_BYTES:
            raise HTTPException(status_code=413, detail="Photo must be under 8 MB")
        ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/heic": "heic", "image/gif": "gif"}.get(content_type, "jpg")
        try:
            result = await store.put_object(EMERGENT_LLM_KEY, store.object_path("local-accounts", f"{account.id}.{ext}"), data, content_type)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 402:
                raise HTTPException(status_code=402, detail="Photo storage is out of credits. Save without a photo or top up.") from exc
            logger.error("photo upload failed: %s", exc)
            raise HTTPException(status_code=502, detail="Couldn't store the photo right now") from exc
        except Exception as exc:
            logger.error("photo upload failed: %s", exc)
            raise HTTPException(status_code=502, detail="Couldn't store the photo right now") from exc
        photo_path = result["path"]
        account.photo_url = f"/api/local-accounts/{account.id}/photo"
    await db.local_accounts.insert_one({**account.model_dump(), "photo_path": photo_path, "deleted": False})
    return account


@api.delete("/admin/local-accounts/{aid}")
async def delete_local_account(aid: str, admin=Depends(require_admin)):
    res = await db.local_accounts.update_one({"id": aid, "deleted": False}, {"$set": {"deleted": True}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Local account not found")
    return {"deleted": 1}


# ---- Narration ----


@api.post("/history/{key}/narrate")
async def narrate(key: str, voice: Literal["fable", "sage", "onyx", "coral"] = "fable"):
    doc = await db.histories.find_one({"key": key}, {"_id": 0})
    if not doc or not doc.get("has_records"):
        raise HTTPException(status_code=404, detail="No story to narrate yet")
    place = await get_place(key)
    parts = [f"{place.title}."] + [f"{e['label']}. {e['text']}" for e in doc["eras"] if e["text"]]
    text = clean_for_tts(" ".join(parts))[:3800]
    audio_key = hashlib.sha256(f"{voice}|tts-1|mp3|{text}".encode()).hexdigest()
    path = TTS_CACHE_DIR / f"{audio_key}.mp3"
    if not path.exists():
        try:
            audio = await asyncio.wait_for(
                OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY).generate_speech(text=text, model="tts-1", voice=voice, response_format="mp3"),
                timeout=60,
            )
        except Exception as exc:
            logger.error("tts failed for %s: %s", key, exc)
            raise HTTPException(status_code=502, detail="Narration unavailable right now") from exc
        path.write_bytes(audio)
    return {"audio_url": f"/api/tts/{audio_key}.mp3"}


@api.get("/tts/{key}.mp3")
async def get_tts(key: str):
    path = TTS_CACHE_DIR / f"{key}.mp3"
    if not re.fullmatch(r"[0-9a-f]{64}", key) or not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=31536000"})


app.include_router(api)

app.add_middleware(CORSMiddleware, allow_credentials=False, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


@app.on_event("startup")
async def startup():
    app.state.index_task = asyncio.create_task(ensure_indexes())
    await seed_admin()
    try:
        await store.init_storage(EMERGENT_LLM_KEY)
    except Exception as exc:
        logger.error("object storage init failed (will retry on first upload): %s", exc)


@app.on_event("shutdown")
async def shutdown():
    app.state.index_task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.index_task
    client.close()
