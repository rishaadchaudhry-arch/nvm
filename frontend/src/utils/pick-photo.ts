import * as ImagePicker from "expo-image-picker";
import { Platform } from "react-native";

import type { LocalFile } from "@/src/utils/upload";

export type PickPhotoResult = { file: LocalFile } | { denied: true; blocked: boolean } | { cancelled: true };

/** Ask for photo access only when the admin taps "Add a photo", then open the gallery. */
export async function pickPhoto(): Promise<PickPhotoResult> {
  if (Platform.OS !== "web") {
    let perm = await ImagePicker.getMediaLibraryPermissionsAsync();
    if (!perm.granted && perm.canAskAgain) perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return { denied: true, blocked: !perm.canAskAgain };
  }
  const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.7, allowsMultipleSelection: false });
  if (res.canceled || !res.assets[0]) return { cancelled: true };
  const a = res.assets[0];
  return { file: { uri: a.uri, name: a.fileName ?? "photo.jpg", mimeType: a.mimeType ?? "image/jpeg" } };
}
