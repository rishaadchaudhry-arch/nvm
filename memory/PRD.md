# Yatra — India's Heritage Through Time

## Vision
A mobile travel companion that tells the history of any Indian heritage site you visit — with AI-generated timelines, 360° panoramic exploration, AR camera overlays, audio narration, and a community "Did You Know?" layer for local traditions. India first, global later.

## MVP Scope (shipped)
- **Discover tab** – Hero header "Yatra", GPS-based "Nearby" row (haversine sorted), curated full-bleed destination cards for 8 India sites (Taj Mahal, Hampi, Red Fort, Mysore Palace, Konark, Khajuraho, Qutub Minar, Golden Temple).
- **Place Detail** – Cinematic hero, AI-generated 2–3 sentence summary, chronological event timeline (year / title / description), "Did You Know?" card, community trivia list, sticky narration player.
- **360° Viewer** – Wide panoramic image with glowing tappable info hotspots.
- **AR Camera View** – Live camera feed (back camera) with floating historical fact cards; navigate chronologically through events. Falls back to panorama image on web/no-permission.
- **Add Contribution** – "Did you know?" form (author / title / story) saved per place, surfaced in the detail screen.
- **Search tab** – Typeahead across name/city/state.
- **Journey tab** – AsyncStorage-backed Visited + Saved lists.

## Integrations
- **GPT 5.6 Terra** via Emergent Universal LLM Key — generates place timeline (JSON: summary, events, did_you_know, hotspots). Cached per place in `timelines` collection.
- **OpenAI TTS (tts-1, voice: fable)** via Emergent Universal LLM Key — narrates each place's combined history. Audio cached on disk by SHA-256 of (place, voice, model, text) and served from `/api/tts/{key}.mp3`.
- **expo-location** — foreground permission, Balanced accuracy.
- **expo-camera** — back camera for AR overlay.
- **expo-audio** — streaming the narration MP3 with pause/resume.

## Backend (FastAPI + MongoDB)
All routes prefixed with `/api`. Collections: `places`, `timelines`, `trivia`. Indexes on slug, place_id, name/city/state. Seeded on startup.

Endpoints: `GET /places`, `GET /places/nearby`, `GET /places/search`, `GET /places/{slug}`, `GET /places/{slug}/timeline`, `GET|POST /places/{slug}/trivia`, `POST /places/{slug}/narrate`, `GET /tts/{key}.mp3`.

## Design
Editorial Mobile LIGHT — warm heritage palette (saffron `#C85A32`, parchment `#F9F6F0`, gold `#D4AF37`, deep indigo `#1A2130`). Display: Cormorant Garamond. Body: DM Sans. Solid surfaces, fine borders, generous whitespace — no glassmorphism.

## Smart Business Enhancement
Every place's community-submitted trivia is unlocked when users contribute at least one of their own, turning passive readers into contributors and compounding content as travellers roam — Yatra effectively crowdsources its moat while showing each user something no guidebook offers.

## Roadmap (not in MVP)
- Expand to global sites (same schema, add country-scoped seed data).
- Photo upload on contributions via Emergent Object Storage.
- True 360° WebGL viewer via pannellum in WebView.
- Streaming TTS as text chunks.
- Share a trip (export visited sites as a timeline card).
