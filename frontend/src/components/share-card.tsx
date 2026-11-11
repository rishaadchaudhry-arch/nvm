import { useMutation, useQuery } from "@tanstack/react-query";
import Feather from "@react-native-vector-icons/feather";
import { Image } from "expo-image";
import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";
import { useState } from "react";
import { ActivityIndicator, Linking, Modal, Platform, Pressable, Text, View, useWindowDimensions } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

/** Preview of the share card for a street, with "another fact" and a share sheet (Instagram, WhatsApp…). */
export function ShareCardModal({ placeKey, placeTitle, visible, onClose }: { placeKey: string; placeTitle: string; visible: boolean; onClose: () => void }) {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { width, height } = useWindowDimensions();
  const [idx, setIdx] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const facts = useQuery({ queryKey: ["card-facts", placeKey], queryFn: () => api.cardFacts(placeKey), enabled: visible, staleTime: Infinity });
  const count = facts.data?.length ?? 0;
  const url = api.cardUrl(placeKey, idx);
  // Fit the preview to the screen: never wider than 360, never taller than ~half the screen.
  const cardW = Math.min(width - spacing.xl * 2, 360, (height * 0.5) / 1.25);

  const share = useMutation({
    mutationFn: async () => {
      setNote(null);
      if (Platform.OS === "web") {
        const opened = typeof window !== "undefined" ? window.open(url, "_blank") : null;
        if (!opened) await Linking.openURL(url);
        return opened ? "Opened in a new tab. Right-click or long-press the image to save it." : "If nothing opened, allow pop-ups for this site and try again.";
      }
      const safe = placeTitle.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "street";
      const f = new File(Paths.cache, `nvm-${safe}-${idx}.png`);
      if (f.exists) f.delete();
      await File.downloadFileAsync(url, f);
      if (!(await Sharing.isAvailableAsync())) return `Saved to ${f.uri}`;
      await Sharing.shareAsync(f.uri, { mimeType: "image/png", dialogTitle: `What was here: ${placeTitle}` });
      return null;
    },
    onSuccess: (n) => setNote(n),
  });

  const next = () => {
    if (!count) return;
    setLoaded(false);
    setIdx((i) => (i + 1) % count);
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={s.backdrop}>
        <View style={[s.sheet, { paddingBottom: insets.bottom + spacing.lg }]} testID="share-sheet">
          <View style={s.handle} />
          <View style={s.top}>
            <Text style={s.title}>Share this street</Text>
            <Pressable onPress={onClose} style={s.close} testID="share-close" accessibilityLabel="Close">
              <Feather name="x" size={20} color={colors.onSurface} />
            </Pressable>
          </View>

          <View style={[s.cardWrap, { width: cardW, height: cardW * 1.25 }]}>
            {facts.isError ? (
              <Text style={s.muted}>{(facts.error as Error).message}</Text>
            ) : (
              <Image
                source={{ uri: url }}
                style={{ width: cardW, height: cardW * 1.25, borderRadius: radius.md }}
                contentFit="cover"
                onLoadStart={() => setLoaded(false)}
                onLoad={() => setLoaded(true)}
                accessibilityLabel={`Share card for ${placeTitle}`}
                testID="share-card-image"
              />
            )}
            {!loaded && !facts.isError ? (
              <View style={s.loading}>
                <ActivityIndicator color={colors.brandPrimary} />
              </View>
            ) : null}
          </View>
          {count ? (
            <Text style={s.counter} testID="share-fact-counter">
              Fact {idx + 1} of {count}
            </Text>
          ) : null}

          <View style={s.actions}>
            <Pressable style={s.ghost} onPress={next} disabled={count < 2} testID="share-next-fact">
              <Feather name="shuffle" size={16} color={colors.brandPrimary} />
              <Text style={s.ghostText}>Another fact</Text>
            </Pressable>
            <Pressable style={s.primary} onPress={() => share.mutate()} disabled={share.isPending || facts.isError} testID="share-send">
              {share.isPending ? <ActivityIndicator color={colors.onBrandPrimary} /> : (
                <>
                  <Feather name="share-2" size={16} color={colors.onBrandPrimary} />
                  <Text style={s.primaryText}>Share</Text>
                </>
              )}
            </Pressable>
          </View>
          {note ? <Text style={s.muted} testID="share-note">{note}</Text> : null}
          {share.isError ? <Text style={s.error}>{(share.error as Error).message}</Text> : null}
          <Text style={s.hint}>
            {Platform.OS === "web" ? "Opens the image in a new tab so you can save it and post it anywhere." : "Opens your phone's share sheet, so you can post it to Instagram, WhatsApp or save it to Photos."}
          </Text>
        </View>
      </View>
    </Modal>
  );
}

const useStyles = makeStyles((colors) => ({
  backdrop: { flex: 1, justifyContent: "flex-end", backgroundColor: `${colors.surfaceInverse}99` },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, paddingHorizontal: spacing.xl, paddingTop: spacing.sm, alignItems: "center" },
  handle: { width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: spacing.md },
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", alignSelf: "stretch" },
  title: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.onSurface },
  close: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  cardWrap: { marginTop: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, overflow: "hidden", alignItems: "center", justifyContent: "center" },
  loading: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary },
  counter: { fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.muted, marginTop: spacing.sm },
  actions: { flexDirection: "row", gap: spacing.sm, alignSelf: "stretch", marginTop: spacing.lg },
  ghost: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, height: 52, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary },
  ghostText: { fontFamily: fonts.bodyBold, fontSize: 14, color: colors.brandPrimary },
  primary: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, height: 52, borderRadius: radius.pill, backgroundColor: colors.brandPrimary },
  primaryText: { fontFamily: fonts.bodyBold, fontSize: 15, color: colors.onBrandPrimary },
  muted: { fontFamily: fonts.body, fontSize: 13, color: colors.muted, marginTop: spacing.md, textAlign: "center" },
  error: { fontFamily: fonts.body, fontSize: 13, color: colors.error, marginTop: spacing.md, textAlign: "center" },
  hint: { fontFamily: fonts.body, fontSize: 12, lineHeight: 18, color: colors.muted, marginTop: spacing.md, textAlign: "center" },
}));
