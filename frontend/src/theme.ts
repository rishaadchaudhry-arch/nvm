import { useMemo } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";
import type { ImageStyle, TextStyle, ViewStyle } from "react-native";

export type ColorScheme = "light" | "dark";

const light = {
  surface: "#FDFBF7",
  onSurface: "#2A241F",
  surfaceSecondary: "#F2EAE0",
  onSurfaceSecondary: "#2A241F",
  surfaceTertiary: "#E6DACB",
  onSurfaceTertiary: "#2A241F",
  surfaceInverse: "#2A241F",
  onSurfaceInverse: "#FDFBF7",
  muted: "#8C8177",

  brand: "#8E735B",
  onBrand: "#FDFBF7",
  brandPrimary: "#5A4634",
  onBrandPrimary: "#FDFBF7",
  brandSecondary: "#B49A82",
  onBrandSecondary: "#2A241F",
  brandTertiary: "#DCD0C3",
  onBrandTertiary: "#2A241F",

  success: "#4A6D52",
  onSuccess: "#FDFBF7",
  warning: "#9B7235",
  onWarning: "#FDFBF7",
  error: "#8B4545",
  onError: "#FDFBF7",
  info: "#5A6B7C",
  onInfo: "#FDFBF7",

  border: "#DCD0C3",
  borderStrong: "#A89B8F",
  divider: "#E6DACB",
};

export type ThemeColors = typeof light;

export const defaultScheme = "light" satisfies ColorScheme;
export const themes: { light: ThemeColors; dark?: ThemeColors } = { light };

export function setColorScheme(scheme: ColorScheme | null) {
  Appearance.setColorScheme?.(scheme ?? "unspecified");
}

setColorScheme?.(themes.dark ? null : defaultScheme);

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  const system = useColorScheme();
  const scheme: ColorScheme =
    (system === "light" || system === "dark") && themes[system] ? system : defaultScheme;
  return { scheme, colors: themes[scheme] ?? themes.light };
}

// React Native 0.88 dropped StyleSheet.NamedStyles from its types; this is the same shape.
type NamedStyles<T> = { [P in keyof T]: ViewStyle | TextStyle | ImageStyle };

export function makeStyles<T extends NamedStyles<T>>(factory: (colors: ThemeColors) => T): () => T {
  return function useStyles(): T {
    const { colors } = useTheme();
    return useMemo(() => StyleSheet.create(factory(colors)), [colors]);
  };
}

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, "2xl": 32, "3xl": 48 } as const;
export const radius = { sm: 6, md: 12, lg: 20, pill: 999 } as const;

export const fonts = {
  display: "PlayfairDisplay_500Medium",
  displayBold: "PlayfairDisplay_700Bold",
  body: "DMSans_400Regular",
  bodyMedium: "DMSans_500Medium",
  bodyBold: "DMSans_700Bold",
} as const;
