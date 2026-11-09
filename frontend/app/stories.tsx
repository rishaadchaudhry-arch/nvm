import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import Feather from "@react-native-vector-icons/feather";
import { ActivityIndicator, FlatList, Pressable, RefreshControl, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { CommunityCard } from "@/src/components/tradition-cards";
import { fonts, makeStyles, spacing, useTheme } from "@/src/theme";

export default function Stories() {
  const s = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const pending = useQuery({ queryKey: ["stories", "pending"], queryFn: api.pendingStories });
  const cfg = useQuery({ queryKey: ["config"], queryFn: api.config, staleTime: Infinity });
  const threshold = cfg.data?.upvote_threshold ?? 5;

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))} style={s.iconBtn} testID="stories-back" accessibilityLabel="Back">
          <Feather name="arrow-left" size={20} color={colors.onSurface} />
        </Pressable>
      </View>
      <FlatList
        data={pending.data ?? []}
        keyExtractor={(t) => t.id}
        contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: insets.bottom + spacing.xl }}
        refreshControl={<RefreshControl refreshing={pending.isRefetching} onRefresh={() => pending.refetch()} tintColor={colors.brandPrimary} />}
        ListHeaderComponent={
          <View style={{ marginBottom: spacing.lg }}>
            <Text style={s.kicker}>COMMUNITY</Text>
            <Text style={s.title}>Stories waiting for votes</Text>
            <Text style={s.body}>
              Upvote the ones you know are true. At {threshold} upvotes a story becomes a &quot;Did you know?&quot; for anyone standing at that spot.
            </Text>
          </View>
        }
        ListEmptyComponent={
          pending.isLoading ? (
            <ActivityIndicator color={colors.brandPrimary} />
          ) : pending.isError ? (
            <Pressable onPress={() => pending.refetch()} testID="stories-error">
              <Text style={s.body}>Couldn&apos;t load stories. Tap to retry.</Text>
            </Pressable>
          ) : (
            <Text style={s.body} testID="stories-empty">
              No stories waiting right now. Point your camera at a street and add one.
            </Text>
          )
        }
        renderItem={({ item }) => <CommunityCard t={item} threshold={threshold} showPlace />}
        ListFooterComponent={
          <Pressable onPress={() => router.push("/admin")} style={s.admin} testID="admin-link">
            <Text style={s.adminText}>NVM team: review stories</Text>
          </Pressable>
        }
      />
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  iconBtn: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  kicker: { fontFamily: fonts.bodyBold, fontSize: 11, letterSpacing: 1.6, color: colors.brand, marginTop: spacing.sm },
  title: { fontFamily: fonts.displayBold, fontSize: 30, lineHeight: 38, color: colors.onSurface, marginTop: spacing.xs },
  body: { fontFamily: fonts.body, fontSize: 14, lineHeight: 21, color: colors.muted, marginTop: spacing.sm },
  admin: { minHeight: 44, justifyContent: "center", alignItems: "center", marginTop: spacing["2xl"] },
  adminText: { fontFamily: fonts.body, fontSize: 13, color: colors.muted },
}));
