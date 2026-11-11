# NVM (Nevermind): point your camera at any street, see what was there

## Problem statement (latest, v3)
"Everything has to be when you are in front of that place. Not just monuments — streets are the main thing. Any street I go to, I put my camera on and it tells me its history: 1500s, 1600s, 1700s… everywhere in the world, starting with India. One camera that shows a place and tells me its detail — Chandni Chowk, something inside it, a random street near it, or any street in India. If I search a street, I know what was there before (maybe just barren land). Build the base right; content can grow. App name NVM (Nevermind). Simple design: white + brown." Earlier asks kept: oral traditions people can add. Verified ones become "Did you know?" at that spot.

## User choices
- Story verification: BOTH 5 community upvotes AND admin approval
- Camera works on location (search lets you read any street remotely)
- AI on the user's own OPENAI_API_KEY (switched 2026-11-11): history text = gpt-6-sol via Responses API; narration = gpt-realtime-2.1-mini over the Realtime API (PCM → MP3 with lameenc, voice "marin"), because tts-1/tts-1-hd/gpt-4o-mini-tts shut down 6 Jan 2027. EMERGENT_LLM_KEY is now used only for Emergent Object Storage (local-account photos).
- Design: simple, warm white/brown (Playfair Display + DM Sans)
- History text: AI (GPT-5.6-terra) may ONLY arrange fetched open-data sources. Every era is cited and scope-labelled, and empty eras stay empty. (This replaces the v2 choice of "nothing without hand-written content", because v3 needs coverage of any street.)

## Architecture
- backend/history_engine.py: OSM Nominatim reverse/search (1 req/s throttle) → Wikipedia geosearch + level articles (street, neighbourhood, city, district, state) + Wikidata items within 400 m → GPT-5.6-terra makes JSON for 8 eras (pre1500, 1500s, 1600s, 1700s, 1800s, 1900_1947, 1947_2000, today), each with scope + source ids. Uncited text is dropped, and OSM is never a history citation.
- backend/server.py: /api/look (35 m ahead along the compass heading, 11 m geocode cache cell), /api/history/{key} (cached per place, in-flight dedupe, 40 builds/IP/hour, failures uncounted), /api/search, stories (geo 2dsphere, 150 m radius), device tokens + per-network vote cap, admin JWT (argon2), DELETE /api/admin/history/{key} to rebuild, TTS narration
- frontend: stack only. index (camera home: live camera, facing pill, era chips, era card, "Did you know?" toast), place/[key] (full timeline, then-now, facts, sources, narration, stories), search, story/new, stories (community votes), admin

## Done
- 2026-11-09 v1 Yatra (basic places) → v2 (Chandni Chowk hand-written camera labels) → v3 NVM rebuild (any street, open-data engine)
- v3 testing iteration_4: all flows pass. Fixed the unreadable "Did you know?" card, scope over-claims, repeated filler, uncited summary/then-now, OSM as citation, and failed builds counting against the limit

## Local accounts
- Admin → "Local accounts" tab: add an entry for any street (search → pick), era, story text, who told it, their village/town, date collected, optional photo (Emergent Object Storage via backend). Shown inside the matching era node of the street timeline as a "LOCAL ACCOUNT" card (brown left bar, tinted panel, legend) — separate from sourced Wikipedia text. Timeline also renders when a street has only local accounts and no written records. Soft delete from admin.
- Endpoints: POST/GET/DELETE /api/admin/local-accounts, GET /api/local-accounts?place_key=, GET /api/local-accounts/{id}/photo
- Tested iteration_5: backend 36/36, admin + timeline flows pass
- Bulk CSV import (street name or key, era label/key, flexible dates; per-row failure report) + CSV backup export of all stories and local accounts (iteration_6)
- Admin "History" tab: edit any street's summary/then-now/eras with per-era scope + citation toggles, add manual sources, rebuild from fresh sources; server rejects text without a citable source. "Add/Replace photo" on existing accounts. Hindi Wikipedia (geosearch, interlanguage links, direct search) added as a source; shown as "Wikipedia (Hindi)" (iteration_7)

- Share card: share-btn on the place screen opens a preview of a 1080×1350 PNG (street name, one fact, NVM mark; Pillow-rendered server-side with the app fonts/palette), "Another fact" cycles did-you-knows → eras → summary, Share uses the native share sheet (web: new tab). (iteration_8)

## Backlog
- P0 before launch: replace public Nominatim with a paid geocoder (public usage policy disallows heavy app traffic); re-check TRUSTED_PROXY_HOPS in production
- P1: Hindi/regional-language Wikipedia sources (much richer for small towns), archival photos per era, offline cache for an area, admin "rebuild/edit history" UI
- P2: global rollout (engine is already country-agnostic; search is limited to India via countrycodes=in)
