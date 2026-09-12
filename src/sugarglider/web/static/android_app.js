// A packaged page has a separate, fixed origin; remote sharing retains its own.
export const ANDROID_APP_ORIGIN = "https://appassets.androidplatform.net";

export function isBundledAndroidApp({
  location = globalThis.location,
  bridge = globalThis.sugargliderNative,
} = {}) {
  return location?.origin === ANDROID_APP_ORIGIN && typeof bridge?.postMessage === "function";
}
