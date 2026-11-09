import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams, useRouter } from "expo-router";
import Feather from "@react-native-vector-icons/feather";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { ErrorView } from "@/src/components/error-view";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

export default function RegionScreen() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const q = useQuery({ queryKey: ["region", slug], queryFn: () => api.region(slug!), enabled: !!slug });

  if (q.isError) return <ErrorView onBack={() => router.back()} />;
  if (!q.data) return <View style={[styles.container, styles.center]}><ActivityIndicator color={colors.brandPrimary} /></View>;
  const { region, areas } = q.data;

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ paddingBottom: insets.bottom + spacing["2xl"] }}>
      <View style={styles.hero}>
        <Image source={{ uri: region.cover_image }} style={StyleSheet.absoluteFill} contentFit="cover" />
        <LinearGradient colors={["rgba(26,33,48,0.4)", "transparent", "rgba(26,33,48,0.95)"]} style={StyleSheet.absoluteFill} />
        <Pressable onPress={() => router.back()} style={[styles.back, { top: insets.top + spacing.sm }]} testID="region-back">
          <Feather name="arrow-left" size={20} color="#F9F6F0" />
        </Pressable>
        <View style={styles.heroText}>
          <Text style={styles.heroTag}>STATE</Text>
          <Text style={styles.heroTitle} testID="region-name">{region.name}</Text>
        </View>
      </View>
      <View style={styles.body}>
        {region.eras.length ? (
          <>
            {region.summary ? <Text style={styles.summary}>{region.summary}</Text> : null}
            <Text style={styles.section}>Through the ages</Text>
            {region.eras.map((e, i) => (
              <View key={e.key} style={styles.tlRow}>
                <View style={styles.tlCol}>
                  <View style={styles.dot} />
                  {i < region.eras.length - 1 ? <View style={styles.line} /> : null}
                </View>
                <View style={styles.tlItem}>
                  <Text style={styles.tlYear}>{e.key === "today" ? "TODAY" : e.key.toUpperCase()}</Text>
                  <Text style={styles.tlTitle}>{e.title}</Text>
                  <Text style={styles.tlDesc}>{e.description}</Text>
                </View>
              </View>
            ))}
          </>
        ) : (
          <Text style={styles.summary} testID="region-no-stories">
            No stories have been added for {region.name} yet. Know one? Share it from the Traditions tab.
          </Text>
        )}

        <Text style={styles.section}>Places</Text>
        {areas.map((a) => (
          <Pressable key={a.slug} style={styles.row} onPress={() => router.push(`/area/${a.slug}`)} testID={`area-row-${a.slug}`}>
            <Image source={{ uri: a.cover_image }} style={styles.rowImg} contentFit="cover" />
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle}>{a.name}</Text>
              <Text style={[styles.rowMeta, a.eras.length > 0 && { color: colors.brandPrimary }]}>
                {a.eras.length ? `${a.era_keys.length} eras · camera view ready` : "No stories yet"}
              </Text>
            </View>
            <Feather name="chevron-right" size={18} color={colors.muted} />
          </Pressable>
        ))}
      </View>
    </ScrollView>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  hero: { height: 300, backgroundColor: colors.surfaceInverse },
  back: { position: "absolute", left: spacing.lg, width: 44, height: 44, borderRadius: 22, backgroundColor: "rgba(26,33,48,0.5)", alignItems: "center", justifyContent: "center" },
  heroText: { position: "absolute", left: spacing.xl, right: spacing.xl, bottom: spacing.xl },
  heroTag: { fontFamily: fonts.bodyBold, fontSize: 11, color: "#F9F6F0", letterSpacing: 1.4, opacity: 0.85 },
  heroTitle: { fontFamily: fonts.displayBold, fontSize: 40, color: "#F9F6F0" },
  body: { padding: spacing.xl },
  summary: { fontFamily: fonts.body, fontSize: 15, lineHeight: 24, color: colors.onSurface },
  section: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.onSurface, marginTop: spacing.xl, marginBottom: spacing.md },
  tlRow: { flexDirection: "row", gap: spacing.md },
  tlCol: { width: 14, alignItems: "center" },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brandPrimary, marginTop: 5 },
  line: { flex: 1, width: 1, backgroundColor: colors.border, marginTop: 4 },
  tlItem: { flex: 1, paddingBottom: spacing.lg },
  tlYear: { fontFamily: fonts.bodyBold, fontSize: 11, color: colors.brandPrimary, letterSpacing: 1 },
  tlTitle: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.onSurface, marginTop: 2 },
  tlDesc: { fontFamily: fonts.body, fontSize: 14, lineHeight: 21, color: colors.muted, marginTop: 4 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider },
  rowImg: { width: 64, height: 64, borderRadius: radius.lg, backgroundColor: colors.surfaceTertiary },
  rowTitle: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.onSurface },
  rowMeta: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: 2 },
  errBtn: { minHeight: 48, justifyContent: "center", paddingHorizontal: spacing.xl, borderRadius: radius.pill, backgroundColor: colors.brandPrimary },
  errBtnText: { fontFamily: fonts.bodyBold, fontSize: 14, color: colors.onBrandPrimary },
}));
