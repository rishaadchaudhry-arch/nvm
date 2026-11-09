import { ScrollView, Pressable, Text } from "react-native";

import type { EraLabel } from "@/src/api";
import { fonts, makeStyles, radius, spacing } from "@/src/theme";

type Props = {
  eras: EraLabel[];
  selected: string;
  onSelect: (key: string) => void;
  dark?: boolean;
  testPrefix?: string;
};

export function EraChips({ eras, selected, onSelect, dark, testPrefix = "era-chip" }: Props) {
  const styles = useStyles();
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      style={styles.row}
      contentContainerStyle={styles.content}
    >
      {eras.map((e) => {
        const active = e.key === selected;
        return (
          <Pressable
            key={e.key}
            onPress={() => onSelect(e.key)}
            testID={`${testPrefix}-${e.key}`}
            style={[
              styles.chip,
              dark ? styles.chipDark : styles.chipLight,
              active && (dark ? styles.activeDark : styles.activeLight),
            ]}
          >
            <Text style={[styles.text, dark ? styles.textDark : styles.textLight, active && styles.textActive]}>
              {e.label}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const useStyles = makeStyles((colors) => ({
  row: { height: 56, flexGrow: 0 },
  content: { gap: spacing.sm, paddingHorizontal: spacing.xl, alignItems: "center" },
  chip: {
    height: 36,
    flexShrink: 0,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    justifyContent: "center",
  },
  chipLight: { backgroundColor: colors.surfaceSecondary, borderColor: colors.border },
  chipDark: { backgroundColor: "rgba(26,33,48,0.6)", borderColor: "rgba(249,246,240,0.25)" },
  activeLight: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  activeDark: { backgroundColor: "#C85A32", borderColor: "#C85A32" },
  text: { fontFamily: fonts.bodyMedium, fontSize: 13 },
  textLight: { color: colors.onSurface },
  textDark: { color: "#F9F6F0" },
  textActive: { color: "#F9F6F0" },
}));
