import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import Feather from "@react-native-vector-icons/feather";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Place } from "@/src/api";
import { useJourney } from "@/src/journey";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

export default function Journey() {
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const { saved, visited, reload } = useJourney();
  useFocusEffect(
    useCallback(() => {
      reload();
    }, [reload]),
  );
  const [tab, setTab] = useState<"visited" | "saved">("visited");

  const all = useQuery({ queryKey: ["places"], queryFn: api.listPlaces });

  const slugs = tab === "visited" ? visited : saved;
  const items = useMemo(
    () => (all.data ?? []).filter((p) => slugs.includes(p.slug)),
    [all.data, slugs],
  );

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={{ paddingBottom: spacing["2xl"] }}
      showsVerticalScrollIndicator={false}
    >
      <View style={[styles.hero, { paddingTop: insets.top + spacing["2xl"] }]}>
        <LinearGradient colors={["rgba(26,33,48,0.1)", "rgba(26,33,48,0.85)"]} style={StyleSheet.absoluteFill} />
        <Text style={styles.heroTag}>MY JOURNEY</Text>
        <Text style={styles.heroTitle}>{"A traveler's log"}</Text>
        <View style={styles.stats}>
          <Stat n={visited.length} label="Visited" />
          <View style={styles.vdivider} />
          <Stat n={saved.length} label="Saved" />
        </View>
      </View>

      <View style={styles.tabs}>
        {(["visited", "saved"] as const).map((t) => (
          <Pressable
            key={t}
            onPress={() => setTab(t)}
            style={[styles.tab, tab === t && styles.tabActive]}
            testID={`journey-tab-${t}`}
          >
            <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>
              {t === "visited" ? "Visited" : "Saved"}
            </Text>
          </Pressable>
        ))}
      </View>

      {items.length === 0 ? (
        <View style={styles.empty}>
          <Feather name={tab === "visited" ? "map" : "bookmark"} size={28} color={colors.muted} />
          <Text style={styles.emptyText}>
            {tab === "visited" ? "You haven't visited any sites yet." : "Nothing saved yet."}
          </Text>
        </View>
      ) : (
        <View style={styles.grid}>
          {items.map((p) => (
            <Card key={p.id} place={p} onPress={() => router.push(`/place/${p.slug}`)} />
          ))}
        </View>
      )}
    </ScrollView>
  );
}

function Stat({ n, label }: { n: number; label: string }) {
  const styles = useStyles();
  return (
    <View style={styles.stat}>
      <Text style={styles.statNum}>{n}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function Card({ place, onPress }: { place: Place; onPress: () => void }) {
  const styles = useStyles();
  return (
    <Pressable style={styles.card} onPress={onPress}>
      <Image source={{ uri: place.hero_image }} style={styles.cardImg} contentFit="cover" />
      <LinearGradient colors={["transparent", "rgba(26,33,48,0.9)"]} style={styles.cardScrim} />
      <Text style={styles.cardTitle} numberOfLines={2}>{place.name}</Text>
    </Pressable>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, backgroundColor: colors.surface },
  hero: {
    minHeight: 200,
    backgroundColor: colors.surfaceInverse,
    paddingHorizontal: spacing.xl,
    justifyContent: "flex-end",
    paddingBottom: spacing.xl,
  },
  heroTag: { fontFamily: fonts.bodyMedium, fontSize: 11, color: "#D4AF37", letterSpacing: 1.2 },
  heroTitle: { fontFamily: fonts.displayBold, fontSize: 32, color: "#F9F6F0", marginTop: spacing.xs },
  stats: { flexDirection: "row", gap: spacing.xl, marginTop: spacing.md },
  stat: { alignItems: "flex-start" },
  statNum: { fontFamily: fonts.displayBold, fontSize: 28, color: "#F9F6F0" },
  statLabel: { fontFamily: fonts.body, fontSize: 11, color: "#F9F6F0", opacity: 0.8, letterSpacing: 1 },
  vdivider: { width: 1, backgroundColor: "rgba(249,246,240,0.3)" },
  tabs: { flexDirection: "row", paddingHorizontal: spacing.xl, paddingVertical: spacing.lg, gap: spacing.md },
  tab: { paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderBottomWidth: 2, borderBottomColor: "transparent" },
  tabActive: { borderBottomColor: colors.brandPrimary },
  tabText: { fontFamily: fonts.bodyMedium, fontSize: 14, color: colors.muted },
  tabTextActive: { color: colors.onSurface },
  empty: { alignItems: "center", padding: spacing["2xl"], gap: spacing.md },
  emptyText: { fontFamily: fonts.body, fontSize: 14, color: colors.muted },
  grid: { flexDirection: "row", flexWrap: "wrap", paddingHorizontal: spacing.lg, gap: spacing.md },
  card: {
    width: "47%",
    height: 180,
    borderRadius: radius.lg,
    overflow: "hidden",
    backgroundColor: colors.surfaceTertiary,
  },
  cardImg: { ...StyleSheet.absoluteFillObject },
  cardScrim: { position: "absolute", left: 0, right: 0, bottom: 0, height: "60%" },
  cardTitle: {
    position: "absolute",
    bottom: spacing.sm,
    left: spacing.sm,
    right: spacing.sm,
    fontFamily: fonts.displayBold,
    fontSize: 15,
    color: "#F9F6F0",
  },
}));
