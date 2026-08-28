import { DEFAULT_AVATAR_KEY, normalizeAvatarKey } from "./avatar.js";
import { normalizeGeolocationPosition } from "./outing_tracking.js";

export const PLANNER_LOCATION_WATCH_OPTIONS = Object.freeze({
  enableHighAccuracy: true,
  maximumAge: 10_000,
  timeout: 30_000,
});

export const PLANNER_PERMISSION_QUERY_TIMEOUT_MS = 250;

const DEFAULT_ASSET = "/static/brand/gps-recenter-default.png";
const ACTIVE_ASSET = "/static/brand/gps-recenter-active.png";

export function createPlannerLocationController({
  geolocation = browserGeolocation(),
  permissions = browserPermissions(),
  windowTarget = browserWindow(),
  control = browserDocument()?.getElementById("planner-location-control"),
  status = browserDocument()?.getElementById("planner-location-status"),
  renderFix = () => {},
  clearFix = () => {},
  centerFix = () => {},
  avatarKey = () => DEFAULT_AVATAR_KEY,
  subscribeAvatar = () => () => {},
} = {}) {
  let initialized = false;
  let suspended = false;
  let lifecycleGeneration = 0;
  let activeWatch = null;
  let currentFix = null;
  let permissionState = "unknown";
  let acquiring = false;
  let followMode = false;
  let permissionStatus = null;
  let permissionChangeListener = null;
  let geolocationDenied = false;
  let unsubscribeAvatar = null;
  let lastAnnouncement = "";

  function supported() {
    return Boolean(
      geolocation
      && typeof geolocation.watchPosition === "function"
      && typeof geolocation.clearWatch === "function"
    );
  }

  async function initialize() {
    if (initialized) return;
    initialized = true;
    control?.addEventListener("click", activate);
    windowTarget?.addEventListener("pagehide", suspend);
    windowTarget?.addEventListener("pageshow", resume);
    unsubscribeAvatar = subscribeAvatar(() => renderCurrentFix());
    control?.classList.remove("hidden");
    renderControl();
    await evaluatePermission();
  }

  async function evaluatePermission() {
    const generation = lifecycleGeneration;
    detachPermissionStatus();
    if (!supported()) {
      permissionState = "unavailable";
      announce("Location is unavailable on this device.");
      renderControl();
      return;
    }
    if (!permissions || typeof permissions.query !== "function") {
      permissionState = "unknown";
      renderControl();
      return;
    }
    let queried;
    let timeoutId = null;
    try {
      queried = await Promise.race([
        permissions.query({ name: "geolocation" }),
        new Promise((resolve) => {
          timeoutId = globalThis.setTimeout(
            () => resolve(null),
            PLANNER_PERMISSION_QUERY_TIMEOUT_MS,
          );
        }),
      ]);
    } catch {
      if (generation !== lifecycleGeneration || suspended) return;
      permissionState = "unknown";
      renderControl();
      return;
    } finally {
      if (timeoutId !== null) globalThis.clearTimeout(timeoutId);
    }
    if (generation !== lifecycleGeneration || suspended) return;
    if (!queried) {
      permissionState = "unknown";
      renderControl();
      return;
    }
    permissionStatus = queried;
    permissionChangeListener = () => applyPermissionState(queried.state);
    queried.addEventListener?.("change", permissionChangeListener);
    applyPermissionState(queried.state);
  }

  function applyPermissionState(value) {
    if (suspended) return;
    permissionState = ["granted", "prompt", "denied"].includes(value)
      ? value
      : "unknown";
    if (permissionState === "granted") {
      geolocationDenied = false;
      startWatch();
    } else if (permissionState === "denied") {
      if (!activeWatch && !currentFix) {
        announce(
          "Location permission may be blocked. Use the GPS button to check.",
        );
      }
    } else {
      geolocationDenied = false;
    }
    renderControl();
  }

  function activate() {
    if (suspended) return;
    if (!supported() || permissionState === "unavailable") {
      announce("Location is unavailable on this device.");
      renderControl();
      return;
    }
    if (geolocationDenied) {
      announce(
        "Location permission is blocked. Enable it in browser or app settings.",
      );
      renderControl();
      return;
    }
    followMode = true;
    if (currentFix) centerFix(currentFix);
    if (!activeWatch) startWatch();
    if (!currentFix) {
      acquiring = true;
      announce("Locating your private position.");
    }
    renderControl();
  }

  function startWatch() {
    if (suspended || activeWatch || !supported()) return false;
    const watch = { generation: lifecycleGeneration, id: null };
    activeWatch = watch;
    acquiring = currentFix === null;
    if (acquiring) announce("Locating your private position.");
    renderControl();
    try {
      watch.id = geolocation.watchPosition(
        (position) => receivePosition(watch, position),
        (error) => receiveError(watch, error),
        PLANNER_LOCATION_WATCH_OPTIONS,
      );
      return true;
    } catch {
      if (activeWatch !== watch) return false;
      activeWatch = null;
      acquiring = false;
      permissionState = "unavailable";
      followMode = false;
      announce("Location is unavailable on this device.");
      renderControl();
      return false;
    }
  }

  function receivePosition(watch, position) {
    if (!ownsWatch(watch)) return;
    const normalized = normalizeGeolocationPosition(position);
    if (!normalized) return;
    const firstFix = currentFix === null;
    currentFix = Object.freeze({
      coordinate: Object.freeze({ ...normalized.coordinate }),
      accuracy_m: normalized.accuracy_m,
      captured_at: normalized.captured_at,
    });
    geolocationDenied = false;
    permissionState = "granted";
    acquiring = false;
    renderCurrentFix();
    if (followMode) centerFix(currentFix);
    if (firstFix) announce("Private location available.");
    renderControl();
  }

  function receiveError(watch, error) {
    if (!ownsWatch(watch)) return;
    if (error?.code === 1) {
      permissionState = "denied";
      geolocationDenied = true;
      stopWatch();
      dropCurrentFix();
      followMode = false;
      acquiring = false;
      announce(
        "Location permission is blocked. Enable it in browser or app settings.",
      );
    } else {
      acquiring = currentFix === null;
      announce("Location is temporarily unavailable.");
    }
    renderControl();
  }

  function manualMapInteraction() {
    if (!followMode) return;
    followMode = false;
    announce("Location remains visible; follow mode is off.");
    renderControl();
  }

  function mapReady() {
    renderCurrentFix();
  }

  function renderCurrentFix() {
    if (!currentFix || suspended) return;
    renderFix(currentFix, normalizeAvatarKey(avatarKey()));
  }

  function stopWatch() {
    const watch = activeWatch;
    activeWatch = null;
    if (watch && watch.id !== null && supported()) {
      geolocation.clearWatch(watch.id);
    }
  }

  function dropCurrentFix() {
    currentFix = null;
    clearFix();
  }

  function suspend() {
    if (suspended) return;
    suspended = true;
    lifecycleGeneration += 1;
    stopWatch();
    detachPermissionStatus();
    followMode = false;
    acquiring = false;
    dropCurrentFix();
    renderControl();
  }

  function resume() {
    if (!suspended) return;
    suspended = false;
    lifecycleGeneration += 1;
    void evaluatePermission();
  }

  function dispose() {
    suspend();
    control?.removeEventListener("click", activate);
    windowTarget?.removeEventListener("pagehide", suspend);
    windowTarget?.removeEventListener("pageshow", resume);
    unsubscribeAvatar?.();
    unsubscribeAvatar = null;
    control?.classList.add("hidden");
  }

  function detachPermissionStatus() {
    if (permissionStatus && permissionChangeListener) {
      permissionStatus.removeEventListener?.("change", permissionChangeListener);
    }
    permissionStatus = null;
    permissionChangeListener = null;
  }

  function ownsWatch(watch) {
    return activeWatch === watch
      && watch.generation === lifecycleGeneration
      && !suspended;
  }

  function announce(message) {
    if (message === lastAnnouncement) return;
    lastAnnouncement = message;
    if (status) status.textContent = message;
  }

  function renderControl() {
    if (!control) return;
    const active = Boolean(followMode && currentFix);
    const state = active
      ? "active"
      : acquiring
        ? "acquiring"
        : permissionState === "denied"
          ? "denied"
          : permissionState === "unavailable"
            ? "unavailable"
            : "default";
    const image = control.querySelector("img");
    if (image) image.src = active ? ACTIVE_ASSET : DEFAULT_ASSET;
    control.dataset.state = state;
    control.setAttribute("aria-pressed", String(active));
    control.setAttribute("aria-busy", String(state === "acquiring"));
    const label = active
      ? "Following my location"
      : currentFix
        ? "Center map on my location"
        : state === "denied"
          ? "Location permission blocked"
          : state === "unavailable"
            ? "Location unavailable"
            : "Show my location";
    control.setAttribute("aria-label", label);
    control.title = label;
  }

  function diagnostics() {
    return Object.freeze({
      permissionState,
      watchActive: activeWatch !== null,
      hasCurrentFix: currentFix !== null,
      currentFix,
      followMode,
      acquiring,
      suspended,
    });
  }

  return {
    initialize,
    activate,
    manualMapInteraction,
    mapReady,
    suspend,
    resume,
    dispose,
    diagnostics,
  };
}

function browserGeolocation() {
  return typeof navigator === "undefined" ? null : navigator.geolocation;
}

function browserPermissions() {
  return typeof navigator === "undefined" ? null : navigator.permissions;
}

function browserWindow() {
  return typeof window === "undefined" ? null : window;
}

function browserDocument() {
  return typeof document === "undefined" ? null : document;
}
