import { t, tr, setLocalizedText } from "./i18n.js";
import { isBundledAndroidApp } from "./android_app.js";

const byId = (id) => document.getElementById(id);

export function bindPwaControls({
  retry,
  activateUpdate,
  clearData,
  saveSnapshot,
  removeSnapshot,
  rememberParticipant,
  forgetParticipant,
}) {
  byId("retry-connection")?.addEventListener("click", retry);
  byId("reload-pwa-update")?.addEventListener("click", activateUpdate);
  byId("clear-offline-data")?.addEventListener("click", clearData);
  byId("save-saved-route-offline")?.addEventListener(
    "click",
    () => saveSnapshot("saved_route"),
  );
  byId("remove-saved-route-offline")?.addEventListener(
    "click",
    () => removeSnapshot("saved_route"),
  );
  byId("save-outing-offline")?.addEventListener(
    "click",
    () => saveSnapshot("outing"),
  );
  byId("remove-outing-offline")?.addEventListener(
    "click",
    () => removeSnapshot("outing"),
  );
  byId("remember-outing-participant")?.addEventListener(
    "click",
    rememberParticipant,
  );
  byId("forget-outing-participant")?.addEventListener(
    "click",
    forgetParticipant,
  );
}

export function renderPwaStatus(state) {
  const panel = byId("pwa-status-panel");
  if (!panel) return;
  const offline = state.networkStatus === "offline";
  const snapshotOffline = Boolean(state.offlineSnapshotKind);
  const meaningful = state.pwaSupported
    || offline
    || snapshotOffline
    || state.pwaUpdateAvailable
    || !["idle", "ready"].includes(state.pwaStatus)
    || state.storagePersistenceStatus !== "unknown";
  const message = statusMessage(state);
  const healthy = !offline && !snapshotOffline && !state.pwaUpdateAvailable
    && ["idle", "ready"].includes(state.pwaStatus) && state.storagePersistenceStatus === "unknown";
  panel.classList.toggle("hidden", !meaningful || healthy);
  const summary = byId("app-status-summary");
  if (summary) setLocalizedText(summary, () => `${isBundledAndroidApp() ? t("On device") : offline ? t("Offline") : t("Online")} · ${message}`);
  setLocalizedText(byId("pwa-network-status"), () => isBundledAndroidApp() ? t("On device") : offline ? t("Offline") : t("Online"));
  byId("pwa-status-message").textContent = statusMessage(state);
  byId("retry-connection").classList.toggle("hidden", !offline);
  byId("reload-pwa-update").classList.toggle(
    "hidden",
    !state.pwaUpdateAvailable,
  );
}

export function renderOfflineCopyControls(state) {
  const savedRouteVisible = Boolean(
    state.savedRouteSnapshotDisplay
    && state.savedRouteSnapshot,
  );
  toggleOfflineButtons(
    "save-saved-route-offline",
    "remove-saved-route-offline",
    savedRouteVisible,
    state.offlineCopySaved,
    state.networkStatus === "offline",
  );
  const outingVisible = Boolean(
    state.outingDisplay
    && state.outingSnapshot,
  );
  toggleOfflineButtons(
    "save-outing-offline",
    "remove-outing-offline",
    outingVisible,
    state.offlineCopySaved,
    state.networkStatus === "offline",
  );
  byId("offline-map-status")?.classList.toggle(
    "hidden",
    !state.offlineSnapshotKind,
  );
}

export function renderRememberedParticipantControls(state) {
  const outing = state.outingSnapshot;
  const receipt = state.outingParticipantReceipt;
  const present = Boolean(
    outing
    && receipt?.slug === outing.slug
    && outing.participants?.some(
      (participant) => (
        participant.participant_id === receipt.participant_id
      ),
    ),
  );
  byId("outing-remember-actions")?.classList.toggle("hidden", !present);
  byId("remember-outing-participant")?.classList.toggle(
    "hidden",
    !present || state.participantRemembered,
  );
  byId("forget-outing-participant")?.classList.toggle(
    "hidden",
    !present || !state.participantRemembered,
  );
  byId("outing-outbox-status")?.classList.toggle(
    "hidden",
    !present || !state.durableOutboxPresent,
  );
}

function toggleOfflineButtons(saveId, removeId, visible, saved, offline) {
  byId(saveId)?.classList.toggle(
    "hidden",
    !visible || saved || offline,
  );
  byId(removeId)?.classList.toggle("hidden", !visible || !saved);
}

function statusMessage(state) {
  if (state.pwaStatus === "reloading_update") return t("Reloading update.");
  if (state.pwaStatus === "update_blocked") {
    return t("Stop foreground sharing and finish the current outing action before reloading the update.");
  }
  if (state.pwaUpdateAvailable) return t("Update available.");
  if (state.offlineSnapshotKind) return t("Showing saved offline copy.");
  if (state.pwaStatus === "storage_cleared") {
    return t("Saved offline data cleared.");
  }
  if (state.pwaStatus === "offline_copy_updated") {
    return t("Offline copy updated.");
  }
  if (state.pwaStatus === "offline_copy_removed") {
    return t("Offline copy removed.");
  }
  if (state.pwaStatus === "participant_remembered") {
    return t("Participant remembered on this device.");
  }
  if (state.pwaStatus === "participant_forgotten") {
    return t("Participant forgotten.");
  }
  if (state.storagePersistenceStatus === "evictable") {
    return t("Saved offline data is available, but the browser may evict it.");
  }
  if (state.storagePersistenceStatus === "unavailable") {
    return t("Offline storage unavailable.");
  }
  if (state.networkStatus === "offline") {
    return isBundledAndroidApp()
      ? t("You can use regions already installed on this device.")
      : t("Server features are unavailable. Retry when connectivity returns.");
  }
  if (isBundledAndroidApp()) return t("Maps and routes use installed regions.");
  return t("App ready for offline use.");
}
