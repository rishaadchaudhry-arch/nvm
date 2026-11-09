import { useCallback, useEffect, useState } from "react";

import { storage } from "@/src/utils/storage";

const SAVED_KEY = "yatra_saved";
const VISITED_KEY = "yatra_visited";

async function readList(key: string): Promise<string[]> {
  const raw = await storage.getItem(key, "");
  return raw ? String(raw).split("|").filter(Boolean) : [];
}

async function writeList(key: string, list: string[]) {
  await storage.setItem(key, list.join("|"));
}

export function useJourney() {
  const [saved, setSaved] = useState<string[]>([]);
  const [visited, setVisited] = useState<string[]>([]);

  const reload = useCallback(async () => {
    setSaved(await readList(SAVED_KEY));
    setVisited(await readList(VISITED_KEY));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const toggleSaved = useCallback(async (slug: string) => {
    const cur = await readList(SAVED_KEY);
    const next = cur.includes(slug) ? cur.filter((s) => s !== slug) : [...cur, slug];
    await writeList(SAVED_KEY, next);
    setSaved(next);
  }, []);

  const markVisited = useCallback(async (slug: string) => {
    const cur = await readList(VISITED_KEY);
    if (cur.includes(slug)) return;
    const next = [slug, ...cur];
    await writeList(VISITED_KEY, next);
    setVisited(next);
  }, []);

  return { saved, visited, toggleSaved, markVisited, reload };
}
