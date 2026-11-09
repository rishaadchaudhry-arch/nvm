import { useQuery } from "@tanstack/react-query";
import { CameraView, useCameraPermissions } from "expo-camera";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import {
  ActivityIndicator,
  Dimensions,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import Feather from "@react-native-vector-icons/feather";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

const { height: H } = Dimensions.get("window");

export default function ARView() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const [permission, requestPermission] = useCameraPermissions();
  const [factIdx, setFactIdx] = useState(0);

  const place = useQuery({ queryKey: ["place", slug], queryFn: () => api.place(slug!), enabled: !!slug });
  const timeline = useQuery({ queryKey: ["timeline", slug], queryFn: () => api.timeline(slug!), enabled: !!slug });

  const canUseCamera = Platform.OS !== "web" && permission?.granted;

  const events = timeline.data?.events ?? [];
  const fact = events[factIdx];

  return (
    <View style={styles.container}>
      {canUseCamera ? (
        <CameraView style={StyleSheet.absoluteFill} facing="back" />
      ) : (
        <Image
          source={{ uri: place.data?.panorama_image }}
          style={StyleSheet.absoluteFill}
          contentFit="cover"
        />
      )}
      <LinearGradient
        colors={["rgba(26,33,48,0.5)", "transparent", "rgba(26,33,48,0.8)"]}
        style={StyleSheet.absoluteFill}
      />

      {!canUseCamera && Platform.OS !== "web" ? (
        <View style={styles.permWrap}>
          <View style={styles.permCard}>
            <Feather name="camera" size={24} color={colors.brandPrimary} />
            <Text style={styles.permTitle}>Enable camera for AR</Text>
            <Text style={styles.permText}>
              Point your phone around the site. We’ll overlay historical facts as you explore.
            </Text>
            <Pressable style={styles.permBtn} onPress={requestPermission} testID="camera-perm-btn">
              <Text style={styles.permBtnText}>Allow Camera</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {fact ? (
        <View style={[styles.factCard, { top: H * 0.25 }]}>
          <Text style={styles.factYear}>{fact.year}</Text>
          <Text style={styles.factTitle}>{fact.title}</Text>
          <Text style={styles.factDesc}>{fact.description}</Text>
        </View>
      ) : null}

      <View style={[styles.topBar, { top: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} testID="ar-back-btn">
          <Feather name="x" size={20} color="#F9F6F0" />
        </Pressable>
        <View style={styles.badge}>
          <View style={styles.badgeDot} />
          <Text style={styles.badgeText}>AR · {place.data?.name}</Text>
        </View>
      </View>

      <View style={[styles.bottomBar, { paddingBottom: insets.bottom + spacing.lg }]}>
        <Pressable
          style={styles.navBtn}
          onPress={() => setFactIdx((i) => Math.max(0, i - 1))}
          disabled={factIdx === 0}
        >
          <Feather name="chevron-left" size={22} color={factIdx === 0 ? "#6B7280" : "#F9F6F0"} />
        </Pressable>
        <View style={styles.counter}>
          <Text style={styles.counterText}>
            {events.length ? `${factIdx + 1} / ${events.length}` : "—"}
          </Text>
        </View>
        <Pressable
          style={styles.navBtn}
          onPress={() => setFactIdx((i) => Math.min(events.length - 1, i + 1))}
          disabled={factIdx >= events.length - 1}
          testID="ar-next-fact"
        >
          <Feather name="chevron-right" size={22} color={factIdx >= events.length - 1 ? "#6B7280" : "#F9F6F0"} />
        </Pressable>
      </View>

      {timeline.isLoading && (
        <View style={styles.loading}>
          <ActivityIndicator color="#D4AF37" />
        </View>
      )}
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, backgroundColor: colors.surfaceInverse },
  topBar: { position: "absolute", left: spacing.lg, right: spacing.lg, flexDirection: "row", alignItems: "center", gap: spacing.md },
  iconBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: "rgba(26,33,48,0.6)", alignItems: "center", justifyContent: "center" },
  badge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "rgba(26,33,48,0.6)",
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
  },
  badgeDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: "#D4AF37" },
  badgeText: { fontFamily: fonts.bodyMedium, fontSize: 12, color: "#F9F6F0" },
  factCard: {
    position: "absolute",
    left: spacing.xl,
    right: spacing.xl,
    backgroundColor: "rgba(249,246,240,0.96)",
    padding: spacing.lg,
    borderRadius: radius.lg,
    borderLeftWidth: 3,
    borderLeftColor: "#D4AF37",
  },
  factYear: { fontFamily: fonts.bodyBold, fontSize: 11, color: "#C85A32", letterSpacing: 1.5 },
  factTitle: { fontFamily: fonts.displayBold, fontSize: 20, color: "#1A2130", marginTop: spacing.xs },
  factDesc: { fontFamily: fonts.body, fontSize: 13, lineHeight: 20, color: "#1A2130", marginTop: spacing.xs },
  bottomBar: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.md,
  },
  navBtn: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: "rgba(26,33,48,0.6)",
    alignItems: "center",
    justifyContent: "center",
  },
  counter: {
    flex: 1,
    alignItems: "center",
    backgroundColor: "rgba(26,33,48,0.6)",
    paddingVertical: 14,
    borderRadius: radius.pill,
  },
  counterText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: "#F9F6F0" },
  permWrap: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl },
  permCard: {
    backgroundColor: "#F9F6F0",
    padding: spacing.xl,
    borderRadius: radius.lg,
    alignItems: "center",
    gap: spacing.sm,
    maxWidth: 320,
  },
  permTitle: { fontFamily: fonts.displayBold, fontSize: 20, color: "#1A2130" },
  permText: { fontFamily: fonts.body, fontSize: 13, color: "#5C667A", textAlign: "center", lineHeight: 20 },
  permBtn: {
    backgroundColor: "#C85A32",
    paddingVertical: 12,
    paddingHorizontal: spacing.xl,
    borderRadius: radius.pill,
    marginTop: spacing.sm,
  },
  permBtnText: { fontFamily: fonts.bodyBold, fontSize: 13, color: "#FFFFFF", letterSpacing: 0.5 },
  loading: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center" },
}));
