import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useRef, useState } from "react";
import {
  ActivityIndicator,
  Dimensions,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import Feather from "@react-native-vector-icons/feather";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

const { width: SCREEN_W } = Dimensions.get("window");
const PAN_W = SCREEN_W * 2.4;

export default function Panorama() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();

  const place = useQuery({ queryKey: ["place", slug], queryFn: () => api.place(slug!), enabled: !!slug });
  const timeline = useQuery({ queryKey: ["timeline", slug], queryFn: () => api.timeline(slug!), enabled: !!slug });

  const [active, setActive] = useState<number | null>(null);
  const scrollRef = useRef<ScrollView>(null);

  if (!place.data) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color={colors.brandTertiary} />
      </View>
    );
  }

  const hotspots = timeline.data?.hotspots ?? [];
  const hotspotPositions = hotspots.map((_, i) => (PAN_W / (hotspots.length + 1)) * (i + 1));

  return (
    <View style={styles.container}>
      <ScrollView
        ref={scrollRef}
        horizontal
        showsHorizontalScrollIndicator={false}
        pagingEnabled={false}
      >
        <View style={{ width: PAN_W, height: "100%" }}>
          <Image
            source={{ uri: place.data.panorama_image }}
            style={StyleSheet.absoluteFill}
            contentFit="cover"
          />
          {hotspots.map((h, i) => (
            <Pressable
              key={i}
              onPress={() => setActive(i === active ? null : i)}
              style={[styles.hotspot, { left: hotspotPositions[i] - 24, top: 180 + (i % 2) * 120 }]}
              testID={`hotspot-${i}`}
            >
              <View style={styles.hotspotDot}>
                <View style={styles.hotspotInner} />
              </View>
              {active === i && (
                <View style={styles.hotspotCard}>
                  <Text style={styles.hotspotText}>{h}</Text>
                </View>
              )}
            </Pressable>
          ))}
        </View>
      </ScrollView>

      <View style={[styles.topBar, { top: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} testID="panorama-back">
          <Feather name="x" size={20} color="#F9F6F0" />
        </Pressable>
        <View style={styles.pill}>
          <Feather name="globe" size={12} color="#F9F6F0" />
          <Text style={styles.pillText}>360° · Swipe to look around</Text>
        </View>
      </View>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <Text style={styles.title}>{place.data.name}</Text>
        <Text style={styles.sub}>Tap the glowing points to reveal history</Text>
      </View>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, backgroundColor: colors.surfaceInverse },
  center: { alignItems: "center", justifyContent: "center" },
  topBar: { position: "absolute", left: spacing.lg, right: spacing.lg, flexDirection: "row", alignItems: "center", gap: spacing.md },
  iconBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: "rgba(26,33,48,0.6)", alignItems: "center", justifyContent: "center" },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(26,33,48,0.6)",
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
  },
  pillText: { fontFamily: fonts.bodyMedium, fontSize: 12, color: "#F9F6F0" },
  hotspot: { position: "absolute", width: 48, height: 48, alignItems: "center", justifyContent: "center" },
  hotspotDot: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "rgba(212,175,55,0.3)",
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    borderColor: "#D4AF37",
  },
  hotspotInner: { width: 10, height: 10, borderRadius: 5, backgroundColor: "#D4AF37" },
  hotspotCard: {
    position: "absolute",
    top: 44,
    left: -80,
    width: 200,
    padding: spacing.sm,
    backgroundColor: "#F9F6F0",
    borderRadius: radius.lg,
  },
  hotspotText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: "#1A2130" },
  footer: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    backgroundColor: "rgba(26,33,48,0.85)",
  },
  title: { fontFamily: fonts.displayBold, fontSize: 22, color: "#F9F6F0" },
  sub: { fontFamily: fonts.body, fontSize: 12, color: "#F9F6F0", opacity: 0.8, marginTop: 2 },
}));
