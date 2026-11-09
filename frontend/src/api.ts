import { storage } from "@/src/utils/storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

export type Era = { key: string; title: string; description: string };
export type EraLabel = { key: string; label: string };

export type Region = {
  slug: string;
  name: string;
  kind: string;
  cover_image: string;
  summary: string;
  eras: Era[];
  area_count?: number;
  has_stories?: boolean;
};

export type Area = {
  slug: string;
  region_slug: string;
  name: string;
  lat: number;
  lng: number;
  radius_m: number;
  cover_image: string;
  summary: string;
  era_keys: string[];
  eras: Era[];
  distance_m?: number;
};

export type Poi = {
  slug: string;
  area_slug: string;
  name: string;
  category: string;
  lat: number;
  lng: number;
  image: string;
  eras: Era[];
  distance_m?: number;
};

export type Tradition = {
  id: string;
  area_slug: string;
  poi_slug: string | null;
  author: string;
  title: string;
  body: string;
  status: "pending" | "verified" | "rejected";
  verified_by: "community" | "admin" | null;
  upvotes: number;
  created_at: string;
  has_voted?: boolean;
};

export type Nearby = {
  inside: null | { area: Area; eras: EraLabel[]; pois: Poi[]; did_you_know: Tradition[] };
  nearest: null | { slug: string; name: string; distance_m: number };
  areas: Area[];
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}, token?: string | null): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") detail = j.detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

// Anonymous per-install token issued (and signed) by the server, used only to stop double upvotes.
let deviceTokenCache: string | null = null;
let devicePending: Promise<string> | null = null;
export async function getDeviceToken(): Promise<string> {
  if (deviceTokenCache) return deviceTokenCache;
  if (!devicePending) {
    devicePending = (async () => {
      let tok = String((await storage.secureGet("device_token", "")) ?? "");
      if (!tok) {
        tok = (await request<{ device_token: string }>("/api/devices", { method: "POST" })).device_token;
        await storage.secureSet("device_token", tok);
      }
      deviceTokenCache = tok;
      return tok;
    })().finally(() => (devicePending = null));
  }
  return devicePending;
}
// Reads must not fail just because a device token couldn't be issued.
const tokenOrEmpty = () => getDeviceToken().catch(() => "");

const ADMIN_TOKEN_KEY = "admin_token";
export const adminToken = {
  get: async () => (await storage.secureGet(ADMIN_TOKEN_KEY, "")) as string,
  set: (t: string) => storage.secureSet(ADMIN_TOKEN_KEY, t),
  clear: () => storage.secureRemove(ADMIN_TOKEN_KEY),
};

export const api = {
  regions: () => request<Region[]>("/api/regions"),
  region: (slug: string) => request<{ region: Region; areas: Area[] }>(`/api/regions/${slug}`),
  area: async (slug: string) =>
    request<{ area: Area; pois: Poi[]; did_you_know: Tradition[]; eras: EraLabel[] }>(
      `/api/areas/${slug}?device_token=${await tokenOrEmpty()}`,
    ),
  poi: async (slug: string) =>
    request<{
      poi: Poi;
      area: { slug: string; name: string };
      eras: EraLabel[];
      did_you_know: Tradition[];
      community: Tradition[];
      upvote_threshold: number;
    }>(`/api/pois/${slug}?device_token=${await tokenOrEmpty()}`),
  poisBySlugs: (slugs: string[]) => request<Poi[]>(`/api/pois?slugs=${encodeURIComponent(slugs.join(","))}`),
  nearby: (lat: number, lng: number) => request<Nearby>(`/api/nearby?lat=${lat}&lng=${lng}`),
  traditions: async (status: "pending" | "verified") =>
    request<Tradition[]>(`/api/traditions?status=${status}&device_token=${await tokenOrEmpty()}`),
  addTradition: (body: { area_slug: string; poi_slug?: string | null; author: string; title: string; body: string }) =>
    request<Tradition>("/api/traditions", json(body)),
  upvote: async (id: string) => request<Tradition>(`/api/traditions/${id}/upvote`, json({ device_token: await getDeviceToken() })),
  narrate: (slug: string) => request<{ audio_url: string }>(`/api/pois/${slug}/narrate`, { method: "POST" }),
  audioUrl: (path: string) => `${BASE}${path}`,

  login: async (email: string, password: string) => {
    const body = `username=${encodeURIComponent(email)}&password=${encodeURIComponent(password)}`;
    const res = await request<{ access_token: string }>("/api/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    await adminToken.set(res.access_token);
  },
  adminQueue: async () => request<Tradition[]>("/api/admin/traditions?status=pending", {}, await adminToken.get()),
  moderate: async (id: string, action: "verify" | "reject") =>
    request<Tradition>(`/api/admin/traditions/${id}/moderate`, json({ action }), await adminToken.get()),
};

export function formatDistance(m: number) {
  if (m < 1000) return `${Math.round(m)} m`;
  if (m < 100000) return `${(m / 1000).toFixed(1)} km`;
  return `${Math.round(m / 1000).toLocaleString()} km`;
}

export function bearingDeg(lat1: number, lng1: number, lat2: number, lng2: number) {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const y = Math.sin(toRad(lng2 - lng1)) * Math.cos(toRad(lat2));
  const x =
    Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) -
    Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(toRad(lng2 - lng1));
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

export function distanceM(lat1: number, lng1: number, lat2: number, lng2: number) {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const a =
    Math.sin(toRad(lat2 - lat1) / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(toRad(lng2 - lng1) / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(a));
}
