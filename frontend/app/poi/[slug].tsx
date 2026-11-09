import { useQuery } from "@tanstack/react-query";
import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from "expo-audio";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import Feather from "@react-native-vector-icons/feather";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, AppState, BackHandler, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { CommunityCard, DidYouKnowCard } from "@/src/components/tradition-cards";
import { useJourney } from "@/src/journey";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";
import { ErrorView } from "@/src/components/error-view";

// One player for the whole app so narration never overlaps.
let player: AudioPlayer | null = null;
function stopPlayer() {
  try {
    player?.pause();
    player?.remove();
  } catch {}
  player = null;
}

export default function PoiScreen() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { saved, toggleSaved, markVisited } = useJourney();
  const q = useQuery({ queryKey: ["poi", slug], queryFn: () => api.poi(slug!), enabled: !!slug });

  const [audio, setAudio] = useState<"idle" | "loading" | "playing" | "paused" | "error">("idle");

  useEffect(() => {
    if (slug && q.data) markVisited(slug);
  }, [slug, q.data, markVisited]);

  // Stop narration on blur, back press and app background.
  useFocusEffect(
    useCallback(() => {
      const back = BackHandler.addEventListener("hardwareBackPress", () => {
        stopPlayer();
        return false;
      });
      const app = AppState.addEventListener("change", (st) => {
        if (st !== "active") {
          player?.pause();
          setAudio((a) => (a === "playing" ? "paused" : a));
        }
      });
      return () => {
        back.remove();
        app.remove();
        stopPlayer();
        setAudio("idle");
      };
    }, []),
  );

  const toggleAudio = async () => {
    if (!slug) return;
    if (audio === "playing" && player) {
      player.pause();
      return setAudio("paused");
    }
    if (audio === "paused" && player) {
      player.play();
      return setAudio("playing");
    }
    setAudio("loading");
    try {
      const { audio_url } = await api.narrate(slug);
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false });
      stopPlayer();
      const p = createAudioPlayer({ uri: api.audioUrl(audio_url) });
      player = p;
      p.addListener("playbackStatusUpdate", (st) => {
        if (st.didJustFinish) setAudio("idle");
        else if (st.playing) setAudio("playing");
      });
      p.play();
      // If playback never starts, surface an error instead of spinning forever.
      setTimeout(() => {
        if (player === p && !p.playing && p.currentTime === 0) {
          stopPlayer();
          setAudio((a) => (a === "loading" ? "error" : a));
        }
      }, 15000);
    } catch (e) {
      console.warn("narration failed", e);
      setAudio("error");
    }
  };

  if (q.isError) return <ErrorView onBack={() => router.back()} />;
  if (!q.data) return <View style={[styles.container, styles.center]}><ActivityIndicator color={colors.brandPrimary} /></View>;
  const { poi, area, eras, did_you_know, community, upvote_threshold } = q.data;
  const isSaved = !!slug && saved.includes(slug);
  const labelFor = (key: string) => eras.find((e) => e.key === key)?.label ?? key;
  const ordered = eras.map((e) => poi.eras.find((x) => x.key === e.key)).filter(Boolean) as typeof poi.eras;
  const then = ordered.find((e) => e.key !== "today");
  const now = poi.eras.find((e) => e.key === "today");

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 110 }}>
        <View style={styles.hero}>
          <Image source={{ uri: poi.image }} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient colors={["rgba(26,33,48,0.4)", "transparent", "rgba(26,33,48,0.95)"]} style={StyleSheet.absoluteFill} />
          <View style={[styles.heroActions, { top: insets.top + spacing.sm }]}>
            <Pressable onPress={() => router.back()} style={styles.iconBtn} testID="poi-back">
              <Feather name="arrow-left" size={20} color="#F9F6F0" />
            </Pressable>
            <Pressable onPress={() => slug && toggleSaved(slug)} style={styles.iconBtn} testID="poi-save">
              <Feather name="bookmark" size={20} color={isSaved ? "#D4AF37" : "#F9F6F0"} />
            </Pressable>
          </View>
          <View style={styles.heroText}>
            <Pressable onPress={() => router.push(`/area/${area.slug}`)} testID="poi-area-link">
              <Text style={styles.heroTag}>{poi.category.toUpperCase()} · {area.name.toUpperCase()}</Text>
            </Pressable>
            <Text style={styles.heroTitle} testID="poi-name">{poi.name}</Text>
          </View>
        </View>

        <View style={styles.body}>
          {then && now ? (
            <View style={styles.compare} testID="then-now">
              <View style={styles.compareCol}>
                <Text style={styles.compareTag}>THEN · {labelFor(then.key).split(" · ")[0]}</Text>
                <Text style={styles.compareTitle}>{then.title}</Text>
              </View>
              <View style={styles.compareDivider} />
              <View style={styles.compareCol}>
                <Text style={styles.compareTag}>NOW</Text>
                <Text style={styles.compareTitle}>{now.title}</Text>
              </View>
            </View>
          ) : null}

          <Text style={styles.section}>What was here, era by era</Text>
          {ordered.length === 0 ? (
            <Text style={styles.empty}>No stories for this place yet.</Text>
          ) : (
            ordered.map((e, i) => (
              <View key={e.key} style={styles.tlRow} testID={`poi-era-${e.key}`}>
                <View style={styles.tlCol}>
                  <View style={styles.dot} />
                  {i < ordered.length - 1 ? <View style={styles.line} /> : null}
                </View>
                <View style={styles.tlItem}>
                  <Text style={styles.tlYear}>{labelFor(e.key).toUpperCase()}</Text>
                  <Text style={styles.tlTitle}>{e.title}</Text>
                  <Text style={styles.tlDesc}>{e.description}</Text>
                </View>
              </View>
            ))
          )}

          {did_you_know.length ? (
            <>
              <Text style={styles.section}>Did you know?</Text>
              {did_you_know.map((t) => <DidYouKnowCard key={t.id} t={t} />)}
            </>
          ) : null}

          <View style={styles.sectionRow}>
            <Text style={styles.section}>Oral traditions</Text>
          </View>
          <Text style={styles.empty}>
            Stories from locals. At {upvote_threshold} upvotes, or once checked by the Yatra team, a story becomes a &quot;Did you know?&quot;.
          </Text>
          {community.map((t) => <CommunityCard key={t.id} t={t} threshold={upvote_threshold} />)}
          <Pressable
            style={styles.addBtn}
            onPress={() => router.push({ pathname: "/tradition/new", params: { area: area.slug, poi: poi.slug } })}
            testID="poi-add-tradition"
          >
            <Feather name="plus" size={16} color={colors.brandPrimary} />
            <Text style={styles.addText}>Share a tradition about this place</Text>
          </Pressable>
        </View>
      </ScrollView>

      {ordered.length ? (
        <View style={[styles.player, { paddingBottom: insets.bottom + spacing.sm }]}>
          <View style={{ flex: 1 }}>
            <Text style={styles.playerTag}>NARRATION</Text>
            <Text style={[styles.playerTitle, audio === "error" && { color: colors.error }]} testID="narrate-status">
              {audio === "error" ? "Couldn't play the story. Tap to retry." : audio === "loading" ? "Preparing the story…" : audio === "playing" ? "Playing…" : audio === "paused" ? "Paused" : "Hear this place's story"}
            </Text>
          </View>
          <Pressable onPress={toggleAudio} style={styles.playBtn} testID="narrate-btn" disabled={audio === "loading"}>
            {audio === "loading" ? (
              <ActivityIndicator color={colors.onBrandPrimary} />
            ) : (
              <Feather name={audio === "playing" ? "pause" : audio === "error" ? "rotate-cw" : "play"} size={22} color={colors.onBrandPrimary} />
            )}
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  hero: { height: 360, backgroundColor: colors.surfaceInverse },
  heroActions: { position: "absolute", left: spacing.lg, right: spacing.lg, flexDirection: "row", justifyContent: "space-between" },
  iconBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: "rgba(26,33,48,0.5)", alignItems: "center", justifyContent: "center" },
  heroText: { position: "absolute", left: spacing.xl, right: spacing.xl, bottom: spacing.xl },
  heroTag: { fontFamily: fonts.bodyBold, fontSize: 11, color: "#F9F6F0", letterSpacing: 1.2, opacity: 0.9, paddingVertical: spacing.xs },
  heroTitle: { fontFamily: fonts.displayBold, fontSize: 36, lineHeight: 40, color: "#F9F6F0" },
  body: { padding: spacing.xl },
  compare: { flexDirection: "row", borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary },
  compareCol: { flex: 1, padding: spacing.md },
  compareDivider: { width: 1, backgroundColor: colors.border },
  compareTag: { fontFamily: fonts.bodyBold, fontSize: 10, color: colors.brandPrimary, letterSpacing: 1 },
  compareTitle: { fontFamily: fonts.displayBold, fontSize: 16, color: colors.onSurface, marginTop: 4 },
  section: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.onSurface, marginTop: spacing.xl, marginBottom: spacing.md },
  sectionRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  empty: { fontFamily: fonts.body, fontSize: 13, lineHeight: 19, color: colors.muted, marginBottom: spacing.md },
  tlRow: { flexDirection: "row", gap: spacing.md },
  tlCol: { width: 14, alignItems: "center" },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brandPrimary, marginTop: 5 },
  line: { flex: 1, width: 1, backgroundColor: colors.border, marginTop: 4 },
  tlItem: { flex: 1, paddingBottom: spacing.lg },
  tlYear: { fontFamily: fonts.bodyBold, fontSize: 11, color: colors.brandPrimary, letterSpacing: 1 },
  tlTitle: { fontFamily: fonts.displayBold, fontSize: 19, color: colors.onSurface, marginTop: 2 },
  tlDesc: { fontFamily: fonts.body, fontSize: 14, lineHeight: 22, color: colors.muted, marginTop: 4 },
  addBtn: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 48, marginTop: spacing.sm, paddingHorizontal: spacing.lg, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, alignSelf: "flex-start" },
  addText: { fontFamily: fonts.bodyBold, fontSize: 13, color: colors.brandPrimary },
  player: { position: "absolute", left: 0, right: 0, bottom: 0, flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.xl, paddingTop: spacing.md, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.border },
  playerTag: { fontFamily: fonts.bodyBold, fontSize: 10, color: colors.brandPrimary, letterSpacing: 1.4 },
  playerTitle: { fontFamily: fonts.displayBold, fontSize: 16, color: colors.onSurface, marginTop: 2 },
  playBtn: { width: 52, height: 52, borderRadius: 26, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
}));
