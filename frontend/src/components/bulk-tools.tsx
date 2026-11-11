import { useMutation, useQueryClient } from "@tanstack/react-query";
import Feather from "@react-native-vector-icons/feather";
import * as DocumentPicker from "expo-document-picker";
import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";
import { useState } from "react";
import { ActivityIndicator, Linking, Platform, Pressable, Text, View } from "react-native";

import { api, type ImportResult } from "@/src/api";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

/** Admin-only: import many local accounts from a CSV, and download everything as a CSV backup. */
export function BulkTools() {
  const s = useStyles();
  const { colors } = useTheme();
  const qc = useQueryClient();
  const [result, setResult] = useState<ImportResult | null>(null);
  const [exportNote, setExportNote] = useState<string | null>(null);

  const importCsv = useMutation({
    mutationFn: async () => {
      const picked = await DocumentPicker.getDocumentAsync({ type: ["text/csv", "text/comma-separated-values", "application/vnd.ms-excel", "text/plain"], copyToCacheDirectory: true, multiple: false });
      if (picked.canceled || !picked.assets[0]) return null;
      const a = picked.assets[0];
      return api.importLocalAccounts({ uri: a.uri, name: a.name ?? "accounts.csv", mimeType: "text/csv" });
    },
    onSuccess: (r) => {
      if (!r) return;
      setResult(r);
      qc.invalidateQueries({ queryKey: ["admin-local-accounts"] });
      qc.invalidateQueries({ queryKey: ["local-accounts"] });
    },
  });

  const exportCsv = useMutation({
    mutationFn: async () => {
      setExportNote(null);
      if (Platform.OS === "web") {
        await Linking.openURL(await api.exportUrl());
        return "Your backup is downloading.";
      }
      const text = await api.exportCsv();
      const f = new File(Paths.cache, `nvm-backup-${new Date().toISOString().slice(0, 10)}.csv`);
      if (f.exists) f.delete();
      f.create();
      f.write(text);
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(f.uri, { mimeType: "text/csv", dialogTitle: "Save NVM backup" });
        return "Backup ready to save or share.";
      }
      return `Saved to ${f.uri}`;
    },
    onSuccess: (note) => setExportNote(note),
  });

  return (
    <View style={s.box} testID="bulk-tools">
      <Text style={s.heading}>Bulk import & backup</Text>
      <Text style={s.body}>Upload a CSV to add many local accounts at once (one row per account; the street can be a name like &quot;Nai Sarak Delhi&quot;). Photos aren&apos;t part of the CSV: after importing, use &quot;Add photo&quot; on each account below.</Text>

      <View style={s.row}>
        <Pressable style={s.primary} onPress={() => importCsv.mutate()} disabled={importCsv.isPending} testID="bulk-import-btn">
          {importCsv.isPending ? <ActivityIndicator color={colors.onBrandPrimary} /> : (
            <>
              <Feather name="upload" size={16} color={colors.onBrandPrimary} />
              <Text style={s.primaryText}>Import CSV</Text>
            </>
          )}
        </Pressable>
        <Pressable style={s.ghost} onPress={() => Linking.openURL(api.templateUrl())} testID="bulk-template-btn">
          <Feather name="file-text" size={16} color={colors.brandPrimary} />
          <Text style={s.ghostText}>Template</Text>
        </Pressable>
      </View>
      {importCsv.isPending ? <Text style={s.hint}>Looking up each street on the map. A long file can take a minute.</Text> : null}
      {importCsv.isError ? <Text style={s.error} testID="bulk-import-error">{(importCsv.error as Error).message}</Text> : null}
      {result ? (
        <View style={s.result} testID="bulk-import-result">
          <Text style={s.resultTitle}>
            {result.created} of {result.rows} {result.rows === 1 ? "row" : "rows"} added
          </Text>
          {result.failed.length ? (
            <>
              <Text style={s.resultSub}>Fix these rows and import them again:</Text>
              {result.failed.map((f) => (
                <Text key={f.row} style={s.failRow}>
                  Row {f.row}{f.street ? ` · ${f.street}` : ""}: {f.reason}
                </Text>
              ))}
            </>
          ) : null}
        </View>
      ) : null}

      <Pressable style={[s.ghost, { marginTop: spacing.lg, alignSelf: "flex-start" }]} onPress={() => exportCsv.mutate()} disabled={exportCsv.isPending} testID="bulk-export-btn">
        {exportCsv.isPending ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Feather name="download" size={16} color={colors.brandPrimary} />}
        <Text style={s.ghostText}>Download backup (all stories + local accounts)</Text>
      </Pressable>
      {exportNote ? <Text style={s.hint} testID="bulk-export-note">{exportNote}</Text> : null}
      {exportCsv.isError ? <Text style={s.error}>{(exportCsv.error as Error).message}</Text> : null}
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  box: { marginTop: spacing["2xl"], padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  heading: { fontFamily: fonts.displayBold, fontSize: 20, color: colors.onSurface },
  body: { fontFamily: fonts.body, fontSize: 13, lineHeight: 20, color: colors.muted, marginTop: spacing.xs },
  row: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg },
  primary: { flex: 1, flexDirection: "row", gap: spacing.sm, height: 48, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  primaryText: { fontFamily: fonts.bodyBold, fontSize: 14, color: colors.onBrandPrimary },
  ghost: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 48, paddingHorizontal: spacing.lg, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, justifyContent: "center" },
  ghostText: { fontFamily: fonts.bodyBold, fontSize: 14, color: colors.brandPrimary, flexShrink: 1 },
  hint: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: spacing.sm },
  error: { fontFamily: fonts.body, fontSize: 13, color: colors.error, marginTop: spacing.sm },
  result: { marginTop: spacing.md, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surface },
  resultTitle: { fontFamily: fonts.bodyBold, fontSize: 14, color: colors.onSurface },
  resultSub: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: spacing.xs },
  failRow: { fontFamily: fonts.body, fontSize: 12, lineHeight: 18, color: colors.error, marginTop: spacing.xs },
}));
