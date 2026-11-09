import asyncio
import hashlib
import logging
import math
import os
import re
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import emoji
from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.llm.openai import OpenAITextToSpeech
from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, field_validator
from pymongo import ASCENDING, DESCENDING, IndexModel
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

TTS_CACHE_DIR = ROOT_DIR / "tts_cache"
TTS_CACHE_DIR.mkdir(exist_ok=True)

INDEXES: dict[str, list[IndexModel]] = {
    "places": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("slug", ASCENDING)], name="slug", unique=True),
        IndexModel([("name", ASCENDING)]),
        IndexModel([("city", ASCENDING)]),
        IndexModel([("state", ASCENDING)]),
    ],
    "trivia": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("place_id", ASCENDING), ("created_at", DESCENDING)]),
    ],
    "timelines": [
        IndexModel([("place_id", ASCENDING)], name="place_id", unique=True),
    ],
}


async def ensure_indexes() -> None:
    for collection, models in INDEXES.items():
        for model in models:
            try:
                await db[collection].create_indexes([model])
            except Exception as exc:
                logging.getLogger(__name__).error(
                    "ensure_indexes(%s.%s): %s", collection, model.document["name"], exc
                )


app = FastAPI()


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


api_router = APIRouter(prefix="/api")


# ------------------------------- MODELS -------------------------------------


class Place(BaseModel):
    id: str
    slug: str
    name: str
    city: str
    state: str
    country: str = "India"
    lat: float
    lng: float
    era: str
    tagline: str
    hero_image: str
    panorama_image: str


class TimelineEvent(BaseModel):
    year: str
    title: str
    description: str


class PlaceTimeline(BaseModel):
    place_id: str
    summary: str
    events: List[TimelineEvent]
    did_you_know: str
    hotspots: List[str]


class Trivia(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    place_id: str
    author: str
    title: str
    body: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TriviaCreate(BaseModel):
    author: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=10, max_length=600)

    @field_validator("author", "title", "body", mode="before")
    @classmethod
    def strip_text(cls, v):
        return v.strip() if isinstance(v, str) else v


class NarrateRequest(BaseModel):
    place_id: str
    voice: str = "fable"


# ------------------------------ SEED DATA -----------------------------------

SEED_PLACES: list[dict] = [
    {
        "slug": "taj-mahal",
        "name": "Taj Mahal",
        "city": "Agra",
        "state": "Uttar Pradesh",
        "lat": 27.1751,
        "lng": 78.0421,
        "era": "17th century",
        "tagline": "A monument of eternal love in white marble.",
        "hero_image": "https://images.unsplash.com/photo-1587135941948-670b381f08ce?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        "panorama_image": "https://commons.wikimedia.org/wiki/Special:FilePath/Taj_Mahal_(Edited).jpeg?width=2400",
    },
    {
        "slug": "hampi",
        "name": "Hampi",
        "city": "Hampi",
        "state": "Karnataka",
        "lat": 15.3350,
        "lng": 76.4600,
        "era": "14th–16th century",
        "tagline": "Ruins of the once-glorious Vijayanagara Empire.",
        "hero_image": "https://images.unsplash.com/photo-1696239109250-a83577abcbeb?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        "panorama_image": "https://commons.wikimedia.org/wiki/Special:FilePath/Hampi_virupaksha_temple.jpg?width=2400",
    },
    {
        "slug": "red-fort",
        "name": "Red Fort",
        "city": "Delhi",
        "state": "Delhi",
        "lat": 28.6562,
        "lng": 77.2410,
        "era": "17th century",
        "tagline": "The seat of Mughal emperors for two centuries.",
        "hero_image": "https://images.unsplash.com/photo-1713729991304-d0b6c328560e?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        "panorama_image": "https://images.unsplash.com/photo-1713729991304-d0b6c328560e?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
    },
    {
        "slug": "mysore-palace",
        "name": "Mysore Palace",
        "city": "Mysore",
        "state": "Karnataka",
        "lat": 12.3051,
        "lng": 76.6551,
        "era": "19th–20th century",
        "tagline": "The royal residence of the Wadiyar dynasty.",
        "hero_image": "https://images.unsplash.com/photo-1764858147489-47a546c6e8ca?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        "panorama_image": "https://images.unsplash.com/photo-1764858147489-47a546c6e8ca?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
    },
    {
        "slug": "konark-sun-temple",
        "name": "Konark Sun Temple",
        "city": "Konark",
        "state": "Odisha",
        "lat": 19.8876,
        "lng": 86.0945,
        "era": "13th century",
        "tagline": "A chariot of the Sun god carved in stone.",
        "hero_image": "https://images.unsplash.com/photo-1639980290886-6bdd61c7582b?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        "panorama_image": "https://commons.wikimedia.org/wiki/Special:FilePath/Konark_Sun_Temple_Front_view.jpg?width=2400",
    },
    {
        "slug": "khajuraho",
        "name": "Khajuraho Temples",
        "city": "Khajuraho",
        "state": "Madhya Pradesh",
        "lat": 24.8318,
        "lng": 79.9199,
        "era": "10th–11th century",
        "tagline": "Chandela-era temples of intricate sculpture.",
        "hero_image": "https://images.unsplash.com/photo-1672215055915-e6143dc70e6a?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        "panorama_image": "https://images.unsplash.com/photo-1672215055915-e6143dc70e6a?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
    },
    {
        "slug": "qutub-minar",
        "name": "Qutub Minar",
        "city": "Delhi",
        "state": "Delhi",
        "lat": 28.5245,
        "lng": 77.1855,
        "era": "12th–14th century",
        "tagline": "The tallest brick minaret in the world.",
        "hero_image": "https://commons.wikimedia.org/wiki/Special:FilePath/Qutb_Minar_2011.jpg?width=1600",
        "panorama_image": "https://commons.wikimedia.org/wiki/Special:FilePath/Qutub_Minar_in_the_monsoons.jpg?width=2400",
    },
    {
        "slug": "golden-temple",
        "name": "Golden Temple",
        "city": "Amritsar",
        "state": "Punjab",
        "lat": 31.6200,
        "lng": 74.8765,
        "era": "16th century",
        "tagline": "The holiest Gurdwara of the Sikh faith.",
        "hero_image": "https://commons.wikimedia.org/wiki/Special:FilePath/The_Golden_Temple_of_Amrithsar_7.jpg?width=1600",
        "panorama_image": "https://commons.wikimedia.org/wiki/Special:FilePath/Golden_Temple_India.jpg?width=2400",
    },
]


async def seed_places() -> None:
    for p in SEED_PLACES:
        await db.places.update_one(
            {"slug": p["slug"]},
            {"$set": {**p, "country": "India"}, "$setOnInsert": {"id": str(uuid.uuid4())}},
            upsert=True,
        )


# ------------------------------ HELPERS -------------------------------------


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def clean_for_tts(text: str) -> str:
    text = emoji.replace_emoji(text, replace="")
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)
    text = re.sub(r"[*_#>~|]", "", text)
    return re.sub(r"\s+", " ", text).strip()


async def generate_timeline(place: dict) -> PlaceTimeline:
    cached = await db.timelines.find_one({"place_id": place["id"]}, {"_id": 0})
    if cached:
        return PlaceTimeline(**cached)

    import json as _json

    system = (
        "You are a concise heritage historian for an Indian travel app. Respond with STRICT JSON only, "
        "no markdown, no code fences. Keep each description to 1-2 sentences. Years should be specific "
        "where possible (e.g., '1632', '1857', '1600s'). Focus on verified history."
    )
    prompt = (
        f"Create a historical fact sheet for '{place['name']}' in {place['city']}, {place['state']}, India.\n"
        "Return JSON with this exact shape:\n"
        "{\n"
        '  "summary": "2-3 sentence overview",\n'
        '  "events": [ {"year": "...", "title": "...", "description": "..."}, ... 5 to 7 items in chronological order ],\n'
        '  "did_you_know": "A single surprising fact in 1-2 sentences",\n'
        '  "hotspots": ["short label 1", "short label 2", "short label 3"]\n'
        "}\n"
        "Only output the JSON object."
    )
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"timeline-{place['id']}",
        system_message=system,
    ).with_model("openai", "gpt-5.6-terra")

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        text = response if isinstance(response, str) else str(response)
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
        data = _json.loads(text)
    except Exception as exc:
        logging.getLogger(__name__).error("generate_timeline failed: %s", exc)
        data = {
            "summary": f"{place['name']} is a celebrated heritage site in {place['city']}, {place['state']}.",
            "events": [
                {"year": place.get("era", ""), "title": "Built", "description": place.get("tagline", "")}
            ],
            "did_you_know": "Fun fact coming soon.",
            "hotspots": ["Main entrance", "Central hall", "Outer wall"],
        }

    failed = data.get("did_you_know") == "Fun fact coming soon."
    timeline = PlaceTimeline(
        place_id=place["id"],
        summary=data.get("summary", ""),
        events=[TimelineEvent(**e) for e in data.get("events", [])],
        did_you_know=data.get("did_you_know", ""),
        hotspots=data.get("hotspots", [])[:6],
    )
    if not failed:
        await db.timelines.update_one(
            {"place_id": place["id"]},
            {"$set": timeline.model_dump()},
            upsert=True,
        )
    return timeline


# ------------------------------ ROUTES --------------------------------------


@api_router.get("/")
async def root():
    return {"message": "Yatra API"}


@api_router.get("/places", response_model=List[Place])
async def list_places():
    docs = await db.places.find({}, {"_id": 0}).sort("name", 1).to_list(200)
    return [Place(**d) for d in docs]


@api_router.get("/places/nearby", response_model=List[dict])
async def nearby_places(lat: float = Query(...), lng: float = Query(...), limit: int = Query(10, ge=1, le=50)):
    docs = await db.places.find({}, {"_id": 0}).to_list(200)
    with_dist = [{**d, "distance_km": round(haversine(lat, lng, d["lat"], d["lng"]), 1)} for d in docs]
    with_dist.sort(key=lambda x: x["distance_km"])
    return with_dist[:limit]


@api_router.get("/places/search", response_model=List[Place])
async def search_places(q: str = Query(..., min_length=1)):
    pattern = re.escape(q)
    docs = await db.places.find(
        {
            "$or": [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"city": {"$regex": pattern, "$options": "i"}},
                {"state": {"$regex": pattern, "$options": "i"}},
            ]
        },
        {"_id": 0},
    ).to_list(50)
    return [Place(**d) for d in docs]


@api_router.get("/places/{slug}", response_model=Place)
async def get_place(slug: str):
    doc = await db.places.find_one({"slug": slug}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Place not found")
    return Place(**doc)


@api_router.get("/places/{slug}/timeline", response_model=PlaceTimeline)
async def get_place_timeline(slug: str):
    place = await db.places.find_one({"slug": slug}, {"_id": 0})
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    return await generate_timeline(place)


@api_router.get("/places/{slug}/trivia", response_model=List[Trivia])
async def list_trivia(slug: str):
    place = await db.places.find_one({"slug": slug}, {"_id": 0})
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    docs = (
        await db.trivia.find({"place_id": place["id"]}, {"_id": 0})
        .sort("created_at", -1)
        .to_list(50)
    )
    return [Trivia(**d) for d in docs]


@api_router.post("/places/{slug}/trivia", response_model=Trivia)
async def create_trivia(slug: str, body: TriviaCreate):
    place = await db.places.find_one({"slug": slug}, {"_id": 0})
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    doc = Trivia(place_id=place["id"], author=body.author, title=body.title, body=body.body)
    await db.trivia.insert_one(doc.model_dump())
    return doc


@api_router.post("/places/{slug}/narrate")
async def narrate_place(slug: str, voice: str = "fable"):
    place = await db.places.find_one({"slug": slug}, {"_id": 0})
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    timeline = await generate_timeline(place)

    parts = [f"{place['name']} in {place['city']}, {place['state']}.", timeline.summary]
    for e in timeline.events:
        parts.append(f"In {e.year}, {e.title}. {e.description}")
    parts.append(f"Did you know? {timeline.did_you_know}")
    text = clean_for_tts(" ".join(parts))[:3800]

    key = hashlib.sha256(f"{place['id']}|{voice}|tts-1|mp3|{text}".encode()).hexdigest()
    path = TTS_CACHE_DIR / f"{key}.mp3"
    if not path.exists():
        tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
        try:
            audio = await tts.generate_speech(text=text, model="tts-1", voice=voice, response_format="mp3")
        except Exception as exc:
            logging.getLogger(__name__).error("tts failed: %s", exc)
            raise HTTPException(status_code=502, detail="Narration unavailable right now.") from exc
        path.write_bytes(audio)
    return {"audio_url": f"/api/tts/{key}.mp3", "text": text}


@api_router.get("/tts/{key}.mp3")
async def get_tts(key: str):
    if not re.fullmatch(r"[0-9a-f]{64}", key):
        raise HTTPException(status_code=404, detail="Audio not found")
    path = TTS_CACHE_DIR / f"{key}.mp3"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=31536000"})


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def start_tasks():
    app.state.index_task = asyncio.create_task(ensure_indexes())
    app.state.seed_task = asyncio.create_task(seed_places())


@app.on_event("shutdown")
async def shutdown_db_client():
    for task_name in ("index_task", "seed_task"):
        task: Optional[asyncio.Task] = getattr(app.state, task_name, None)
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    client.close()
