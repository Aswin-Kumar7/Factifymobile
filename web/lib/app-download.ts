// Where the Android app is downloaded from, and what is said about the file. The
// app is not on the Play Store yet: the signed release APK is served from our own
// server. Each value is set at build time; one that is not set is simply not shown.

export const APK_URL = process.env.NEXT_PUBLIC_APK_URL || "/downloads/factify.apk";
export const APK_VERSION = process.env.NEXT_PUBLIC_APK_VERSION || "";
export const APK_SIZE = process.env.NEXT_PUBLIC_APK_SIZE || "";
export const APK_SHA256 = process.env.NEXT_PUBLIC_APK_SHA256 || "";
export const APK_MIN_ANDROID = process.env.NEXT_PUBLIC_APK_MIN_ANDROID || "";

/** "Version 1.0.0 · 24 MB · Android 8 or newer", with only what is known. */
export function apkFacts() {
  return [APK_VERSION && `Version ${APK_VERSION}`, APK_SIZE, APK_MIN_ANDROID ? `Android ${APK_MIN_ANDROID} or newer` : "For Android phones"].filter(Boolean).join(" · ");
}
