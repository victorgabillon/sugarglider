import { getConfig } from "./api.js";
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
  discardStaleParticipantReceipt,
} from "./outing_live_lifecycle.js";
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
  renderOutingLiveView,
  renderOutingReceipt,
  savedRouteSlugForOuting,
  setOutingMutationControls,
  showOutingView,
  triggerOutingDownload,
} from "./outing_view.js";
import { selectedCandidate, state } from "./state.js";

let callbacks = null;
let outingMutationPending = false;
let outingLiveConnection = null;
let outingLiveFreshnessTimer = null;
let outingLiveSession = null;
let outingTracker = null;
let lifecycleEventsBound = false;
const outingLiveLifecycle = createOutingLiveLifecycle();
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
  state.outingSnapshot = snapshot;
  discardStaleParticipantReceipt(state, snapshot, {
    shutdownTracker: () => outingTracker?.shutdown(),
    syncTrackerState: syncOutingTrackingState,
  });
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
  if (stopTracking) outingTracker?.shutdown();
  if (clearPositions) clearOutingLivePositions();
}

function handleOutingClosed(session = outingLiveSession) {
  if (session && !currentOutingLiveSession(session)) return;
  state.outingClosed = true;
  stopOutingLiveExperience({ stopTracking: true, clearPositions: true });
  state.outingLiveConnectionStatus = "outing_closed";
  state.outingLiveState = emptyOutingLiveState();
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
  });
  return outingTracker;
}

function syncOutingTrackingState() {
  if (!outingTracker) return;
  const tracking = outingTracker.status();
  state.outingTrackingStatus = tracking.status;
  state.outingTrackingActive = tracking.active;
  state.outingTrackingTransitionPending = tracking.transitionPending;
  state.outingTrackingClearFailed = tracking.clearingFailed;
  state.outingTrackingLastPublishedAt = tracking.lastPublishedAt;
  renderCurrentOutingLiveState();
}

function startCurrentOutingPositionSharing() {
  const receipt = state.outingParticipantReceipt;
  const outing = state.outingSnapshot;
  if (!receipt || !outing || receipt.slug !== outing.slug) return;
  const tracker = ensureOutingTracker();
  tracker.start(receipt, {
    available: Boolean(state.config?.outing_live_positions_available),
    currentPosition: livePositionForParticipant(
      state.outingLiveState,
      receipt.participant_id,
    ),
  });
  syncOutingTrackingState();
}

async function stopCurrentOutingPositionSharing() {
  const receipt = state.outingParticipantReceipt;
  if (!receipt) return;
  const tracker = ensureOutingTracker();
  await tracker.stop(receipt, { clearServer: true });
  syncOutingTrackingState();
}

function stopTrackerBeforeOutingMutation() {
  outingTracker?.shutdown();
  syncOutingTrackingState();
}

function prepareParticipantTracker() {
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
  window.addEventListener("online", () => outingTracker?.online());
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
    const created = await createOuting(title, displayName, savedSlug);
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
  };
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
  state.outingInviteToken = captureOutingInviteToken();
  [state.config, state.outingSnapshot] = await Promise.all([
    getConfig(),
    getOuting(slug),
  ]);
  state.outingDisplay = true;
  state.selectedOutingParticipantId = (
    state.outingSnapshot.participants[0]?.participant_id ?? null
  );
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
  startOutingLiveExperience(slug);
  setStatus(
    "Independent immutable participant routes loaded. Live viewing does not request location permission.",
  );
  window.addEventListener("resize", resizeMap);
}
