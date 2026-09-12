import { ANDROID_APP_ORIGIN, isBundledAndroidApp } from "../../src/sugarglider/web/static/android_app.js";
import { createPwaController } from "../../src/sugarglider/web/static/pwa_controller.js";

function assert(condition, message) { if (!condition) throw new Error(message); }
export async function runPr41AndroidShellHarness() {
  const scenarios = [], bridge = { postMessage() {} };
  assert(isBundledAndroidApp({ location: { origin: ANDROID_APP_ORIGIN }, bridge }), "fixed local origin with native bridge");
  for (const origin of ["http://appassets.androidplatform.net", "https://sharing.example", `${ANDROID_APP_ORIGIN}:8443`, "http://localhost:8000"]) {
    assert(!isBundledAndroidApp({ location: { origin }, bridge }), "a sharing or development page is separate");
  }
  assert(!isBundledAndroidApp({ location: { origin: ANDROID_APP_ORIGIN }, bridge: null }), "web alone is not the native app");
  scenarios.push("fixed_bundled_origin_and_native_transport");
  let registrations = 0, supported = null, status = null;
  const controller = createPwaController({ bundledShell: true, serviceWorkers: { register() { registrations++;throw Error("must not register"); } },
    onSupported: (value) => { supported = value; }, onStatus: (value) => { status = value; } });
  assert(await controller.register() === null && registrations === 0 && supported === false && status === "ready", "APK bytes do not depend on a service worker");
  assert(!await controller.checkForUpdate() && !controller.activateUpdate(), "app updates cannot be replaced by a web cache");
  scenarios.push("apk_shell_bypasses_independent_service_worker_cache");
  const browser = createPwaController({ bundledShell: false, secureContext: true,
    serviceWorkers: { register: async () => { registrations++;return { addEventListener() {} }; }, addEventListener() {} } });
  assert(await browser.register() && registrations === 1, "normal browser retains service worker behavior");
  scenarios.push("shared_browser_shell_behavior_preserved");
  return scenarios;
}
