import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import Feather from "@react-native-vector-icons/feather";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, Text, TextInput, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { adminToken, api, ApiError, type LocalAccount, type Tradition } from "@/src/api";
import { LocalAccountCard } from "@/src/components/local-account-card";
import { LocalAccountForm } from "@/src/components/local-account-form";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

type Mode = "stories" | "accounts";

export default function Admin() {
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loggingIn, setLoggingIn] = useState(false);
  const [mode, setMode] = useState<Mode>("stories");
  const [savedNote, setSavedNote] = useState<string | null>(null);

  useEffect(() => {
    adminToken.get().then((t) => setAuthed(!!t));
  }, []);

  const queue = useQuery({
    queryKey: ["admin-queue"],
    queryFn: api.adminQueue,
    enabled: !!authed,
    retry: false,
  });
  const accounts = useQuery({
    queryKey: ["admin-local-accounts"],
    queryFn: api.adminLocalAccounts,
    enabled: !!authed && mode === "accounts",
    retry: false,
  });

  // An expired session drops back to the sign-in form.
  const expired = (queue.error instanceof ApiError && queue.error.status === 401) || (accounts.error instanceof ApiError && accounts.error.status === 401);
  useEffect(() => {
    if (expired) adminToken.clear();
  }, [expired]);
  const signedIn = !!authed && !expired;

  const signIn = async () => {
    setLoggingIn(true);
    setLoginError(null);
    try {
      await api.login(email.trim(), password);
      setPassword("");
      await qc.resetQueries({ queryKey: ["admin-queue"] });
    await qc.resetQueries({ queryKey: ["admin-local-accounts"] });
      setAuthed(true);
    } catch {
      setLoginError("Incorrect email or password");
    } finally {
      setLoggingIn(false);
    }
  };

  const signOut = async () => {
    await adminToken.clear();
    qc.removeQueries({ queryKey: ["admin-queue"] });
    qc.removeQueries({ queryKey: ["admin-local-accounts"] });
    setAuthed(false);
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} testID="admin-back">
          <Feather name="arrow-left" size={20} color={colors.onSurface} />
        </Pressable>
        {signedIn ? (
          <Pressable onPress={signOut} style={styles.signOut} testID="admin-signout">
            <Text style={styles.signOutText}>Sign out</Text>
          </Pressable>
        ) : null}
      </View>
      <KeyboardAwareScrollView contentContainerStyle={{ padding: spacing.xl, paddingBottom: insets.bottom + spacing["2xl"] }} bottomOffset={spacing.xl} keyboardShouldPersistTaps="handled">
        <Text style={styles.tag}>NVM TEAM</Text>
        <Text style={styles.title}>{signedIn && mode === "accounts" ? "Local accounts" : "Review stories"}</Text>

        {signedIn ? (
          <View style={styles.segment} testID="admin-mode">
            {(["stories", "accounts"] as Mode[]).map((m) => (
              <Pressable key={m} onPress={() => setMode(m)} style={[styles.segmentBtn, mode === m && styles.segmentActive]} testID={`admin-mode-${m}`}>
                <Text style={[styles.segmentText, mode === m && styles.segmentTextActive]}>{m === "stories" ? "Stories" : "Local accounts"}</Text>
              </Pressable>
            ))}
          </View>
        ) : null}

        {authed === null ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : !signedIn ? (
          <View style={styles.form}>
            <Text style={styles.label}>Email</Text>
            <TextInput testID="admin-email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" autoComplete="email" style={styles.input} placeholder="you@example.com" placeholderTextColor={colors.muted} />
            <Text style={styles.label}>Password</Text>
            <TextInput testID="admin-password" value={password} onChangeText={setPassword} secureTextEntry style={styles.input} placeholder="Password" placeholderTextColor={colors.muted} onSubmitEditing={signIn} />
            {loginError ? <Text style={styles.error} testID="admin-login-error">{loginError}</Text> : null}
            <Pressable style={[styles.primary, (!email || !password) && { opacity: 0.5 }]} disabled={!email || !password || loggingIn} onPress={signIn} testID="admin-login-btn">
              {loggingIn ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.primaryText}>Sign in</Text>}
            </Pressable>
          </View>
        ) : mode === "accounts" ? (
          <>
            <Text style={styles.empty}>Record what locals remember about a street. It appears inside that street&apos;s timeline, marked as a local account.</Text>
            <LocalAccountForm
              onSaved={() => {
                setSavedNote("Saved. It now shows in the street's timeline.");
                setTimeout(() => setSavedNote(null), 4000);
              }}
            />
            {savedNote ? (
              <Text style={styles.saved} testID="la-saved">
                {savedNote}
              </Text>
            ) : null}
            <Text style={styles.subTitle}>Already collected</Text>
            {accounts.isLoading ? (
              <ActivityIndicator color={colors.brandPrimary} />
            ) : accounts.isError ? (
              <Pressable onPress={() => accounts.refetch()} testID="admin-accounts-retry">
                <Text style={styles.empty}>Couldn&apos;t load local accounts. Tap to retry.</Text>
              </Pressable>
            ) : accounts.data?.length ? (
              accounts.data.map((a) => <AccountRow key={a.id} a={a} />)
            ) : (
              <Text style={styles.empty} testID="admin-accounts-empty">No local accounts yet.</Text>
            )}
          </>
        ) : queue.isLoading ? (
          <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
        ) : queue.isError ? (
          <Pressable onPress={() => queue.refetch()} testID="admin-queue-retry">
            <Text style={styles.empty}>Couldn&apos;t load the queue. Tap to retry.</Text>
          </Pressable>
        ) : queue.data?.length ? (
          <>
            <Text style={styles.empty}>{queue.data.length} waiting. Verified stories appear as &quot;Did you know?&quot; facts.</Text>
            {queue.data.map((t) => <ReviewCard key={t.id} t={t} />)}
          </>
        ) : (
          <Text style={styles.empty} testID="admin-queue-empty">Nothing to review. All caught up.</Text>
        )}
      </KeyboardAwareScrollView>
    </View>
  );
}

function ReviewCard({ t }: { t: Tradition }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: (action: "verify" | "reject") => api.moderate(t.id, action),
    onSuccess: () => qc.invalidateQueries(),
  });
  return (
    <View style={styles.card} testID={`review-${t.id}`}>
      <Text style={styles.cardPlace}>{t.place_title.toUpperCase()} · {t.upvotes} {t.upvotes === 1 ? "UPVOTE" : "UPVOTES"}</Text>
      <Text style={styles.cardTitle}>{t.title}</Text>
      <Text style={styles.cardBody}>{t.body}</Text>
      <Text style={styles.cardAuthor}>Shared by {t.author}</Text>
      <View style={styles.actions}>
        <Pressable style={[styles.action, styles.reject]} onPress={() => m.mutate("reject")} disabled={m.isPending} testID={`reject-${t.id}`}>
          <Text style={[styles.actionText, { color: colors.error }]}>Reject</Text>
        </Pressable>
        <Pressable style={[styles.action, styles.verify]} onPress={() => m.mutate("verify")} disabled={m.isPending} testID={`verify-${t.id}`}>
          {m.isPending ? <ActivityIndicator color={colors.onSuccess} /> : <Text style={[styles.actionText, { color: colors.onSuccess }]}>Verify</Text>}
        </Pressable>
      </View>
      {m.isError ? <Text style={styles.error}>{(m.error as Error).message}</Text> : null}
    </View>
  );
}

function AccountRow({ a }: { a: LocalAccount }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const qc = useQueryClient();
  const del = useMutation({
    mutationFn: () => api.deleteLocalAccount(a.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-local-accounts"] });
      qc.invalidateQueries({ queryKey: ["local-accounts"] });
    },
  });
  return (
    <View style={{ marginBottom: spacing.md }}>
      <Text style={styles.cardPlace}>{a.era_label.toUpperCase()}</Text>
      <LocalAccountCard a={a} showPlace />
      <Pressable style={styles.remove} onPress={() => del.mutate()} disabled={del.isPending} testID={`delete-account-${a.id}`}>
        {del.isPending ? <ActivityIndicator size="small" color={colors.error} /> : <Text style={[styles.actionText, { color: colors.error }]}>Remove</Text>}
      </Pressable>
      {del.isError ? <Text style={styles.error}>{(del.error as Error).message}</Text> : null}
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.lg },
  iconBtn: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  signOut: { minHeight: 44, justifyContent: "center", paddingHorizontal: spacing.md },
  signOutText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.brandPrimary },
  tag: { fontFamily: fonts.bodyBold, fontSize: 11, color: colors.brandPrimary, letterSpacing: 1.4 },
  title: { fontFamily: fonts.displayBold, fontSize: 34, color: colors.onSurface, marginTop: spacing.xs, marginBottom: spacing.lg },
  form: { marginTop: spacing.sm },
  label: { fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.muted, marginTop: spacing.lg, marginBottom: spacing.xs },
  input: { borderBottomWidth: 1, borderBottomColor: colors.borderStrong, paddingVertical: spacing.sm, fontFamily: fonts.body, fontSize: 16, color: colors.onSurface },
  error: { fontFamily: fonts.body, fontSize: 13, color: colors.error, marginTop: spacing.md },
  primary: { height: 52, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", marginTop: spacing.xl },
  primaryText: { fontFamily: fonts.bodyBold, fontSize: 15, color: colors.onBrandPrimary },
  empty: { fontFamily: fonts.body, fontSize: 14, color: colors.muted, marginBottom: spacing.md },
  card: { padding: spacing.lg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary, marginBottom: spacing.md },
  cardPlace: { fontFamily: fonts.bodyBold, fontSize: 10, color: colors.muted, letterSpacing: 1.2 },
  cardTitle: { fontFamily: fonts.displayBold, fontSize: 19, color: colors.onSurface, marginTop: spacing.xs },
  cardBody: { fontFamily: fonts.body, fontSize: 14, lineHeight: 21, color: colors.onSurface, marginTop: spacing.xs },
  cardAuthor: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: spacing.sm },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  action: { flex: 1, height: 44, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  reject: { borderWidth: 1, borderColor: colors.error },
  verify: { backgroundColor: colors.success },
  actionText: { fontFamily: fonts.bodyBold, fontSize: 14 },
  remove: { alignSelf: "flex-start", height: 44, paddingHorizontal: spacing.lg, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.error, alignItems: "center", justifyContent: "center", marginTop: spacing.sm },
  segment: { flexDirection: "row", padding: 3, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, marginBottom: spacing.lg },
  segmentBtn: { flex: 1, height: 40, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  segmentActive: { backgroundColor: colors.brandPrimary },
  segmentText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.onSurface },
  segmentTextActive: { color: colors.onBrandPrimary },
  saved: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.success, marginTop: spacing.md },
  subTitle: { fontFamily: fonts.displayBold, fontSize: 20, color: colors.onSurface, marginTop: spacing["2xl"], marginBottom: spacing.md },
}));
