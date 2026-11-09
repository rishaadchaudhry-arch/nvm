import asyncio
import hashlib
import logging
import math
import os
import re
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, List, Literal, Optional

import emoji
import jwt
from dotenv import load_dotenv
from emergentintegrations.llm.openai import OpenAITextToSpeech
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorClient
from pwdlib import PasswordHash
from pydantic import BaseModel, Field, field_validator
from pymongo import ASCENDING, DESCENDING, IndexModel
from starlette.middleware.cors import CORSMiddleware

from seed_content import AREAS, ERAS, POIS, REGIONS, SEED_VERSION

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
JWT_ALG = "HS256"
TOKEN_MINUTES = 60 * 12

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
logger = logging.getLogger(__name__)

TTS_CACHE_DIR = ROOT_DIR / "tts_cache"
TTS_CACHE_DIR.mkdir(exist_ok=True)

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummy-password-to-even-out-timing")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

INDEXES: dict[str, list[IndexModel]] = {
    "regions": [IndexModel([("slug", ASCENDING)], name="slug", unique=True)],
    "areas": [
        IndexModel([("slug", ASCENDING)], name="slug", unique=True),
        IndexModel([("region_slug", ASCENDING)], name="region_slug"),
    ],
    "pois": [
        IndexModel([("slug", ASCENDING)], name="slug", unique=True),
        IndexModel([("area_slug", ASCENDING)], name="area_slug"),
    ],
    "traditions": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("area_slug", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)], name="area_status"),
        IndexModel([("poi_slug", ASCENDING), ("status", ASCENDING)], name="poi_status"),
        IndexModel([("status", ASCENDING), ("created_at", ASCENDING)], name="status_created"),
    ],
    "admins": [IndexModel([("email", ASCENDING)], name="email", unique=True)],
    "device_issues": [
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


class Era(BaseModel):
    key: str
    title: str
    description: str


class Region(BaseModel):
    slug: str
    name: str
    kind: str = "state"
    cover_image: str
    summary: str = ""
    eras: List[Era] = []


class Area(BaseModel):
    slug: str
    region_slug: str
    name: str
    lat: float
    lng: float
    radius_m: int
    cover_image: str
    summary: str = ""
    era_keys: List[str] = []
    eras: List[Era] = []


class Poi(BaseModel):
    slug: str
    area_slug: str
    name: str
    category: str
    lat: float
    lng: float
    image: str
    eras: List[Era] = []


class Tradition(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    area_slug: str
    poi_slug: Optional[str] = None
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
    area_slug: str
    poi_slug: Optional[str] = None
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


TRADITION_PROJECTION = {"_id": 0, "voters": 0, "voter_ips": 0}
DEVICES_PER_IP_PER_HOUR = 20
VOTES_PER_IP_PER_TRADITION = 3

# ------------------------------ SEED / AUTH ----------------------------------


async def seed() -> None:
    # Starter content is (re)applied only when SEED_VERSION goes up, so admin edits made
    # through the content API are not overwritten on every restart.
    meta = await db.meta.find_one({"_id": "seed"}) or {}
    op = "$set" if meta.get("version", 0) < SEED_VERSION else "$setOnInsert"
    for coll, items in (("regions", REGIONS), ("areas", AREAS), ("pois", POIS)):
        for item in items:
            await db[coll].update_one({"slug": item["slug"]}, {op: item}, upsert=True)
    await db.meta.update_one({"_id": "seed"}, {"$set": {"version": SEED_VERSION}}, upsert=True)
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


# ------------------------------ HELPERS -------------------------------------


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def clean_for_tts(text: str) -> str:
    text = emoji.replace_emoji(text, replace="")
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#>~|]", "", text)
    return re.sub(r"\s+", " ", text).strip()


async def get_or_404(collection: str, slug: str) -> dict:
    doc = await db[collection].find_one({"slug": slug}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail=f"{collection[:-1].capitalize()} not found")
    return doc


async def list_traditions(query: dict, device_token: Optional[str], limit: int = 100) -> List[TraditionOut]:
    device_id = device_from_token(device_token)
    docs = await db.traditions.find(query, {"_id": 0, "voter_ips": 0}).sort("created_at", -1).to_list(limit)
    return [TraditionOut(**{k: v for k, v in d.items() if k != "voters"}, has_voted=bool(device_id and device_id in d.get("voters", []))) for d in docs]


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


# ------------------------------ APP / ROUTES --------------------------------

app = FastAPI()


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"message": "Yatra API"}


@api.get("/eras")
async def eras():
    return [{"key": k, "label": v} for k, v in ERAS.items()]


@api.get("/regions", response_model=List[dict])
async def regions():
    docs = await db.regions.find({}, {"_id": 0}).sort("name", 1).to_list(100)
    counts = {c["_id"]: c["n"] for c in await db.areas.aggregate([{"$group": {"_id": "$region_slug", "n": {"$sum": 1}}}]).to_list(100)}
    return [{**Region(**d).model_dump(), "area_count": counts.get(d["slug"], 0), "has_stories": bool(d.get("eras"))} for d in docs]


@api.get("/regions/{slug}")
async def region_detail(slug: str):
    region = Region(**await get_or_404("regions", slug))
    areas = await db.areas.find({"region_slug": slug}, {"_id": 0}).sort("name", 1).to_list(200)
    return {"region": region, "areas": [Area(**a) for a in areas]}


@api.get("/areas/{slug}")
async def area_detail(slug: str, device_token: Optional[str] = None):
    area = Area(**await get_or_404("areas", slug))
    pois = await db.pois.find({"area_slug": slug}, {"_id": 0}).sort("name", 1).to_list(500)
    verified = await list_traditions({"area_slug": slug, "status": "verified"}, device_token)
    return {"area": area, "pois": [Poi(**p) for p in pois], "did_you_know": verified, "eras": [{"key": k, "label": ERAS.get(k, k)} for k in area.era_keys]}


@api.get("/pois")
async def pois_by_slugs(slugs: str = Query("", max_length=4000)):
    wanted = [s for s in slugs.split(",") if s][:100]
    if not wanted:
        return []
    docs = await db.pois.find({"slug": {"$in": wanted}}, {"_id": 0}).to_list(100)
    return [Poi(**d) for d in docs]


@api.get("/pois/{slug}")
async def poi_detail(slug: str, device_token: Optional[str] = None):
    poi = Poi(**await get_or_404("pois", slug))
    area = Area(**await get_or_404("areas", poi.area_slug))
    verified = await list_traditions({"poi_slug": slug, "status": "verified"}, device_token)
    pending = await list_traditions({"poi_slug": slug, "status": "pending"}, device_token)
    return {
        "poi": poi,
        "area": {"slug": area.slug, "name": area.name},
        "eras": [{"key": k, "label": ERAS.get(k, k)} for k in area.era_keys],
        "did_you_know": verified,
        "community": pending,
        "upvote_threshold": UPVOTE_THRESHOLD,
    }


@api.get("/nearby")
async def nearby(lat: float = Query(..., ge=-90, le=90), lng: float = Query(..., ge=-180, le=180)):
    areas = await db.areas.find({}, {"_id": 0}).to_list(1000)
    ranked = sorted(({**a, "distance_m": round(haversine_m(lat, lng, a["lat"], a["lng"]))} for a in areas), key=lambda a: a["distance_m"])
    inside = next((a for a in ranked if a["distance_m"] <= a["radius_m"] and a.get("eras")), None)
    nearest_with_stories = next((a for a in ranked if a.get("eras")), None)
    result = {"inside": None, "nearest": None, "areas": [{**Area(**a).model_dump(), "distance_m": a["distance_m"]} for a in ranked[:10]]}
    if nearest_with_stories:
        result["nearest"] = {"slug": nearest_with_stories["slug"], "name": nearest_with_stories["name"], "distance_m": nearest_with_stories["distance_m"]}
    if inside:
        pois = await db.pois.find({"area_slug": inside["slug"]}, {"_id": 0}).to_list(500)
        poi_out = sorted(({**Poi(**p).model_dump(), "distance_m": round(haversine_m(lat, lng, p["lat"], p["lng"]))} for p in pois), key=lambda p: p["distance_m"])
        verified = await db.traditions.find({"area_slug": inside["slug"], "status": "verified"}, TRADITION_PROJECTION).sort("created_at", -1).to_list(200)
        result["inside"] = {
            "area": Area(**inside).model_dump(),
            "eras": [{"key": k, "label": ERAS.get(k, k)} for k in inside["era_keys"]],
            "pois": poi_out,
            "did_you_know": [Tradition(**t).model_dump(mode="json") for t in verified],
        }
    return result


# ---- Oral traditions (community) ----


@api.get("/traditions", response_model=List[TraditionOut])
async def traditions(
    status_: Literal["pending", "verified"] = Query("pending", alias="status"),
    area_slug: Optional[str] = None,
    device_token: Optional[str] = None,
):
    q: dict = {"status": status_}
    if area_slug:
        q["area_slug"] = area_slug
    return await list_traditions(q, device_token)


@api.post("/traditions", response_model=Tradition)
async def create_tradition(body: TraditionCreate):
    await get_or_404("areas", body.area_slug)
    if body.poi_slug:
        poi = await get_or_404("pois", body.poi_slug)
        if poi["area_slug"] != body.area_slug:
            raise HTTPException(status_code=400, detail="This place is not in the selected area")
    t = Tradition(**body.model_dump())
    await db.traditions.insert_one({**t.model_dump(), "voters": [], "voter_ips": []})
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
        raise HTTPException(status_code=404, detail="Tradition not found")
    if existing["status"] != "pending":
        raise HTTPException(status_code=409, detail="Voting is closed for this tradition")
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
        projection={"_id": 0, "voter_ips": 0},
        return_document=True,
    )
    if not doc:
        raise HTTPException(status_code=409, detail="Could not record your vote. Refresh and try again.")
    if doc["upvotes"] >= UPVOTE_THRESHOLD:
        await db.traditions.update_one({"id": tid, "status": "pending"}, {"$set": {"status": "verified", "verified_by": "community"}})
        doc.update(status="verified", verified_by="community")
    return TraditionOut(**{k: v for k, v in doc.items() if k != "voters"}, has_voted=True)


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
        raise HTTPException(status_code=404, detail="Tradition not found")
    return Tradition(**doc)


@api.put("/admin/regions/{slug}", response_model=Region)
async def upsert_region(slug: str, body: Region, admin=Depends(require_admin)):
    data = {**body.model_dump(), "slug": slug}
    await db.regions.update_one({"slug": slug}, {"$set": data}, upsert=True)
    return Region(**data)


@api.put("/admin/areas/{slug}", response_model=Area)
async def upsert_area(slug: str, body: Area, admin=Depends(require_admin)):
    await get_or_404("regions", body.region_slug)
    data = {**body.model_dump(), "slug": slug}
    await db.areas.update_one({"slug": slug}, {"$set": data}, upsert=True)
    return Area(**data)


@api.put("/admin/pois/{slug}", response_model=Poi)
async def upsert_poi(slug: str, body: Poi, admin=Depends(require_admin)):
    await get_or_404("areas", body.area_slug)
    data = {**body.model_dump(), "slug": slug}
    await db.pois.update_one({"slug": slug}, {"$set": data}, upsert=True)
    return Poi(**data)


# ---- Narration ----


@api.post("/pois/{slug}/narrate")
async def narrate_poi(slug: str, voice: Literal["fable", "sage", "onyx", "coral"] = "fable"):
    poi = Poi(**await get_or_404("pois", slug))
    if not poi.eras:
        raise HTTPException(status_code=404, detail="No story to narrate yet")
    parts = [f"{poi.name}."] + [f"{ERAS.get(e.key, e.key).split(' · ')[0]}. {e.title}. {e.description}" for e in poi.eras]
    text = clean_for_tts(" ".join(parts))[:3800]
    key = hashlib.sha256(f"{voice}|tts-1|mp3|{text}".encode()).hexdigest()
    path = TTS_CACHE_DIR / f"{key}.mp3"
    if not path.exists():
        try:
            audio = await asyncio.wait_for(
                OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY).generate_speech(text=text, model="tts-1", voice=voice, response_format="mp3"),
                timeout=60,
            )
        except Exception as exc:
            logger.error("tts failed for %s: %s", slug, exc)
            raise HTTPException(status_code=502, detail="Narration unavailable right now") from exc
        path.write_bytes(audio)
    return {"audio_url": f"/api/tts/{key}.mp3"}


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
    await seed()


@app.on_event("shutdown")
async def shutdown():
    app.state.index_task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.index_task
    client.close()
