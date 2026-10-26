import { t, tr } from "./i18n.js";
import { escapeHtml, formatDistance, formatPercent } from "./format.js";

// Presentation only: IDs, array order, selection and measurements belong to the result.
export function routeColor(index, selected = false) {
  return selected ? "#214b3b" : ["#497c6c", "#5f6d91", "#7d6b52", "#596f63"][index % 4];
}

export function resultsNotice({ request, generationResult, resultsInvalidated }) {
  if (request.status === "running") return [t("Finding your routes…"), t("You can cancel in Plan. Your points and preferences are kept.")];
  if (resultsInvalidated) return [t("Your plan has changed"), t("Generate again to see routes for your current plan.")];
  if (request.status === "cancelled") return [t("Planning cancelled"), t("Your points and preferences are kept. Return to Plan when you’re ready to try again.")];
  if (request.status === "error") return [t("Couldn’t find routes this time"), t("Return to Plan to check your points and routing availability, then try again.")];
  if (generationResult) return [t("No matching route found"), t("Try changing the distance or your points in Plan. Your exact constraints have been kept.")];
  return [t("Your next route starts in Plan"), t("Choose a distance or the points to connect, then generate your routes.")];
}

export function routeChoiceMarkup(candidate, index, selected, count) {
  const repeated = candidate.route.analysis.repetition;
  const repetitions = repeated.available ? formatPercent(repeated.repeated_distance.share) : t("Unknown");
  const changedStops = candidate.approximated_stops.length + candidate.dropped_stops.length;
  return `<span class="candidate-choice-heading"><strong><i class="route-swatch${selected ? " solid" : ""}" style="--route-color:${routeColor(index, selected)}" aria-hidden="true"></i>${tr`Route ${candidate.rank}`}</strong><strong>${formatDistance(candidate.route.summary.distance_m)}</strong></span>
    <span class="route-comparison">${tr`${candidate.diagnostics.within_tolerance ? t("Within distance range") : t("Outside distance range")} · Repeated travel ${repetitions}`}</span>
    ${changedStops ? `<span class="route-stop-notice">${tr`${candidate.approximated_stops.length} nearby · ${candidate.dropped_stops.length} unvisited stops — see details`}</span>` : ""}
    <span class="candidate-choice-action">${selected ? t("✓ Selected") : t("Choose route")}${count > 1 && candidate.rank === 1 ? t(" · Recommended") : ""}</span>`;
}

export function renderRouteChoices(container, candidates, selectedId, onSelect) {
  // Render without losing keyboard focus when the authoritative selection changes.
  const document = container.ownerDocument;
  const focusedId = container.contains(document.activeElement) ? document.activeElement.dataset.candidateId : null;
  container.replaceChildren();
  candidates.forEach((candidate, index) => {
    const selected = candidate.id === selectedId;
    const card = document.createElement("article");
    card.className = `candidate-card${selected ? " selected" : ""}`;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "candidate-select";
    button.dataset.candidateId = candidate.id;
    button.setAttribute("aria-pressed", String(selected));
    button.setAttribute("aria-label", tr`Route ${candidate.rank}, ${formatDistance(candidate.route.summary.distance_m)}${selected ? t(", selected") : t(", choose route")}`);
    button.innerHTML = routeChoiceMarkup(candidate, index, selected, candidates.length);
    button.addEventListener("click", () => onSelect(candidate.id));
    card.append(button);
    container.append(card);
    if (candidate.id === focusedId) button.focus({ preventScroll: true });
  });
}

export function emptyResultsMarkup(state) {
  const [title, message] = resultsNotice(state);
  return `<div class="route-empty"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p></div>`;
}
