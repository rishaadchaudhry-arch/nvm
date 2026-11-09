import { useMutation, useQueryClient } from "@tanstack/react-query";
import Feather from "@react-native-vector-icons/feather";
import { useState } from "react";
import { ActivityIndicator, Pressable, Text, View } from "react-native";

import { api, type Tradition } from "@/src/api";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

export function DidYouKnowCard({ t }: { t: Tradition }) {
  const styles = useStyles();
  return (
    <View style={styles.dyk} testID={`dyk-${t.id}`}>
      <Text style={styles.dykTag}>
        DID YOU KNOW? · {t.verified_by === "admin" ? "VERIFIED BY YATRA" : "VERIFIED BY COMMUNITY"}
      </Text>
      <Text style={styles.dykTitle}>{t.title}</Text>
      <Text style={styles.dykBody}>{t.body}</Text>
      <Text style={styles.author}>Shared by {t.author}</Text>
    </View>
  );
}

export function CommunityCard({ t, threshold, place }: { t: Tradition; threshold: number; place?: string }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const vote = useMutation({
    mutationFn: () => api.upvote(t.id),
    onSuccess: () => {
      setError(null);
      qc.invalidateQueries();
    },
    onError: (e: Error) => setError(e.message),
  });
  const voted = t.has_voted || vote.isSuccess;
  const count = vote.data?.upvotes ?? t.upvotes;

  return (
    <View style={styles.card} testID={`community-${t.id}`}>
      {place ? <Text style={styles.place}>{place}</Text> : null}
      <Text style={styles.title}>{t.title}</Text>
      <Text style={styles.body}>{t.body}</Text>
      <View style={styles.footer}>
        <Text style={styles.author}>Shared by {t.author}</Text>
        <Pressable
          onPress={() => !voted && vote.mutate()}
          disabled={voted || vote.isPending}
          style={[styles.vote, voted && styles.voteDone]}
          testID={`upvote-${t.id}`}
        >
          {vote.isPending ? (
            <ActivityIndicator size="small" color={colors.brandPrimary} />
          ) : (
            <Feather name="arrow-up" size={16} color={voted ? colors.onBrandPrimary : colors.brandPrimary} />
          )}
          <Text style={[styles.voteText, voted && styles.voteTextDone]}>
            {count}/{threshold}
          </Text>
        </Pressable>
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  dyk: {
    padding: spacing.lg,
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.lg,
    borderLeftWidth: 3,
    borderLeftColor: colors.brandTertiary,
    marginBottom: spacing.md,
  },
  dykTag: { fontFamily: fonts.bodyBold, fontSize: 10, color: colors.brandPrimary, letterSpacing: 1.2 },
  dykTitle: { fontFamily: fonts.displayBold, fontSize: 19, color: colors.onSurface, marginTop: spacing.sm },
  dykBody: { fontFamily: fonts.body, fontSize: 14, lineHeight: 22, color: colors.onSurface, marginTop: spacing.xs },
  card: {
    padding: spacing.lg,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    marginBottom: spacing.md,
  },
  place: { fontFamily: fonts.bodyBold, fontSize: 10, color: colors.muted, letterSpacing: 1.2, marginBottom: spacing.xs },
  title: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.onSurface },
  body: { fontFamily: fonts.body, fontSize: 14, lineHeight: 21, color: colors.onSurface, marginTop: spacing.xs },
  footer: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.md },
  author: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: spacing.sm },
  vote: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    minHeight: 44,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.brandPrimary,
  },
  voteDone: { backgroundColor: colors.brandPrimary },
  voteText: { fontFamily: fonts.bodyBold, fontSize: 13, color: colors.brandPrimary },
  voteTextDone: { color: colors.onBrandPrimary },
  error: { fontFamily: fonts.body, fontSize: 12, color: colors.error, marginTop: spacing.xs },
}));
