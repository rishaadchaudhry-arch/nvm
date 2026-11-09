import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams, useRouter } from "expo-router";
import Feather from "@react-native-vector-icons/feather";
import { useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { EraChips } from "@/src/components/era-chips";
import { DidYouKnowCard } from "@/src/components/tradition-cards";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";
import { ErrorView } from "@/src/components/error-view";

export default function AreaScreen() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const q = useQuery({ queryKey: ["area", slug], queryFn: () => api.area(slug!), enabled: !!slug });
  const [era, setEra] = useState<string | null>(null);

  if (q.isError) return <ErrorView onBack={() => router.back()} />;
  if (!q.data) return <View style={[styles.container, styles.center]}><ActivityIndicator color={colors.brandPrimary} /></View>;
  const { area, pois, did_you_know, eras } = q.data;
  const eraKey = era ?? eras[0]?.key;
  const areaEra = area.eras.find((e) => e.key === eraKey);

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ paddingBottom: insets.bottom + spacing["2xl"] }} stickyHeaderIndices={eras.length ? [1] : []}>
      <View style={styles.hero}>
        <Image source={{ uri: area.cover_image }} style={StyleSheet.absoluteFill} contentFit="cover" />
        <LinearGradient colors={["rgba(26,33,48,0.4)", "transparent", "rgba(26,33,48,0.95)"]} style={StyleSheet.absoluteFill} />
        <Pressable onPress={() => router.back()} style={[styles.back, { top: insets.top + spacing.sm }]} testID="area-back">
          <Feather name="arrow-left" size={20} color="#F9F6F0" />
        </Pressable>
        <View style={styles.heroText}>
          <Text style={styles.heroTitle} testID="area-name">{area.name}</Text>
          {area.summary ? <Text style={styles.heroSub}>{area.summary}</Text> : null}
        </View>
      </View>

      {eras.length ? (
        <View style={styles.chipBar}>
          <EraChips eras={eras} selected={eraKey!} onSelect={setEra} />
        </View>
      ) : <View />}

      <View style={styles.body}>
        {eras.length === 0 ? (
          <Text style={styles.text} testID="area-no-stories">
            No stories have been added for {area.name} yet. Know one? Share it as an oral tradition.
          </Text>
        ) : (
          <>
            {areaEra ? (
              <View style={styles.eraBlock} testID="area-era-block">
                <Text style={styles.eraTitle}>{areaEra.title}</Text>
                <Text style={styles.text}>{areaEra.description}</Text>
              </View>
            ) : null}

            <View style={styles.cameraNote}>
              <Feather name="camera" size={16} color={colors.brandPrimary} />
              <Text style={styles.cameraNoteText}>
                At {area.name}? Open the Camera tab and point your phone down the street to see these places in front of you.
              </Text>
            </View>

            <Text style={styles.section}>What was where</Text>
            {pois.map((p) => {
              const e = p.eras.find((x) => x.key === eraKey);
              return (
                <Pressable key={p.slug} style={styles.row} onPress={() => router.push(`/poi/${p.slug}`)} testID={`poi-row-${p.slug}`}>
                  <Image source={{ uri: p.image }} style={styles.rowImg} contentFit="cover" />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowCat}>{p.category.toUpperCase()}</Text>
                    <Text style={styles.rowTitle}>{p.name}</Text>
                    <Text style={[styles.rowEra, !e && styles.rowEraEmpty]} numberOfLines={2}>
                      {e ? e.title : "No record from this era yet"}
                    </Text>
                  </View>
                </Pressable>
              );
            })}
          </>
        )}

        {did_you_know.length ? (
          <>
            <Text style={styles.section}>Did you know?</Text>
            {did_you_know.map((t) => <DidYouKnowCard key={t.id} t={t} />)}
          </>
        ) : null}

        <Pressable
          style={styles.addBtn}
          onPress={() => router.push({ pathname: "/tradition/new", params: { area: area.slug } })}
          testID="area-add-tradition"
        >
          <Feather name="plus" size={16} color={colors.brandPrimary} />
          <Text style={styles.addText}>Share an oral tradition about {area.name}</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

const useStyles = makeStyles((colors) => ({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  hero: { height: 340, backgroundColor: colors.surfaceInverse },
  back: { position: "absolute", left: spacing.lg, width: 44, height: 44, borderRadius: 22, backgroundColor: "rgba(26,33,48,0.5)", alignItems: "center", justifyContent: "center" },
  heroText: { position: "absolute", left: spacing.xl, right: spacing.xl, bottom: spacing.xl },
  heroTitle: { fontFamily: fonts.displayBold, fontSize: 40, color: "#F9F6F0" },
  heroSub: { fontFamily: fonts.body, fontSize: 14, lineHeight: 20, color: "#F9F6F0", opacity: 0.9, marginTop: spacing.xs },
  chipBar: { backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider },
  body: { padding: spacing.xl },
  eraBlock: { marginBottom: spacing.lg },
  eraTitle: { fontFamily: fonts.displayBold, fontSize: 24, color: colors.onSurface, marginBottom: spacing.xs },
  text: { fontFamily: fonts.body, fontSize: 15, lineHeight: 24, color: colors.onSurface },
  cameraNote: { flexDirection: "row", gap: spacing.sm, padding: spacing.md, borderRadius: radius.lg, backgroundColor: colors.surfaceTertiary },
  cameraNoteText: { flex: 1, fontFamily: fonts.body, fontSize: 13, lineHeight: 19, color: colors.onSurface },
  section: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.onSurface, marginTop: spacing.xl, marginBottom: spacing.sm },
  row: { flexDirection: "row", gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider },
  rowImg: { width: 72, height: 72, borderRadius: radius.lg, backgroundColor: colors.surfaceTertiary },
  rowCat: { fontFamily: fonts.bodyBold, fontSize: 10, color: colors.muted, letterSpacing: 1 },
  rowTitle: { fontFamily: fonts.displayBold, fontSize: 18, color: colors.onSurface, marginTop: 2 },
  rowEra: { fontFamily: fonts.body, fontSize: 13, color: colors.brandPrimary, marginTop: 2 },
  rowEraEmpty: { color: colors.muted, fontStyle: "italic" },
  addBtn: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 48, marginTop: spacing.xl, paddingHorizontal: spacing.lg, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, alignSelf: "flex-start" },
  addText: { fontFamily: fonts.bodyBold, fontSize: 13, color: colors.brandPrimary, flexShrink: 1 },
}));
