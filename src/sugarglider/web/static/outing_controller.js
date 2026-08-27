import { getConfig } from "./api.js";
import {
  foregroundOutboxFlushAllowed,
} from "./outing_durable_session.js";
import {
  clearOutingLivePositions,
  fitOutingRoutes,
  initializeMap,
  renderOutingLivePositions,
  renderOutingRoutes,
  resizeMap,
} from "./map.js";
import {
  clearOutingPosition,
  connectOutingLiveEvents,
  getOutingLiveSnapshot,
  publishOutingPosition,
} from "./outing_live.js";
import {
  applyLiveEvent,
  emptyOutingLiveState,
  estimatedServerNow,
  livePositionForParticipant,
  removeOptimisticPosition,
  replaceWithSnapshot,
  upsertOptimisticPosition,
  visibleLivePositions,
  withConnectionStatus,
} from "./outing_live_state.js";
import {
  createDirtyRerun,
  createGuardedSingleFlight,
  createOutingLiveLifecycle,
  installAuthoritativeOutingSnapshot,
} from "./outing_live_lifecycle.js";
import {
  applyNativeTerminalFailureToCurrentPage,
  createRetainedTerminalFailureProcessor,
  nativeStatusBelongsToOuting,
  nativeStatusBusy,
  nativeTrackingBridge,
  projectNativeStatusForCurrentOuting,
  resetNativePageProjection,
} from "./outing_native_bridge.js";
import { createOutingTracker } from "./outing_tracking.js";
import {
  captureOutingInviteToken,
  createOuting,
  deleteOuting,
  downloadOutingParticipantGpx,
  getOuting,
  joinOuting,
  leaveOuting,
  outingInviteUrl,
  parseSavedRouteReference,
  publicOutingUrl,
  shareOutingInvitation,
} from "./outings.js";
import {
  bindOutingCreationControls,
  prepareOutingPage,
  renderOutingConnectivityControls,
  renderOutingLiveView,
  renderOutingReceipt,
  savedRouteSlugForOuting,
  setOutingMutationControls,
  showOutingView,
  triggerOutingDownload,
} from "./outing_view.js";
import {
  applyPermanentParticipantFailureState,
  applyRememberedParticipantResult,
  completeParticipantForget,
  createEpochOperationOwner,
  readOptionalStorage,
  resolveNetworkResource,
  runBestEffortStorage,
  settleOptionalPersistence,
} from "./pwa_network.js";
import {
  applyOfflineCopyRefresh,
  clearOfflineSnapshotStatus,
  durableSampleAdapter,
  forgetParticipant as forgetRememberedParticipant,
  forgetParticipantIdentity,
  loadOfflineSnapshot,
  markOfflineSnapshot,
  offlineMapConfig,
  readRememberedOutbox,
  refreshOfflineSnapshot,
  reportOptionalStorageFailure,
  removeOfflineSnapshot,
  rememberParticipant as persistRememberedParticipant,
  restorePublicConfig,
  restoreRememberedParticipant,
  setPwaNetworkStatus,
  storePublicConfig,
  transportFailure,
} from "./pwa_runtime.js";
import { selectedCandidate, state } from "./state.js";
import { trailProfileAvatarKey } from "./trail_profile.js";

let callbacks = null;
let outingMutationPending = false;
let outingLiveConnection = null;
let outingLiveFreshnessTimer = null;
let outingLiveSession = null;
let outingTracker = null;
let lifecycleEventsBound = false;
let nativeBridgeEventsBound = false;
let positionStartPending = false;
let outingPageEpoch = 0;
let requestedOutingSlug = null;
let outingReconnectOperation = null;
const outingPageOperations = createEpochOperationOwner(
  (operation) => (
    operation.epoch === outingPageEpoch
    && operation.slug === requestedOutingSlug
  ),
);
const outingLiveLifecycle = createOutingLiveLifecycle();
const nativeTerminalFailureProcessor = createRetainedTerminalFailureProcessor({
  matches: nativeTerminalFailureMatchesCurrentPage,
  clearInMemory: (failure) => (
    applyNativeTerminalFailureToCurrentPage(state, failure)
  ),
  durableCleanup: (failure) => runBestEffortStorage([
    () => forgetParticipantIdentity(
      failure.outing_slug,
      failure.participant_id,
    ),
  ]),
  acknowledge: (failure) => (
    nativeTrackingBridge.acknowledgeTerminalFailure(failure)
  ),
  onCleared: () => {
    outingTracker?.shutdown();
    showOutingView(state, outingViewHandlers());
    renderCurrentOutingLiveState();
    setStatus(
      "Participant access is no longer available. Native and remembered participant authority were removed.",
    );
  },
  onStorageFailure: reportOptionalStorageFailure,
});
const outingLiveRecovery = createGuardedSingleFlight({
  isCurrent: currentOutingLiveSession,
  onStart: beginOutingLiveRecovery,
  load: (session) => getOutingLiveSnapshot(session.slug),
  apply: applyRecoveredOutingLiveSnapshot,
  onError: handleOutingLiveRecoveryError,
});
const outingMembershipRefresh = createDirtyRerun({
  isCurrent: currentOutingLiveSession,
  load: (session) => getOuting(session.slug),
  apply: applyRefreshedOutingMembership,
  onError: handleOutingMembershipRefreshError,
});

function reportError(error, fallback) { callbacks?.handleError(error, fallback); }
function setStatus(message) { callbacks?.setStatus(message); }

function setOutingLiveConnectionStatus(status, session = null) {
  if (session && !currentOutingLiveSession(session)) return;
  state.outingLiveConnectionStatus = status;
  state.outingLiveState = withConnectionStatus(
    state.outingLiveState,
    status === "outing_closed" ? "closed" : status,
  );
  renderCurrentOutingLiveState();
}

function renderCurrentOutingLiveState() {
  if (!state.outingSnapshot) return;
  const serverNow = estimatedServerNow(state.outingLiveState);
  renderOutingLiveView(state);
  renderOutingLivePositions(
    state.outingSnapshot.participants,
    visibleLivePositions(state.outingLiveState, serverNow),
    state.selectedOutingParticipantId,
    serverNow,
    selectOutingParticipant,
  );
}

export function renderCurrentOutingConnectivity() {
  renderOutingConnectivityControls(state);
  setOutingMutationControls(state, outingMutationPending);
}

function closeOutingLiveConnection() {
  const operation = outingLiveConnection;
  outingLiveConnection = null;
  operation?.connection?.close();
}

function connectCurrentOutingLiveEvents(session) {
  if (!currentOutingLiveSession(session)) return;
  closeOutingLiveConnection();
  const operation = { session, connection: null };
  outingLiveConnection = operation;
  operation.connection = connectOutingLiveEvents(session.slug, {
    open: () => {
      if (currentOutingOperation(outingLiveConnection, operation)) {
        setOutingLiveConnectionStatus("open", session);
      }
    },
    reconnecting: () => {
      if (currentOutingOperation(outingLiveConnection, operation)) {
        setOutingLiveConnectionStatus("reconnecting", session);
      }
    },
    closed: () => {
      if (
        currentOutingOperation(outingLiveConnection, operation)
        && !state.outingClosed
      ) {
        setOutingLiveConnectionStatus("closed", session);
      }
    },
    snapshot: (snapshot) => {
      if (currentOutingOperation(outingLiveConnection, operation)) {
        applyOutingLiveSnapshot(snapshot, session);
      }
    },
    reset: (snapshot) => {
      if (currentOutingOperation(outingLiveConnection, operation)) {
        applyOutingLiveSnapshot(snapshot, session);
      }
    },
    positionUpdated: (event, lastEventId) => {
      if (currentOutingOperation(outingLiveConnection, operation)) {
        applyOutingLiveUpdate(event, lastEventId, session);
      }
    },
    positionCleared: (event, lastEventId) => {
      if (currentOutingOperation(outingLiveConnection, operation)) {
        applyOutingLiveClear(event, lastEventId, session);
      }
    },
    outingClosed: () => {
      if (currentOutingOperation(outingLiveConnection, operation)) {
        handleOutingClosed(session);
      }
    },
    malformed: () => {
      if (currentOutingOperation(outingLiveConnection, operation)) {
        void recoverOutingLiveSnapshot(session);
      }
    },
  });
}

function applyOutingLiveSnapshot(snapshot, session) {
  if (!currentOutingLiveSession(session)) return;
  const result = replaceWithSnapshot(
    state.outingLiveState,
    snapshot,
    session.slug,
    Date.now(),
  );
  if (result.status !== "applied") {
    void recoverOutingLiveSnapshot(session);
    return;
  }
  state.outingLiveState = result.state;
  renderCurrentOutingLiveState();
}

function applyOutingLiveUpdate(event, lastEventId, session) {
  if (!currentOutingLiveSession(session)) return;
  const result = applyLiveEvent(
    state.outingLiveState,
    event,
    lastEventId,
    Date.now(),
  );
  if (result.status === "recovery_required") {
    void recoverOutingLiveSnapshot(session);
    return;
  }
  if (result.status === "ignored") return;
  state.outingLiveState = result.state;
  renderCurrentOutingLiveState();
  if (!state.outingSnapshot?.participants.some(
    (participant) => participant.participant_id === event.participant_id,
  )) {
    void refreshOutingSnapshotForMembershipChange(session);
  }
}

function applyOutingLiveClear(event, lastEventId, session) {
  if (!currentOutingLiveSession(session)) return;
  const result = applyLiveEvent(
    state.outingLiveState,
    event,
    lastEventId,
    Date.now(),
  );
  if (result.status === "recovery_required") {
    void recoverOutingLiveSnapshot(session);
    return;
  }
  if (result.status === "ignored") return;
  state.outingLiveState = result.state;
  renderCurrentOutingLiveState();
  if (event.clear_reason === "participant_left") {
    void refreshOutingSnapshotForMembershipChange(session);
  }
}

async function recoverOutingLiveSnapshot(session = outingLiveSession) {
  return outingLiveRecovery.run(session);
}

function beginOutingLiveRecovery(session) {
  closeOutingLiveConnection();
  setOutingLiveConnectionStatus("reconnecting", session);
}

function applyRecoveredOutingLiveSnapshot(snapshot, session) {
  const result = replaceWithSnapshot(
    state.outingLiveState,
    snapshot,
    session.slug,
    Date.now(),
  );
  if (result.status !== "applied") {
    setOutingLiveConnectionStatus("unavailable", session);
    return;
  }
  state.outingLiveState = result.state;
  renderCurrentOutingLiveState();
  connectCurrentOutingLiveEvents(session);
}

function handleOutingLiveRecoveryError(error, session) {
  if (error?.code === "outing_not_found") {
    handleOutingClosed(session);
    return;
  }
  if (!currentOutingLiveSession(session)) return;
  setOutingLiveConnectionStatus("reconnecting", session);
  connectCurrentOutingLiveEvents(session);
}

async function refreshOutingSnapshotForMembershipChange(
  session = outingLiveSession,
) {
  return outingMembershipRefresh.run(session);
}

function applyRefreshedOutingMembership(snapshot, session) {
  if (snapshot.slug !== session.slug) return;
  const nativeBeforeRefresh = state.nativeServiceStatus;
  const removedReceipt = installAuthoritativeOutingSnapshot(
    state,
    snapshot,
    {
      shutdownTracker: () => outingTracker?.shutdown(),
      syncTrackerState: syncOutingTrackingState,
    },
  );
  if (removedReceipt) {
    void runBestEffortStorage(
      [() => forgetParticipantIdentity(
        removedReceipt.slug,
        removedReceipt.participant_id,
      )],
      { onFailure: reportOptionalStorageFailure },
    );
  }
  if (
    nativeBeforeRefresh?.active
    && nativeBeforeRefresh.outing_slug === snapshot.slug
    && !snapshot.participants.some(
      (participant) => participant.participant_id === nativeBeforeRefresh.participant_id,
    )
  ) {
    void nativeTrackingBridge.stop({
      outingSlug: nativeBeforeRefresh.outing_slug,
      participantId: nativeBeforeRefresh.participant_id,
    });
    resetNativePageProjection(state);
  }
  if (!snapshot.participants.some(
    (participant) => (
      participant.participant_id === state.selectedOutingParticipantId
    ),
  )) {
    state.selectedOutingParticipantId = (
      snapshot.participants[0]?.participant_id ?? null
    );
  }
  showOutingView(state, outingViewHandlers());
  renderOutingRoutes(
    snapshot.participants,
    state.selectedOutingParticipantId,
  );
  renderCurrentOutingLiveState();
  callbacks?.renderMetrics();
}

function handleOutingMembershipRefreshError(error, session) {
  if (error?.code === "outing_not_found") handleOutingClosed(session);
}

function startOutingLiveExperience(slug) {
  stopOutingLiveExperience({ stopTracking: false, clearPositions: true });
  const session = outingLiveLifecycle.start(slug);
  outingLiveSession = session;
  state.outingClosed = false;
  state.outingLiveState = emptyOutingLiveState();
  if (!state.config?.outing_live_positions_available) {
    setOutingLiveConnectionStatus("unavailable", session);
    return;
  }
  setOutingLiveConnectionStatus("connecting", session);
  connectCurrentOutingLiveEvents(session);
  const timer = { session, id: null };
  timer.id = window.setInterval(() => {
    if (outingLiveFreshnessTimer === timer) {
      renderCurrentOutingLiveState();
    }
  }, 1_000);
  outingLiveFreshnessTimer = timer;
  void synchronizeNativeTrackingStatus();
}

function stopOutingLiveExperience({
  stopTracking = true,
  clearPositions = true,
} = {}) {
  outingLiveLifecycle.invalidate();
  outingLiveSession = null;
  outingLiveRecovery.invalidate();
  outingMembershipRefresh.invalidate();
  closeOutingLiveConnection();
  if (outingLiveFreshnessTimer !== null) {
    window.clearInterval(outingLiveFreshnessTimer.id);
    outingLiveFreshnessTimer = null;
  }
  if (stopTracking) {
    outingTracker?.shutdown();
    if (
      state.outingTrackingBackend === "native"
      && nativeStatusBelongsToOuting(
        nativeTrackingBridge.status(),
        state.outingSnapshot,
      )
    ) void stopMatchingNativeTracking(state.nativeTrackingIdentity);
  }
  if (clearPositions) clearOutingLivePositions();
}

function handleOutingClosed(session = outingLiveSession) {
  if (session && !currentOutingLiveSession(session)) return;
  state.outingClosed = true;
  stopOutingLiveExperience({ stopTracking: true, clearPositions: true });
  state.outingLiveConnectionStatus = "outing_closed";
  state.outingLiveState = emptyOutingLiveState();
  const slug = state.outingSnapshot?.slug;
  if (slug) {
    void runBestEffortStorage([
      () => forgetRememberedParticipant(slug, { updateState: false }),
      () => removeOfflineSnapshot("outing", slug),
    ], { onFailure: reportOptionalStorageFailure });
  }
  if (state.outingParticipantReceipt?.slug === slug) {
    state.outingParticipantReceipt = null;
  }
  state.participantRemembered = false;
  state.durableOutboxPresent = false;
  resetNativePageProjection(state);
  showOutingView(state, outingViewHandlers());
  renderOutingLiveView(state);
  setStatus("Outing closed.");
}

function currentOutingLiveSession(session) {
  return outingLiveLifecycle.owns(
    session,
    state.outingSnapshot?.slug,
    state.outingClosed,
  );
}

function currentOutingOperation(activeOperation, operation) {
  return activeOperation === operation
    && currentOutingLiveSession(operation.session);
}

export function outingOutboxPresenceIsCurrent(ownership) {
  const receipt = state.outingParticipantReceipt;
  return Boolean(
    receipt
    && ownership?.outingSlug === receipt.slug
    && ownership?.participantId === receipt.participant_id
    && ownership?.generation === outingTracker?.status().generation
  );
}

async function handlePermanentParticipantFailure(failure) {
  if (failure?.code !== "outing_not_found") return;
  await forgetParticipantIdentity(
    failure.receipt.slug,
    failure.receipt.participant_id,
  );
  if (!applyPermanentParticipantFailureState(
    state,
    failure,
    outingTracker?.status().generation,
  )) return;
  syncOutingTrackingState();
  showOutingView(state, outingViewHandlers());
  setStatus(
    "Participant access is no longer available. The remembered participant and unsent position were removed.",
  );
}

function ensureOutingTracker() {
  if (outingTracker) return outingTracker;
  outingTracker = createOutingTracker({
    publishPosition: publishOutingPosition,
    getLiveSnapshot: getOutingLiveSnapshot,
    clearPosition: clearOutingPosition,
    onStatus: (tracking) => {
      state.outingTrackingStatus = tracking.status;
      state.outingTrackingMessage = tracking.message;
      state.outingTrackingActive = tracking.active;
      state.outingTrackingTransitionPending = tracking.transitionPending;
      state.outingTrackingClearFailed = tracking.clearingFailed;
      state.outingTrackingLastPublishedAt = tracking.lastPublishedAt;
      renderCurrentOutingLiveState();
    },
    onPublished: (position, publishedAt) => {
      state.outingLiveState = upsertOptimisticPosition(
        state.outingLiveState,
        position,
      );
      state.outingTrackingLastPublishedAt = publishedAt;
      renderCurrentOutingLiveState();
    },
    onCleared: (participantId) => {
      state.outingLiveState = removeOptimisticPosition(
        state.outingLiveState,
        participantId,
      );
      renderCurrentOutingLiveState();
    },
    onPermanentFailure: handlePermanentParticipantFailure,
    durableSamples: durableSampleAdapter,
  });
  return outingTracker;
}

function bindNativeBridgeEvents() {
  if (nativeBridgeEventsBound) return;
  nativeBridgeEventsBound = true;
  nativeTrackingBridge.subscribe((event) => {
    state.nativeTrackingAvailable = nativeTrackingBridge.available();
    if (event.kind === "status") applyNativeTrackingStatus(event.status);
    else if (event.kind === "permanent_failure") {
      void applyNativePermanentFailure(event.failure).catch(
        reportOptionalStorageFailure,
      );
    }
  });
  void nativeTrackingBridge.initialize().then((available) => {
    state.nativeTrackingAvailable = available;
    if (available) void synchronizeNativeTrackingStatus();
  });
}

async function synchronizeNativeTrackingStatus() {
  if (!state.outingSnapshot) return;
  const status = await nativeTrackingBridge.getStatus();
  state.nativeTrackingAvailable = nativeTrackingBridge.available();
  if (status) applyNativeTrackingStatus(status);
}

function applyNativeTrackingStatus(status) {
  if (!projectNativeStatusForCurrentOuting(state, status)) {
    renderCurrentOutingLiveState();
    return;
  }
  state.outingTrackingMessage = nativeTrackingMessage(status);
  renderCurrentOutingLiveState();
}

async function applyNativePermanentFailure(failure) {
  if (!Number.isSafeInteger(failure.event_id)) {
    applyNativeStartRejection(failure);
    return;
  }
  await nativeTerminalFailureProcessor.process(failure);
}

function nativeTerminalFailureMatchesCurrentPage(failure) {
  return Boolean(
    state.outingSnapshot?.slug === failure.outing_slug
    && (
      state.outingSnapshot.participants.some(
        (participant) => participant.participant_id === failure.participant_id,
      )
      || (
        state.outingParticipantReceipt?.slug === failure.outing_slug
        && state.outingParticipantReceipt.participant_id === failure.participant_id
      )
      || (
        state.nativeTrackingIdentity?.outing_slug === failure.outing_slug
        && state.nativeTrackingIdentity.participant_id === failure.participant_id
      )
    )
  );
}

function applyNativeStartRejection(failure) {
  if (!nativeStatusBelongsToOuting(failure, state.outingSnapshot)) return;
  state.outingTrackingTransitionPending = false;
  const message = {
    permission_denied: "Android background sharing was not started: confirmation or location permission was denied.",
    approximate_location: "Android background sharing requires precise location permission.",
    notification_permission_denied: "Android background sharing requires notification permission.",
    location_disabled: "Turn on Android location services before starting sharing.",
    different_participant_active: "Another Android participant is currently sharing. Stop it from its outing or notification first.",
    stop_in_progress: "Android background sharing is still stopping. Wait for Stop to finish before starting again.",
    start_in_progress: "Android background sharing is already starting.",
    outing_not_found: "This outing is expired or unavailable; Android sharing was not started.",
  }[failure.code] ?? "Android background sharing could not be started.";
  state.outingTrackingMessage = message;
  renderCurrentOutingLiveState();
  setStatus(message);
}

function nativeTrackingMessage(status) {
  if (status.stop_warning) return status.stop_warning;
  return {
    starting: "Starting Android background sharing",
    waiting: "Waiting for a precise Android location fix",
    sharing: "Android background sharing is active — it continues with the screen locked",
    offline_retrying: "Offline — Android is retaining only the latest fix and retrying",
    stopping: "Stopping Android background sharing",
    stopped: "Android background sharing stopped",
    outing_closed: "Outing closed — Android sharing stopped",
  }[status.state] ?? "Android background sharing stopped";
}

function syncOutingTrackingState() {
  if (state.outingTrackingBackend === "native") {
    renderCurrentOutingLiveState();
    return;
  }
  if (!outingTracker) return;
  const tracking = outingTracker.status();
  state.outingTrackingStatus = tracking.status;
  state.outingTrackingActive = tracking.active;
  state.outingTrackingTransitionPending = tracking.transitionPending;
  state.outingTrackingClearFailed = tracking.clearingFailed;
  state.outingTrackingLastPublishedAt = tracking.lastPublishedAt;
  renderCurrentOutingLiveState();
}

async function startCurrentOutingPositionSharing() {
  if (positionStartPending) return;
  const receipt = state.outingParticipantReceipt;
  const outing = state.outingSnapshot;
  if (!receipt || !outing || receipt.slug !== outing.slug) return;
  if (nativeStatusBusy(state.nativeServiceStatus)) {
    const nativeBelongs = nativeStatusBelongsToOuting(
      state.nativeServiceStatus,
      outing,
    );
    if (!nativeBelongs || state.nativeServiceStatus.state === "stopping") {
      setStatus(
        state.nativeServiceStatus.state === "stopping"
          ? "Android background sharing is still stopping. Wait for Stop to finish before starting again."
          : "Another Android participant is currently sharing. Stop it before starting this participant.",
      );
      return;
    }
  }
  positionStartPending = true;
  state.outingTrackingTransitionPending = true;
  renderCurrentOutingLiveState();
  try {
    const nativeAvailable = await nativeTrackingBridge.initialize();
    state.nativeTrackingAvailable = nativeAvailable;
    if (
      !nativeAvailable
      && state.networkStatus === "offline"
      && !state.participantRemembered
    ) {
      setStatus(
        "Remember this participant before starting while offline so only the latest fix can be retained.",
      );
      return;
    }
    if (nativeAvailable) {
      const currentPosition = livePositionForParticipant(
        state.outingLiveState,
        receipt.participant_id,
      );
      const reply = await nativeTrackingBridge.start({
        receipt,
        outingExpiresAt: outing.expires_at,
        currentSequence: currentPosition?.sequence ?? 0,
      });
      if (reply && reply.type !== "permanent_failure") {
        applyNativeTrackingStatus(reply);
      }
      return;
    }
    const resumeSample = state.participantRemembered
      ? await readRememberedOutbox(receipt)
      : null;
    if (
      receipt !== state.outingParticipantReceipt
      || outing !== state.outingSnapshot
    ) return;
    state.durableOutboxPresent = Boolean(resumeSample);
    const tracker = ensureOutingTracker();
    state.outingTrackingBackend = "browser";
    state.nativeTrackingIdentity = null;
    tracker.start(receipt, {
      available: Boolean(state.config?.outing_live_positions_available),
      currentPosition: livePositionForParticipant(
        state.outingLiveState,
        receipt.participant_id,
      ),
      resumeSample,
    });
  } finally {
    positionStartPending = false;
    if (state.outingTrackingBackend !== "native") {
      state.outingTrackingTransitionPending = false;
    }
    syncOutingTrackingState();
  }
}

async function stopCurrentOutingPositionSharing() {
  const receipt = state.outingParticipantReceipt;
  if (state.outingTrackingBackend === "native") {
    state.outingTrackingTransitionPending = true;
    renderCurrentOutingLiveState();
    const identity = state.nativeTrackingIdentity;
    if (!identity) return { cleared: false, pending: false };
    const reply = await nativeTrackingBridge.stop({
      outingSlug: identity.outing_slug,
      participantId: identity.participant_id,
    });
    if (reply && reply.type !== "permanent_failure") {
      applyNativeTrackingStatus(reply);
      return {
        cleared: reply.state === "stopped" && !reply.stop_warning,
        pending: reply.state === "stopping",
        uncertain: Boolean(reply.stop_warning),
      };
    } else if (!reply) {
      state.outingTrackingTransitionPending = false;
      renderCurrentOutingLiveState();
      return { cleared: false, pending: false, uncertain: true };
    }
    return { cleared: false, pending: false, uncertain: true };
  }
  if (!receipt) return;
  const tracker = ensureOutingTracker();
  await tracker.stop(receipt, { clearServer: true });
  syncOutingTrackingState();
}

function stopTrackerBeforeOutingMutation() {
  if (state.outingTrackingBackend === "native") {
    void stopMatchingNativeTracking(state.nativeTrackingIdentity);
  }
  outingTracker?.shutdown();
  syncOutingTrackingState();
}

function stopMatchingNativeTracking(identity) {
  if (!identity) return Promise.resolve(null);
  return nativeTrackingBridge.stop({
    outingSlug: identity.outing_slug,
    participantId: identity.participant_id,
  });
}

function prepareParticipantTracker() {
  if (nativeTrackingBridge.available()) {
    state.nativeTrackingAvailable = true;
    void synchronizeNativeTrackingStatus();
    return;
  }
  const tracker = ensureOutingTracker();
  syncOutingTrackingState();
  if (!tracker.supported()) {
    state.outingTrackingStatus = "unsupported";
    state.outingTrackingMessage = (
      "Browser geolocation is unavailable on this device."
    );
    renderCurrentOutingLiveState();
  }
}

function bindOutingLifecycleEvents() {
  if (lifecycleEventsBound) return;
  lifecycleEventsBound = true;
  bindNativeBridgeEvents();
  window.addEventListener("online", () => {
    if (foregroundOutboxFlushAllowed({
      visible: document.visibilityState === "visible",
      remembered: state.participantRemembered,
      trackingActive: Boolean(outingTracker?.status().active),
    })) outingTracker.online();
  });
  window.addEventListener("pagehide", () => {
    const receipt = state.outingParticipantReceipt;
    if (receipt) outingTracker?.pagehide(receipt);
    stopOutingLiveExperience({ stopTracking: false, clearPositions: false });
  });
}

function beginOutingMutation() {
  if (outingMutationPending) return false;
  outingMutationPending = true;
  setOutingMutationControls(state, true);
  return true;
}

function finishOutingMutation() {
  outingMutationPending = false;
  setOutingMutationControls(state, false);
}

async function createOutingFromSavedRoute(title, displayName) {
  if (!beginOutingMutation()) return;
  try {
    const savedSlug = savedRouteSlugForOuting(state);
    if (!savedSlug) return;
    const created = await createOuting(
      title,
      displayName,
      savedSlug,
      trailProfileAvatarKey(),
    );
    state.outingOwnerReceipt = {
      slug: created.slug,
      owner_token: created.owner_token,
      join_token: created.join_token,
      participant_id: created.participant_id,
      participant_token: created.participant_token,
      share_path: created.share_path,
      invite_path: created.invite_path,
      expires_at: created.expires_at,
      title: created.title,
    };
    renderOutingReceipt(state);
    setStatus("Outing created. Public and invitation links are ready.");
  } catch (error) {
    reportError(error, "The outing could not be created.");
  } finally {
    finishOutingMutation();
  }
}

async function copyOutingLink(kind) {
  const receipt = state.outingOwnerReceipt;
  if (!receipt) return;
  const url = kind === "invite"
    ? outingInviteUrl(receipt)
    : publicOutingUrl(receipt);
  try {
    await navigator.clipboard.writeText(url);
    setStatus(
      `${kind === "invite" ? "Invitation" : "Public outing"} link copied.`,
    );
  } catch (error) {
    reportError(error, "The outing link could not be copied.");
  }
}

async function shareCurrentOutingInvitation() {
  if (!state.outingOwnerReceipt) return;
  try {
    await shareOutingInvitation(state.outingOwnerReceipt);
    setStatus("Outing invitation shared.");
  } catch (error) {
    if (error.name === "AbortError") {
      setStatus("Sharing cancelled.");
      return;
    }
    reportError(error, "The outing invitation could not be shared.");
  }
}

async function removeCurrentOuting() {
  if (outingMutationPending) return;
  const receipt = state.outingOwnerReceipt;
  if (!receipt) return;
  if (!window.confirm("Permanently delete this outing?")) return;
  if (!beginOutingMutation()) return;
  let liveExperienceStopped = false;
  try {
    stopTrackerBeforeOutingMutation();
    stopOutingLiveExperience({
      stopTracking: false,
      clearPositions: false,
    });
    liveExperienceStopped = true;
    await deleteOuting(receipt.slug, receipt.owner_token);
    handleOutingClosed();
    state.outingOwnerReceipt = null;
    state.outingParticipantReceipt = null;
    renderOutingReceipt(state);
    setStatus("Outing deleted.");
  } catch (error) {
    if (
      liveExperienceStopped
      && state.outingSnapshot?.slug === receipt.slug
      && !state.outingClosed
    ) {
      startOutingLiveExperience(receipt.slug);
    }
    reportError(error, "The outing could not be deleted.");
  } finally {
    finishOutingMutation();
  }
}

function selectOutingParticipant(participantId) {
  if (!state.outingSnapshot?.participants.some(
    (participant) => participant.participant_id === participantId,
  )) return;
  state.selectedOutingParticipantId = participantId;
  state.selectedSignature = selectedCandidate()?.id ?? null;
  callbacks?.renderMetrics();
  renderOutingRoutes(
    state.outingSnapshot.participants,
    state.selectedOutingParticipantId,
  );
  renderCurrentOutingLiveState();
}

async function joinCurrentOuting(displayName, savedRouteReference) {
  if (!beginOutingMutation()) return;
  const outing = state.outingSnapshot;
  const savedSlug = parseSavedRouteReference(savedRouteReference);
  try {
    if (!outing || !state.outingInviteToken) return;
    if (!savedSlug) {
      callbacks?.showError(
        "Enter a saved-route slug or a saved-route link from this Sugarglider site.",
      );
      return;
    }
    const joined = await joinOuting(
      outing.slug,
      state.outingInviteToken,
      displayName,
      savedSlug,
      trailProfileAvatarKey(),
    );
    outingMembershipRefresh.invalidate();
    state.outingSnapshot = joined.outing;
    state.outingParticipantReceipt = {
      slug: outing.slug,
      participant_id: joined.participant_id,
      participant_token: joined.participant_token,
    };
    state.outingInviteToken = null;
    showOutingView(state, outingViewHandlers());
    prepareParticipantTracker();
    selectOutingParticipant(joined.participant_id);
    fitOutingRoutes(joined.outing.participants);
    setStatus("You joined this outing with your independent route.");
  } catch (error) {
    reportError(error, "The outing could not be joined.");
  } finally {
    finishOutingMutation();
  }
}

async function downloadMyOutingGpx() {
  const receipt = state.outingParticipantReceipt;
  if (!receipt) return;
  try {
    const result = await downloadOutingParticipantGpx(
      receipt.slug,
      receipt.participant_id,
    );
    triggerOutingDownload(result);
  } catch (error) {
    reportError(error, "Your participant GPX could not be downloaded.");
  }
}

async function leaveCurrentOuting() {
  if (outingMutationPending) return;
  const receipt = state.outingParticipantReceipt;
  if (!receipt) return;
  if (!window.confirm("Leave this outing and remove your planned route?")) return;
  if (!beginOutingMutation()) return;
  let liveExperienceStopped = false;
  try {
    stopTrackerBeforeOutingMutation();
    stopOutingLiveExperience({
      stopTracking: false,
      clearPositions: false,
    });
    liveExperienceStopped = true;
    await leaveOuting(
      receipt.slug,
      receipt.participant_id,
      receipt.participant_token,
    );
    await forgetRememberedParticipant(
      receipt.slug,
      { updateState: false },
    );
    state.participantRemembered = false;
    state.durableOutboxPresent = false;
    state.outingParticipantReceipt = null;
    state.outingSnapshot = await getOuting(receipt.slug);
    state.selectedOutingParticipantId = (
      state.outingSnapshot.participants[0]?.participant_id ?? null
    );
    showOutingView(state, outingViewHandlers());
    renderOutingRoutes(
      state.outingSnapshot.participants,
      state.selectedOutingParticipantId,
    );
    startOutingLiveExperience(receipt.slug);
    renderCurrentOutingLiveState();
    callbacks?.renderMetrics();
  } catch (error) {
    if (
      liveExperienceStopped
      && state.outingSnapshot?.slug === receipt.slug
      && !state.outingClosed
    ) {
      startOutingLiveExperience(receipt.slug);
    }
    reportError(error, "The outing could not be left.");
  } finally {
    finishOutingMutation();
  }
}

function outingViewHandlers() {
  return {
    select: selectOutingParticipant,
    join: joinCurrentOuting,
    downloadMine: downloadMyOutingGpx,
    leave: leaveCurrentOuting,
    deleteOwner: removeCurrentOuting,
    startSharing: startCurrentOutingPositionSharing,
    stopSharing: stopCurrentOutingPositionSharing,
    rememberParticipant: rememberCurrentOutingParticipant,
    forgetParticipant: forgetCurrentOutingParticipant,
  };
}

export async function rememberCurrentOutingParticipant() {
  const receipt = state.outingParticipantReceipt;
  const outing = state.outingSnapshot;
  if (
    !receipt
    || !outing
    || receipt.slug !== outing.slug
    || !outing.participants.some(
      (participant) => participant.participant_id === receipt.participant_id,
    )
  ) return;
  if (!window.confirm(
    "Remember this participant capability on this browser profile? Anyone with access to this profile may act as this participant. Remembering does not start location sharing.",
  )) return;
  try {
    await persistRememberedParticipant(receipt, outing.expires_at);
    showOutingView(state, outingViewHandlers());
    setStatus(
      "Participant remembered on this device. Position sharing remains stopped.",
    );
  } catch (error) {
    reportError(error, "This participant could not be remembered.");
  }
}

export async function forgetCurrentOutingParticipant() {
  const receipt = state.outingParticipantReceipt;
  if (!receipt) return;
  const tracker = ensureOutingTracker();
  const clearServer = state.networkStatus !== "offline";
  const result = await completeParticipantForget({
    clearServer,
    stop: () => state.outingTrackingBackend === "native"
      ? stopCurrentOutingPositionSharing()
      : tracker.stop(receipt, { clearServer }),
    forget: () => forgetRememberedParticipant(receipt.slug),
  });
  if (state.outingParticipantReceipt === receipt) {
    state.outingParticipantReceipt = null;
  }
  state.participantRemembered = false;
  state.durableOutboxPresent = false;
  syncOutingTrackingState();
  showOutingView(state, outingViewHandlers());
  if (result.warningRequired) {
    setStatus(
      "Participant forgotten from this device. Stop was not confirmed; the last position may remain until expiry.",
    );
  } else {
    setStatus(
      "Participant forgotten from this device. The outing and its route remain unchanged.",
    );
  }
  if (result.storageFailure) {
    reportError(
      result.storageFailure,
      "The browser could not confirm removal from durable storage.",
    );
  }
}

async function enterCreatedOutingHere() {
  const receipt = state.outingOwnerReceipt;
  if (!receipt || !beginOutingMutation()) return;
  try {
    const snapshot = await getOuting(receipt.slug);
    state.outingSnapshot = snapshot;
    state.outingParticipantReceipt = {
      slug: receipt.slug,
      participant_id: receipt.participant_id,
      participant_token: receipt.participant_token,
    };
    state.outingDisplay = true;
    state.outingClosed = false;
    state.outingInviteToken = null;
    state.selectedOutingParticipantId = receipt.participant_id;
    state.selectedSignature = selectedCandidate()?.id ?? null;
    window.history.replaceState(
      null,
      "",
      `/o/${encodeURIComponent(receipt.slug)}`,
    );
    prepareOutingPage();
    prepareParticipantTracker();
    showOutingView(state, outingViewHandlers());
    renderOutingRoutes(snapshot.participants, receipt.participant_id);
    fitOutingRoutes(snapshot.participants);
    callbacks?.renderMetrics();
    startOutingLiveExperience(receipt.slug);
    setStatus(
      "Live outing opened in this tab. Position sharing remains stopped until Start is pressed.",
    );
  } catch (error) {
    reportError(error, "The live outing could not be opened in this tab.");
  } finally {
    finishOutingMutation();
  }
}

export function bindOutingController(nextCallbacks) {
  callbacks = nextCallbacks;
  bindOutingLifecycleEvents();
  bindOutingCreationControls({
    create: createOutingFromSavedRoute,
    open: () => {
      if (state.outingOwnerReceipt) {
        window.open(
          publicOutingUrl(state.outingOwnerReceipt),
          "_blank",
          "noopener",
        );
      }
    },
    openHere: enterCreatedOutingHere,
    copyPublic: () => copyOutingLink("public"),
    copyInvite: () => copyOutingLink("invite"),
    shareInvite: shareCurrentOutingInvitation,
    delete: removeCurrentOuting,
    dismiss: () => {
      state.outingOwnerReceipt = null;
      renderOutingReceipt(state);
    },
  });
}

export async function startOutingPage(slug, nextCallbacks) {
  callbacks = nextCallbacks;
  bindOutingLifecycleEvents();
  const pageEpoch = ++outingPageEpoch;
  requestedOutingSlug = slug;
  const pageOperation = outingPageOperations.begin({
    slug,
    epoch: pageEpoch,
  });
  state.outingInviteToken = captureOutingInviteToken();
  let offline = false;
  try {
    const loaded = await resolveNetworkResource({
      loadResource: () => getOuting(slug),
      loadConfig: () => getConfig(),
      loadStoredConfig: restorePublicConfig,
      fallbackConfig: (snapshot) => onlineFallbackConfig(snapshot),
    });
    if (!outingPageOperations.owns(pageOperation)) return;
    state.config = loaded.config;
    state.outingSnapshot = loaded.resource;
    clearOfflineSnapshotStatus();
    void persistOutingNetworkData(
      loaded,
      pageOperation,
      () => outingPageOperations.owns(pageOperation)
        && state.outingSnapshot?.slug === slug,
    );
  } catch (error) {
    if (!outingPageOperations.owns(pageOperation)) return;
    if (error?.code === "outing_not_found") {
      await Promise.allSettled([
        removeOfflineSnapshot("outing", slug),
        forgetRememberedParticipant(slug, { updateState: false }),
      ]);
      if (!outingPageOperations.owns(pageOperation)) return;
      state.participantRemembered = false;
      state.durableOutboxPresent = false;
      throw error;
    }
    if (!transportFailure(error)) throw error;
    const [recordResult, configResult] = await Promise.allSettled([
      loadOfflineSnapshot("outing", slug),
      restorePublicConfig(),
    ]);
    if (!outingPageOperations.owns(pageOperation)) return;
    const record = recordResult.status === "fulfilled"
      ? recordResult.value
      : null;
    if (!record) throw error;
    const storedConfig = configResult.status === "fulfilled"
      ? configResult.value
      : null;
    offline = true;
    state.outingSnapshot = record.payload;
    state.config = offlineMapConfig(storedConfig, record.payload);
    state.outingInviteToken = null;
    markOfflineSnapshot("outing", slug);
  }
  if (!currentLoadedOutingPage(pageOperation)) return;
  state.outingDisplay = true;
  state.outingParticipantReceipt = null;
  const loadedOuting = state.outingSnapshot;
  const restored = await readOptionalStorage(
    () => restoreRememberedParticipant(loadedOuting, {
      isCurrent: () => currentLoadedOutingPage(pageOperation),
    }),
    { onFailure: reportOptionalStorageFailure },
  );
  if (!currentLoadedOutingPage(pageOperation)) return;
  applyRememberedParticipantResult(state, loadedOuting, restored, {
    isCurrent: () => currentLoadedOutingPage(pageOperation),
  });
  if (!restored) {
    state.selectedOutingParticipantId = (
      loadedOuting.participants[0]?.participant_id ?? null
    );
  }
  state.selectedSignature = selectedCandidate()?.id ?? null;
  initializeMap(state.config, {
    onReady: () => {
      callbacks?.onMapReady();
      renderOutingRoutes(
        state.outingSnapshot.participants,
        state.selectedOutingParticipantId,
      );
      fitOutingRoutes(state.outingSnapshot.participants);
      renderCurrentOutingLiveState();
    },
    onError: callbacks.showMapError,
    onViewportChange: () => {},
    onMapClick: () => {},
  });
  showOutingView(state, outingViewHandlers());
  callbacks.renderMetrics();
  prepareOutingPage();
  if (offline) {
    state.outingLiveState = emptyOutingLiveState();
    state.outingLiveConnectionStatus = "unavailable";
    clearOutingLivePositions();
    renderCurrentOutingLiveState();
    setStatus(
      "Showing an explicit offline outing copy. Live positions and server mutations are unavailable.",
    );
  } else {
    startOutingLiveExperience(slug);
    setStatus(
      "Independent immutable participant routes loaded. Live viewing does not request location permission.",
    );
  }
  window.addEventListener("resize", resizeMap);
}

export async function retryCurrentOutingConnection() {
  const slug = state.outingSnapshot?.slug;
  if (!slug) return false;
  if (outingReconnectOperation) return outingReconnectOperation.promise;
  const epoch = outingPageEpoch;
  const identity = Object.freeze({ epoch, slug });
  const operation = { identity, promise: null };
  outingReconnectOperation = operation;
  operation.promise = (async () => {
    try {
      const wasOfflineSnapshot = state.offlineSnapshotKind === "outing";
      const loaded = await resolveNetworkResource({
        loadResource: () => getOuting(slug),
        loadConfig: () => getConfig(),
        loadStoredConfig: restorePublicConfig,
        fallbackConfig: (snapshot) => onlineFallbackConfig(snapshot),
      });
      if (!currentOutingReconnect(operation)) return false;
      state.config = loaded.config;
      const removedReceipt = installAuthoritativeOutingSnapshot(
        state,
        loaded.resource,
        {
          shutdownTracker: () => outingTracker?.shutdown(),
          syncTrackerState: syncOutingTrackingState,
        },
      );
      clearOfflineSnapshotStatus();
      if (removedReceipt) {
        const cleanup = await settleOptionalPersistence([
          () => forgetParticipantIdentity(
            removedReceipt.slug,
            removedReceipt.participant_id,
          ),
        ]);
        if (!currentOutingReconnect(operation)) return false;
        if (cleanup.failed) reportOptionalStorageFailure();
      }
      const restored = await readOptionalStorage(
        () => restoreRememberedParticipant(loaded.resource, {
          isCurrent: () => currentOutingReconnect(operation),
        }),
        { onFailure: reportOptionalStorageFailure },
      );
      if (!currentOutingReconnect(operation)) return false;
      applyRememberedParticipantResult(
        state,
        loaded.resource,
        restored,
        { isCurrent: () => currentOutingReconnect(operation) },
      );
      if (!loaded.resource.participants.some(
        (participant) => (
          participant.participant_id === state.selectedOutingParticipantId
        ),
      )) {
        state.selectedOutingParticipantId = (
          loaded.resource.participants[0]?.participant_id ?? null
        );
      }
      showOutingView(state, outingViewHandlers());
      if (wasOfflineSnapshot) initializeOutingMap();
      else {
        renderOutingRoutes(
          loaded.resource.participants,
          state.selectedOutingParticipantId,
        );
      }
      startOutingLiveExperience(slug);
      await persistOutingNetworkData(
        loaded,
        operation,
        () => currentOutingReconnect(operation),
      );
      if (!currentOutingReconnect(operation)) return false;
      setStatus("Outing reconnected. Live viewing resumed.");
      return true;
    } catch (error) {
      if (!currentOutingReconnect(operation)) return false;
      if (error?.code === "outing_not_found") {
        await Promise.allSettled([
          removeOfflineSnapshot("outing", slug),
          forgetRememberedParticipant(slug, { updateState: false }),
        ]);
        if (!currentOutingReconnect(operation)) return false;
        handleOutingClosed();
      } else if (transportFailure(error)) {
        setPwaNetworkStatus("offline");
      } else {
        setPwaNetworkStatus("online");
        reportError(error, "The outing could not be refreshed.");
      }
      return false;
    } finally {
      if (outingReconnectOperation === operation) {
        outingReconnectOperation = null;
      }
    }
  })();
  return operation.promise;
}

function currentLoadedOutingPage(operation) {
  return outingPageOperations.owns(operation)
    && state.outingSnapshot?.slug === operation.slug;
}

function currentOutingReconnect(operation) {
  return outingReconnectOperation === operation
    && operation.identity.epoch === outingPageEpoch
    && state.outingSnapshot?.slug === operation.identity.slug;
}

function onlineFallbackConfig(snapshot) {
  return { ...offlineMapConfig(null, snapshot), offline_mode: false };
}

async function persistOutingNetworkData(loaded, identity, isCurrent) {
  const actions = [
    () => refreshOfflineSnapshot("outing", loaded.resource),
  ];
  if (loaded.configFromNetwork) {
    actions.push(() => storePublicConfig(loaded.config));
  }
  const persisted = await settleOptionalPersistence(actions);
  if (!isCurrent(identity)) return;
  if (persisted.results[0].status === "fulfilled") {
    applyOfflineCopyRefresh(persisted.results[0].value);
  }
  if (persisted.failed) reportOptionalStorageFailure();
}

function initializeOutingMap() {
  initializeMap(state.config, {
    onReady: () => {
      callbacks?.onMapReady();
      renderOutingRoutes(
        state.outingSnapshot.participants,
        state.selectedOutingParticipantId,
      );
      fitOutingRoutes(state.outingSnapshot.participants);
      renderCurrentOutingLiveState();
    },
    onError: callbacks.showMapError,
    onViewportChange: () => {},
    onMapClick: () => {},
  });
}

export function outingMutationIsPending() {
  return outingMutationPending || positionStartPending;
}
