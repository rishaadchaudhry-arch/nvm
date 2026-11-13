# NVM (Nevermind)

Point your camera at any street and read what was there — 1500s, 1600s, 1700s,
up to today. An Expo app over a FastAPI backend that builds each street's
history from open data (OpenStreetMap and Overpass, English, Hindi and Urdu
Wikipedia, Wikidata), arranged by an OpenAI model that may only use the sources
it is given.

**Coverage is Delhi NCT.** Searches are confined to it and a point outside it is
refused, because the sources that make a street history worth reading are deep
for Delhi and thin elsewhere. `SCOPE_BBOX`, `SCOPE_NAME` and `SCOPE_STATE` in
`backend/.env` move or lift that boundary; no code changes are needed.

```
backend/    FastAPI + motor (async MongoDB) + Pydantic v2
  server.py          routes, auth, rate limits, CSV import/export
  history_engine.py  geocoding, source gathering, era composition
  openai_voice.py    history text + MP3 narration
  photo_storage.py   local-account photos (MongoDB today, S3/R2 ready)
  share_card.py      1080×1350 share image, rendered with Pillow
  tests/             pytest suite, run against a live backend
frontend/   Expo + expo-router, strict TypeScript
  app/      screens (index = camera, place/[key], search, stories, admin)
  src/      api.ts, components, theme
memory/     PRD.md — the product decisions behind the app
```

This project previously ran inside Emergent. It no longer depends on any
Emergent service, package or environment: see "What changed when it left
Emergent" at the bottom.

## What you need

- Node 20 or newer, and Yarn
- Python 3.11 or newer
- MongoDB — locally, or a free MongoDB Atlas cluster
- An OpenAI API key with credit on the account

## Setup

```bash
# 1. Backend dependencies
cd backend
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Backend config — fill in every value
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste as JWT_SECRET

# 3. Frontend
cd ../frontend
yarn install
cp .env.example .env
```

MongoDB, if you are not using Atlas:

```bash
docker run -d --name nvm-mongo -p 27017:27017 -v nvm-mongo:/data/db mongo:7
```

## Running

Two terminals:

```bash
cd backend && source .venv/bin/activate && uvicorn server:app --host 0.0.0.0 --port 8001 --reload
cd frontend && yarn start                     # press w for web, or scan the QR in Expo Go
```

The backend answers on `http://localhost:8001`; `http://localhost:8001/docs`
lists every endpoint. The admin screen is at `/admin` in the app, and the login
is the `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `backend/.env` (the account is
created or updated on every start).

## How the app reaches the backend

Every backend route lives under `/api`, because the backend mounts one
`APIRouter(prefix="/api")`. The app reads `EXPO_PUBLIC_BACKEND_URL` from
`frontend/.env` and calls `EXPO_PUBLIC_BACKEND_URL + "/api/..."`.

That URL has to be absolute. The same bundle runs on a phone in Expo Go, where
`localhost` means the phone itself — so for a phone, use your computer's LAN
address (`http://192.168.x.x:8001`). Only `EXPO_PUBLIC_*` names reach the app,
and Metro bakes their values in at bundle time, so restart Metro after editing
`.env`.

## Deploying

- **Backend:** any host that runs a Python web service (Render, Railway, Fly,
  a VM). Serve it with `uvicorn server:app --host 0.0.0.0 --port $PORT`, set
  the same environment variables there, and point `MONGO_URL` at Atlas. Set
  `TRUSTED_PROXY_HOPS` to the number of proxies you put in front of it —
  leaving it at 0 behind a proxy lets a forged `X-Forwarded-For` header walk
  past the rate limits.
- **App builds:** `eas.json` is set up for Expo Application Services. Run
  `npx eas-cli build --profile preview --platform android` for a shareable
  APK, or `--profile production` for store builds. The first run asks you to
  log in and creates the EAS project. Set `EXPO_PUBLIC_BACKEND_URL` for the
  build profile in `eas.json` to your deployed backend.

## Backend notes

- Routes are registered on `api = APIRouter(prefix="/api")`, never on `app`
  directly, or the phone cannot reach them.
- Documents use a string `id` from `uuid4`, not `ObjectId`, and `_id` is left
  out of every response.
- Store aware UTC datetimes (`datetime.now(timezone.utc)`); motor returns them
  without a timezone, so attach one before comparing.
- Every query's index belongs in `INDEXES` in `server.py`.
- Motor connects lazily, so `python -c "import server"` is a quick check for
  syntax and import errors.

## Frontend notes

- expo-router, file-based: each file under `app/` is a screen, typed routes
  are on, `@/*` points at the app folder.
- All colors come from `src/theme.ts` (`useTheme`, `makeStyles`).
- Storage goes through `@/src/utils/storage` (`secureGet`/`secureSet` for
  tokens) — never AsyncStorage or SecureStore directly.
- Uploads go through `@/src/utils/upload`; building a `FormData` by hand works
  in the web preview and throws on a phone.
- Data fetching is TanStack Query against the typed `src/api.ts`. The
  TypeScript types there mirror the Pydantic models by hand — change both in
  the same edit.

Checks:

```bash
cd frontend && yarn tsc --noEmit && yarn lint
```

## Tests

The backend tests run against a *running* backend, not an in-process app. Start
the backend, then:

```bash
cd backend && source .venv/bin/activate
EXPO_PUBLIC_BACKEND_URL=http://localhost:8001 pytest -c pytest.ini tests
```

The admin login comes from `backend/.env`; no password is written in a test
file. `pytest.ini` already sets `-n 2 --dist loadscope`, so don't pass your own
`-n` (serial is `-n 0`).

Some tests still hardcode street keys from the original database
(`lajpat-nagar-ii-1a9b6fe7`, `nai-sarak-1017b307`). Against a fresh database
those tests fail until the streets are visited once in the app, or the keys are
replaced.

## What changed when it left Emergent

- Dropped the `emergentintegrations` package, the Emergent-hosted `litellm`
  wheel, and ~90 unused packages from `requirements.txt`.
- Deleted `backend/object_storage.py` (Emergent Object Storage) and the
  one-off photo migration that used it. Photos live in MongoDB through
  `photo_storage.py`; the legacy photos were already migrated.
- Deleted the pod-only install guard (`frontend/scripts/cmd-guard*`) and its
  `preinstall` hook, plus `.emergent/` and `TEMPLATE.md`.
- Replaced the platform bundle identifiers with `app.nvm.mobile` and added
  `eas.json`, since Expo builds are yours to run now.
- Added `backend/.env.example` and `frontend/.env.example`; the backend now
  fails at startup with a readable message when a value is missing.
