import { useQuery } from "@tanstack/react-query";
import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from "expo-audio";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import Feather from "@react-native-vector-icons/feather";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, SCOPE_LABEL, type Source } from "@/src/api";
import { ErrorView } from "@/src/components/error-view";
import { CommunityCard, DidYouKnowCard } from "@/src/components/tradition-cards";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

export default function PlaceHistory() {
  const s = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { key } = useLocalSearchParams<{ key: string }>();

  const place = useQuery({ queryKey: ["place", key], queryFn: () => api.place(key), enabled: !!key, retry: false });
  const history = useQuery({ queryKey: ["history", key], queryFn: () => api.history(key), enabled: place.isSuccess, staleTime: Infinity, retry: 1 });
  const verified = useQuery({ queryKey: ["stories", "place", key, "verified"], queryFn: () => api.storiesForPlace(key, "verified"), enabled: place.isSuccess });
  const pending = useQuery({ queryKey: ["stories", "place", key, "pending"], queryFn: () => api.storiesForPlace(key, "pending"), enabled: place.isSuccess });
  const cfg = useQuery({ queryKey: ["config"], queryFn: api.config, staleTime: Infinity });

  const [audio, setAudio] = useState<"idle" | "loading" | "playing" | "paused" | "error">("idle");
  const player = useRef<AudioPlayer | null>(null);
  useEffect(() => () => player.current?.remove(), []);

  const toggleAudio = async () => {
    const p = player.current;
    if (p && audio === "playing") {
      p.pause();
      setAudio("paused");
      return;
    }
    if (p && audio === "paused") {
      p.play();
      setAudio("playing");
      return;
    }
    setAudio("loading");
    try {
      await setAudioModeAsync({ playsInSilentMode: true });
      const { audio_url } = await api.narrate(key);
      player.current?.remove();
      const np = createAudioPlayer({ uri: api.audioUrl(audio_url) });
      player.current = np;
      np.addListener("playbackStatusUpdate", (st) => {
        if (st.didJustFinish) setAudio("idle");
        else if (st.playing) setAudio("playing");
      });
      np.play();
    } catch {
      setAudio("error");
    }
  };

  const back = () => (router.canGoBack() ? router.back() : router.replace("/"));

  if (place.isError) return <ErrorView onBack={back} text="We couldn't find this place." />;

  const h = history.data;
  const sourceById = new Map<number, Source>((h?.sources ?? []).map((src) => [src.id, src]));
  const threshold = cfg.data?.upvote_threshold ?? 5;

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={back} style={s.iconBtn} testID="place-back" accessibilityLabel="Back">
          <Feather name="arrow-left" size={20} color={colors.onSurface} />
        </Pressable>
        {h?.has_records ? (
          <Pressable onPress={toggleAudio} style={s.listen} testID="narrate-btn" disabled={audio === "loading"}>
            {audio === "loading" ? (
              <ActivityIndicator size="small" color={colors.onBrandPrimary} />
            ) : (
              <Feather name={audio === "playing" ? "pause" : "play"} size={16} color={colors.onBrandPrimary} />
            )}
            <Text style={s.listenText} testID="narrate-status">
              {audio === "playing" ? "Playing" : audio === "paused" ? "Paused" : audio === "error" ? "Retry audio" : audio === "loading" ? "Preparing" : "Listen"}
            </Text>
          </Pressable>
        ) : null}
      </View>

      <ScrollView contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: insets.bottom + spacing["2xl"] }}>
        <Text style={s.kicker}>WHAT WAS HERE</Text>
        <Text style={s.title} testID="place-title">
          {place.data?.title ?? " "}
        </Text>
        {place.data?.subtitle ? <Text style={s.subtitle}>{place.data.subtitle}</Text> : null}

        {history.isPending ? (
          <View style={s.loading} testID="history-loading">
            <ActivityIndicator color={colors.brandPrimary} />
            <Text style={s.muted}>Unearthing the history of this spot…</Text>
          </View>
        ) : history.isError ? (
          <Pressable onPress={() => history.refetch()} style={s.loading} testID="history-error">
            <Text style={s.body}>{(history.error as Error).message}</Text>
            <Text style={s.link}>Tap to try again</Text>
          </Pressable>
        ) : h && !h.has_records ? (
          <View style={s.emptyBox} testID="history-empty">
            <Text style={s.emptyTitle}>No recorded history for this exact spot yet.</Text>
            <Text style={s.body}>Open sources don&apos;t cover it yet. If you know what used to be here, be the first to add it.</Text>
          </View>
        ) : h ? (
          <>
            {h.summary ? <Text style={s.summary} testID="history-summary">{h.summary}</Text> : null}
            {h.then_now ? (
              <View style={s.thenNow} testID="then-now">
                <Text style={s.thenNowTag}>THEN → NOW</Text>
                <Text style={s.body}>{h.then_now}</Text>
              </View>
            ) : null}

            <Text style={s.section}>Through the centuries</Text>
            <View style={s.timeline}>
              {h.eras.map((e, i) => (
                <View key={e.key} style={s.node} testID={`timeline-${e.key}`}>
                  <View style={s.spineCol}>
                    <View style={[s.dot, !e.text && s.dotEmpty]} />
                    {i < h.eras.length - 1 ? <View style={s.spine} /> : null}
                  </View>
                  <View style={s.nodeBody}>
                    <Text style={s.eraLabel}>{e.label.toUpperCase()}</Text>
                    {e.text ? (
                      <>
                        <Text style={s.eraHeading}>{e.heading}</Text>
                        <Text style={s.body}>{e.text}</Text>
                        <View style={s.metaRow}>
                          <Text style={s.scope}>{SCOPE_LABEL[e.scope]}</Text>
                          {e.sources.map((id) => (
                            <Text key={id} style={s.srcRef}>
                              [{id}]
                            </Text>
                          ))}
                        </View>
                      </>
                    ) : (
                      <Text style={s.muted}>No records found for this period.</Text>
                    )}
                  </View>
                </View>
              ))}
            </View>

            {h.did_you_know.length ? (
              <>
                <Text style={s.section}>From the records</Text>
                {h.did_you_know.map((d, i) => (
                  <View key={i} style={s.fact} testID={`record-fact-${i}`}>
                    <Text style={s.body}>{d.text}</Text>
                    <Text style={s.srcRefInline}>{d.sources.map((id) => `[${id}]`).join(" ")}</Text>
                  </View>
                ))}
              </>
            ) : null}
          </>
        ) : null}

        <Text style={s.section}>Did you know?</Text>
        <Text style={s.sectionHint}>Local stories shared by people, verified by the community or the NVM team.</Text>
        {verified.data?.length ? verified.data.map((t) => <DidYouKnowCard key={t.id} t={t} />) : <Text style={s.muted}>No verified stories here yet.</Text>}

        {pending.data?.length ? (
          <>
            <Text style={s.subSection}>Waiting for votes · {threshold} upvotes makes it a fact</Text>
            {pending.data.map((t) => (
              <CommunityCard key={t.id} t={t} threshold={threshold} />
            ))}
          </>
        ) : null}

        <Pressable style={s.addBtn} onPress={() => router.push({ pathname: "/story/new", params: { key } })} testID="place-add-story-btn">
          <Feather name="edit-3" size={16} color={colors.onBrandPrimary} />
          <Text style={s.addText}>Add a story about this place</Text>
        </Pressable>

        {h?.sources.length ? (
          <>
            <Text style={s.section}>Sources</Text>
            {h.sources.map((src) => (
              <Pressable key={src.id} style={s.source} onPress={() => WebBrowser.openBrowserAsync(src.url)} testID={`source-${src.id}`}>
                <Text style={s.srcNum}>[{src.id}]</Text>
                <View style={{ flex: 1 }}>
                  <Text style={s.srcTitle}>{src.title}</Text>
                  <Text style={s.srcMeta}>
                    {src.type === "wikipedia" ? "Wikipedia" : src.type === "wikidata" ? "Wikidata" : "OpenStreetMap"} · {SCOPE_LABEL[src.scope] || "Map data"}
                  </Text>
                </View>
                <Feather name="external-link" size={14} color={colors.muted} />
              </Pressable>
            ))}
            {sourceById.size ? (
              <Text style={s.disclaimer}>
                Written by AI only from the sources above, and labelled by how close each fact is to this exact spot. Tap a source to check it.
              </Text>
            ) : null}
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, backgroundColor: colors.surface },
  iconBtn: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  listen: { flexDirection: "row", alignItems: "center", gap: spacing.xs, minHeight: 44, paddingHorizontal: spacing.lg, borderRadius: radius.pill, backgroundColor: colors.brandPrimary },
  listenText: { fontFamily: fonts.bodyBold, fontSize: 13, color: colors.onBrandPrimary },
  kicker: { fontFamily: fonts.bodyBold, fontSize: 11, letterSpacing: 1.6, color: colors.brand, marginTop: spacing.md },
  title: { fontFamily: fonts.displayBold, fontSize: 34, lineHeight: 42, color: colors.onSurface, marginTop: spacing.xs },
  subtitle: { fontFamily: fonts.body, fontSize: 14, color: colors.muted, marginTop: spacing.xs },
  summary: { fontFamily: fonts.display, fontSize: 18, lineHeight: 27, color: colors.onSurface, marginTop: spacing.xl },
  thenNow: { marginTop: spacing.lg, padding: spacing.lg, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary },
  thenNowTag: { fontFamily: fonts.bodyBold, fontSize: 10, letterSpacing: 1.4, color: colors.brand },
  section: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.onSurface, marginTop: spacing["2xl"], marginBottom: spacing.md },
  sectionHint: { fontFamily: fonts.body, fontSize: 13, color: colors.muted, marginTop: -spacing.sm, marginBottom: spacing.md },
  subSection: { fontFamily: fonts.bodyBold, fontSize: 12, color: colors.muted, marginTop: spacing.lg, marginBottom: spacing.sm },
  timeline: {},
  node: { flexDirection: "row", gap: spacing.md },
  spineCol: { width: 14, alignItems: "center" },
  dot: { width: 12, height: 12, borderRadius: 6, backgroundColor: colors.brandPrimary, marginTop: 3 },
  dotEmpty: { backgroundColor: colors.surface, borderWidth: 2, borderColor: colors.borderStrong },
  spine: { flex: 1, width: 2, backgroundColor: colors.border, marginTop: 2 },
  nodeBody: { flex: 1, paddingBottom: spacing.xl },
  eraLabel: { fontFamily: fonts.bodyBold, fontSize: 11, letterSpacing: 1.4, color: colors.brand },
  eraHeading: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.onSurface, marginTop: spacing.xs },
  body: { fontFamily: fonts.body, fontSize: 15, lineHeight: 23, color: colors.onSurface, marginTop: spacing.xs },
  muted: { fontFamily: fonts.body, fontSize: 14, color: colors.muted, marginTop: spacing.xs },
  link: { fontFamily: fonts.bodyBold, fontSize: 14, color: colors.brandPrimary, marginTop: spacing.sm },
  metaRow: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: spacing.xs, marginTop: spacing.sm },
  scope: { fontFamily: fonts.bodyMedium, fontSize: 11, color: colors.onSurfaceSecondary, backgroundColor: colors.surfaceSecondary, paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: radius.sm, overflow: "hidden" },
  srcRef: { fontFamily: fonts.bodyBold, fontSize: 11, color: colors.brand },
  srcRefInline: { fontFamily: fonts.bodyBold, fontSize: 11, color: colors.brand, marginTop: spacing.xs },
  fact: { paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider },
  loading: { flexDirection: "row", gap: spacing.md, alignItems: "center", marginTop: spacing.xl },
  emptyBox: { marginTop: spacing.xl, padding: spacing.lg, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary },
  emptyTitle: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.onSurface },
  addBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, height: 52, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, marginTop: spacing.lg },
  addText: { fontFamily: fonts.bodyBold, fontSize: 15, color: colors.onBrandPrimary },
  source: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 52, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  srcNum: { fontFamily: fonts.bodyBold, fontSize: 12, color: colors.brand, width: 28 },
  srcTitle: { fontFamily: fonts.bodyMedium, fontSize: 14, color: colors.onSurface },
  srcMeta: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: 2 },
  disclaimer: { fontFamily: fonts.body, fontSize: 12, lineHeight: 18, color: colors.muted, marginTop: spacing.lg },
}));
