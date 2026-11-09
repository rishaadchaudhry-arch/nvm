import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import * as Location from "expo-location";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import Feather from "@react-native-vector-icons/feather";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, formatDistance, type Region } from "@/src/api";
import { usesNativeTabs } from "@/src/navigation";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

function useCoords() {
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [state, setState] = useState<"checking" | "granted" | "denied">("checking");
  useEffect(() => {
    // Only read location if the user already allowed it; asking happens on the Camera tab.
    (async () => {
      try {
        const perm = await Location.getForegroundPermissionsAsync();
        if (!perm.granted) return setState("denied");
        setState("granted");
        const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
        setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
      } catch {
        setState("denied");
      }
    })();
  }, []);
  return { coords, state };
}

export default function Explore() {
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const { coords, state } = useCoords();

  const regions = useQuery({ queryKey: ["regions"], queryFn: api.regions });
  const nearby = useQuery({
    queryKey: ["nearby", coords?.lat.toFixed(4), coords?.lng.toFixed(4)],
    queryFn: () => api.nearby(coords!.lat, coords!.lng),
    enabled: !!coords,
  });

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.lg }]}>
        <Text style={styles.brand} testID="brand-title">Yatra</Text>
        <Text style={styles.sub}>Point your camera. See what was here.</Text>
      </View>
      <ScrollView
        contentContainerStyle={{ paddingBottom: bottomChrome + spacing["2xl"] }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={regions.isRefetching} onRefresh={() => { regions.refetch(); nearby.refetch(); }} tintColor={colors.brandPrimary} />}
      >
        <View style={styles.hereCard} testID="here-card">
          {state === "checking" || (coords && nearby.isLoading) ? (
            <ActivityIndicator color={colors.onSurfaceInverse} />
          ) : nearby.data?.inside ? (
            <>
              <Text style={styles.hereTag}>YOU ARE IN</Text>
              <Text style={styles.hereTitle}>{nearby.data.inside.area.name}</Text>
              <Text style={styles.hereText}>
                {nearby.data.inside.pois.length} places with stories around you.
              </Text>
              <Pressable style={styles.hereBtn} onPress={() => router.push("/camera")} testID="open-camera-btn">
                <Feather name="camera" size={16} color={colors.onBrandPrimary} />
                <Text style={styles.hereBtnText}>Open the camera view</Text>
              </Pressable>
            </>
          ) : (
            <>
              <Text style={styles.hereTag}>{state === "denied" ? "LOCATION OFF" : "NOT AT A STORY SPOT YET"}</Text>
              <Text style={styles.hereTitle}>
                {state === "denied" ? "Turn on location to see what's around you" : "No stories where you are yet"}
              </Text>
              <Text style={styles.hereText}>
                {nearby.data?.nearest
                  ? `Nearest place with stories: ${nearby.data.nearest.name}, ${formatDistance(nearby.data.nearest.distance_m)} away. The camera view unlocks when you're there.`
                  : "The camera view unlocks when you are at a place with stories, starting with Chandni Chowk, Delhi."}
              </Text>
              <Pressable style={styles.hereBtn} onPress={() => router.push("/area/chandni-chowk")} testID="read-chandni-chowk-btn">
                <Text style={styles.hereBtnText}>Read about Chandni Chowk</Text>
              </Pressable>
            </>
          )}
        </View>

        <Text style={styles.sectionTitle}>States</Text>
        {regions.isLoading ? (
          <ActivityIndicator style={{ marginTop: spacing.xl }} color={colors.brandPrimary} />
        ) : regions.isError ? (
          <Pressable onPress={() => regions.refetch()} testID="regions-retry">
            <Text style={styles.hint}>Unable to load states. Tap to retry.</Text>
          </Pressable>
        ) : (
          regions.data?.map((r) => <RegionCard key={r.slug} region={r} onPress={() => router.push(`/region/${r.slug}`)} />)
        )}
      </ScrollView>
    </View>
  );
}

function RegionCard({ region, onPress }: { region: Region; onPress: () => void }) {
  const styles = useStyles();
  return (
    <Pressable style={styles.card} onPress={onPress} testID={`region-card-${region.slug}`}>
      <Image source={{ uri: region.cover_image }} style={StyleSheet.absoluteFill} contentFit="cover" transition={200} />
      <LinearGradient colors={["transparent", "rgba(26,33,48,0.92)"]} style={styles.scrim} />
      <View style={styles.cardText}>
        <Text style={styles.cardMeta}>
          {region.has_stories ? "STORIES AVAILABLE" : "COMING SOON"} · {region.area_count} {region.area_count === 1 ? "PLACE" : "PLACES"}
        </Text>
        <Text style={styles.cardTitle}>{region.name}</Text>
      </View>
    </Pressable>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.xl, paddingBottom: spacing.md, backgroundColor: colors.surface },
  brand: { fontFamily: fonts.displayBold, fontSize: 44, color: colors.onSurface },
  sub: { fontFamily: fonts.body, fontSize: 14, color: colors.muted, marginTop: spacing.xs },
  hereCard: {
    marginHorizontal: spacing.xl,
    marginTop: spacing.md,
    padding: spacing.xl,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceInverse,
    minHeight: 160,
    justifyContent: "center",
  },
  hereTag: { fontFamily: fonts.bodyBold, fontSize: 11, color: colors.brandTertiary, letterSpacing: 1.4 },
  hereTitle: { fontFamily: fonts.displayBold, fontSize: 28, color: colors.onSurfaceInverse, marginTop: spacing.xs, lineHeight: 32 },
  hereText: { fontFamily: fonts.body, fontSize: 14, lineHeight: 21, color: colors.onSurfaceInverse, opacity: 0.85, marginTop: spacing.sm },
  hereBtn: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    gap: spacing.sm,
    minHeight: 44,
    marginTop: spacing.lg,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
  },
  hereBtnText: { fontFamily: fonts.bodyBold, fontSize: 14, color: colors.onBrandPrimary },
  sectionTitle: { fontFamily: fonts.displayBold, fontSize: 24, color: colors.onSurface, paddingHorizontal: spacing.xl, marginTop: spacing["2xl"], marginBottom: spacing.sm },
  hint: { fontFamily: fonts.body, fontSize: 14, color: colors.muted, paddingHorizontal: spacing.xl },
  card: { height: 170, marginHorizontal: spacing.xl, marginTop: spacing.md, borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.surfaceTertiary },
  scrim: { position: "absolute", left: 0, right: 0, bottom: 0, height: "75%" },
  cardText: { position: "absolute", left: spacing.lg, right: spacing.lg, bottom: spacing.lg },
  cardMeta: { fontFamily: fonts.bodyBold, fontSize: 10, color: "#F9F6F0", opacity: 0.85, letterSpacing: 1.2 },
  cardTitle: { fontFamily: fonts.displayBold, fontSize: 30, color: "#F9F6F0", marginTop: 2 },
}));
