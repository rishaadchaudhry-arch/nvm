# Yatra: India's history through your camera

## Original problem statement
"I want to create an app that could tell the history of each place. Wherever I travel, I open my phone, see a VR/AR view of the place I'm around, and it tells the history: exact dates, what happened in the 1700s, 1800s. Make it global later, India first. Keep an add-history section where people can add local traditions, like a sudden 'Did you know?' when you get to that place."

Second brief (v2): "It's very basic. I want it to work like Wikipedia + maps through the camera. Point the camera at a place (not just monuments, normal places and states too) and see what was there in the 1700s, 1800s, 1970s and what's there now. Start with Chandni Chowk. Content can be added later, but code it properly. Add oral traditions that people can submit. Verified ones become 'Did you know?' facts."

## User choices
- Verification: BOTH community upvotes (5) AND admin approval
- Places with no hand-written content: show NOTHING (no AI-written history)
- Camera view: ONLY on location (no remote/virtual tour)
- Narration: OpenAI TTS (tts-1, voice "fable") via the Emergent key
- Style: warm heritage palette (Cormorant Garamond + DM Sans)

## Architecture
- Backend: FastAPI + MongoDB (`server.py`, starter content in `seed_content.py` with SEED_VERSION)
  - Content model: regions (states) → areas (e.g. Chandni Chowk, with a GPS radius) → POIs (lat/lng + era entries keyed by era: 1650s, 1700s, 1857, 1900s, 1947, 1970s, today)
  - Traditions: pending → verified (5 upvotes from server-signed device tokens, max 3 votes per network, or admin) / rejected
  - Admin: JWT login (argon2 hash, account seeded from env), moderation queue, content upsert APIs (PUT /api/admin/regions|areas|pois/{slug})
  - Narration: TTS mp3 cached on disk and served with FileResponse
- Frontend: Expo Router. Tabs: Explore, Camera, Traditions, Journey. Stack: region, area, poi, tradition/new, admin
  - Camera: live GPS + compass heading projects nearby POIs (600 m range, 55° FOV) onto the camera feed. An era picker changes every label. A "Did you know?" pops up within 80 m of a POI with verified traditions. On web you drag to rotate (there's no compass)

## Implemented
- 2026-11-09 v1: basic places, AI timeline, 360 photo, AR overlay, trivia (replaced)
- 2026-11-09 v2: full rebuild into location-based camera + era time-travel; Chandni Chowk with 12 hand-written POIs; Delhi state timeline; 5 other states as "coming soon"; oral traditions with upvotes + admin moderation; admin content APIs; bundled fonts; real Wikimedia photos; anti-spoof IP handling (TRUSTED_PROXY_HOPS)

## Backlog
- P0: fact-check the starter content with a historian before launch
- P1: admin screen for adding/editing places (APIs already exist), photo uploads on traditions, offline cache of an area
- P1: then/now photo slider (archival images per era)
- P2: more areas (Hauz Khas, Lodhi Road, Fort Kochi, Old Goa), global expansion, multilingual (Hindi) content + narration
- Note: TRUSTED_PROXY_HOPS=2 matches the preview proxy chain (Cloudflare + Google LB). Re-check it in production.
