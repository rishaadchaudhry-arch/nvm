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
        DID YOU KNOW? · {t.verified_by === "admin" ? "VERIFIED BY NVM" : "VERIFIED BY COMMUNITY"}
      </Text>
      <Text style={[styles.title, styles.dykText]}>{t.title}</Text>
      <Text style={[styles.body, styles.dykText]}>{t.body}</Text>
      <Text style={[styles.author, styles.dykAuthor]}>Shared by {t.author}</Text>
    </View>
  );
}

export function CommunityCard({ t, threshold, showPlace }: { t: Tradition; threshold: number; showPlace?: boolean }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const vote = useMutation({
    mutationFn: () => api.upvote(t.id),
    onSuccess: () => {
      setError(null);
      qc.invalidateQueries({ queryKey: ["stories"] });
    },
    onError: (e: Error) => setError(e.message),
  });
  const voted = t.has_voted || vote.isSuccess;
  const count = vote.data?.upvotes ?? t.upvotes;

  return (
    <View style={styles.card} testID={`community-${t.id}`}>
      {showPlace ? <Text style={styles.place}>{t.place_title.toUpperCase()}</Text> : null}
      <Text style={styles.title}>{t.title}</Text>
      <Text style={styles.body}>{t.body}</Text>
      <View style={styles.footer}>
        <Text style={styles.author}>Shared by {t.author}</Text>
        <Pressable
          onPress={() => !voted && vote.mutate()}
          disabled={voted || vote.isPending}
          style={[styles.vote, voted && styles.voteDone]}
          testID={`upvote-${t.id}`}
          accessibilityLabel={voted ? "Upvoted" : "Upvote this story"}
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
  dyk: { padding: spacing.lg, borderRadius: radius.md, backgroundColor: colors.surfaceInverse, marginBottom: spacing.md },
  dykTag: { fontFamily: fonts.bodyBold, fontSize: 10, letterSpacing: 1.4, color: colors.brandSecondary, marginBottom: spacing.xs },
  dykText: { color: colors.onSurfaceInverse },
  dykAuthor: { color: colors.brandTertiary },
  card: { padding: spacing.lg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, marginBottom: spacing.md },
  place: { fontFamily: fonts.bodyBold, fontSize: 10, letterSpacing: 1.2, color: colors.muted, marginBottom: spacing.xs },
  title: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.onSurface },
  body: { fontFamily: fonts.body, fontSize: 14, lineHeight: 21, color: colors.onSurface, marginTop: spacing.xs },
  author: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: spacing.sm, flexShrink: 1 },
  footer: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  vote: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    minHeight: 44,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.brandPrimary,
    marginTop: spacing.sm,
  },
  voteDone: { backgroundColor: colors.brandPrimary },
  voteText: { fontFamily: fonts.bodyBold, fontSize: 13, color: colors.brandPrimary },
  voteTextDone: { color: colors.onBrandPrimary },
  error: { fontFamily: fonts.body, fontSize: 12, color: colors.error, marginTop: spacing.xs },
}));
