import { formatDistance, friendlyLabel } from "./format.js";
import { outingInviteUrl, publicOutingUrl } from "./outings.js";

const byId = (id) => document.getElementById(id);

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
  byId("join-outing").disabled = pending;
  byId("delete-outing").disabled = pending;
  byId("leave-outing").disabled = pending;
}

export function renderOutingReceipt(state) {
  const receipt = state.outingOwnerReceipt;
  const panel = byId("outing-receipt-panel");
  panel.classList.toggle("hidden", !receipt);
  if (!receipt) return;
  byId("create-outing-form").classList.add("hidden");
  byId("outing-public-link").value = publicOutingUrl(receipt);
  byId("outing-invite-link").value = outingInviteUrl(receipt);
  byId("share-outing-invite").classList.toggle(
    "hidden",
    typeof navigator.share !== "function",
  );
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
  renderParticipantCards(state, handlers.select);
  byId("join-outing-form").classList.toggle(
    "hidden",
    !state.outingInviteToken,
  );
  const own = state.outingParticipantReceipt;
  byId("outing-participant-actions").classList.toggle(
    "hidden",
    !own || own.slug !== outing.slug,
  );
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
}

function renderParticipantCards(state, onSelect) {
  const cards = byId("outing-participant-cards");
  cards.replaceChildren();
  state.outingSnapshot.participants.forEach((participant, index) => {
    const candidate = participant.planned_route.candidate;
    const request = participant.planned_route.source_request;
    const selected = (
      participant.participant_id === state.selectedOutingParticipantId
    );
    const card = document.createElement("button");
    card.type = "button";
    card.className = `outing-participant-card${selected ? " selected" : ""}`;
    card.setAttribute("aria-pressed", String(selected));
    card.addEventListener(
      "click",
      () => onSelect(participant.participant_id),
    );
    const name = document.createElement("strong");
    name.textContent = participant.display_name;
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
    card.append(name, order, route, facts);
    cards.append(card);
  });
}
