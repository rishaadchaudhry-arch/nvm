import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Feather from "@react-native-vector-icons/feather";
import { Image } from "expo-image";
import { useEffect, useState } from "react";
import { ActivityIndicator, Linking, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";

import { api, ERAS, type SearchResult } from "@/src/api";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";
import { pickPhoto } from "@/src/utils/pick-photo";
import type { LocalFile } from "@/src/utils/upload";

export type PickedPlace = { key: string; title: string; subtitle: string };

const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/** Admin-only form: record a first-hand account for any street and pin it to an era. */
export function LocalAccountForm({ onSaved }: { onSaved: () => void }) {
  const s = useStyles();
  const { colors } = useTheme();
  const qc = useQueryClient();

  const [place, setPlace] = useState<PickedPlace | null>(null);
  const [era, setEra] = useState<string | null>(null);
  const [body, setBody] = useState("");
  const [toldBy, setToldBy] = useState("");
  const [village, setVillage] = useState("");
  const [collectedOn, setCollectedOn] = useState(today());
  const [photo, setPhoto] = useState<LocalFile | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [photoBlocked, setPhotoBlocked] = useState(false);

  const submit = useMutation({
    mutationFn: () =>
      api.addLocalAccount(
        { place_key: place!.key, era: era!, body: body.trim(), told_by: toldBy.trim(), village: village.trim(), collected_on: collectedOn.trim() },
        photo,
      ),
    onSuccess: (a) => {
      qc.invalidateQueries({ queryKey: ["local-accounts"] });
      qc.invalidateQueries({ queryKey: ["admin-local-accounts"] });
      qc.invalidateQueries({ queryKey: ["local-accounts", a.place_key] });
      setEra(null);
      setBody("");
      setToldBy("");
      setVillage("");
      setCollectedOn(today());
      setPhoto(null);
      onSaved();
    },
  });

  const choosePhoto = async () => {
    setPhotoError(null);
    const r = await pickPhoto();
    if ("file" in r) setPhoto(r.file);
    else if ("denied" in r) {
      setPhotoBlocked(r.blocked);
      setPhotoError("NVM needs photo access to attach a picture to this account.");
    }
  };

  const dateOk = /^\d{4}-\d{2}-\d{2}$/.test(collectedOn.trim());
  const valid = !!place && !!era && body.trim().length >= 10 && toldBy.trim().length > 0 && village.trim().length > 0 && dateOk;

  return (
    <View testID="local-account-form">
      <Text style={s.label}>Street</Text>
      {place ? (
        <View style={s.picked} testID="la-picked-place">
          <Feather name="map-pin" size={16} color={colors.brand} />
          <View style={{ flex: 1 }}>
            <Text style={s.pickedTitle} numberOfLines={1}>{place.title}</Text>
            {place.subtitle ? <Text style={s.pickedSub} numberOfLines={1}>{place.subtitle}</Text> : null}
          </View>
          <Pressable onPress={() => setPlace(null)} hitSlop={12} style={s.change} testID="la-change-place">
            <Text style={s.changeText}>Change</Text>
          </Pressable>
        </View>
      ) : (
        <StreetPicker onPick={setPlace} />
      )}

      <Text style={s.label}>Era</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chips}>
        {ERAS.map((e) => {
          const active = e.key === era;
          return (
            <Pressable key={e.key} onPress={() => setEra(e.key)} style={[s.chip, active && s.chipActive]} testID={`la-era-${e.key}`}>
              <Text style={[s.chipText, active && s.chipTextActive]}>{e.label}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <Text style={s.label}>The account, in their words</Text>
      <TextInput
        value={body}
        onChangeText={setBody}
        maxLength={2000}
        multiline
        textAlignVertical="top"
        style={[s.input, s.multi]}
        placeholder="What they remember or were told about this street in that era"
        placeholderTextColor={colors.muted}
        testID="la-body"
      />
      <Text style={s.count}>{body.trim().length}/2000 · at least 10 characters</Text>

      <Text style={s.label}>Who told it</Text>
      <TextInput value={toldBy} onChangeText={setToldBy} maxLength={80} style={s.input} placeholder="e.g. Shanti Devi, 82" placeholderTextColor={colors.muted} testID="la-told-by" />
      <Text style={s.label}>Their village or town</Text>
      <TextInput value={village} onChangeText={setVillage} maxLength={80} style={s.input} placeholder="e.g. Ballimaran, Old Delhi" placeholderTextColor={colors.muted} testID="la-village" />
      <Text style={s.label}>Date collected</Text>
      <TextInput
        value={collectedOn}
        onChangeText={setCollectedOn}
        maxLength={10}
        style={s.input}
        placeholder="YYYY-MM-DD"
        placeholderTextColor={colors.muted}
        keyboardType={Platform.OS === "ios" ? "numbers-and-punctuation" : "default"}
        autoCapitalize="none"
        testID="la-collected-on"
      />
      {!dateOk && collectedOn ? <Text style={s.hint}>Use the form YYYY-MM-DD, e.g. {today()}</Text> : null}

      <Text style={s.label}>Photo (optional)</Text>
      {photo ? (
        <View style={s.photoRow}>
          <Image source={{ uri: photo.uri }} style={s.thumb} contentFit="cover" testID="la-photo-preview" />
          <Pressable onPress={() => setPhoto(null)} style={s.ghost} testID="la-remove-photo">
            <Feather name="trash-2" size={14} color={colors.brandPrimary} />
            <Text style={s.ghostText}>Remove photo</Text>
          </Pressable>
        </View>
      ) : (
        <Pressable onPress={choosePhoto} style={s.ghost} testID="la-add-photo">
          <Feather name="image" size={16} color={colors.brandPrimary} />
          <Text style={s.ghostText}>Add a photo</Text>
        </Pressable>
      )}
      {photoError ? (
        <View>
          <Text style={s.error}>{photoError}</Text>
          {photoBlocked ? (
            <Pressable onPress={() => Linking.openSettings()} style={[s.ghost, { marginTop: spacing.sm }]} testID="la-open-settings">
              <Text style={s.ghostText}>Open settings</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}

      {submit.isError ? (
        <Text style={s.error} testID="la-error">
          {(submit.error as Error).message}
        </Text>
      ) : null}
      <Pressable style={[s.primary, !valid && s.disabled]} disabled={!valid || submit.isPending} onPress={() => submit.mutate()} testID="la-submit">
        {submit.isPending ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={s.primaryText}>Save local account</Text>}
      </Pressable>
    </View>
  );
}

export function StreetPicker({ onPick }: { onPick: (p: PickedPlace) => void }) {
  const s = useStyles();
  const { colors } = useTheme();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [opening, setOpening] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 500);
    return () => clearTimeout(t);
  }, [q]);

  const results = useQuery({ queryKey: ["search", debounced], queryFn: () => api.search(debounced), enabled: debounced.length >= 2, staleTime: 10 * 60_000 });

  const pick = async (r: SearchResult, i: number) => {
    setOpening(i);
    setError(null);
    try {
      const look = await api.look(r.lat, r.lng);
      onPick({ key: look.place.key, title: look.place.title, subtitle: look.place.subtitle });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setOpening(null);
    }
  };

  return (
    <View>
      <View style={s.searchWrap}>
        <Feather name="search" size={16} color={colors.muted} />
        <TextInput value={q} onChangeText={setQ} placeholder="Search any street in India" placeholderTextColor={colors.muted} style={s.searchInput} testID="la-street-search" />
      </View>
      {error ? <Text style={s.error}>{error}</Text> : null}
      {debounced.length >= 2 && results.isFetching && !results.data ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.md }} /> : null}
      {debounced.length >= 2 && results.data?.length === 0 ? <Text style={s.hint}>No places found for &quot;{debounced}&quot;.</Text> : null}
      {(debounced.length >= 2 ? results.data ?? [] : []).slice(0, 6).map((r, i) => (
        <Pressable key={`${r.lat},${r.lng},${i}`} style={s.row} onPress={() => pick(r, i)} disabled={opening !== null} testID={`la-street-result-${i}`}>
          <Feather name="map-pin" size={14} color={colors.brand} />
          <View style={{ flex: 1 }}>
            <Text style={s.rowTitle} numberOfLines={1}>{r.title}</Text>
            {r.subtitle ? <Text style={s.rowSub} numberOfLines={1}>{r.subtitle}</Text> : null}
          </View>
          {opening === i ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Feather name="chevron-right" size={16} color={colors.muted} />}
        </Pressable>
      ))}
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  label: { fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.muted, marginTop: spacing.xl, marginBottom: spacing.xs },
  input: { borderBottomWidth: 1, borderBottomColor: colors.borderStrong, paddingVertical: spacing.sm, fontFamily: fonts.body, fontSize: 16, color: colors.onSurface },
  multi: { minHeight: 140, borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.xs },
  count: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: spacing.xs },
  hint: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: spacing.sm },
  error: { fontFamily: fonts.body, fontSize: 13, color: colors.error, marginTop: spacing.md },
  primary: { height: 52, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", marginTop: spacing.xl },
  disabled: { opacity: 0.5 },
  primaryText: { fontFamily: fonts.bodyBold, fontSize: 15, color: colors.onBrandPrimary },
  ghost: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", gap: spacing.sm, minHeight: 44, paddingHorizontal: spacing.lg, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary },
  ghostText: { fontFamily: fonts.bodyBold, fontSize: 14, color: colors.brandPrimary },
  photoRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  thumb: { width: 72, height: 72, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  chips: { gap: spacing.sm, paddingVertical: spacing.xs },
  chip: { height: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, justifyContent: "center", borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.onSurface },
  chipTextActive: { color: colors.onBrandPrimary },
  picked: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 56, paddingHorizontal: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary },
  pickedTitle: { fontFamily: fonts.bodyMedium, fontSize: 15, color: colors.onSurface },
  pickedSub: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: 2 },
  change: { minHeight: 44, justifyContent: "center" },
  changeText: { fontFamily: fonts.bodyBold, fontSize: 13, color: colors.brandPrimary },
  searchWrap: { flexDirection: "row", alignItems: "center", gap: spacing.sm, height: 48, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary },
  searchInput: { flex: 1, fontFamily: fonts.body, fontSize: 15, color: colors.onSurface, height: 48, ...(Platform.OS === "web" ? ({ outlineStyle: "none" } as object) : {}) },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 52, borderBottomWidth: 1, borderBottomColor: colors.divider },
  rowTitle: { fontFamily: fonts.bodyMedium, fontSize: 14, color: colors.onSurface },
  rowSub: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: 2 },
}));
