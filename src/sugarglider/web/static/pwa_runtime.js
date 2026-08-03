import {
  createOfflineSnapshotRepository,
} from "./offline_snapshots.js";
import {
  createDurableOutboxBridge,
  createParticipantSessionRepository,
  createPositionOutboxRepository,
} from "./outing_durable_session.js";
import { createPwaController } from "./pwa_controller.js";
import { createMemoryPwaStore, openPwaStore } from "./pwa_store.js";
import {
  bindPwaControls,
  renderOfflineCopyControls,
  renderPwaStatus,
  renderRememberedParticipantControls,
} from "./pwa_view.js";
import { state } from "./state.js";

let runtimePromise = null;
let renderApplication = () => {};
let retryConnection = async () => {};
let rememberParticipantAction = async () => {};
let forgetParticipantAction = async () => {};
let mutationPending = () => false;
let ownsDurablePresence = () => true;
let controlsBound = false;

export function initializePwaRuntime({
  render = () => {},
  retry = async () => {},
  rememberParticipant = async () => {},
  forgetParticipant = async () => {},
  isMutationPending = () => false,
  ownsOutboxPresence = () => true,
} = {}) {
  renderApplication = render;
  retryConnection = retry;
  rememberParticipantAction = rememberParticipant;
  forgetParticipantAction = forgetParticipant;
  mutationPending = isMutationPending;
  ownsDurablePresence = ownsOutboxPresence;
  if (!runtimePromise) runtimePromise = createRuntime();
  bindControlsOnce();
  bindNetworkHintsOnce();
  return runtimePromise;
}

export async function pwaRuntime() {
  if (!runtimePromise) runtimePromise = createRuntime();
  return runtimePromise;
}

export async function saveCurrentOfflineSnapshot(kind) {
  const runtime = await pwaRuntime();
  if (!runtime.snapshots.durable) {
    state.storagePersistenceStatus = "unavailable";
    state.pwaStatus = "storage_unavailable";
    renderPwaState();
    return null;
  }
  const payload = kind === "saved_route"
    ? state.savedRouteSnapshot
    : state.outingSnapshot;
  if (!payload || state.networkStatus === "offline") return null;
  const record = await runtime.snapshots.save(kind, payload);
  state.offlineCopySaved = true;
  state.pwaStatus = "offline_copy_updated";
  state.storagePersistenceStatus = (
    await runtime.controller.requestPersistentStorage()
  );
  renderPwaState();
  return record;
}

export async function removeCurrentOfflineSnapshot(kind) {
  const runtime = await pwaRuntime();
  const slug = kind === "saved_route"
    ? state.savedRouteSnapshot?.slug
    : state.outingSnapshot?.slug;
  if (!slug) return;
  await runtime.snapshots.remove(kind, slug);
  state.offlineCopySaved = false;
  state.pwaStatus = "offline_copy_removed";
  renderPwaState();
}

export async function loadOfflineSnapshot(kind, slug) {
  const runtime = await pwaRuntime();
  return runtime.snapshots.read(kind, slug);
}

export async function refreshOfflineSnapshot(kind, payload) {
  const runtime = await pwaRuntime();
  return runtime.snapshots.refreshExisting(kind, payload);
}

export async function removeOfflineSnapshot(kind, slug) {
  const runtime = await pwaRuntime();
  await runtime.snapshots.remove(kind, slug);
}

export async function storePublicConfig(config) {
  const runtime = await pwaRuntime();
  return runtime.snapshots.savePublicConfig(config);
}

export async function restorePublicConfig() {
  const runtime = await pwaRuntime();
  return runtime.snapshots.readPublicConfig();
}

export async function restoreRememberedParticipant(
  outing,
  { isCurrent = () => true } = {},
) {
  const runtime = await pwaRuntime();
  if (!isCurrent()) return null;
  const session = await runtime.sessions.restore(outing.slug, outing);
  if (!isCurrent()) return null;
  if (!session) return null;
  const outbox = await runtime.outbox.read(session);
  if (!isCurrent()) return null;
  return {
    receipt: {
      slug: session.outing_slug,
      participant_id: session.participant_id,
      participant_token: session.participant_token,
    },
    session,
    outbox,
  };
}

export async function rememberParticipant(receipt, expiresAt) {
  const runtime = await pwaRuntime();
  if (!runtime.sessions.durable) {
    state.storagePersistenceStatus = "unavailable";
    renderPwaState();
    throw new Error("Durable participant storage is unavailable.");
  }
  const session = await runtime.sessions.remember(receipt, expiresAt);
  state.participantRemembered = true;
  state.pwaStatus = "participant_remembered";
  state.storagePersistenceStatus = (
    await runtime.controller.requestPersistentStorage()
  );
  renderPwaState();
  return session;
}

export async function forgetParticipant(slug, { updateState = true } = {}) {
  const runtime = await pwaRuntime();
  runtime.durableBridge.invalidate();
  await runtime.sessions.forget(slug);
  if (!updateState) return;
  state.participantRemembered = false;
  state.durableOutboxPresent = false;
  state.pwaStatus = "participant_forgotten";
  renderPwaState();
}

export async function forgetParticipantIdentity(slug, participantId) {
  const runtime = await pwaRuntime();
  runtime.durableBridge.invalidate();
  return runtime.sessions.forgetMatching(slug, participantId);
}

export async function readRememberedOutbox(receipt) {
  const runtime = await pwaRuntime();
  const session = await runtime.sessions.restore(receipt?.slug);
  if (
    !session
    || session.participant_id !== receipt?.participant_id
    || session.participant_token !== receipt?.participant_token
  ) return null;
  return runtime.outbox.read(session);
}

export function applyOfflineCopyRefresh(record) {
  state.offlineCopySaved = Boolean(record);
  renderPwaState();
}

export function reportOptionalStorageFailure() {
  state.storagePersistenceStatus = "unavailable";
  state.pwaStatus = "storage_unavailable";
  renderPwaState();
}

export async function createPwaStorageRuntime({
  openStore = openPwaStore,
  onPresence = () => {},
} = {}) {
  let store = null;
  try {
    store = await openStore();
    const repositories = await initializePwaRepositories(
      store,
      onPresence,
    );
    return {
      ...repositories,
      storageUnavailable: !store.durable,
    };
  } catch {
    try {
      store?.close();
    } catch {
      // A failed durable connection is already unusable.
    }
    const memoryStore = createMemoryPwaStore();
    const repositories = await initializePwaRepositories(
      memoryStore,
      onPresence,
    );
    return {
      ...repositories,
      storageUnavailable: true,
    };
  }
}

export async function clearSavedOfflineData() {
  const runtime = await pwaRuntime();
  runtime.durableBridge.invalidate();
  await runtime.store.clearApplicationData();
  state.offlineCopySaved = false;
  state.participantRemembered = false;
  state.durableOutboxPresent = false;
  state.pwaStatus = "storage_cleared";
  renderPwaState();
}

export async function durableOutboxBridge() {
  return (await pwaRuntime()).durableBridge;
}

export const durableSampleAdapter = Object.freeze({
  prepare: async (...arguments_) => (
    (await durableOutboxBridge()).prepare(...arguments_)
  ),
  prepareRestored: async (...arguments_) => (
    (await durableOutboxBridge()).prepareRestored(...arguments_)
  ),
  published: async (...arguments_) => (
    (await durableOutboxBridge()).published(...arguments_)
  ),
  discard: async (...arguments_) => (
    (await durableOutboxBridge()).discard(...arguments_)
  ),
  stop: async (...arguments_) => (
    (await durableOutboxBridge()).stop(...arguments_)
  ),
  invalidate: async () => (await durableOutboxBridge()).invalidate(),
});

export function setPwaNetworkStatus(status) {
  state.networkStatus = status;
  renderPwaState();
}

export function markOfflineSnapshot(kind, slug) {
  state.networkStatus = "offline";
  state.offlineSnapshotKind = kind;
  state.offlineSnapshotSlug = slug;
  state.offlineCopySaved = true;
  state.pwaStatus = "offline";
  renderPwaState();
}

export function clearOfflineSnapshotStatus() {
  state.networkStatus = "online";
  state.offlineSnapshotKind = null;
  state.offlineSnapshotSlug = null;
  state.pwaStatus = "ready";
  renderPwaState();
}

export function offlineMapConfig(config, payload) {
  const geometry = firstGeometry(payload);
  const initialCenter = geometry?.[0] ?? config?.initial_center ?? [0, 0];
  return {
    tile_url_template: config?.tile_url_template ?? "about:blank",
    tile_attribution: config?.tile_attribution ?? "",
    initial_center: initialCenter,
    initial_zoom: config?.initial_zoom ?? 11,
    max_required_points: config?.max_required_points ?? 30,
    nature_index_available: false,
    nature_water_buffer_m: config?.nature_water_buffer_m ?? 100,
    nature_preference_values: ["off", "prefer"],
    loop_geometry_preference_values: ["off", "prefer"],
    poi_index_available: false,
    poi_default_limit: config?.poi_default_limit ?? 100,
    poi_max_limit: config?.poi_max_limit ?? 500,
    saved_routes_available: false,
    outings_available: false,
    outing_max_participants: config?.outing_max_participants ?? 20,
    outing_live_positions_available: Boolean(
      config?.outing_live_positions_available,
    ),
    outing_live_stale_after_seconds: (
      config?.outing_live_stale_after_seconds ?? 60
    ),
    outing_live_expire_after_seconds: (
      config?.outing_live_expire_after_seconds ?? 300
    ),
    default_planning_mode: "auto_tour",
    auto_tour_max_hard_waypoints: 6,
    auto_tour_max_preferred_pois: 8,
    auto_tour_scenic_corridor_radius_m: (
      config?.auto_tour_scenic_corridor_radius_m ?? 500
    ),
    auto_tour_water_corridor_radius_m: (
      config?.auto_tour_water_corridor_radius_m ?? 250
    ),
    offline_mode: true,
  };
}

export function transportFailure(error) {
  return !error?.code
    && (
      error instanceof TypeError
      || error?.name === "TypeError"
      || error?.name === "NetworkError"
    );
}

function bindControlsOnce() {
  if (controlsBound) return;
  controlsBound = true;
  bindPwaControls({
    retry: () => runUiAction(() => retryConnection()),
    activateUpdate: async () => {
      await runUiAction(async () => {
        const runtime = await pwaRuntime();
        runtime.controller.activateUpdate();
      });
    },
    clearData: async () => {
      if (
        window.confirm(
          "Clear offline copies, remembered participants, and unsent position samples from this browser?",
        )
      ) await runUiAction(clearSavedOfflineData);
    },
    saveSnapshot: (kind) => runUiAction(
      () => saveCurrentOfflineSnapshot(kind),
    ),
    removeSnapshot: (kind) => runUiAction(
      () => removeCurrentOfflineSnapshot(kind),
    ),
    rememberParticipant: () => runUiAction(
      () => rememberParticipantAction(),
    ),
    forgetParticipant: () => runUiAction(
      () => forgetParticipantAction(),
    ),
  });
}

async function runUiAction(action) {
  try {
    return await action();
  } catch {
    state.storagePersistenceStatus = "unavailable";
    state.pwaStatus = "storage_unavailable";
    renderPwaState();
    return null;
  }
}

let networkHintsBound = false;
function bindNetworkHintsOnce() {
  if (networkHintsBound) return;
  networkHintsBound = true;
  window.addEventListener("offline", () => {
    setPwaNetworkStatus("offline");
  });
  window.addEventListener("online", () => {
    void retryConnection();
  });
}

async function createRuntime() {
  const repositories = await createPwaStorageRuntime({
    onPresence: (present, ownership) => {
      if (!ownsDurablePresence(ownership)) return;
      state.durableOutboxPresent = present;
      renderPwaState();
    },
  });
  if (repositories.storageUnavailable) {
    state.storagePersistenceStatus = "unavailable";
    state.pwaStatus = "storage_unavailable";
  }
  const controller = createPwaController({
    onSupported: (supported) => {
      state.pwaSupported = supported;
      renderPwaState();
    },
    onUpdateAvailable: (available) => {
      state.pwaUpdateAvailable = available;
      renderPwaState();
    },
    onStatus: (status) => {
      state.pwaStatus = status;
      renderPwaState();
    },
    canActivateUpdate: () => (
      !state.outingTrackingActive
      && !state.outingTrackingTransitionPending
      && !mutationPending()
    ),
  });
  void controller.register();
  return { ...repositories, controller };
}

async function initializePwaRepositories(store, onPresence) {
  const snapshots = createOfflineSnapshotRepository(store);
  const sessions = createParticipantSessionRepository(store);
  const outbox = createPositionOutboxRepository(store);
  const durableBridge = createDurableOutboxBridge({
    sessions,
    outbox,
    onPresence,
  });
  await snapshots.prune();
  return {
    store,
    snapshots,
    sessions,
    outbox,
    durableBridge,
  };
}

function renderPwaState() {
  renderPwaStatus(state);
  renderOfflineCopyControls(state);
  renderRememberedParticipantControls(state);
  renderApplication();
}

function firstGeometry(payload) {
  if (Array.isArray(payload?.candidate?.route?.geometry)) {
    return payload.candidate.route.geometry;
  }
  for (const participant of payload?.participants ?? []) {
    const geometry = participant?.planned_route?.candidate?.route?.geometry;
    if (Array.isArray(geometry) && geometry.length) return geometry;
  }
  return null;
}
