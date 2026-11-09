import { useMemo } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const light = {
  surface: "#F9F6F0",
  onSurface: "#1A2130",
  surfaceSecondary: "#FFFFFF",
  onSurfaceSecondary: "#1A2130",
  surfaceTertiary: "#EFE9DF",
  onSurfaceTertiary: "#1A2130",
  surfaceInverse: "#1A2130",
  onSurfaceInverse: "#F9F6F0",
  muted: "#5C667A",

  brand: "#C85A32",
  onBrand: "#FFFFFF",
  brandPrimary: "#C85A32",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#E37B40",
  onBrandSecondary: "#FFFFFF",
  brandTertiary: "#D4AF37",
  onBrandTertiary: "#1A2130",

  success: "#4F7942",
  onSuccess: "#FFFFFF",
  warning: "#E37B40",
  onWarning: "#FFFFFF",
  error: "#9E3B33",
  onError: "#FFFFFF",
  info: "#2C3E50",
  onInfo: "#FFFFFF",

  border: "#E5DED5",
  borderStrong: "#D1C7B9",
  divider: "#E5DED5",
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

export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors } = useTheme();
    return useMemo(() => StyleSheet.create(factory(colors)), [colors]);
  };
}

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, "2xl": 32, "3xl": 48 } as const;
export const radius = { sm: 0, md: 4, lg: 8, pill: 999 } as const;

export const fonts = {
  display: "CormorantGaramond_500Medium",
  displayBold: "CormorantGaramond_700Bold",
  body: "DMSans_400Regular",
  bodyMedium: "DMSans_500Medium",
  bodyBold: "DMSans_700Bold",
} as const;
