const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

export type Place = {
  id: string;
  slug: string;
  name: string;
  city: string;
  state: string;
  country: string;
  lat: number;
  lng: number;
  era: string;
  tagline: string;
  hero_image: string;
  panorama_image: string;
  distance_km?: number;
};

export type TimelineEvent = { year: string; title: string; description: string };

export type PlaceTimeline = {
  place_id: string;
  summary: string;
  events: TimelineEvent[];
  did_you_know: string;
  hotspots: string[];
};

export type Trivia = {
  id: string;
  place_id: string;
  author: string;
  title: string;
  body: string;
  created_at: string;
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export const api = {
  listPlaces: () => get<Place[]>("/api/places"),
  nearby: (lat: number, lng: number) => get<Place[]>(`/api/places/nearby?lat=${lat}&lng=${lng}&limit=8`),
  search: (q: string) => get<Place[]>(`/api/places/search?q=${encodeURIComponent(q)}`),
  place: (slug: string) => get<Place>(`/api/places/${slug}`),
  timeline: (slug: string) => get<PlaceTimeline>(`/api/places/${slug}/timeline`),
  trivia: (slug: string) => get<Trivia[]>(`/api/places/${slug}/trivia`),
  addTrivia: (slug: string, body: { author: string; title: string; body: string }) =>
    post<Trivia>(`/api/places/${slug}/trivia`, body),
  narrate: (slug: string, voice = "fable") =>
    post<{ audio_url: string; text: string }>(`/api/places/${slug}/narrate?voice=${voice}`, {}),
  audioUrl: (path: string) => `${BASE}${path}`,
};
