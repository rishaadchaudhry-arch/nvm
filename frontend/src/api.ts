import { storage } from "@/src/utils/storage";
import { uploadForm, type LocalFile } from "@/src/utils/upload";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

export type Scope = "spot" | "street" | "neighbourhood" | "city" | "region" | "none";

export type Place = {
  key: string;
  title: string;
  subtitle: string;
  lat: number;
  lng: number;
  city: string | null;
  state: string | null;
  country: string | null;
  display_name: string;
  osm_url: string | null;
};

export type EraEntry = { key: string; label: string; heading: string; text: string; scope: Scope; sources: number[] };
export type Source = { id: number; type: "wikipedia" | "wikidata" | "openstreetmap" | "openstreetmap_heritage" | "gazetteer" | "manual"; title: string; url: string; scope: Scope; lang?: string | null };

export type History = {
  key: string;
  summary: string;
  eras: EraEntry[];
  then_now: string;
  did_you_know: { text: string; sources: number[] }[];
  sources: Source[];
  has_records: boolean;
  built_at: string;
  edited_at?: string | null;
  edited_by?: string | null;
};

export type HistoryEdit = {
  summary: string;
  then_now: string;
  eras: { key: string; heading: string; text: string; scope: Scope; sources: number[] }[];
  new_sources: { title: string; url: string; scope: Scope }[];
};

export const sourceLabel = (src: Source) =>
  src.type === "wikipedia" ? (src.lang === "hi" ? "Wikipedia (Hindi)" : "Wikipedia") : src.type === "wikidata" ? "Wikidata" : src.type === "manual" ? "Added by the NVM team" : "OpenStreetMap";

export type Look = { place: Place; facing: { lat: number; lng: number }; history: History | null };

export type SearchResult = { title: string; subtitle: string; lat: number; lng: number; type: string };

export type Tradition = {
  id: string;
  place_key: string;
  place_title: string;
  lat: number;
  lng: number;
  author: string;
  title: string;
  body: string;
  status: "pending" | "verified" | "rejected";
  verified_by: "community" | "admin" | null;
  upvotes: number;
  created_at: string;
  has_voted?: boolean;
};

export type LocalAccount = {
  id: string;
  place_key: string;
  place_title: string;
  era: string;
  era_label: string;
  body: string;
  told_by: string;
  village: string;
  collected_on: string;
  photo_url: string | null;
  added_by: string;
  created_at: string;
};

export const ERAS = [
  { key: "pre1500", label: "Before 1500" },
  { key: "1500s", label: "1500s" },
  { key: "1600s", label: "1600s" },
  { key: "1700s", label: "1700s" },
  { key: "1800s", label: "1800s" },
  { key: "1900_1947", label: "1900–1947" },
  { key: "1947_2000", label: "1947–2000" },
  { key: "today", label: "Today" },
];

export const SCOPE_LABEL: Record<Scope, string> = {
  spot: "About this exact spot",
  street: "About this street",
  neighbourhood: "About this neighbourhood",
  city: "About the wider city",
  region: "About the wider region",
  none: "",
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
  look: (lat: number, lng: number, heading?: number | null) =>
    request<Look>(`/api/look?lat=${lat}&lng=${lng}${heading == null ? "" : `&heading=${Math.round(heading) % 360}`}`),
  history: (key: string) => request<History>(`/api/history/${encodeURIComponent(key)}`),
  place: (key: string) => request<Place>(`/api/places/${encodeURIComponent(key)}`),
  search: (q: string) => request<SearchResult[]>(`/api/search?q=${encodeURIComponent(q)}`),
  config: () => request<{ upvote_threshold: number; story_radius_m: number }>("/api/config"),

  storiesForPlace: async (key: string, status: "pending" | "verified") =>
    request<Tradition[]>(`/api/traditions?status=${status}&place_key=${encodeURIComponent(key)}&device_token=${await tokenOrEmpty()}`),
  storiesNear: async (lat: number, lng: number) =>
    request<Tradition[]>(`/api/traditions?status=verified&lat=${lat}&lng=${lng}&device_token=${await tokenOrEmpty()}`),
  pendingStories: async () => request<Tradition[]>(`/api/traditions?status=pending&device_token=${await tokenOrEmpty()}`),
  addStory: (body: { place_key: string; author: string; title: string; body: string }) => request<Tradition>("/api/traditions", json(body)),
  upvote: async (id: string) => request<Tradition>(`/api/traditions/${id}/upvote`, json({ device_token: await getDeviceToken() })),

  narrate: (key: string) => request<{ audio_url: string }>(`/api/history/${encodeURIComponent(key)}/narrate`, { method: "POST" }),
  audioUrl: (path: string) => `${BASE}${path}`,
  cardFacts: (key: string) => request<{ label: string; text: string }[]>(`/api/history/${encodeURIComponent(key)}/card-facts`),
  cardUrl: (key: string, fact: number) => `${BASE}/api/history/${encodeURIComponent(key)}/card.png?fact=${fact}`,

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

  localAccounts: (key: string) => request<LocalAccount[]>(`/api/local-accounts?place_key=${encodeURIComponent(key)}`),
  adminLocalAccounts: async () => request<LocalAccount[]>("/api/admin/local-accounts", {}, await adminToken.get()),
  addLocalAccount: async (fields: { place_key: string; era: string; body: string; told_by: string; village: string; collected_on: string }, photo?: LocalFile | null) => {
    const res = await uploadForm(`${BASE}/api/admin/local-accounts`, {
      headers: { Authorization: `Bearer ${await adminToken.get()}` },
      fields,
      files: photo ? { photo } : {},
    });
    if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
    return (await res.json()) as LocalAccount;
  },
  deleteLocalAccount: async (id: string) => request<{ deleted: number }>(`/api/admin/local-accounts/${id}`, { method: "DELETE" }, await adminToken.get()),
  setAccountPhoto: async (id: string, photo: LocalFile) => {
    const res = await uploadForm(`${BASE}/api/admin/local-accounts/${id}/photo`, { headers: { Authorization: `Bearer ${await adminToken.get()}` }, files: { photo } });
    if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
    return (await res.json()) as LocalAccount;
  },
  editHistory: async (key: string, body: HistoryEdit) => request<History>(`/api/admin/history/${encodeURIComponent(key)}`, { ...json(body), method: "PUT" }, await adminToken.get()),
  rebuildHistory: async (key: string) => request<History>(`/api/admin/history/${encodeURIComponent(key)}/rebuild`, { method: "POST" }, await adminToken.get()),
  importLocalAccounts: async (file: LocalFile) => {
    const res = await uploadForm(`${BASE}/api/admin/local-accounts/import`, { headers: { Authorization: `Bearer ${await adminToken.get()}` }, files: { file } });
    if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
    return (await res.json()) as ImportResult;
  },
  templateUrl: () => `${BASE}/api/admin/local-accounts/template.csv`,
  exportUrl: async () => `${BASE}/api/admin/export.csv?token=${encodeURIComponent(await adminToken.get())}`,
  exportCsv: async () => {
    const res = await fetch(`${BASE}/api/admin/export.csv`, { headers: { Authorization: `Bearer ${await adminToken.get()}` } });
    if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
    return res.text();
  },
};

export type ImportResult = {
  created: number;
  rows: number;
  failed: { row: number; street: string; reason: string }[];
  created_rows: { row: number; id: string; place_title: string; era_label: string }[];
};

async function errorDetail(res: Response) {
  try {
    const j = await res.json();
    if (typeof j.detail === "string") return j.detail;
  } catch {}
  return `Request failed (${res.status})`;
}

export function distanceM(lat1: number, lng1: number, lat2: number, lng2: number) {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const a =
    Math.sin(toRad(lat2 - lat1) / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(toRad(lng2 - lng1) / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(a));
}

export function angleDiff(a: number, b: number) {
  return Math.abs(((a - b + 540) % 360) - 180);
}

export function compassLabel(deg: number) {
  return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round(deg / 45) % 8];
}
