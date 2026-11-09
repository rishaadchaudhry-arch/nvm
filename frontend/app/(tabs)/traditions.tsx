import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import Feather from "@react-native-vector-icons/feather";
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { CommunityCard, DidYouKnowCard } from "@/src/components/tradition-cards";
import { usesNativeTabs } from "@/src/navigation";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

const THRESHOLD = 5;

export default function Traditions() {
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;

  const pending = useQuery({ queryKey: ["traditions", "pending"], queryFn: () => api.traditions("pending") });
  const verified = useQuery({ queryKey: ["traditions", "verified"], queryFn: () => api.traditions("verified") });

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.lg }]}>
        <Text style={styles.title}>Oral traditions</Text>
        <Text style={styles.sub}>
          Local stories, legends and customs shared by people who know a place. Upvote the ones you know to be true: at {THRESHOLD} upvotes, or once the Yatra team checks them, they become &quot;Did you know?&quot; facts.
        </Text>
      </View>
      <ScrollView
        contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: bottomChrome + 96 }}
        refreshControl={<RefreshControl refreshing={pending.isRefetching} onRefresh={() => { pending.refetch(); verified.refetch(); }} tintColor={colors.brandPrimary} />}
      >
        <Text style={styles.section}>Waiting for upvotes</Text>
        {pending.isLoading ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : pending.isError ? (
          <Text style={styles.empty}>Couldn&apos;t load traditions. Pull to retry.</Text>
        ) : pending.data?.length ? (
          pending.data.map((t) => <CommunityCard key={t.id} t={t} threshold={THRESHOLD} place={(t.poi_slug ?? t.area_slug).replace(/-/g, " ").toUpperCase()} />)
        ) : (
          <Text style={styles.empty} testID="pending-empty">Nothing waiting right now. Be the first to share a story.</Text>
        )}

        <Text style={styles.section}>Did you know?</Text>
        {verified.data?.length ? (
          verified.data.map((t) => <DidYouKnowCard key={t.id} t={t} />)
        ) : (
          <Text style={styles.empty}>No verified traditions yet.</Text>
        )}
      </ScrollView>

      <Pressable
        style={[styles.fab, { bottom: bottomChrome + spacing.lg }]}
        onPress={() => router.push("/tradition/new")}
        testID="add-tradition-fab"
      >
        <Feather name="plus" size={18} color={colors.onBrandPrimary} />
        <Text style={styles.fabText}>Share a tradition</Text>
      </Pressable>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider },
  title: { fontFamily: fonts.displayBold, fontSize: 34, color: colors.onSurface },
  sub: { fontFamily: fonts.body, fontSize: 13, lineHeight: 20, color: colors.muted, marginTop: spacing.xs },
  section: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.onSurface, marginTop: spacing.xl, marginBottom: spacing.md },
  empty: { fontFamily: fonts.body, fontSize: 14, color: colors.muted, marginBottom: spacing.md },
  fab: {
    position: "absolute",
    right: spacing.xl,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    height: 52,
    paddingHorizontal: spacing.xl,
    borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
  },
  fabText: { fontFamily: fonts.bodyBold, fontSize: 14, color: colors.onBrandPrimary },
}));
