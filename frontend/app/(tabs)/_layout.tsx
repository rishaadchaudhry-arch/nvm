import { Tabs } from "expo-router";
import { NativeTabs } from "expo-router/unstable-native-tabs";
import Feather from "@react-native-vector-icons/feather";
import { Platform } from "react-native";

import { usesNativeTabs } from "@/src/navigation";
import { fonts, useTheme } from "@/src/theme";

export default function TabsLayout() {
  const { colors } = useTheme();

  if (usesNativeTabs) {
    return (
      <NativeTabs tintColor={colors.brandPrimary}>
        <NativeTabs.Trigger name="index">
          <NativeTabs.Trigger.Icon sf="map.fill" />
          <NativeTabs.Trigger.Label>Explore</NativeTabs.Trigger.Label>
        </NativeTabs.Trigger>
        <NativeTabs.Trigger name="camera">
          <NativeTabs.Trigger.Icon sf="camera.viewfinder" />
          <NativeTabs.Trigger.Label>Camera</NativeTabs.Trigger.Label>
        </NativeTabs.Trigger>
        <NativeTabs.Trigger name="traditions">
          <NativeTabs.Trigger.Icon sf="text.bubble.fill" />
          <NativeTabs.Trigger.Label>Traditions</NativeTabs.Trigger.Label>
        </NativeTabs.Trigger>
        <NativeTabs.Trigger name="journey">
          <NativeTabs.Trigger.Icon sf="bookmark.fill" />
          <NativeTabs.Trigger.Label>Journey</NativeTabs.Trigger.Label>
        </NativeTabs.Trigger>
      </NativeTabs>
    );
  }

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.onSurface,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surfaceSecondary,
          borderTopColor: colors.border,
          ...(Platform.OS === "web" ? { height: 64 } : {}),
        },
        tabBarItemStyle: { alignSelf: "center" },
        tabBarLabelStyle: { fontFamily: fonts.bodyMedium, fontSize: 11 },
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Explore", tabBarButtonTestID: "tab-explore", tabBarIcon: ({ color, size }) => <Feather name="map" size={size} color={color} /> }} />
      <Tabs.Screen name="camera" options={{ title: "Camera", tabBarButtonTestID: "tab-camera", tabBarIcon: ({ color, size }) => <Feather name="camera" size={size} color={color} /> }} />
      <Tabs.Screen name="traditions" options={{ title: "Traditions", tabBarButtonTestID: "tab-traditions", tabBarIcon: ({ color, size }) => <Feather name="message-square" size={size} color={color} /> }} />
      <Tabs.Screen name="journey" options={{ title: "Journey", tabBarButtonTestID: "tab-journey", tabBarIcon: ({ color, size }) => <Feather name="bookmark" size={size} color={color} /> }} />
    </Tabs>
  );
}
