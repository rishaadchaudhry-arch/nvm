import { QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { useFonts } from "expo-font";
import { useEffect, useState } from "react";
import { LogBox, StyleSheet, View, ActivityIndicator } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { KeyboardProvider } from "react-native-keyboard-controller";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
// Preload icon font so Feather icons never show as "?" boxes on first launch in Expo Go Android.
// Keep this import; it is a build-time side effect registration.
import "@react-native-vector-icons/feather";

import { ErrorBoundary } from "@/src/components/error-boundary";
import { queryClient } from "@/src/query-client";
import { themes } from "@/src/theme";

LogBox.ignoreAllLogs(true);

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts({
    PlayfairDisplay_500Medium: require("../assets/fonts/PlayfairDisplay-Medium.ttf"),
    PlayfairDisplay_700Bold: require("../assets/fonts/PlayfairDisplay-Bold.ttf"),
    DMSans_400Regular: require("../assets/fonts/DMSans-Regular.ttf"),
    DMSans_500Medium: require("../assets/fonts/DMSans-Medium.ttf"),
    DMSans_700Bold: require("../assets/fonts/DMSans-Bold.ttf"),
  });
  // Never block the UI on font fetch; system font is a fine fallback while they stream in.
  const ready = fontsLoaded || !!fontError;

  // Second guard: show the app after 1.5s even if fonts haven't resolved yet.
  const [forceReady, setForceReady] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setForceReady(true), 1500);
    return () => clearTimeout(t);
  }, []);
  const showApp = ready || forceReady;

  return (
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <ErrorBoundary>
          <QueryClientProvider client={queryClient}>
            <KeyboardProvider>
              <StatusBar style="dark" />
              {showApp ? (
                <Stack
                  screenOptions={{
                    headerShown: false,
                    contentStyle: { backgroundColor: themes.light.surface },
                  }}
                />
              ) : (
                <View style={styles.loading}>
                  <ActivityIndicator color={themes.light.brandPrimary} />
                </View>
              )}
            </KeyboardProvider>
          </QueryClientProvider>
        </ErrorBoundary>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: themes.light.surface,
  },
});
