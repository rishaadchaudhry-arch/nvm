import Feather from "@react-native-vector-icons/feather";
import { Image } from "expo-image";
import { Text, View } from "react-native";

import { api, type LocalAccount } from "@/src/api";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

function formatDate(iso: string) {
  const d = new Date(`${iso}T00:00:00`);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

/** A first-hand account collected by the NVM team: a separate voice from the sourced history. */
export function LocalAccountCard({ a, showPlace }: { a: LocalAccount; showPlace?: boolean }) {
  const s = useStyles();
  const { colors } = useTheme();
  return (
    <View style={s.card} testID={`local-account-${a.id}`}>
      <View style={s.tagRow}>
        <Feather name="mic" size={12} color={colors.brand} />
        <Text style={s.tag}>LOCAL ACCOUNT</Text>
        {showPlace ? <Text style={s.tagPlace} numberOfLines={1}>· {a.place_title.toUpperCase()}</Text> : null}
      </View>
      {a.photo_url ? (
        <Image source={{ uri: api.audioUrl(a.photo_url) }} style={s.photo} contentFit="cover" transition={200} accessibilityLabel={`Photo shared with the account by ${a.told_by}`} testID={`local-account-photo-${a.id}`} />
      ) : null}
      <Text style={s.body}>“{a.body}”</Text>
      <Text style={s.who}>
        As told by <Text style={s.whoStrong}>{a.told_by}</Text>, {a.village}
      </Text>
      <Text style={s.meta}>Collected {formatDate(a.collected_on)} by the NVM team</Text>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  card: {
    marginTop: spacing.md,
    padding: spacing.lg,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderLeftWidth: 3,
    borderLeftColor: colors.brand,
  },
  tagRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  tag: { fontFamily: fonts.bodyBold, fontSize: 10, letterSpacing: 1.4, color: colors.brand },
  tagPlace: { fontFamily: fonts.bodyBold, fontSize: 10, letterSpacing: 1.2, color: colors.muted, flexShrink: 1 },
  photo: { width: "100%", aspectRatio: 4 / 3, borderRadius: radius.sm, marginTop: spacing.md, backgroundColor: colors.surfaceTertiary },
  body: { fontFamily: fonts.display, fontSize: 16, lineHeight: 25, color: colors.onSurfaceSecondary, marginTop: spacing.md },
  who: { fontFamily: fonts.body, fontSize: 13, color: colors.onSurfaceSecondary, marginTop: spacing.md },
  whoStrong: { fontFamily: fonts.bodyBold },
  meta: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: 2 },
}));
