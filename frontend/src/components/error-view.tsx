import { Pressable, Text, View } from "react-native";

import { fonts, makeStyles, radius, spacing } from "@/src/theme";

export function ErrorView({ onBack, text = "We couldn't find this place." }: { onBack: () => void; text?: string }) {
  const styles = useStyles();
  return (
    <View style={styles.container}>
      <Text style={styles.title} testID="not-found">{text}</Text>
      <Pressable onPress={onBack} style={styles.btn} testID="not-found-back">
        <Text style={styles.btnText}>Go back</Text>
      </Pressable>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.lg, backgroundColor: colors.surface },
  title: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.onSurface, textAlign: "center" },
  btn: { minHeight: 48, justifyContent: "center", paddingHorizontal: spacing.xl, borderRadius: radius.pill, backgroundColor: colors.brandPrimary },
  btnText: { fontFamily: fonts.bodyBold, fontSize: 14, color: colors.onBrandPrimary },
}));
