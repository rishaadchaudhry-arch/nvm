import { useQuery } from "@tanstack/react-query";
import { CameraView, useCameraPermissions } from "expo-camera";
import * as Location from "expo-location";
import { useFocusEffect, useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";
import Feather from "@react-native-vector-icons/feather";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Modal,
  PanResponder,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, bearingDeg, distanceM, formatDistance, type Poi, type Tradition } from "@/src/api";
import { EraChips } from "@/src/components/era-chips";
import { usesNativeTabs } from "@/src/navigation";
import { fonts, radius, spacing } from "@/src/theme";

const FOV = 55; // horizontal field of view of a phone camera in portrait, degrees
const RANGE_M = 600; // only show places within this distance
const CARD_W = 180;
const DYK_RADIUS_M = 80;
const EDGE_GUTTER = 56;

type Coords = { lat: number; lng: number; accuracy: number | null };
type PermState = { status: "undetermined" | "granted" | "denied"; canAskAgain: boolean };

const INK = "#1A2130";
const PAPER = "#F9F6F0";
const SAFFRON = "#C85A32";
const GOLD = "#D4AF37";

export default function CameraScreen() {
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const { width: W, height: H } = useWindowDimensions();

  const [focused, setFocused] = useState(false);
  useFocusEffect(
    useCallback(() => {
      setFocused(true);
      return () => setFocused(false);
    }, []),
  );

  // ---- Location permission + live position ----
  const [locPerm, setLocPerm] = useState<PermState | null>(null);
  const [coords, setCoords] = useState<Coords | null>(null);
  const [asked, setAsked] = useState(false);

  useEffect(() => {
    Location.getForegroundPermissionsAsync().then((p) =>
      setLocPerm({ status: p.status as PermState["status"], canAskAgain: p.canAskAgain }),
    );
  }, []);

  const requestLocation = async () => {
    setAsked(true);
    const p = await Location.requestForegroundPermissionsAsync();
    setLocPerm({ status: p.status as PermState["status"], canAskAgain: p.canAskAgain });
  };

  useEffect(() => {
    if (!focused || locPerm?.status !== "granted") return;
    let sub: Location.LocationSubscription | null = null;
    let cancelled = false;
    Location.watchPositionAsync({ accuracy: Location.Accuracy.High, distanceInterval: 3, timeInterval: 2000 }, (pos) =>
      setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy: pos.coords.accuracy ?? null }),
    )
      .then((s) => (cancelled ? s.remove() : (sub = s)))
      .catch(() => {});
    return () => {
      cancelled = true;
      sub?.remove();
    };
  }, [focused, locPerm?.status]);

  // ---- Compass heading (smoothed). Web has no compass: drag to turn instead. ----
  const [heading, setHeading] = useState(0);
  const [compass, setCompass] = useState<"waiting" | "live" | "unavailable">(Platform.OS === "web" ? "unavailable" : "waiting");
  const headingRef = useRef(0);
  const lastEmit = useRef(0);

  useEffect(() => {
    if (Platform.OS === "web" || !focused || locPerm?.status !== "granted") return;
    let sub: Location.LocationSubscription | null = null;
    let cancelled = false;
    Location.watchHeadingAsync((h) => {
      const raw = h.trueHeading >= 0 ? h.trueHeading : h.magHeading;
      if (raw < 0 || Number.isNaN(raw)) return;
      const prev = headingRef.current;
      const delta = ((raw - prev + 540) % 360) - 180;
      headingRef.current = (prev + delta * 0.25 + 360) % 360; // low-pass filter
      const now = Date.now();
      if (now - lastEmit.current > 80) {
        lastEmit.current = now;
        setHeading(headingRef.current);
        setCompass("live");
      }
    })
      .then((s) => (cancelled ? s.remove() : (sub = s)))
      .catch(() => setCompass("unavailable"));
    return () => {
      cancelled = true;
      sub?.remove();
    };
  }, [focused, locPerm?.status]);

  const dragStart = useRef(0);
  const pan = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, g) => compass === "unavailable" && Math.abs(g.dx) > 6,
        onPanResponderGrant: () => (dragStart.current = headingRef.current),
        onPanResponderMove: (_, g) => {
          headingRef.current = (dragStart.current - (g.dx / W) * FOV + 720) % 360;
          setHeading(headingRef.current);
        },
      }),
    [compass, W],
  );

  // ---- Area + places around the user ----
  const nearby = useQuery({
    queryKey: ["nearby-live", coords?.lat.toFixed(3), coords?.lng.toFixed(3)],
    queryFn: () => api.nearby(coords!.lat, coords!.lng),
    enabled: !!coords,
    placeholderData: (prev) => prev,
  });
  const inside = nearby.data?.inside ?? null;

  // ---- Camera permission (asked only once the user is at a place with stories) ----
  const [camPerm, requestCam] = useCameraPermissions();

  // ---- Era selection ----
  const [era, setEra] = useState<string | null>(null);
  const eraKey = era ?? inside?.eras[0]?.key ?? "today";

  // ---- Project places onto the screen ----
  const projected = useMemo(() => {
    if (!coords || !inside) return { onScreen: [], left: 0, right: 0, nearest: null as null | (Poi & { d: number }) };
    const all = inside.pois
      .map((p) => {
        const d = distanceM(coords.lat, coords.lng, p.lat, p.lng);
        const rel = ((bearingDeg(coords.lat, coords.lng, p.lat, p.lng) - heading + 540) % 360) - 180;
        return { ...p, d, rel };
      })
      .filter((p) => p.d <= RANGE_M)
      .sort((a, b) => a.d - b.d);
    const placed: { x: number; y: number }[] = [];
    const CARD_H = 112;
    const onScreen = all
      .filter((p) => Math.abs(p.rel) <= FOV / 2)
      .map((p) => {
        const rawX = W / 2 + (p.rel / (FOV / 2)) * (W / 2) - CARD_W / 2;
        // Keep labels clear of the left/right counter pills at the screen edges.
        const x = Math.max(EDGE_GUTTER, Math.min(W - CARD_W - EDGE_GUTTER, rawX));
        let y = H * 0.2 + Math.min(1, p.d / RANGE_M) * H * 0.22;
        while (placed.some((q) => Math.abs(q.x - x) < CARD_W + 4 && Math.abs(q.y - y) < CARD_H + 8)) y += CARD_H + 8;
        placed.push({ x, y });
        return { ...p, x, y };
      })
      .filter((p) => p.y + CARD_H < H - 180); // drop labels that would run under the bottom panel
    return {
      onScreen,
      left: all.filter((p) => p.rel < -FOV / 2).length,
      right: all.filter((p) => p.rel > FOV / 2).length,
      nearest: all[0] ? { ...all[0] } : null,
    };
  }, [coords, inside, heading, W, H]);

  // ---- "Did you know?" pop-up when standing next to a place with verified traditions ----
  const [dyk, setDyk] = useState<Tradition | null>(null);
  const shown = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!inside || !projected.nearest || projected.nearest.d > DYK_RADIUS_M || dyk) return;
    const t = inside.did_you_know.find((x) => x.poi_slug === projected.nearest!.slug && !shown.current.has(x.id));
    if (t) {
      shown.current.add(t.id);
      setDyk(t);
    }
  }, [inside, projected.nearest, dyk]);

  const [selected, setSelected] = useState<(Poi & { d: number }) | null>(null);

  // ---------------------------- RENDER ----------------------------

  if (!locPerm) return <Centered><ActivityIndicator color={GOLD} /></Centered>;

  if (locPerm.status !== "granted") {
    const blocked = !locPerm.canAskAgain || (asked && locPerm.status === "denied");
    return (
      <Centered>
        <PermissionCard
          icon="map-pin"
          title="See what was here, right where you stand"
          text="Yatra uses your location to know which street you're on and which buildings you're looking at. It's never shared."
          action={blocked && !locPerm.canAskAgain ? "Open Settings" : asked ? "Try again" : "Allow location"}
          onPress={blocked && !locPerm.canAskAgain ? () => Linking.openSettings() : requestLocation}
          testID="location-permission-btn"
        />
      </Centered>
    );
  }

  if (!coords || (nearby.isLoading && !nearby.data)) {
    return (
      <Centered>
        <ActivityIndicator color={GOLD} />
        <Text style={s.waitText}>Finding where you are…</Text>
      </Centered>
    );
  }

  if (!inside) {
    return (
      <Centered>
        <View style={s.permCard} testID="not-on-location">
          <Feather name="navigation" size={24} color={SAFFRON} />
          <Text style={s.permTitle}>The camera view works on location</Text>
          <Text style={s.permText}>
            {nearby.data?.nearest
              ? `There are no stories where you are yet. The nearest place with stories is ${nearby.data.nearest.name}, ${formatDistance(nearby.data.nearest.distance_m)} away.`
              : "There are no stories where you are yet."}
          </Text>
          {nearby.data?.nearest ? (
            <Pressable style={s.permBtn} onPress={() => router.push(`/area/${nearby.data!.nearest!.slug}`)} testID="read-nearest-btn">
              <Text style={s.permBtnText}>Read about {nearby.data.nearest.name}</Text>
            </Pressable>
          ) : null}
        </View>
      </Centered>
    );
  }

  if (!camPerm?.granted) {
    const blocked = camPerm && !camPerm.canAskAgain;
    return (
      <Centered>
        <PermissionCard
          icon="camera"
          title={`You're in ${inside.area.name}`}
          text="Allow the camera and point it down the street. Labels appear over the buildings in front of you, for any era you pick."
          action={blocked ? "Open Settings" : "Allow camera"}
          onPress={blocked ? () => Linking.openSettings() : requestCam}
          testID="camera-permission-btn"
        />
      </Centered>
    );
  }

  return (
    <View style={s.root} {...pan.panHandlers} testID="ar-view">
      {focused ? <StatusBar style="light" /> : null}
      {focused ? <CameraView style={StyleSheet.absoluteFill} facing="back" /> : <View style={[StyleSheet.absoluteFill, { backgroundColor: INK }]} />}

      <View style={[s.top, { paddingTop: insets.top + spacing.sm }]}>
        <View style={s.headerRow}>
          <View style={s.badge}>
            <View style={s.liveDot} />
            <Text style={s.badgeText} numberOfLines={1} testID="ar-area-name">{inside.area.name}</Text>
          </View>
          <View style={s.badge}>
            <Feather name="compass" size={12} color={PAPER} />
            <Text style={s.badgeText} testID="ar-heading">{Math.round(heading)}°</Text>
          </View>
        </View>
        <EraChips eras={inside.eras} selected={eraKey} onSelect={setEra} dark testPrefix="ar-era" />
        {compass === "unavailable" ? (
          <Text style={s.note}>No compass on this device. Drag left or right to look around.</Text>
        ) : compass === "waiting" ? (
          <Text style={s.note}>Calibrating compass… move your phone in a figure of eight.</Text>
        ) : coords.accuracy && coords.accuracy > 40 ? (
          <Text style={s.note}>GPS is rough here (±{Math.round(coords.accuracy)} m). Labels may be slightly off.</Text>
        ) : null}
      </View>

      {projected.onScreen.map((p) => {
        const e = p.eras.find((x) => x.key === eraKey);
        return (
          <Pressable
            key={p.slug}
            style={[s.marker, { left: p.x, top: p.y }]}
            onPress={() => setSelected(p)}
            testID={`ar-marker-${p.slug}`}
          >
            <Text style={s.markerCat}>{p.category.toUpperCase()} · {formatDistance(p.d)}</Text>
            <Text style={s.markerName} numberOfLines={2}>{p.name}</Text>
            <Text style={[s.markerEra, !e && s.markerEraEmpty]} numberOfLines={2}>
              {e ? e.title : "No record from this era yet"}
            </Text>
            <View style={s.stem} />
          </Pressable>
        );
      })}

      {projected.left > 0 ? (
        <View style={[s.edge, { left: spacing.sm, top: H * 0.45 }]} testID="ar-left-count">
          <Feather name="chevron-left" size={18} color={PAPER} />
          <Text style={s.edgeText}>{projected.left}</Text>
        </View>
      ) : null}
      {projected.right > 0 ? (
        <View style={[s.edge, { right: spacing.sm, top: H * 0.45 }]} testID="ar-right-count">
          <Text style={s.edgeText}>{projected.right}</Text>
          <Feather name="chevron-right" size={18} color={PAPER} />
        </View>
      ) : null}

      <View style={[s.bottom, { bottom: bottomChrome + spacing.lg }]}>
        {dyk ? (
          <View style={s.dyk} testID="ar-did-you-know">
            <View style={s.dykHead}>
              <Text style={s.dykTag}>DID YOU KNOW?</Text>
              <Pressable onPress={() => setDyk(null)} hitSlop={12} style={s.dykClose} testID="ar-dyk-close">
                <Feather name="x" size={16} color={INK} />
              </Pressable>
            </View>
            <Text style={s.dykTitle}>{dyk.title}</Text>
            <Text style={s.dykBody} numberOfLines={4}>{dyk.body}</Text>
          </View>
        ) : projected.onScreen.length === 0 ? (
          <View style={s.hintPill} testID="ar-hint" pointerEvents="none">
            <Text style={s.hintText}>
              {projected.left + projected.right > 0
                ? "Turn around slowly. There are places with stories beside you."
                : "Nothing with stories within 600 m. Walk along the street."}
            </Text>
          </View>
        ) : null}
      </View>

      <Modal visible={!!selected} transparent animationType="slide" onRequestClose={() => setSelected(null)}>
        <Pressable style={s.backdrop} onPress={() => setSelected(null)} testID="ar-sheet-backdrop" />
        {selected ? (
          <View style={[s.sheet, { paddingBottom: insets.bottom + spacing.lg }]} testID="ar-sheet">
            <Text style={s.sheetCat}>{selected.category.toUpperCase()} · {formatDistance(selected.d)} AWAY</Text>
            <Text style={s.sheetTitle}>{selected.name}</Text>
            {(() => {
              const e = selected.eras.find((x) => x.key === eraKey);
              const label = inside.eras.find((x) => x.key === eraKey)?.label;
              return e ? (
                <>
                  <Text style={s.sheetEra}>{label}</Text>
                  <Text style={s.sheetEraTitle}>{e.title}</Text>
                  <Text style={s.sheetBody}>{e.description}</Text>
                </>
              ) : (
                <Text style={s.sheetBody}>No record from {label} yet. Know something? Add it as an oral tradition.</Text>
              );
            })()}
            <Pressable
              style={s.sheetBtn}
              onPress={() => {
                const slug = selected.slug;
                setSelected(null);
                router.push(`/poi/${slug}`);
              }}
              testID="ar-sheet-open"
            >
              <Text style={s.sheetBtnText}>See every era, then and now</Text>
            </Pressable>
          </View>
        ) : null}
      </Modal>
    </View>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <View style={[s.root, s.center]}>{children}</View>;
}

function PermissionCard(props: { icon: "map-pin" | "camera"; title: string; text: string; action: string; onPress: () => void; testID: string }) {
  return (
    <View style={s.permCard}>
      <Feather name={props.icon} size={24} color={SAFFRON} />
      <Text style={s.permTitle}>{props.title}</Text>
      <Text style={s.permText}>{props.text}</Text>
      <Pressable style={s.permBtn} onPress={props.onPress} testID={props.testID}>
        <Text style={s.permBtnText}>{props.action}</Text>
      </Pressable>
    </View>
  );
}

// The camera screen is always dark over live video, so its colours are fixed in both themes.
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: INK, ...(Platform.OS === "web" ? ({ userSelect: "none" } as object) : {}) },
  center: { alignItems: "center", justifyContent: "center", padding: spacing.xl },
  waitText: { fontFamily: fonts.body, fontSize: 13, color: PAPER, marginTop: spacing.md },
  top: { position: "absolute", left: 0, right: 0, top: 0, backgroundColor: "rgba(26,33,48,0.45)", paddingBottom: spacing.xs },
  headerRow: { flexDirection: "row", justifyContent: "space-between", paddingHorizontal: spacing.lg, gap: spacing.sm },
  badge: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: "rgba(26,33,48,0.7)", paddingHorizontal: spacing.md, height: 36, borderRadius: radius.pill, flexShrink: 1 },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: GOLD },
  badgeText: { fontFamily: fonts.bodyBold, fontSize: 13, color: PAPER },
  note: { fontFamily: fonts.body, fontSize: 12, color: PAPER, opacity: 0.9, paddingHorizontal: spacing.xl, paddingBottom: spacing.xs },
  marker: {
    position: "absolute",
    width: CARD_W,
    height: 112,
    overflow: "hidden",
    padding: spacing.md,
    backgroundColor: "rgba(249,246,240,0.95)",
    borderRadius: radius.lg,
    borderLeftWidth: 3,
    borderLeftColor: SAFFRON,
  },
  markerCat: { fontFamily: fonts.bodyBold, fontSize: 9, color: SAFFRON, letterSpacing: 1 },
  markerName: { fontFamily: fonts.displayBold, fontSize: 17, color: INK, marginTop: 2, lineHeight: 19 },
  markerEra: { fontFamily: fonts.body, fontSize: 12, color: INK, marginTop: 4 },
  markerEraEmpty: { color: "#5C667A", fontStyle: "italic" },
  stem: { position: "absolute", bottom: -10, left: CARD_W / 2 - 1, width: 2, height: 10, backgroundColor: "rgba(249,246,240,0.95)" },
  edge: { position: "absolute", flexDirection: "row", alignItems: "center", gap: 2, height: 44, paddingHorizontal: spacing.sm, borderRadius: radius.pill, backgroundColor: "rgba(26,33,48,0.7)" },
  edgeText: { fontFamily: fonts.bodyBold, fontSize: 13, color: PAPER },
  bottom: { position: "absolute", left: spacing.lg, right: spacing.lg },
  hintPill: { backgroundColor: "rgba(26,33,48,0.75)", padding: spacing.md, borderRadius: radius.lg },
  hintText: { fontFamily: fonts.body, fontSize: 13, color: PAPER, textAlign: "center" },
  dyk: { backgroundColor: PAPER, padding: spacing.lg, borderRadius: radius.lg, borderLeftWidth: 3, borderLeftColor: GOLD },
  dykHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  dykTag: { fontFamily: fonts.bodyBold, fontSize: 10, color: SAFFRON, letterSpacing: 1.4 },
  dykClose: { width: 44, height: 44, alignItems: "flex-end", justifyContent: "center", marginVertical: -12 },
  dykTitle: { fontFamily: fonts.displayBold, fontSize: 19, color: INK, marginTop: spacing.xs },
  dykBody: { fontFamily: fonts.body, fontSize: 13, lineHeight: 20, color: INK, marginTop: spacing.xs },
  backdrop: { flex: 1, backgroundColor: "rgba(26,33,48,0.4)" },
  sheet: { backgroundColor: PAPER, padding: spacing.xl, borderTopLeftRadius: 16, borderTopRightRadius: 16 },
  sheetCat: { fontFamily: fonts.bodyBold, fontSize: 10, color: "#5C667A", letterSpacing: 1.2 },
  sheetTitle: { fontFamily: fonts.displayBold, fontSize: 28, color: INK, marginTop: spacing.xs },
  sheetEra: { fontFamily: fonts.bodyBold, fontSize: 11, color: SAFFRON, letterSpacing: 1, marginTop: spacing.lg },
  sheetEraTitle: { fontFamily: fonts.displayBold, fontSize: 20, color: INK, marginTop: spacing.xs },
  sheetBody: { fontFamily: fonts.body, fontSize: 15, lineHeight: 23, color: INK, marginTop: spacing.sm },
  sheetBtn: { minHeight: 48, borderRadius: radius.pill, backgroundColor: SAFFRON, alignItems: "center", justifyContent: "center", marginTop: spacing.xl },
  sheetBtnText: { fontFamily: fonts.bodyBold, fontSize: 14, color: "#FFFFFF" },
  permCard: { backgroundColor: PAPER, padding: spacing.xl, borderRadius: radius.lg, alignItems: "center", gap: spacing.sm, maxWidth: 340 },
  permTitle: { fontFamily: fonts.displayBold, fontSize: 22, color: INK, textAlign: "center" },
  permText: { fontFamily: fonts.body, fontSize: 14, color: "#5C667A", textAlign: "center", lineHeight: 21 },
  permBtn: { minHeight: 48, justifyContent: "center", backgroundColor: SAFFRON, paddingHorizontal: spacing.xl, borderRadius: radius.pill, marginTop: spacing.sm },
  permBtnText: { fontFamily: fonts.bodyBold, fontSize: 14, color: "#FFFFFF" },
});
