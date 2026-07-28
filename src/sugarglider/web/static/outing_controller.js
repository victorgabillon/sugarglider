import { getConfig } from "./api.js";
import {
  fitOutingRoutes,
  initializeMap,
  renderOutingRoutes,
  resizeMap,
} from "./map.js";
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
  renderOutingReceipt,
  savedRouteSlugForOuting,
  setOutingMutationControls,
  showOutingView,
  triggerOutingDownload,
} from "./outing_view.js";
import { selectedCandidate, state } from "./state.js";

let callbacks = null;
let outingMutationPending = false;

function reportError(error, fallback) {
  callbacks?.handleError(error, fallback);
}

function setStatus(message) {
  callbacks?.setStatus(message);
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
  try {
    await deleteOuting(receipt.slug, receipt.owner_token);
    state.outingOwnerReceipt = null;
    renderOutingReceipt(state);
    setStatus("Outing deleted.");
  } catch (error) {
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
  showOutingView(state, outingViewHandlers());
  callbacks?.renderMetrics();
  renderOutingRoutes(
    state.outingSnapshot.participants,
    state.selectedOutingParticipantId,
  );
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
    state.outingSnapshot = joined.outing;
    state.outingParticipantReceipt = {
      slug: outing.slug,
      participant_id: joined.participant_id,
      participant_token: joined.participant_token,
    };
    state.outingInviteToken = null;
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
  try {
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
    callbacks?.renderMetrics();
  } catch (error) {
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
  };
}

export function bindOutingController(nextCallbacks) {
  callbacks = nextCallbacks;
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
    },
    onError: callbacks.showMapError,
    onViewportChange: () => {},
    onMapClick: () => {},
  });
  showOutingView(state, outingViewHandlers());
  callbacks.renderMetrics();
  prepareOutingPage();
  setStatus(
    "Independent immutable participant routes loaded without generation or rerouting.",
  );
  window.addEventListener("resize", resizeMap);
}
