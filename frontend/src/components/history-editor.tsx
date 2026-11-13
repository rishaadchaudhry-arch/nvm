import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Feather from "@react-native-vector-icons/feather";
import { useState } from "react";
import { ActivityIndicator, Pressable, Text, TextInput, View } from "react-native";

import { api, SCOPE_LABEL, sourceLabel, type History, type HistoryEdit, type Scope, type Source } from "@/src/api";
import { StreetPicker, type PickedPlace } from "@/src/components/local-account-form";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

const EDIT_SCOPES: Scope[] = ["spot", "street", "neighbourhood", "city", "region"];

type EraDraft = { key: string; label: string; heading: string; text: string; scope: Scope; sources: number[] };
type NewSource = { title: string; url: string };

/** Admin-only: correct or rebuild a street's history. Text without a source cannot be saved. */
export function HistoryEditor() {
  const s = useStyles();
  const { colors } = useTheme();
  const [place, setPlace] = useState<PickedPlace | null>(null);

  return (
    <View testID="history-editor">
      <Text style={s.label}>Street</Text>
      {place ? (
        <View style={s.picked} testID="he-picked-place">
          <Feather name="map-pin" size={16} color={colors.brand} />
          <View style={{ flex: 1 }}>
            <Text style={s.pickedTitle} numberOfLines={1}>{place.title}</Text>
            {place.subtitle ? <Text style={s.pickedSub} numberOfLines={1}>{place.subtitle}</Text> : null}
          </View>
          <Pressable onPress={() => setPlace(null)} hitSlop={12} style={s.change} testID="he-change-place">
            <Text style={s.changeText}>Change</Text>
          </Pressable>
        </View>
      ) : (
        <StreetPicker onPick={setPlace} />
      )}
      {place ? <Editor key={place.key} placeKey={place.key} /> : null}
    </View>
  );
}

function Editor({ placeKey }: { placeKey: string }) {
  const s = useStyles();
  const { colors } = useTheme();
  const qc = useQueryClient();
  const history = useQuery({ queryKey: ["history", placeKey], queryFn: () => api.history(placeKey), staleTime: Infinity, retry: 1 });

  const [summary, setSummary] = useState("");
  const [thenNow, setThenNow] = useState("");
  const [eras, setEras] = useState<EraDraft[]>([]);
  const [newSources, setNewSources] = useState<NewSource[]>([]);
  const [dirty, setDirty] = useState(false);
  const [confirmRebuild, setConfirmRebuild] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = (h: History) => {
    setSummary(h.summary);
    setThenNow(h.then_now);
    setEras(h.eras.map((e) => ({ key: e.key, label: e.label, heading: e.heading, text: e.text, scope: e.scope, sources: e.sources })));
    setNewSources([]);
    setDirty(false);
  };

  // Fill the form from a *new* version of the history only. Keying on the object itself would reset
  // the admin's unsaved edits every time react-query handed back a fresh copy of the same record.
  const [loadedVersion, setLoadedVersion] = useState<string | null>(null);
  const version = history.data ? `${history.data.key}|${history.data.edited_at ?? history.data.built_at}` : null;
  if (history.data && version !== loadedVersion) {
    setLoadedVersion(version);
    load(history.data);
  }

  const existing: Source[] = (history.data?.sources ?? []).filter((src) => src.type !== "openstreetmap");
  const nextId = Math.max(0, ...(history.data?.sources ?? []).map((src) => src.id)) + 1;
  // Sources typed in below get provisional ids that the server assigns in the same order.
  const pending = newSources.map((ns, i) => ({ id: nextId + i, title: ns.title.trim() || `New source ${i + 1}`, url: ns.url.trim() }));
  const citable = [...existing.map((src) => ({ id: src.id, title: src.title, meta: `${sourceLabel(src)} · ${SCOPE_LABEL[src.scope]}` })), ...pending.map((p) => ({ id: p.id, title: p.title, meta: "Added by the NVM team" }))];

  const update = (key: string, patch: Partial<EraDraft>) => {
    setEras((prev) => prev.map((e) => (e.key === key ? { ...e, ...patch } : e)));
    setDirty(true);
  };
  const toggleSource = (key: string, id: number) => {
    const e = eras.find((x) => x.key === key)!;
    update(key, { sources: e.sources.includes(id) ? e.sources.filter((x) => x !== id) : [...e.sources, id] });
  };

  const citableIds = new Set(citable.map((c) => c.id));
  const removeNewSource = (i: number) => {
    const removedId = nextId + i;
    setNewSources((p) => p.filter((_, j) => j !== i));
    // Later new sources shift down one id, so their citations move with them.
    setEras((p) => p.map((e) => ({ ...e, sources: e.sources.filter((id) => id !== removedId).map((id) => (id > removedId ? id - 1 : id)) })));
    setDirty(true);
  };
  const problems = eras.filter((e) => e.text.trim() && !e.sources.some((id) => citableIds.has(id))).map((e) => e.label);
  const badNew = newSources.some((ns) => ns.title.trim().length < 2 || !/^https?:\/\/.+/.test(ns.url.trim()));
  const canSave = dirty && !problems.length && !badNew;

  const save = useMutation({
    mutationFn: () => {
      const body: HistoryEdit = {
        summary: summary.trim(),
        then_now: thenNow.trim(),
        eras: eras.map((e) => ({ key: e.key, heading: e.heading.trim(), text: e.text.trim(), scope: e.text.trim() ? (e.scope === "none" ? "street" : e.scope) : "none", sources: e.sources })),
        new_sources: newSources.map((ns) => ({ title: ns.title.trim(), url: ns.url.trim(), scope: "street" as Scope })),
      };
      return api.editHistory(placeKey, body);
    },
    onSuccess: (h) => {
      qc.setQueryData(["history", placeKey], h);
      qc.invalidateQueries({ queryKey: ["look"] });
      load(h);
      setNote("Saved. Readers now see the corrected text.");
    },
  });

  const rebuild = useMutation({
    mutationFn: () => api.rebuildHistory(placeKey),
    onSuccess: (h) => {
      qc.setQueryData(["history", placeKey], h);
      qc.invalidateQueries({ queryKey: ["look"] });
      load(h);
      setConfirmRebuild(false);
      setNote(h.has_records ? "Rebuilt from fresh sources (English and Hindi Wikipedia)." : "Rebuilt, but open sources still have nothing for this spot.");
    },
    onError: () => setConfirmRebuild(false),
  });

  if (history.isPending) {
    return (
      <View style={s.loading} testID="he-loading">
        <ActivityIndicator color={colors.brandPrimary} />
        <Text style={s.muted}>Loading this street&apos;s history…</Text>
      </View>
    );
  }
  if (history.isError) {
    return (
      <Pressable onPress={() => history.refetch()} style={s.loading} testID="he-error">
        <Text style={s.error}>{(history.error as Error).message} Tap to retry.</Text>
      </Pressable>
    );
  }

  return (
    <View>
      <View style={s.rebuildBox}>
        <Text style={s.muted}>
          {history.data?.edited_at ? "Edited by the NVM team. " : ""}Built {new Date(history.data!.built_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}.
          Rebuilding fetches sources again and replaces all text, including edits.
        </Text>
        <Pressable
          style={[s.ghost, confirmRebuild && s.ghostDanger]}
          onPress={() => (confirmRebuild ? rebuild.mutate() : setConfirmRebuild(true))}
          disabled={rebuild.isPending}
          testID="he-rebuild"
        >
          {rebuild.isPending ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Feather name="refresh-cw" size={14} color={confirmRebuild ? colors.error : colors.brandPrimary} />}
          <Text style={[s.ghostText, confirmRebuild && { color: colors.error }]}>{rebuild.isPending ? "Rebuilding…" : confirmRebuild ? "Tap again to replace everything" : "Rebuild from sources"}</Text>
        </Pressable>
        {confirmRebuild && !rebuild.isPending ? (
          <Pressable onPress={() => setConfirmRebuild(false)} style={s.cancel} testID="he-rebuild-cancel">
            <Text style={s.changeText}>Keep current text</Text>
          </Pressable>
        ) : null}
        {rebuild.isError ? <Text style={s.error}>{(rebuild.error as Error).message}</Text> : null}
      </View>

      <Text style={s.label}>Summary</Text>
      <TextInput value={summary} onChangeText={(v) => { setSummary(v); setDirty(true); }} multiline maxLength={400} style={[s.input, s.multiShort]} placeholder="One or two sentences, drawn from the eras below" placeholderTextColor={colors.muted} testID="he-summary" />
      <Text style={s.label}>Then → now</Text>
      <TextInput value={thenNow} onChangeText={(v) => { setThenNow(v); setDirty(true); }} multiline maxLength={400} style={[s.input, s.multiShort]} placeholder="Earliest known state vs today" placeholderTextColor={colors.muted} testID="he-then-now" />

      <Text style={s.section}>Sources you can cite</Text>
      {citable.length ? citable.map((c) => (
        <Text key={c.id} style={s.srcLine}>
          <Text style={s.srcNum}>[{c.id}]</Text> {c.title} <Text style={s.muted}>· {c.meta}</Text>
        </Text>
      )) : <Text style={s.muted}>No sources yet. Add one below, then write.</Text>}
      {newSources.map((ns, i) => (
        <View key={i} style={s.newSrc} testID={`he-new-source-${i}`}>
          <Text style={s.srcNum}>[{nextId + i}] new source</Text>
          <TextInput value={ns.title} onChangeText={(v) => setNewSources((p) => p.map((x, j) => (j === i ? { ...x, title: v } : x)))} maxLength={160} style={s.input} placeholder="Title, e.g. Delhi District Gazetteer 1883" placeholderTextColor={colors.muted} testID={`he-new-source-title-${i}`} />
          <TextInput value={ns.url} onChangeText={(v) => setNewSources((p) => p.map((x, j) => (j === i ? { ...x, url: v } : x)))} maxLength={600} autoCapitalize="none" keyboardType="url" style={s.input} placeholder="https://…" placeholderTextColor={colors.muted} testID={`he-new-source-url-${i}`} />
          <Pressable onPress={() => removeNewSource(i)} style={s.cancel} testID={`he-remove-source-${i}`}>
            <Text style={[s.changeText, { color: colors.error }]}>Remove this source</Text>
          </Pressable>
        </View>
      ))}
      <Pressable onPress={() => { setNewSources((p) => [...p, { title: "", url: "" }]); setDirty(true); }} style={[s.ghost, { alignSelf: "flex-start", marginTop: spacing.md }]} testID="he-add-source">
        <Feather name="plus" size={14} color={colors.brandPrimary} />
        <Text style={s.ghostText}>Add a source</Text>
      </Pressable>

      <Text style={s.section}>Eras</Text>
      {eras.map((e) => (
        <View key={e.key} style={s.era} testID={`he-era-${e.key}`}>
          <Text style={s.eraLabel}>{e.label.toUpperCase()}</Text>
          <TextInput value={e.heading} onChangeText={(v) => update(e.key, { heading: v })} maxLength={80} style={s.input} placeholder="Heading (up to 8 words)" placeholderTextColor={colors.muted} testID={`he-heading-${e.key}`} />
          <TextInput value={e.text} onChangeText={(v) => update(e.key, { text: v })} maxLength={1200} multiline textAlignVertical="top" style={[s.input, s.multi]} placeholder="Leave empty if nothing is known for this period" placeholderTextColor={colors.muted} testID={`he-text-${e.key}`} />
          {e.text.trim() ? (
            <>
              <Text style={s.small}>How close is this to the spot?</Text>
              <View style={s.chipsWrap}>
                {EDIT_SCOPES.map((sc) => {
                  const active = e.scope === sc || (e.scope === "none" && sc === "street");
                  return (
                    <Pressable key={sc} onPress={() => update(e.key, { scope: sc })} style={[s.chip, active && s.chipActive]} testID={`he-scope-${e.key}-${sc}`}>
                      <Text style={[s.chipText, active && s.chipTextActive]}>{SCOPE_LABEL[sc].replace("About ", "")}</Text>
                    </Pressable>
                  );
                })}
              </View>
              <Text style={s.small}>Sources for this text</Text>
              <View style={s.chipsWrap}>
                {citable.map((c) => {
                  const on = e.sources.includes(c.id);
                  return (
                    <Pressable key={c.id} onPress={() => toggleSource(e.key, c.id)} style={[s.chip, on && s.chipActive]} testID={`he-cite-${e.key}-${c.id}`}>
                      <Text style={[s.chipText, on && s.chipTextActive]}>[{c.id}]</Text>
                    </Pressable>
                  );
                })}
              </View>
              {!e.sources.length ? <Text style={s.error}>Pick at least one source, or clear the text.</Text> : null}
            </>
          ) : null}
        </View>
      ))}

      {problems.length ? <Text style={s.error} testID="he-problems">Needs a source: {problems.join(", ")}</Text> : null}
      {badNew ? <Text style={s.error}>Each new source needs a title and a link starting with http.</Text> : null}
      {save.isError ? <Text style={s.error} testID="he-save-error">{(save.error as Error).message}</Text> : null}
      {note ? <Text style={s.saved} testID="he-note">{note}</Text> : null}
      <Pressable style={[s.primary, !canSave && s.disabled]} disabled={!canSave || save.isPending} onPress={() => save.mutate()} testID="he-save">
        {save.isPending ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={s.primaryText}>Save corrections</Text>}
      </Pressable>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  label: { fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.muted, marginTop: spacing.xl, marginBottom: spacing.xs },
  small: { fontFamily: fonts.bodyMedium, fontSize: 11, color: colors.muted, marginTop: spacing.md, marginBottom: spacing.xs },
  section: { fontFamily: fonts.displayBold, fontSize: 20, color: colors.onSurface, marginTop: spacing["2xl"], marginBottom: spacing.sm },
  input: { borderBottomWidth: 1, borderBottomColor: colors.borderStrong, paddingVertical: spacing.sm, fontFamily: fonts.body, fontSize: 15, color: colors.onSurface },
  multi: { minHeight: 110, borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.sm },
  multiShort: { minHeight: 72, borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.md, padding: spacing.md },
  muted: { fontFamily: fonts.body, fontSize: 13, lineHeight: 19, color: colors.muted },
  error: { fontFamily: fonts.body, fontSize: 13, color: colors.error, marginTop: spacing.sm },
  saved: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.success, marginTop: spacing.md },
  loading: { flexDirection: "row", gap: spacing.md, alignItems: "center", marginTop: spacing.xl },
  picked: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 56, paddingHorizontal: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary },
  pickedTitle: { fontFamily: fonts.bodyMedium, fontSize: 15, color: colors.onSurface },
  pickedSub: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: 2 },
  change: { minHeight: 44, justifyContent: "center" },
  cancel: { minHeight: 44, justifyContent: "center", alignSelf: "flex-start" },
  changeText: { fontFamily: fonts.bodyBold, fontSize: 13, color: colors.brandPrimary },
  rebuildBox: { marginTop: spacing.xl, padding: spacing.lg, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, gap: spacing.md },
  ghost: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 44, paddingHorizontal: spacing.lg, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, alignSelf: "flex-start" },
  ghostDanger: { borderColor: colors.error },
  ghostText: { fontFamily: fonts.bodyBold, fontSize: 13, color: colors.brandPrimary },
  srcLine: { fontFamily: fonts.body, fontSize: 13, lineHeight: 20, color: colors.onSurface, marginTop: spacing.xs },
  srcNum: { fontFamily: fonts.bodyBold, fontSize: 12, color: colors.brand },
  newSrc: { marginTop: spacing.md, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, gap: spacing.xs },
  era: { marginTop: spacing.lg, paddingTop: spacing.md, borderTopWidth: 1, borderTopColor: colors.divider },
  eraLabel: { fontFamily: fonts.bodyBold, fontSize: 11, letterSpacing: 1.4, color: colors.brand },
  chipsWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, paddingVertical: spacing.xs },
  chip: { height: 44, paddingHorizontal: spacing.md, borderRadius: radius.pill, justifyContent: "center", borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.onSurface },
  chipTextActive: { color: colors.onBrandPrimary },
  primary: { height: 52, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", marginTop: spacing.xl },
  disabled: { opacity: 0.5 },
  primaryText: { fontFamily: fonts.bodyBold, fontSize: 15, color: colors.onBrandPrimary },
}));
