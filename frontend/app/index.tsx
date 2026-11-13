import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CameraView, useCameraPermissions } from "expo-camera";
import * as Haptics from "expo-haptics";
import * as Location from "expo-location";
import { useFocusEffect, useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";
import Feather from "@react-native-vector-icons/feather";
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Linking, PanResponder, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { angleDiff, api, compassLabel, distanceM, ERAS, SCOPE_LABEL, type Tradition } from "@/src/api";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

type Perm = { granted: boolean; canAskAgain: boolean } | null;

const SETTLE_MS = 1200; // wait for the phone to be held still before looking something up
const MOVE_M = 15;
const TURN_DEG = 30;

export default function CameraHome() {
  const s = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [locPerm, setLocPerm] = useState<Perm>(null);
  const [camPerm, requestCam] = useCameraPermissions();
  const [focused, setFocused] = useState(true);
  const [fix, setFix] = useState<{ lat: number; lng: number } | null>(null);
  const [heading, setHeading] = useState<number | null>(null);
  const [hasCompass, setHasCompass] = useState(Platform.OS !== "web");
  const [manualHeading, setManualHeading] = useState(0);
  const [target, setTarget] = useState<{ lat: number; lng: number; heading: number | null } | null>(null);
  const [pickedEra, setPickedEra] = useState<string | null>(null);
  const [toast, setToast] = useState<Tradition | null>(null);
  const seenStories = useRef(new Set<string>());

  useEffect(() => {
    Location.getForegroundPermissionsAsync().then((p) => setLocPerm({ granted: p.granted, canAskAgain: p.canAskAgain }));
  }, []);

  const askLocation = async () => {
    const p = await Location.requestForegroundPermissionsAsync();
    setLocPerm({ granted: p.granted, canAskAgain: p.canAskAgain });
  };

  // Live position + compass, only while this screen is visible.
  useFocusEffect(
    useCallback(() => {
      setFocused(true);
      if (!locPerm?.granted) return () => setFocused(false);
      let cancelled = false;
      let posSub: Location.LocationSubscription | null = null;
      let headSub: Location.LocationSubscription | null = null;
      let last = -999;
      (async () => {
        try {
          posSub = await Location.watchPositionAsync(
            { accuracy: Location.Accuracy.High, distanceInterval: 4, timeInterval: 2000 },
            (p) => setFix({ lat: p.coords.latitude, lng: p.coords.longitude }),
          );
        } catch {}
        if (Platform.OS !== "web") {
          try {
            headSub = await Location.watchHeadingAsync((h) => {
              const v = h.trueHeading >= 0 ? h.trueHeading : h.magHeading;
              if (angleDiff(v, last) > 4) {
                last = v;
                setHeading(v);
              }
            });
          } catch {
            setHasCompass(false);
          }
        }
        if (cancelled) {
          posSub?.remove();
          headSub?.remove();
        }
      })();
      return () => {
        cancelled = true;
        setFocused(false);
        posSub?.remove();
        headSub?.remove();
      };
    }, [locPerm?.granted]),
  );

  // Without a compass (web preview) you drag to turn.
  const dragStart = useRef(0);
  const manualRef = useRef(0);
  // eslint-disable-next-line react-hooks/refs -- dragStart/manualRef are read inside gesture callbacks, never during render
  const [pan] = useState(() =>
    PanResponder.create({
      onMoveShouldSetPanResponder: (_e, g) => Math.abs(g.dx) > 8,
      onPanResponderGrant: () => {
        dragStart.current = manualRef.current;
      },
      onPanResponderMove: (_e, g) => {
        const next = (((dragStart.current - g.dx * 0.35) % 360) + 360) % 360;
        manualRef.current = next;
        setManualHeading(next);
      },
    }),
  );
  const effHeading = hasCompass ? heading : manualHeading;

  // Look something up once the phone has been held still on a new street or direction.
  useEffect(() => {
    if (!fix) return;
    const t = setTimeout(() => {
      setTarget((prev) => {
        const moved = !prev || distanceM(prev.lat, prev.lng, fix.lat, fix.lng) > MOVE_M;
        const turned = !prev || (effHeading != null && (prev.heading == null || angleDiff(effHeading, prev.heading) > TURN_DEG));
        return moved || turned ? { lat: +fix.lat.toFixed(5), lng: +fix.lng.toFixed(5), heading: effHeading } : prev;
      });
    }, SETTLE_MS);
    return () => clearTimeout(t);
  }, [fix, effHeading]);

  const look = useQuery({
    queryKey: ["look", target],
    queryFn: () => api.look(target!.lat, target!.lng, target!.heading),
    enabled: !!target,
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
  });
  const place = look.data?.place;
  const history = useQuery({
    queryKey: ["history", place?.key],
    queryFn: () => api.history(place!.key),
    enabled: !!place,
    initialData: () => look.data?.history ?? undefined,
    staleTime: Infinity,
    retry: 1,
  });

  // Verified community stories near you pop up as "Did you know?".
  const cell = fix ? `${fix.lat.toFixed(3)},${fix.lng.toFixed(3)}` : null;
  const near = useQuery({
    queryKey: ["stories", "near", cell],
    queryFn: () => api.storiesNear(fix!.lat, fix!.lng),
    enabled: !!cell,
    staleTime: 60_000,
  });
  useEffect(() => {
    const next = near.data?.find((t) => !seenStories.current.has(t.id));
    if (!next) return;
    seenStories.current.add(next.id);
    setToast(next);
    if (Platform.OS !== "web") Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    const t = setTimeout(() => setToast((cur) => (cur?.id === next.id ? null : cur)), 9000);
    return () => clearTimeout(t);
  }, [near.data]);

  const eras = history.data?.eras ?? [];
  const firstWithText = eras.find((e) => e.text)?.key ?? "today";
  const eraKey = pickedEra ?? firstWithText;
  const entry = eras.find((e) => e.key === eraKey);

  const pickEra = (k: string) => {
    setPickedEra(k);
    if (Platform.OS !== "web") Haptics.selectionAsync().catch(() => {});
  };

  if (!locPerm) {
    return (
      <View style={[s.root, s.center]}>
        <ActivityIndicator color={colors.onSurfaceInverse} />
      </View>
    );
  }

  if (!locPerm.granted) {
    return (
      <View style={[s.permRoot, { paddingTop: insets.top + spacing["3xl"], paddingBottom: insets.bottom + spacing.xl }]} testID="location-permission">
        <StatusBar style="dark" />
        <Text style={s.brand}>NVM</Text>
        <Text style={s.permTitle}>Don&apos;t know what was here before? Nevermind.</Text>
        <Text style={s.permBody}>
          NVM uses your location and compass to work out which street you&apos;re pointing at, then shows what stood there through the centuries.
          Your location is only used while the app is open.
        </Text>
        <View style={{ flex: 1 }} />
        {locPerm.canAskAgain ? (
          <Pressable style={s.primary} onPress={askLocation} testID="allow-location-btn">
            <Text style={s.primaryText}>Allow location</Text>
          </Pressable>
        ) : (
          <Pressable style={s.primary} onPress={() => Linking.openSettings()} testID="open-settings-location-btn">
            <Text style={s.primaryText}>Open settings</Text>
          </Pressable>
        )}
        <Pressable style={s.secondary} onPress={() => router.push("/search")} testID="search-instead-btn">
          <Text style={s.secondaryText}>Search a street instead</Text>
        </Pressable>
      </View>
    );
  }

  const camOn = !!camPerm?.granted && focused;

  return (
    <View style={s.root} {...(hasCompass ? {} : pan.panHandlers)} testID="camera-home">
      <StatusBar style="light" />
      {camOn ? <CameraView style={StyleSheet.absoluteFill} facing="back" testID="camera-view" /> : null}

      {/* Top: what you're facing */}
      <View style={[s.top, { paddingTop: insets.top + spacing.sm }]}>
        <View style={s.pill}>
          <View style={s.pillInner} testID="facing-pill">
            <Text style={s.pillTag}>
              FACING{effHeading != null ? ` · ${compassLabel(effHeading)} ${Math.round(effHeading)}°` : ""}
            </Text>
            <Text style={s.pillTitle} numberOfLines={1} testID="facing-title">
              {place?.title ?? (fix ? "Working out the street…" : "Finding where you are…")}
            </Text>
            {place?.subtitle ? (
              <Text style={s.pillSub} numberOfLines={1} testID="facing-subtitle">
                {place.subtitle}
              </Text>
            ) : null}
          </View>
        </View>
        <View style={s.topBtns}>
          <Pressable style={s.roundBtn} onPress={() => router.push("/search")} testID="open-search-btn" accessibilityLabel="Search a street">
            <Feather name="search" size={20} color={colors.onSurface} />
          </Pressable>
          <Pressable style={s.roundBtn} onPress={() => router.push("/stories")} testID="open-stories-btn" accessibilityLabel="Community stories">
            <Feather name="users" size={20} color={colors.onSurface} />
          </Pressable>
        </View>
      </View>

      {!camOn ? (
        <View style={s.camPrompt} testID="camera-permission">
          <Text style={s.camPromptText}>Turn on the camera to see the street as you read about it.</Text>
          {camPerm?.canAskAgain !== false ? (
            <Pressable style={s.camPromptBtn} onPress={requestCam} testID="camera-permission-btn">
              <Text style={s.camPromptBtnText}>Turn on camera</Text>
            </Pressable>
          ) : (
            <Pressable style={s.camPromptBtn} onPress={() => Linking.openSettings()} testID="open-settings-camera-btn">
              <Text style={s.camPromptBtnText}>Open settings</Text>
            </Pressable>
          )}
        </View>
      ) : null}

      {!hasCompass ? (
        <View style={s.dragHint} pointerEvents="none" testID="drag-hint">
          <Feather name="move" size={14} color={colors.onSurfaceInverse} />
          <Text style={s.dragHintText}>No compass here. Drag sideways to turn.</Text>
        </View>
      ) : null}

      {toast ? (
        <Pressable style={[s.toast, { top: insets.top + 110 }]} onPress={() => setToast(null)} testID="dyk-toast">
          <Text style={s.toastTag}>DID YOU KNOW?</Text>
          <Text style={s.toastTitle}>{toast.title}</Text>
          <Text style={s.toastBody} numberOfLines={3}>
            {toast.body}
          </Text>
          <Text style={s.toastMeta}>Shared by {toast.author} · tap to close</Text>
        </Pressable>
      ) : null}

      {/* Bottom: era scrubber + what was here */}
      <View style={[s.bottom, { paddingBottom: insets.bottom + spacing.md }]}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.eraRow} contentContainerStyle={s.eraRowContent}>
          {ERAS.map((e) => {
            const active = e.key === eraKey;
            const has = !!eras.find((x) => x.key === e.key)?.text;
            return (
              <Pressable key={e.key} onPress={() => pickEra(e.key)} style={[s.chip, active && s.chipActive]} testID={`era-${e.key}`}>
                <Text style={[s.chipText, active && s.chipTextActive, !has && !active && s.chipTextEmpty]}>{e.label}</Text>
              </Pressable>
            );
          })}
        </ScrollView>

        <View style={s.card}>
          <View style={s.cardInner} testID="era-card">
            {!target || (look.isPending && !look.data) ? (
              <Status text={fix ? "Finding the street in front of you…" : "Getting your location…"} />
            ) : look.isError && !look.data ? (
              <Retry text={(look.error as Error).message} onPress={() => look.refetch()} testID="look-retry" />
            ) : history.isPending ? (
              <Status text="Unearthing the history of this spot…" sub="Takes a few seconds the first time anyone looks here." />
            ) : history.isError ? (
              <Retry text={(history.error as Error).message} onPress={() => history.refetch()} testID="history-retry" />
            ) : !history.data?.has_records ? (
              <View testID="no-records">
                <Text style={s.cardHeading}>No recorded history found here yet</Text>
                <Text style={s.cardText}>Open sources have nothing on {place?.title} so far. If you know what used to be here, add it.</Text>
              </View>
            ) : entry?.text ? (
              <View>
                <Text style={s.cardEra} testID="era-card-label">
                  {entry.label.toUpperCase()} · {SCOPE_LABEL[entry.scope].toUpperCase()}
                </Text>
                <Text style={s.cardHeading} testID="era-card-heading">
                  {entry.heading}
                </Text>
                <Text style={s.cardText} numberOfLines={5} testID="era-card-text">
                  {entry.text}
                </Text>
              </View>
            ) : (
              <View testID="era-empty">
                <Text style={s.cardEra}>{entry?.label.toUpperCase()}</Text>
                <Text style={s.cardText}>Nothing recorded for this period here. Try another era.</Text>
              </View>
            )}

            {place ? (
              <View style={s.cardActions}>
                <Pressable style={s.cardBtn} onPress={() => router.push({ pathname: "/place/[key]", params: { key: place.key } })} testID="open-full-history-btn">
                  <Text style={s.cardBtnText}>Full history</Text>
                  <Feather name="arrow-right" size={16} color={colors.onBrandPrimary} />
                </Pressable>
                <Pressable style={s.cardBtnGhost} onPress={() => router.push({ pathname: "/story/new", params: { key: place.key } })} testID="add-story-btn">
                  <Feather name="edit-3" size={16} color={colors.brandPrimary} />
                  <Text style={s.cardBtnGhostText}>Add a story</Text>
                </Pressable>
              </View>
            ) : null}
          </View>
        </View>
      </View>
    </View>
  );
}

function Status({ text, sub }: { text: string; sub?: string }) {
  const s = useStyles();
  const { colors } = useTheme();
  return (
    <View style={s.status} testID="card-status">
      <ActivityIndicator color={colors.brandPrimary} />
      <View style={{ flex: 1 }}>
        <Text style={s.cardText}>{text}</Text>
        {sub ? <Text style={s.statusSub}>{sub}</Text> : null}
      </View>
    </View>
  );
}

function Retry({ text, onPress, testID }: { text: string; onPress: () => void; testID: string }) {
  const s = useStyles();
  return (
    <Pressable onPress={onPress} testID={testID}>
      <Text style={s.cardText}>{text}</Text>
      <Text style={s.retry}>Tap to try again</Text>
    </Pressable>
  );
}

const useStyles = makeStyles((colors) => ({
  root: { flex: 1, backgroundColor: colors.surfaceInverse, ...(Platform.OS === "web" ? ({ userSelect: "none" } as object) : {}) },
  center: { alignItems: "center", justifyContent: "center" },
  top: { position: "absolute", left: 0, right: 0, top: 0, flexDirection: "row", gap: spacing.sm, paddingHorizontal: spacing.lg },
  pill: { flex: 1, borderRadius: radius.lg, overflow: "hidden" },
  pillInner: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md, backgroundColor: `${colors.surface}F2` },
  pillTag: { fontFamily: fonts.bodyBold, fontSize: 10, letterSpacing: 1.4, color: colors.brand },
  pillTitle: { fontFamily: fonts.displayBold, fontSize: 20, color: colors.onSurface, marginTop: 2 },
  pillSub: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: 1 },
  topBtns: { gap: spacing.sm },
  roundBtn: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: `${colors.surface}E6` },
  camPrompt: { position: "absolute", left: spacing.lg, right: spacing.lg, top: "38%", padding: spacing.lg, borderRadius: radius.md, backgroundColor: `${colors.surface}14`, borderWidth: 1, borderColor: `${colors.surface}33`, alignItems: "flex-start", gap: spacing.md },
  camPromptText: { fontFamily: fonts.body, fontSize: 14, lineHeight: 20, color: colors.onSurfaceInverse },
  camPromptBtn: { minHeight: 44, paddingHorizontal: spacing.lg, borderRadius: radius.pill, backgroundColor: colors.surface, justifyContent: "center" },
  camPromptBtnText: { fontFamily: fonts.bodyBold, fontSize: 14, color: colors.brandPrimary },
  dragHint: { position: "absolute", alignSelf: "center", top: "30%", flexDirection: "row", alignItems: "center", gap: spacing.xs, paddingHorizontal: spacing.md, paddingVertical: spacing.xs, borderRadius: radius.pill, backgroundColor: `${colors.surfaceInverse}B3` },
  dragHintText: { fontFamily: fonts.body, fontSize: 12, color: colors.onSurfaceInverse },
  toast: { position: "absolute", left: spacing.lg, right: spacing.lg, padding: spacing.lg, borderRadius: radius.md, backgroundColor: colors.surfaceInverse },
  toastTag: { fontFamily: fonts.bodyBold, fontSize: 10, letterSpacing: 1.4, color: colors.brandSecondary },
  toastTitle: { fontFamily: fonts.displayBold, fontSize: 17, color: colors.onSurfaceInverse, marginTop: spacing.xs },
  toastBody: { fontFamily: fonts.body, fontSize: 13, lineHeight: 19, color: colors.onSurfaceInverse, marginTop: 2 },
  toastMeta: { fontFamily: fonts.body, fontSize: 11, color: colors.brandSecondary, marginTop: spacing.sm },
  bottom: { position: "absolute", left: 0, right: 0, bottom: 0 },
  eraRow: { height: 56, flexGrow: 0 },
  eraRowContent: { gap: spacing.sm, paddingHorizontal: spacing.lg, alignItems: "center" },
  chip: { height: 36, flexShrink: 0, paddingHorizontal: spacing.md, borderRadius: radius.pill, justifyContent: "center", backgroundColor: `${colors.surface}CC`, borderWidth: 1, borderColor: "transparent" },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.onSurface },
  chipTextActive: { color: colors.onBrandPrimary },
  chipTextEmpty: { color: colors.muted },
  card: { marginHorizontal: spacing.lg, borderRadius: radius.lg, overflow: "hidden" },
  cardInner: { padding: spacing.lg, backgroundColor: `${colors.surface}EB`, minHeight: 150 },
  cardEra: { fontFamily: fonts.bodyBold, fontSize: 10, letterSpacing: 1.3, color: colors.brand },
  cardHeading: { fontFamily: fonts.displayBold, fontSize: 19, color: colors.onSurface, marginTop: spacing.xs },
  cardText: { fontFamily: fonts.body, fontSize: 14, lineHeight: 21, color: colors.onSurface, marginTop: spacing.xs },
  status: { flexDirection: "row", gap: spacing.md, alignItems: "center", minHeight: 60 },
  statusSub: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: 2 },
  retry: { fontFamily: fonts.bodyBold, fontSize: 13, color: colors.brandPrimary, marginTop: spacing.sm },
  cardActions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  cardBtn: { flex: 1, minHeight: 44, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs },
  cardBtnText: { fontFamily: fonts.bodyBold, fontSize: 14, color: colors.onBrandPrimary },
  cardBtnGhost: { flex: 1, minHeight: 44, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs },
  cardBtnGhostText: { fontFamily: fonts.bodyBold, fontSize: 14, color: colors.brandPrimary },
  permRoot: { flex: 1, backgroundColor: colors.surface, paddingHorizontal: spacing.xl },
  brand: { fontFamily: fonts.displayBold, fontSize: 22, letterSpacing: 4, color: colors.brandPrimary },
  permTitle: { fontFamily: fonts.displayBold, fontSize: 34, lineHeight: 42, color: colors.onSurface, marginTop: spacing.xl },
  permBody: { fontFamily: fonts.body, fontSize: 15, lineHeight: 23, color: colors.muted, marginTop: spacing.lg },
  primary: { height: 52, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  primaryText: { fontFamily: fonts.bodyBold, fontSize: 15, color: colors.onBrandPrimary },
  secondary: { height: 52, alignItems: "center", justifyContent: "center", marginTop: spacing.sm },
  secondaryText: { fontFamily: fonts.bodyBold, fontSize: 15, color: colors.brandPrimary },
}));
