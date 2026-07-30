import { formatDistance, friendlyLabel } from "./format.js";
import { outingParticipantColor } from "./map.js";
import {
  estimatedServerNow,
  liveFreshness,
  livePositionForParticipant,
  visibleLivePositions,
} from "./outing_live_state.js";
import { participantReceiptBelongsToOuting } from "./outing_live_lifecycle.js";
import { publicOutingUrl } from "./outings.js";

const byId = (id) => document.getElementById(id);
let participantSelectHandler = null;

export function savedRouteSlugForOuting(state) {
  return state.savedRouteReceipt?.slug ?? state.savedRouteSnapshot?.slug ?? null;
}

export function renderOutingCreationAction(state) {
  const slug = savedRouteSlugForOuting(state);
  const available = Boolean(
    state.config?.outings_available
    && state.config?.saved_routes_available
    && slug
    && !["running", "reversing"].includes(state.request.status),
  );
  byId("show-create-outing").classList.toggle("hidden", !slug);
  byId("show-create-outing").disabled = !available;
  byId("create-outing").disabled = !available;
}

export function setOutingMutationControls(state, pending) {
  renderOutingCreationAction(state);
  if (pending) {
    byId("show-create-outing").disabled = true;
    byId("create-outing").disabled = true;
  }
  byId("join-outing").disabled = pending || state.outingClosed;
  byId("delete-outing").disabled = pending;
  byId("delete-outing-owner-view").disabled = (
    pending || state.outingClosed
  );
  byId("leave-outing").disabled = pending || state.outingClosed;
}

export function renderOutingReceipt(state) {
  const receipt = state.outingOwnerReceipt;
  const panel = byId("outing-receipt-panel");
  panel.classList.toggle("hidden", !receipt);
  if (!receipt) return;
  byId("create-outing-form").classList.add("hidden");
  byId("outing-public-link").value = publicOutingUrl(receipt);
  byId("outing-invite-link").value = (
    "Private invitation link kept only in this tab's memory"
  );
  byId("share-outing-invite").classList.toggle(
    "hidden",
    typeof navigator.share !== "function",
  );
  byId("open-outing-live-here").classList.remove("hidden");
}

export function bindOutingCreationControls(handlers) {
  byId("show-create-outing").addEventListener("click", () => {
    byId("create-outing-form").classList.toggle("hidden");
    if (!byId("create-outing-form").classList.contains("hidden")) {
      byId("outing-title").focus();
    }
  });
  byId("create-outing-form").addEventListener("submit", (event) => {
    event.preventDefault();
    handlers.create(
      byId("outing-title").value,
      byId("outing-creator-name").value,
    );
  });
  byId("open-outing").addEventListener("click", handlers.open);
  byId("open-outing-live-here").addEventListener("click", handlers.openHere);
  byId("copy-outing-public-link").addEventListener("click", handlers.copyPublic);
  byId("copy-outing-invite-link").addEventListener("click", handlers.copyInvite);
  byId("share-outing-invite").addEventListener("click", handlers.shareInvite);
  byId("delete-outing").addEventListener("click", handlers.delete);
  byId("dismiss-outing").addEventListener("click", handlers.dismiss);
}

export function prepareOutingPage() {
  byId("planner-empty").classList.add("hidden");
}

export function triggerOutingDownload({ blob, filename }) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function showOutingView(state, handlers) {
  const outing = state.outingSnapshot;
  if (!outing) return;
  document.body.classList.add("outing-mode");
  byId("outing-view-panel").classList.remove("hidden");
  byId("saved-route-panel").classList.add("hidden");
  byId("outing-receipt-panel").classList.add("hidden");
  byId("outing-view-title").textContent = outing.title;
  byId("outing-view-summary").textContent = (
    `${outing.participants.length} of ${outing.max_participants} participants · `
    + `available until ${new Date(outing.expires_at).toLocaleString()}`
  );
  participantSelectHandler = handlers.select;
  renderParticipantCardsStructure(state, handlers.select);
  byId("join-outing-form").classList.toggle(
    "hidden",
    !state.outingInviteToken,
  );
  const own = state.outingParticipantReceipt;
  const hasParticipantReceipt = participantReceiptBelongsToOuting(own, outing);
  byId("outing-participant-actions").classList.toggle(
    "hidden",
    !hasParticipantReceipt,
  );
  const owner = state.outingOwnerReceipt;
  byId("outing-owner-actions").classList.toggle(
    "hidden",
    state.outingClosed || !owner || owner.slug !== outing.slug,
  );
  byId("join-outing").disabled = state.outingClosed;
  byId("leave-outing").disabled = state.outingClosed;
  byId("delete-outing-owner-view").disabled = state.outingClosed;
  byId("metrics-title").textContent = "Participant route details";
  byId("search-summary").textContent = (
    `${outing.participants.length} independent immutable route snapshot`
    + `${outing.participants.length === 1 ? "" : "s"} · search diagnostics not applicable`
  );
  byId("join-outing-form").onsubmit = (event) => {
    event.preventDefault();
    handlers.join(
      byId("outing-join-name").value,
      byId("outing-join-route").value,
    );
  };
  byId("download-my-outing-gpx").onclick = handlers.downloadMine;
  byId("leave-outing").onclick = handlers.leave;
  byId("delete-outing-owner-view").onclick = handlers.deleteOwner;
  byId("start-outing-live-sharing").onclick = handlers.startSharing;
  byId("stop-outing-live-sharing").onclick = handlers.stopSharing;
  renderOutingLiveView(state);
}

export function renderOutingLiveView(state) {
  const panel = byId("outing-live-panel");
  const outing = state.outingSnapshot;
  panel.classList.toggle("hidden", !outing);
  if (!outing) return;
  const available = Boolean(state.config?.outing_live_positions_available);
  const serverNow = estimatedServerNow(state.outingLiveState);
  const visible = visibleLivePositions(state.outingLiveState, serverNow);
  const freshCount = visible.filter(
    (position) => liveFreshness(position, serverNow) === "fresh",
  ).length;
  const staleCount = visible.length - freshCount;
  byId("outing-live-connection").textContent = connectionLabel(
    state.outingClosed
      ? "outing_closed"
      : available
        ? state.outingLiveConnectionStatus
        : "unavailable",
  );
  byId("outing-live-summary").textContent = (
    `${visible.length} currently shared position`
    + `${visible.length === 1 ? "" : "s"}`
    + ` · ${freshCount} Live · ${staleCount} Stale`
  );

  const receipt = state.outingParticipantReceipt;
  const hasParticipantReceipt = participantReceiptBelongsToOuting(
    receipt,
    outing,
  );
  const ownsParticipant = Boolean(
    available
    && !state.outingClosed
    && hasParticipantReceipt,
  );
  const controls = byId("outing-live-own-controls");
  controls.classList.toggle("hidden", !ownsParticipant);
  const ownPosition = ownsParticipant
    ? livePositionForParticipant(
      state.outingLiveState,
      receipt.participant_id,
    )
    : null;
  const start = byId("start-outing-live-sharing");
  const stop = byId("stop-outing-live-sharing");
  start.classList.toggle("hidden", !ownsParticipant || state.outingTrackingActive);
  start.disabled = (
    !ownsParticipant
    || state.outingTrackingActive
    || state.outingTrackingTransitionPending
    || state.outingTrackingStatus === "unsupported"
  );
  const canStop = Boolean(
    ownsParticipant
    && (
      state.outingTrackingActive
      || ownPosition
      || state.outingTrackingClearFailed
    ),
  );
  stop.classList.toggle("hidden", !canStop);
  stop.disabled = state.outingTrackingTransitionPending;
  byId("outing-live-tracking-status").textContent = ownsParticipant
    ? state.outingTrackingMessage
    : "Viewer mode — position sharing controls require an in-memory participant receipt.";
  updateParticipantCards(state);
}

function renderParticipantCardsStructure(state, onSelect) {
  if (onSelect) participantSelectHandler = onSelect;
  const cards = byId("outing-participant-cards");
  cards.replaceChildren();
  const serverNow = estimatedServerNow(state.outingLiveState);
  state.outingSnapshot.participants.forEach((participant, index) => {
    const candidate = participant.planned_route.candidate;
    const request = participant.planned_route.source_request;
    const selected = (
      participant.participant_id === state.selectedOutingParticipantId
    );
    const card = document.createElement("button");
    card.type = "button";
    card.className = `outing-participant-card${selected ? " selected" : ""}`;
    card.dataset.participantId = participant.participant_id;
    card.setAttribute("aria-pressed", String(selected));
    if (participantSelectHandler) {
      card.addEventListener(
        "click",
        () => participantSelectHandler(participant.participant_id),
      );
    }
    const heading = document.createElement("span");
    heading.className = "outing-participant-heading";
    const swatch = document.createElement("i");
    swatch.className = "outing-participant-swatch";
    swatch.style.backgroundColor = outingParticipantColor(index);
    const name = document.createElement("strong");
    name.textContent = participant.display_name;
    heading.append(swatch, name);
    const order = document.createElement("span");
    order.textContent = `Participant ${index + 1}`;
    const route = document.createElement("span");
    route.textContent = candidate.route.name;
    const facts = document.createElement("span");
    facts.textContent = [
      friendlyLabel(candidate.routing_profile),
      friendlyLabel(request.topology),
      formatDistance(candidate.route.summary.distance_m),
    ].join(" · ");
    const live = participantLiveDescription(
      livePositionForParticipant(
        state.outingLiveState,
        participant.participant_id,
      ),
      serverNow,
    );
    const liveStatus = document.createElement("span");
    liveStatus.className = `outing-participant-live ${live.className}`;
    liveStatus.textContent = live.status;
    const liveFacts = document.createElement("span");
    liveFacts.className = "outing-participant-live-facts";
    liveFacts.textContent = live.details;
    card.append(heading, order, route, facts, liveStatus, liveFacts);
    cards.append(card);
  });
}

function updateParticipantCards(state) {
  const serverNow = estimatedServerNow(state.outingLiveState);
  byId("outing-participant-cards")
    .querySelectorAll(".outing-participant-card")
    .forEach((card) => {
      const participantId = card.dataset.participantId;
      const selected = participantId === state.selectedOutingParticipantId;
      card.classList.toggle("selected", selected);
      card.setAttribute("aria-pressed", String(selected));
      const live = participantLiveDescription(
        livePositionForParticipant(state.outingLiveState, participantId),
        serverNow,
      );
      const status = card.querySelector(".outing-participant-live");
      status.className = `outing-participant-live ${live.className}`;
      status.textContent = live.status;
      card.querySelector(".outing-participant-live-facts").textContent = (
        live.details
      );
    });
}

function participantLiveDescription(position, serverNow) {
  const freshness = liveFreshness(position, serverNow);
  if (!position || freshness === "expired") {
    return {
      className: "not-sharing",
      status: "Not sharing",
      details: "No current position",
    };
  }
  return {
    className: freshness,
    status: freshness === "fresh" ? "Live" : "Stale",
    details: (
      `Accuracy ±${Math.round(position.accuracy_m)} m`
      + ` · updated ${relativeAge(position.received_at, serverNow)}`
    ),
  };
}

function relativeAge(timestamp, serverNow) {
  const ageSeconds = Math.max(
    0,
    Math.floor((serverNow - Date.parse(timestamp)) / 1_000),
  );
  if (ageSeconds < 10) return "just now";
  if (ageSeconds < 60) return `${ageSeconds} seconds ago`;
  const minutes = Math.floor(ageSeconds / 60);
  return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
}

function connectionLabel(status) {
  return {
    open: "Live",
    connecting: "Connecting",
    reconnecting: "Reconnecting",
    unavailable: "Live updates unavailable",
    outing_closed: "Outing closed",
    closed: "Live updates unavailable",
  }[status] ?? "Live updates unavailable";
}
