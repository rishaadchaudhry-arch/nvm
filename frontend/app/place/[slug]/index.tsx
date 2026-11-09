import { useQuery } from "@tanstack/react-query";
import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from "expo-audio";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import Feather from "@react-native-vector-icons/feather";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Trivia } from "@/src/api";
import { useJourney } from "@/src/journey";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

export default function PlaceDetail() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const router = useRouter();
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { saved, toggleSaved, markVisited } = useJourney();

  const place = useQuery({ queryKey: ["place", slug], queryFn: () => api.place(slug!), enabled: !!slug });
  const timeline = useQuery({ queryKey: ["timeline", slug], queryFn: () => api.timeline(slug!), enabled: !!slug });
  const trivia = useQuery({ queryKey: ["trivia", slug], queryFn: () => api.trivia(slug!), enabled: !!slug });

  const playerRef = useRef<AudioPlayer | null>(null);
  const [audioState, setAudioState] = useState<"idle" | "loading" | "playing" | "paused">("idle");
  const [audioError, setAudioError] = useState<string | null>(null);

  useEffect(() => {
    if (slug && place.data) markVisited(slug);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, place.data]);

  useEffect(() => {
    return () => {
      try {
        playerRef.current?.pause();
        playerRef.current?.remove();
      } catch {}
      playerRef.current = null;
    };
  }, []);

  const handleNarrate = async () => {
    if (!slug) return;
    try {
      if (audioState === "playing" && playerRef.current) {
        playerRef.current.pause();
        setAudioState("paused");
        return;
      }
      if (audioState === "paused" && playerRef.current) {
        playerRef.current.play();
        setAudioState("playing");
        return;
      }
      setAudioError(null);
      setAudioState("loading");
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false });
      const { audio_url } = await api.narrate(slug, "fable");
      const url = api.audioUrl(audio_url);
      const p = createAudioPlayer({ uri: url });
      playerRef.current = p;
      p.addListener("playbackStatusUpdate", (s) => {
        if (s.didJustFinish) {
          setAudioState("idle");
        } else if (s.playing) {
          setAudioState("playing");
        }
      });
      p.play();
      setAudioState("playing");
    } catch {
      setAudioState("idle");
      setAudioError("Narration unavailable. Tap to retry.");
    }
  };

  const isSaved = slug ? saved.includes(slug) : false;

  if (place.isError) {
    return (
      <View style={[styles.container, styles.center, { padding: spacing.xl }]}>
        <Text style={styles.sectionTitle} testID="place-error">Place not found</Text>
        <Pressable
          onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))}
          style={styles.errorBtn}
          testID="place-error-back"
        >
          <Text style={styles.errorBtnText}>Go back</Text>
        </Pressable>
      </View>
    );
  }

  if (!place.data) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }

  const p = place.data;

  return (
    <View style={styles.container}>
      <ScrollView
        contentContainerStyle={{ paddingBottom: 140 + insets.bottom }}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.hero}>
          <Image source={{ uri: p.hero_image }} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient colors={["rgba(26,33,48,0.3)", "transparent", "rgba(26,33,48,0.95)"]} style={StyleSheet.absoluteFill} />
          <View style={[styles.heroActions, { top: insets.top + spacing.sm }]}>
            <Pressable onPress={() => router.back()} style={styles.iconBtn} testID="back-btn">
              <Feather name="arrow-left" size={20} color="#F9F6F0" />
            </Pressable>
            <Pressable onPress={() => slug && toggleSaved(slug)} style={styles.iconBtn} testID="save-btn">
              <Feather name="bookmark" size={20} color={isSaved ? "#D4AF37" : "#F9F6F0"} />
            </Pressable>
          </View>
          <View style={styles.heroText}>
            <Text style={styles.era}>{p.era.toUpperCase()}</Text>
            <Text style={styles.name}>{p.name}</Text>
            <View style={styles.cityRow}>
              <Feather name="map-pin" size={13} color="#F9F6F0" />
              <Text style={styles.city}>{p.city}, {p.state}</Text>
            </View>
          </View>
        </View>

        <View style={styles.body}>
          <View style={styles.actions}>
            <ActionBtn
              icon="globe"
              label="360° View"
              onPress={() => router.push(`/place/${slug}/panorama`)}
              testID="action-panorama"
            />
            <ActionBtn
              icon="camera"
              label="AR Camera"
              onPress={() => router.push(`/place/${slug}/ar`)}
              testID="action-ar"
            />
            <ActionBtn
              icon="plus-circle"
              label="Add Trivia"
              onPress={() => router.push(`/place/${slug}/contribute`)}
              testID="action-contribute"
            />
          </View>

          {timeline.isLoading ? (
            <View style={styles.inlineLoad}>
              <ActivityIndicator color={colors.brandPrimary} />
              <Text style={styles.inlineLoadText}>Uncovering history…</Text>
            </View>
          ) : timeline.data ? (
            <>
              <Text style={styles.summary}>{timeline.data.summary}</Text>

              <Text style={styles.sectionTitle}>Timeline</Text>
              <View style={styles.timeline}>
                {timeline.data.events.map((e, i) => (
                  <View key={i} style={styles.tlRow}>
                    <View style={styles.tlCol}>
                      <View style={styles.tlDot} />
                      {i < timeline.data!.events.length - 1 && <View style={styles.tlLine} />}
                    </View>
                    <View style={styles.tlItem}>
                      <Text style={styles.tlYear}>{e.year}</Text>
                      <Text style={styles.tlTitle}>{e.title}</Text>
                      <Text style={styles.tlDesc}>{e.description}</Text>
                    </View>
                  </View>
                ))}
              </View>

              <View style={styles.didCard}>
                <Text style={styles.didTag}>DID YOU KNOW?</Text>
                <Text style={styles.didText}>{timeline.data.did_you_know}</Text>
              </View>
            </>
          ) : (
            <Pressable onPress={() => timeline.refetch()} style={styles.inlineLoad} testID="timeline-retry">
              <Text style={styles.inlineLoadText}>Could not load history. Tap to retry.</Text>
            </Pressable>
          )}

          <View style={styles.triviaHeader}>
            <Text style={styles.sectionTitle}>Local Traditions</Text>
            <Pressable
              onPress={() => router.push(`/place/${slug}/contribute`)}
              testID="add-trivia-link"
            >
              <Text style={styles.addLink}>+ Add</Text>
            </Pressable>
          </View>
          {(trivia.data ?? []).length === 0 ? (
            <Text style={styles.emptyTrivia}>Be the first to share a tradition about this place.</Text>
          ) : (
            trivia.data!.map((t) => <TriviaCard key={t.id} t={t} />)
          )}
        </View>
      </ScrollView>

      <View style={[styles.player, { paddingBottom: insets.bottom + spacing.sm }]}>
        <View style={styles.playerContent}>
          <View style={{ flex: 1 }}>
            <Text style={styles.playerTag}>NARRATION</Text>
            <Text
              style={[styles.playerTitle, audioError ? { color: colors.error, fontSize: 13 } : null]}
              testID="narrate-status"
            >
              {audioError ?? "Listen to the story"}
            </Text>
          </View>
          <Pressable onPress={handleNarrate} style={styles.playBtn} testID="play-narrate-btn">
            {audioState === "loading" ? (
              <ActivityIndicator color={colors.onBrandPrimary} />
            ) : (
              <Feather
                name={audioState === "playing" ? "pause" : "play"}
                size={22}
                color={colors.onBrandPrimary}
              />
            )}
          </Pressable>
        </View>
      </View>
    </View>
  );
}

function ActionBtn({
  icon,
  label,
  onPress,
  testID,
}: {
  icon: string;
  label: string;
  onPress: () => void;
  testID: string;
}) {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <Pressable style={styles.action} onPress={onPress} testID={testID}>
      <Feather name={icon as any} size={18} color={colors.brandPrimary} />
      <Text style={styles.actionText}>{label}</Text>
    </Pressable>
  );
}

function TriviaCard({ t }: { t: Trivia }) {
  const styles = useStyles();
  return (
    <View style={styles.triviaCard}>
      <Text style={styles.triviaTitle}>{t.title}</Text>
      <Text style={styles.triviaBody}>{t.body}</Text>
      <Text style={styles.triviaAuthor}>— {t.author}</Text>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  hero: { height: 420, backgroundColor: colors.surfaceInverse },
  heroActions: { position: "absolute", left: spacing.lg, right: spacing.lg, flexDirection: "row", justifyContent: "space-between" },
  iconBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "rgba(26,33,48,0.4)",
    alignItems: "center",
    justifyContent: "center",
  },
  heroText: { position: "absolute", bottom: spacing.xl, left: spacing.xl, right: spacing.xl },
  era: { fontFamily: fonts.bodyBold, fontSize: 11, color: "#F9F6F0", letterSpacing: 1.5, opacity: 0.9 },
  errorBtn: {
    marginTop: spacing.md,
    paddingVertical: 12,
    paddingHorizontal: spacing.xl,
    borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
  },
  errorBtnText: { fontFamily: fonts.bodyBold, fontSize: 14, color: colors.onBrandPrimary },
  name: { fontFamily: fonts.displayBold, fontSize: 38, color: "#F9F6F0", marginTop: spacing.xs, lineHeight: 42 },
  cityRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.sm },
  city: { fontFamily: fonts.body, fontSize: 13, color: "#F9F6F0" },
  body: { paddingHorizontal: spacing.xl, paddingTop: spacing.xl },
  actions: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.xl },
  action: {
    flex: 1,
    paddingVertical: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    alignItems: "center",
    backgroundColor: colors.surfaceSecondary,
    gap: 4,
  },
  actionText: { fontFamily: fonts.bodyMedium, fontSize: 11, color: colors.onSurface, marginTop: 2 },
  summary: { fontFamily: fonts.body, fontSize: 15, lineHeight: 24, color: colors.onSurface, marginBottom: spacing.xl },
  sectionTitle: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.onSurface, marginBottom: spacing.md },
  inlineLoad: { paddingVertical: spacing.xl, alignItems: "center", gap: spacing.sm },
  inlineLoadText: { fontFamily: fonts.body, fontSize: 12, color: colors.muted },
  timeline: { marginBottom: spacing.xl },
  tlRow: { flexDirection: "row", gap: spacing.md },
  tlCol: { width: 16, alignItems: "center" },
  tlDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brandPrimary, marginTop: 6 },
  tlLine: { flex: 1, width: 1, backgroundColor: colors.border, marginTop: 4 },
  tlItem: { flex: 1, paddingBottom: spacing.lg },
  tlYear: { fontFamily: fonts.bodyBold, fontSize: 12, color: colors.brandPrimary, letterSpacing: 1 },
  tlTitle: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.onSurface, marginTop: 2 },
  tlDesc: { fontFamily: fonts.body, fontSize: 14, lineHeight: 22, color: colors.muted, marginTop: 4 },
  didCard: {
    padding: spacing.lg,
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.lg,
    borderLeftWidth: 3,
    borderLeftColor: colors.brandTertiary,
    marginBottom: spacing.xl,
  },
  didTag: { fontFamily: fonts.bodyBold, fontSize: 10, color: colors.brandPrimary, letterSpacing: 1.5 },
  didText: { fontFamily: fonts.body, fontSize: 15, lineHeight: 22, color: colors.onSurface, marginTop: spacing.sm, fontStyle: "italic" },
  triviaHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.md },
  addLink: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.brandPrimary },
  emptyTrivia: { fontFamily: fonts.body, fontSize: 13, color: colors.muted, paddingVertical: spacing.md },
  triviaCard: {
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    marginBottom: spacing.sm,
  },
  triviaTitle: { fontFamily: fonts.displayBold, fontSize: 16, color: colors.onSurface },
  triviaBody: { fontFamily: fonts.body, fontSize: 13, lineHeight: 20, color: colors.onSurface, marginTop: 4 },
  triviaAuthor: { fontFamily: fonts.body, fontSize: 11, color: colors.muted, marginTop: spacing.xs },
  player: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.surfaceSecondary,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
  },
  playerContent: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  playerTag: { fontFamily: fonts.bodyBold, fontSize: 10, color: colors.brandPrimary, letterSpacing: 1.5 },
  playerTitle: { fontFamily: fonts.displayBold, fontSize: 16, color: colors.onSurface, marginTop: 2 },
  playBtn: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
}));
