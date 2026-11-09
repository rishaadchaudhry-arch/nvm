import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import Feather from "@react-native-vector-icons/feather";
import { useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

const FOOTER_H = 76;

export default function NewTradition() {
  const params = useLocalSearchParams<{ area?: string; poi?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const qc = useQueryClient();

  const [areaSlug, setAreaSlug] = useState<string | null>(params.area ?? null);
  const [poiSlug, setPoiSlug] = useState<string | null>(params.poi ?? null);
  const [author, setAuthor] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [done, setDone] = useState(false);

  const regions = useQuery({ queryKey: ["regions"], queryFn: api.regions });
  const delhi = useQuery({ queryKey: ["region", "delhi"], queryFn: () => api.region("delhi") });
  const allAreas = useQuery({
    queryKey: ["all-areas", regions.data?.map((r) => r.slug).join(",")],
    queryFn: async () => (await Promise.all(regions.data!.map((r) => api.region(r.slug)))).flatMap((x) => x.areas),
    enabled: !!regions.data,
    placeholderData: delhi.data?.areas,
  });
  const area = useQuery({ queryKey: ["area", areaSlug], queryFn: () => api.area(areaSlug!), enabled: !!areaSlug });

  const submit = useMutation({
    mutationFn: () => api.addTradition({ area_slug: areaSlug!, poi_slug: poiSlug, author: author.trim(), title: title.trim(), body: body.trim() }),
    onSuccess: () => {
      qc.invalidateQueries();
      setDone(true);
    },
  });

  const canSubmit = !!areaSlug && author.trim().length > 0 && title.trim().length > 0 && body.trim().length >= 10;

  if (done) {
    return (
      <View style={[styles.container, styles.center, { padding: spacing.xl }]} testID="tradition-submitted">
        <Feather name="check-circle" size={36} color={colors.success} />
        <Text style={styles.title}>Thank you</Text>
        <Text style={styles.sub}>
          Your story is now in the community queue. Once enough people upvote it, or the Yatra team checks it, it becomes a &quot;Did you know?&quot; fact for everyone who visits.
        </Text>
        <Pressable style={styles.submit} onPress={() => router.back()} testID="tradition-done">
          <Text style={styles.submitText}>Done</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} testID="tradition-back">
          <Feather name="x" size={20} color={colors.onSurface} />
        </Pressable>
      </View>
      <KeyboardAwareScrollView
        contentContainerStyle={{ padding: spacing.xl, paddingBottom: FOOTER_H + insets.bottom + spacing.xl }}
        bottomOffset={FOOTER_H + spacing.lg}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.tag}>ORAL TRADITION</Text>
        <Text style={styles.title}>Share what you know</Text>
        <Text style={styles.sub}>A legend, a custom, a family memory or a little-known fact about a place. The community upvotes stories they recognise.</Text>

        <Text style={styles.label}>Place</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow} contentContainerStyle={styles.chipContent}>
          {(allAreas.data ?? []).map((a) => (
            <Pressable
              key={a.slug}
              onPress={() => { setAreaSlug(a.slug); setPoiSlug(null); }}
              style={[styles.chip, areaSlug === a.slug && styles.chipActive]}
              testID={`pick-area-${a.slug}`}
            >
              <Text style={[styles.chipText, areaSlug === a.slug && styles.chipTextActive]}>{a.name}</Text>
            </Pressable>
          ))}
        </ScrollView>

        {area.data?.pois.length ? (
          <>
            <Text style={styles.label}>Exact spot (optional)</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow} contentContainerStyle={styles.chipContent}>
              <Pressable onPress={() => setPoiSlug(null)} style={[styles.chip, !poiSlug && styles.chipActive]} testID="pick-poi-none">
                <Text style={[styles.chipText, !poiSlug && styles.chipTextActive]}>Whole area</Text>
              </Pressable>
              {area.data.pois.map((p) => (
                <Pressable key={p.slug} onPress={() => setPoiSlug(p.slug)} style={[styles.chip, poiSlug === p.slug && styles.chipActive]} testID={`pick-poi-${p.slug}`}>
                  <Text style={[styles.chipText, poiSlug === p.slug && styles.chipTextActive]}>{p.name}</Text>
                </Pressable>
              ))}
            </ScrollView>
          </>
        ) : null}

        <Text style={styles.label}>Your name</Text>
        <TextInput testID="tradition-author" value={author} onChangeText={setAuthor} placeholder="Priya from Sitaram Bazaar" placeholderTextColor={colors.muted} style={styles.input} maxLength={40} />
        <Text style={styles.label}>Headline</Text>
        <TextInput testID="tradition-title" value={title} onChangeText={setTitle} placeholder="The lamp that never goes out" placeholderTextColor={colors.muted} style={styles.input} maxLength={80} />
        <Text style={styles.label}>The story</Text>
        <TextInput testID="tradition-body" value={body} onChangeText={setBody} placeholder="My grandmother used to say…" placeholderTextColor={colors.muted} style={[styles.input, styles.textarea]} multiline maxLength={800} />
        <Text style={styles.counter}>{body.trim().length < 10 ? `At least 10 characters (${body.trim().length}/10)` : `${body.length}/800`}</Text>
        {submit.isError ? <Text style={styles.error} testID="tradition-error">{(submit.error as Error).message}</Text> : null}
      </KeyboardAwareScrollView>

      <KeyboardStickyView offset={{ opened: insets.bottom }}>
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Pressable
            style={[styles.submit, (!canSubmit || submit.isPending) && styles.submitDisabled]}
            onPress={() => canSubmit && submit.mutate()}
            disabled={!canSubmit || submit.isPending}
            testID="tradition-submit"
          >
            {submit.isPending ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.submitText}>Send to the community</Text>}
          </Pressable>
        </View>
      </KeyboardStickyView>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center", gap: spacing.md },
  header: { paddingHorizontal: spacing.lg },
  iconBtn: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  tag: { fontFamily: fonts.bodyBold, fontSize: 11, color: colors.brandPrimary, letterSpacing: 1.4 },
  title: { fontFamily: fonts.displayBold, fontSize: 34, color: colors.onSurface, marginTop: spacing.xs },
  sub: { fontFamily: fonts.body, fontSize: 14, lineHeight: 21, color: colors.muted, marginTop: spacing.sm, textAlign: "left" },
  label: { fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.muted, marginTop: spacing.xl, marginBottom: spacing.xs, letterSpacing: 0.5 },
  chipRow: { height: 56, flexGrow: 0, marginHorizontal: -spacing.xl },
  chipContent: { gap: spacing.sm, paddingHorizontal: spacing.xl, alignItems: "center" },
  chip: { height: 36, flexShrink: 0, justifyContent: "center", paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  chipActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  chipText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.onSurface },
  chipTextActive: { color: colors.onSurfaceInverse },
  input: { borderBottomWidth: 1, borderBottomColor: colors.borderStrong, paddingVertical: spacing.sm, fontFamily: fonts.body, fontSize: 16, color: colors.onSurface },
  textarea: { minHeight: 120, textAlignVertical: "top" },
  counter: { fontFamily: fonts.body, fontSize: 11, color: colors.muted, marginTop: spacing.xs },
  error: { fontFamily: fonts.body, fontSize: 13, color: colors.error, marginTop: spacing.md },
  footer: { paddingHorizontal: spacing.xl, paddingTop: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border },
  submit: { height: 52, alignSelf: "stretch", borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.xl },
  submitDisabled: { opacity: 0.5 },
  submitText: { fontFamily: fonts.bodyBold, fontSize: 15, color: colors.onBrandPrimary },
}));
