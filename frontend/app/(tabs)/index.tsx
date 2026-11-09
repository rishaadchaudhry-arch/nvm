import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import * as Location from "expo-location";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import Feather from "@react-native-vector-icons/feather";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Place } from "@/src/api";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

type Coords = { lat: number; lng: number };

function useNearby() {
  const [coords, setCoords] = useState<Coords | null>(null);
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (status !== "granted") {
          setDenied(true);
          return;
        }
        const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
        setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
      } catch {
        setDenied(true);
      }
    })();
  }, []);

  const query = useQuery({
    queryKey: ["nearby", coords?.lat, coords?.lng],
    queryFn: () => api.nearby(coords!.lat, coords!.lng),
    enabled: !!coords,
  });

  return { denied, query };
}

export default function Discover() {
  const { colors } = useTheme();
  const styles = useStyles();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { denied, query: nearby } = useNearby();

  const all = useQuery({ queryKey: ["places"], queryFn: api.listPlaces });

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={{ paddingTop: insets.top + spacing.lg, paddingBottom: spacing["2xl"] }}
      showsVerticalScrollIndicator={false}
    >
      <View style={styles.header}>
        <Text style={styles.brand} testID="brand-title">Yatra</Text>
        <Text style={styles.sub}>{"India's heritage, told through time"}</Text>
      </View>

      <Text style={styles.sectionTitle}>Nearby</Text>
      {denied ? (
        <Text style={styles.hint}>Enable location to discover heritage sites around you.</Text>
      ) : nearby.isLoading || !nearby.data ? (
        <View style={styles.loadingRow}>
          <ActivityIndicator color={colors.brandPrimary} />
        </View>
      ) : (
        <FlatList
          horizontal
          data={nearby.data}
          keyExtractor={(p) => p.id}
          contentContainerStyle={styles.hList}
          showsHorizontalScrollIndicator={false}
          renderItem={({ item }) => <NearCard place={item} onPress={() => router.push(`/place/${item.slug}`)} />}
        />
      )}

      <Text style={styles.sectionTitle}>Curated Destinations</Text>
      {all.isLoading ? (
        <View style={styles.loadingRow}>
          <ActivityIndicator color={colors.brandPrimary} />
        </View>
      ) : all.isError ? (
        <Pressable onPress={() => all.refetch()} style={styles.loadingRow} testID="discover-retry">
          <Text style={styles.hint}>Unable to load destinations. Tap to retry.</Text>
        </Pressable>
      ) : (
        all.data?.map((p) => <BigCard key={p.id} place={p} onPress={() => router.push(`/place/${p.slug}`)} />)
      )}
    </ScrollView>
  );
}

function NearCard({ place, onPress }: { place: Place; onPress: () => void }) {
  const styles = useStyles();
  return (
    <Pressable style={styles.nearCard} onPress={onPress} testID={`near-card-${place.slug}`}>
      <Image source={{ uri: place.hero_image }} style={styles.nearImg} contentFit="cover" />
      <LinearGradient colors={["transparent", "rgba(26,33,48,0.95)"]} style={styles.nearScrim} />
      <View style={styles.nearText}>
        <Text style={styles.nearTitle} numberOfLines={1}>{place.name}</Text>
        <Text style={styles.nearMeta}>
          {place.city}
          {place.distance_km != null ? ` · ${place.distance_km} km` : ""}
        </Text>
      </View>
    </Pressable>
  );
}

function BigCard({ place, onPress }: { place: Place; onPress: () => void }) {
  const styles = useStyles();
  return (
    <Pressable style={styles.bigCard} onPress={onPress} testID={`big-card-${place.slug}`}>
      <Image source={{ uri: place.hero_image }} style={styles.bigImg} contentFit="cover" />
      <LinearGradient colors={["transparent", "rgba(26,33,48,0.9)"]} style={styles.bigScrim} />
      <View style={styles.bigText}>
        <Text style={styles.bigEra}>{place.era.toUpperCase()}</Text>
        <Text style={styles.bigTitle} numberOfLines={2}>{place.name}</Text>
        <Text style={styles.bigSub} numberOfLines={2}>{place.tagline}</Text>
        <View style={styles.cityRow}>
          <Feather name="map-pin" size={12} color="#F9F6F0" />
          <Text style={styles.cityText}>{place.city}, {place.state}</Text>
        </View>
      </View>
    </Pressable>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.xl, marginBottom: spacing.xl },
  brand: { fontFamily: fonts.displayBold, fontSize: 44, color: colors.onSurface, letterSpacing: 0.5 },
  sub: { fontFamily: fonts.body, fontSize: 14, color: colors.muted, marginTop: spacing.xs },
  sectionTitle: {
    fontFamily: fonts.display,
    fontSize: 22,
    color: colors.onSurface,
    paddingHorizontal: spacing.xl,
    marginTop: spacing.xl,
    marginBottom: spacing.md,
  },
  hint: { fontFamily: fonts.body, fontSize: 13, color: colors.muted, paddingHorizontal: spacing.xl },
  loadingRow: { height: 120, alignItems: "center", justifyContent: "center" },
  hList: { paddingHorizontal: spacing.xl, gap: spacing.md },
  nearCard: {
    width: 220,
    height: 280,
    borderRadius: radius.lg,
    overflow: "hidden",
    marginRight: spacing.md,
    backgroundColor: colors.surfaceTertiary,
  },
  nearImg: { ...StyleSheet.absoluteFillObject },
  nearScrim: { position: "absolute", left: 0, right: 0, bottom: 0, height: "60%" },
  nearText: { position: "absolute", left: spacing.md, right: spacing.md, bottom: spacing.md },
  nearTitle: { fontFamily: fonts.displayBold, fontSize: 20, color: "#F9F6F0" },
  nearMeta: { fontFamily: fonts.body, fontSize: 12, color: "#F9F6F0", opacity: 0.85, marginTop: 2 },
  bigCard: {
    height: 360,
    marginHorizontal: spacing.xl,
    marginTop: spacing.lg,
    borderRadius: radius.lg,
    overflow: "hidden",
    backgroundColor: colors.surfaceTertiary,
  },
  bigImg: { ...StyleSheet.absoluteFillObject },
  bigScrim: { position: "absolute", left: 0, right: 0, bottom: 0, height: "70%" },
  bigText: { position: "absolute", left: spacing.xl, right: spacing.xl, bottom: spacing.xl },
  bigEra: { fontFamily: fonts.bodyBold, fontSize: 11, color: "#F9F6F0", opacity: 0.9, letterSpacing: 1.2 },
  bigTitle: { fontFamily: fonts.displayBold, fontSize: 32, color: "#F9F6F0", marginTop: spacing.xs, lineHeight: 36 },
  bigSub: { fontFamily: fonts.body, fontSize: 14, color: "#F9F6F0", opacity: 0.9, marginTop: spacing.xs },
  cityRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.sm },
  cityText: { fontFamily: fonts.body, fontSize: 12, color: "#F9F6F0" },
}));
