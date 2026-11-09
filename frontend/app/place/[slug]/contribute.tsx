import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import Feather from "@react-native-vector-icons/feather";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

export default function Contribute() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const qc = useQueryClient();

  const place = useQuery({ queryKey: ["place", slug], queryFn: () => api.place(slug!), enabled: !!slug });

  const [author, setAuthor] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = useMutation({
    mutationFn: () =>
      api.addTrivia(slug!, {
        author: author.trim(),
        title: title.trim(),
        body: body.trim(),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trivia", slug] });
      router.back();
    },
    onError: () => setError("Could not submit. Please try again."),
  });

  const canSubmit = author.trim() && title.trim() && body.trim().length >= 10 && place.data;

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} testID="contribute-back">
          <Feather name="arrow-left" size={20} color={colors.onSurface} />
        </Pressable>
      </View>
      <ScrollView
        contentContainerStyle={{ padding: spacing.xl, paddingBottom: insets.bottom + 120 }}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.tag}>SHARE A TRADITION</Text>
        <Text style={styles.title}>Did you know?</Text>
        <Text style={styles.sub}>
          Add a local legend, a tradition or a lesser-known story about {place.data?.name ?? "this place"}.
        </Text>

        <Field label="Your name">
          <TextInput
            testID="author-input"
            value={author}
            onChangeText={setAuthor}
            placeholder="Priya"
            placeholderTextColor={colors.muted}
            style={styles.input}
            maxLength={40}
          />
        </Field>
        <Field label="Headline">
          <TextInput
            testID="title-input"
            value={title}
            onChangeText={setTitle}
            placeholder="The lamp that never goes out"
            placeholderTextColor={colors.muted}
            style={styles.input}
            maxLength={80}
          />
        </Field>
        <Field label="Your story">
          <TextInput
            testID="body-input"
            value={body}
            onChangeText={setBody}
            placeholder="Locals believe that..."
            placeholderTextColor={colors.muted}
            style={[styles.input, styles.textarea]}
            multiline
            maxLength={600}
          />
        </Field>

        {error ? <Text style={styles.error}>{error}</Text> : null}
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.sm }]}>
        <Pressable
          style={[styles.submit, !canSubmit && styles.submitDisabled]}
          onPress={() => canSubmit && submit.mutate()}
          disabled={!canSubmit || submit.isPending}
          testID="submit-trivia"
        >
          {submit.isPending ? (
            <ActivityIndicator color={colors.onBrandPrimary} />
          ) : (
            <Text style={styles.submitText}>Publish</Text>
          )}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  const styles = useStyles();
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      {children}
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  iconBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  tag: { fontFamily: fonts.bodyBold, fontSize: 11, color: colors.brandPrimary, letterSpacing: 1.5 },
  title: { fontFamily: fonts.displayBold, fontSize: 36, color: colors.onSurface, marginTop: spacing.xs },
  sub: { fontFamily: fonts.body, fontSize: 14, color: colors.muted, marginTop: spacing.sm, marginBottom: spacing.xl, lineHeight: 20 },
  field: { marginBottom: spacing.lg },
  label: { fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.muted, marginBottom: spacing.xs, letterSpacing: 0.5 },
  input: {
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    paddingVertical: spacing.sm,
    fontFamily: fonts.body,
    fontSize: 16,
    color: colors.onSurface,
  },
  textarea: { minHeight: 120, textAlignVertical: "top" },
  error: { fontFamily: fonts.body, fontSize: 13, color: colors.error, marginTop: spacing.md },
  footer: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    padding: spacing.xl,
    paddingTop: spacing.md,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  submit: {
    height: 52,
    borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  submitDisabled: { opacity: 0.5 },
  submitText: { fontFamily: fonts.bodyBold, fontSize: 15, color: colors.onBrandPrimary, letterSpacing: 0.5 },
}));
