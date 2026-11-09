import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { useFocusEffect, useRouter } from "expo-router";
import Feather from "@react-native-vector-icons/feather";
import { useCallback, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, type Poi } from "@/src/api";
import { useJourney } from "@/src/journey";
import { usesNativeTabs } from "@/src/navigation";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

export default function Journey() {
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const { saved, visited, reload } = useJourney();
  const [tab, setTab] = useState<"visited" | "saved">("visited");
  useFocusEffect(useCallback(() => { reload(); }, [reload]));

  const slugs = tab === "visited" ? visited : saved;
  const pois = useQuery({ queryKey: ["pois", slugs.join(",")], queryFn: () => api.poisBySlugs(slugs), enabled: slugs.length > 0 });
  const items = slugs.length ? (pois.data ?? []) : [];

  return (
    <View style={styles.container}>
      <View style={[styles.hero, { paddingTop: insets.top + spacing.lg }]}>
        <Text style={styles.heroTag}>MY JOURNEY</Text>
        <Text style={styles.heroTitle}>{"A traveller's log"}</Text>
        <View style={styles.stats}>
          <Text style={styles.stat} testID="visited-count">{visited.length} visited</Text>
          <Text style={styles.stat} testID="saved-count">{saved.length} saved</Text>
        </View>
      </View>
      <View style={styles.tabs}>
        {(["visited", "saved"] as const).map((t) => (
          <Pressable key={t} onPress={() => setTab(t)} style={[styles.tab, tab === t && styles.tabActive]} testID={`journey-tab-${t}`}>
            <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>{t === "visited" ? "Visited" : "Saved"}</Text>
          </Pressable>
        ))}
      </View>
      <ScrollView contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: bottomChrome + spacing["2xl"] }}>
        {items.length === 0 ? (
          <View style={styles.empty}>
            <Feather name={tab === "visited" ? "map" : "bookmark"} size={26} color={colors.muted} />
            <Text style={styles.emptyText}>{tab === "visited" ? "Places you open will appear here." : "Nothing saved yet."}</Text>
          </View>
        ) : (
          items.map((p) => <Row key={p.slug} poi={p} onPress={() => router.push(`/poi/${p.slug}`)} />)
        )}
        <Pressable style={styles.admin} onPress={() => router.push("/admin")} testID="admin-link">
          <Feather name="shield" size={14} color={colors.muted} />
          <Text style={styles.adminText}>Yatra team: review traditions</Text>
        </Pressable>
      </ScrollView>
    </View>
  );
}

function Row({ poi, onPress }: { poi: Poi; onPress: () => void }) {
  const styles = useStyles();
  return (
    <Pressable style={styles.row} onPress={onPress} testID={`journey-row-${poi.slug}`}>
      <Image source={{ uri: poi.image }} style={styles.rowImg} contentFit="cover" />
      <View style={{ flex: 1 }}>
        <Text style={styles.rowTitle}>{poi.name}</Text>
        <Text style={styles.rowMeta}>{poi.category} · {poi.eras.length} eras</Text>
      </View>
    </Pressable>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, backgroundColor: colors.surface },
  hero: { backgroundColor: colors.surfaceInverse, paddingHorizontal: spacing.xl, paddingBottom: spacing.xl },
  heroTag: { fontFamily: fonts.bodyBold, fontSize: 11, color: colors.brandTertiary, letterSpacing: 1.4 },
  heroTitle: { fontFamily: fonts.displayBold, fontSize: 32, color: colors.onSurfaceInverse, marginTop: spacing.xs },
  stats: { flexDirection: "row", gap: spacing.xl, marginTop: spacing.sm },
  stat: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.onSurfaceInverse, opacity: 0.85 },
  tabs: { flexDirection: "row", paddingHorizontal: spacing.xl, gap: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider },
  tab: { minHeight: 48, justifyContent: "center", borderBottomWidth: 2, borderBottomColor: "transparent" },
  tabActive: { borderBottomColor: colors.brandPrimary },
  tabText: { fontFamily: fonts.bodyMedium, fontSize: 14, color: colors.muted },
  tabTextActive: { color: colors.onSurface },
  empty: { alignItems: "center", paddingVertical: spacing["2xl"], gap: spacing.md },
  emptyText: { fontFamily: fonts.body, fontSize: 14, color: colors.muted },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider },
  rowImg: { width: 64, height: 64, borderRadius: radius.lg, backgroundColor: colors.surfaceTertiary },
  rowTitle: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.onSurface },
  rowMeta: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: 2 },
  admin: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 44, marginTop: spacing["2xl"] },
  adminText: { fontFamily: fonts.body, fontSize: 13, color: colors.muted },
}));
