import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import Feather from "@react-native-vector-icons/feather";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Place } from "@/src/api";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

export default function Search() {
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const [q, setQ] = useState("");

  const results = useQuery({
    queryKey: ["search", q],
    queryFn: () => api.search(q),
    enabled: q.trim().length > 0,
  });
  const popular = useQuery({ queryKey: ["places"], queryFn: api.listPlaces });

  return (
    <View style={[styles.container, { paddingTop: insets.top + spacing.md }]}>
      <Text style={styles.title}>Search</Text>
      <View style={styles.searchBox}>
        <Feather name="search" size={18} color={colors.muted} />
        <TextInput
          testID="search-input"
          value={q}
          onChangeText={setQ}
          placeholder="Taj Mahal, Delhi, Punjab..."
          placeholderTextColor={colors.muted}
          style={styles.input}
          autoCorrect={false}
          returnKeyType="search"
        />
      </View>

      {q.trim().length === 0 ? (
        <>
          <Text style={styles.section}>Popular right now</Text>
          <FlatList
            data={popular.data ?? []}
            keyExtractor={(i) => i.id}
            renderItem={({ item }) => <Row place={item} onPress={() => router.push(`/place/${item.slug}`)} />}
            ItemSeparatorComponent={() => <View style={styles.sep} />}
            contentContainerStyle={{ paddingBottom: spacing.xl }}
          />
        </>
      ) : results.isLoading ? (
        <View style={styles.loading}><ActivityIndicator color={colors.brandPrimary} /></View>
      ) : results.isError ? (
        <Text style={styles.empty} testID="search-error">Search failed. Check your connection.</Text>
      ) : (results.data?.length ?? 0) === 0 ? (
        <Text style={styles.empty}>{`No sites match "${q}".`}</Text>
      ) : (
        <FlatList
          data={results.data}
          keyExtractor={(i) => i.id}
          renderItem={({ item }) => <Row place={item} onPress={() => router.push(`/place/${item.slug}`)} />}
          ItemSeparatorComponent={() => <View style={styles.sep} />}
          contentContainerStyle={{ paddingBottom: spacing.xl }}
        />
      )}
    </View>
  );
}

function Row({ place, onPress }: { place: Place; onPress: () => void }) {
  const styles = useStyles();
  return (
    <Pressable style={styles.row} onPress={onPress} testID={`result-row-${place.slug}`}>
      <Image source={{ uri: place.hero_image }} style={styles.rowImg} contentFit="cover" />
      <View style={styles.rowText}>
        <Text style={styles.rowTitle}>{place.name}</Text>
        <Text style={styles.rowMeta}>{place.city}, {place.state}</Text>
        <Text style={styles.rowEra}>{place.era}</Text>
      </View>
      <Feather name="chevron-right" size={18} color="#C85A32" />
    </Pressable>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, backgroundColor: colors.surface, paddingHorizontal: spacing.xl },
  title: { fontFamily: fonts.displayBold, fontSize: 32, color: colors.onSurface, marginBottom: spacing.lg },
  searchBox: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    marginBottom: spacing.lg,
  },
  input: { flex: 1, fontFamily: fonts.body, fontSize: 15, color: colors.onSurface, paddingVertical: 4 },
  section: { fontFamily: fonts.display, fontSize: 18, color: colors.muted, marginBottom: spacing.md },
  loading: { padding: spacing.xl, alignItems: "center" },
  empty: { fontFamily: fonts.body, fontSize: 14, color: colors.muted, paddingVertical: spacing.xl },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md },
  rowImg: { width: 72, height: 72, borderRadius: radius.lg, backgroundColor: colors.surfaceTertiary },
  rowText: { flex: 1 },
  rowTitle: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.onSurface },
  rowMeta: { fontFamily: fonts.body, fontSize: 13, color: colors.muted, marginTop: 2 },
  rowEra: { fontFamily: fonts.body, fontSize: 11, color: colors.brandPrimary, marginTop: 2, letterSpacing: 0.8 },
  sep: { height: StyleSheet.hairlineWidth, backgroundColor: colors.divider },
}));
