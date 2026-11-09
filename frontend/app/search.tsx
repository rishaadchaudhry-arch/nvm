import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import Feather from "@react-native-vector-icons/feather";
import { useEffect, useState } from "react";
import { ActivityIndicator, FlatList, Platform, Pressable, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, type SearchResult } from "@/src/api";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

export default function Search() {
  const s = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [opening, setOpening] = useState<string | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 500);
    return () => clearTimeout(t);
  }, [q]);

  const results = useQuery({ queryKey: ["search", debounced], queryFn: () => api.search(debounced), enabled: debounced.length >= 2, staleTime: 10 * 60_000 });

  const open = async (r: SearchResult, id: string) => {
    setOpening(id);
    setOpenError(null);
    try {
      const look = await api.look(r.lat, r.lng);
      router.push({ pathname: "/place/[key]", params: { key: look.place.key } });
    } catch (e) {
      setOpenError((e as Error).message);
    } finally {
      setOpening(null);
    }
  };

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))} style={s.iconBtn} testID="search-back" accessibilityLabel="Back">
          <Feather name="arrow-left" size={20} color={colors.onSurface} />
        </Pressable>
        <View style={s.inputWrap}>
          <Feather name="search" size={18} color={colors.muted} />
          <TextInput
            value={q}
            onChangeText={setQ}
            placeholder="Any street, lane or locality in India"
            placeholderTextColor={colors.muted}
            style={s.input}
            autoFocus
            returnKeyType="search"
            onSubmitEditing={() => setDebounced(q.trim())}
            testID="search-input"
          />
          {q ? (
            <Pressable onPress={() => setQ("")} hitSlop={12} testID="search-clear" accessibilityLabel="Clear search">
              <Feather name="x" size={18} color={colors.muted} />
            </Pressable>
          ) : null}
        </View>
      </View>

      {openError ? (
        <Text style={s.error} testID="search-open-error">
          {openError}
        </Text>
      ) : null}

      <FlatList
        data={debounced.length >= 2 ? results.data ?? [] : []}
        keyExtractor={(r, i) => `${r.lat},${r.lng},${i}`}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: insets.bottom + spacing.xl }}
        ListEmptyComponent={
          debounced.length < 2 ? (
            <View style={s.empty} testID="search-empty">
              <Text style={s.emptyTitle}>Search any street in India</Text>
              <Text style={s.emptyBody}>Try &quot;Nai Sarak Delhi&quot;, &quot;MG Road Bengaluru&quot; or the lane outside your home.</Text>
            </View>
          ) : results.isFetching ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
          ) : results.isError ? (
            <Pressable onPress={() => results.refetch()} testID="search-error">
              <Text style={s.emptyBody}>{(results.error as Error).message} Tap to retry.</Text>
            </Pressable>
          ) : (
            <Text style={s.emptyBody} testID="search-no-results">
              No places found for &quot;{debounced}&quot;.
            </Text>
          )
        }
        renderItem={({ item, index }) => {
          const id = `${index}`;
          return (
            <Pressable style={s.row} onPress={() => open(item, id)} disabled={!!opening} testID={`search-result-${index}`}>
              <Feather name="map-pin" size={16} color={colors.brand} />
              <View style={{ flex: 1 }}>
                <Text style={s.rowTitle} numberOfLines={1}>
                  {item.title}
                </Text>
                {item.subtitle ? (
                  <Text style={s.rowSub} numberOfLines={1}>
                    {item.subtitle}
                  </Text>
                ) : null}
              </View>
              {opening === id ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Feather name="chevron-right" size={18} color={colors.muted} />}
            </Pressable>
          );
        }}
      />
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  iconBtn: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  inputWrap: { flex: 1, flexDirection: "row", alignItems: "center", gap: spacing.sm, height: 48, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary },
  input: { flex: 1, fontFamily: fonts.body, fontSize: 15, color: colors.onSurface, height: 48, ...(Platform.OS === "web" ? ({ outlineStyle: "none" } as object) : {}) },
  error: { fontFamily: fonts.body, fontSize: 13, color: colors.error, paddingHorizontal: spacing.xl, marginBottom: spacing.sm },
  empty: { marginTop: spacing.xl },
  emptyTitle: { fontFamily: fonts.displayBold, fontSize: 24, color: colors.onSurface },
  emptyBody: { fontFamily: fonts.body, fontSize: 14, lineHeight: 21, color: colors.muted, marginTop: spacing.sm },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 60, borderBottomWidth: 1, borderBottomColor: colors.divider },
  rowTitle: { fontFamily: fonts.bodyMedium, fontSize: 15, color: colors.onSurface },
  rowSub: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: 2 },
}));
