import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import Feather from "@react-native-vector-icons/feather";
import { useState } from "react";
import { ActivityIndicator, Pressable, Text, TextInput, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { ErrorView } from "@/src/components/error-view";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

export default function NewStory() {
  const s = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { key } = useLocalSearchParams<{ key: string }>();
  const place = useQuery({ queryKey: ["place", key], queryFn: () => api.place(key), enabled: !!key, retry: false });
  const cfg = useQuery({ queryKey: ["config"], queryFn: api.config, staleTime: Infinity });

  const [author, setAuthor] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");

  const submit = useMutation({
    mutationFn: () => api.addStory({ place_key: key, author: author.trim(), title: title.trim(), body: body.trim() }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["stories"] }),
  });

  const back = () => (router.canGoBack() ? router.back() : router.replace("/"));
  if (!key || place.isError) return <ErrorView onBack={back} text="Pick a place first, from the camera or search." />;

  const valid = author.trim().length > 0 && title.trim().length > 0 && body.trim().length >= 10;

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={back} style={s.iconBtn} testID="story-back" accessibilityLabel="Back">
          <Feather name="x" size={20} color={colors.onSurface} />
        </Pressable>
      </View>

      {submit.isSuccess ? (
        <View style={[s.done, { paddingBottom: insets.bottom + spacing.xl }]} testID="story-submitted">
          <Feather name="check-circle" size={36} color={colors.success} />
          <Text style={s.title}>Thank you.</Text>
          <Text style={s.body}>
            Your story about {place.data?.title} is now open for votes. With {cfg.data?.upvote_threshold ?? 5} upvotes, or once the NVM team verifies it, it
            becomes a &quot;Did you know?&quot; for everyone who stands here.
          </Text>
          <Pressable style={s.primary} onPress={back} testID="story-done-btn">
            <Text style={s.primaryText}>Done</Text>
          </Pressable>
        </View>
      ) : (
        <KeyboardAwareScrollView
          bottomOffset={spacing.xl}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: insets.bottom + spacing["2xl"] }}
        >
          <Text style={s.kicker}>ADD A STORY</Text>
          <Text style={s.title}>{place.data?.title ?? " "}</Text>
          {place.data?.subtitle ? <Text style={s.sub}>{place.data.subtitle}</Text> : null}
          <Text style={s.body}>Oral traditions, what your grandparents remember, what this street used to be called, anything worth knowing.</Text>

          <Text style={s.label}>Your name</Text>
          <TextInput value={author} onChangeText={setAuthor} maxLength={40} style={s.input} placeholder="How you'd like to be credited" placeholderTextColor={colors.muted} testID="story-author" />
          <Text style={s.label}>Title</Text>
          <TextInput value={title} onChangeText={setTitle} maxLength={80} style={s.input} placeholder="e.g. The well that gave the lane its name" placeholderTextColor={colors.muted} testID="story-title" />
          <Text style={s.label}>The story</Text>
          <TextInput
            value={body}
            onChangeText={setBody}
            maxLength={800}
            multiline
            textAlignVertical="top"
            style={[s.input, s.multi]}
            placeholder="What happened here, and how do you know?"
            placeholderTextColor={colors.muted}
            testID="story-body"
          />
          <Text style={s.count}>{body.trim().length}/800 · at least 10 characters</Text>

          {submit.isError ? (
            <Text style={s.error} testID="story-error">
              {(submit.error as Error).message}
            </Text>
          ) : null}
          <Pressable style={[s.primary, !valid && s.disabled]} disabled={!valid || submit.isPending} onPress={() => submit.mutate()} testID="story-submit">
            {submit.isPending ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={s.primaryText}>Share story</Text>}
          </Pressable>
        </KeyboardAwareScrollView>
      )}
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  iconBtn: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  kicker: { fontFamily: fonts.bodyBold, fontSize: 11, letterSpacing: 1.6, color: colors.brand, marginTop: spacing.sm },
  title: { fontFamily: fonts.displayBold, fontSize: 30, lineHeight: 38, color: colors.onSurface, marginTop: spacing.xs },
  sub: { fontFamily: fonts.body, fontSize: 13, color: colors.muted, marginTop: 2 },
  body: { fontFamily: fonts.body, fontSize: 15, lineHeight: 23, color: colors.muted, marginTop: spacing.md },
  label: { fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.muted, marginTop: spacing.xl, marginBottom: spacing.xs },
  input: { borderBottomWidth: 1, borderBottomColor: colors.borderStrong, paddingVertical: spacing.sm, fontFamily: fonts.body, fontSize: 16, color: colors.onSurface },
  multi: { minHeight: 140, borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.xs },
  count: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: spacing.xs },
  error: { fontFamily: fonts.body, fontSize: 13, color: colors.error, marginTop: spacing.md },
  primary: { height: 52, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", marginTop: spacing.xl, alignSelf: "stretch" },
  disabled: { opacity: 0.5 },
  primaryText: { fontFamily: fonts.bodyBold, fontSize: 15, color: colors.onBrandPrimary },
  done: { flex: 1, paddingHorizontal: spacing.xl, justifyContent: "center", alignItems: "flex-start" },
}));
