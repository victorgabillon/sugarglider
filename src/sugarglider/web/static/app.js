import { ApiError, exportRoute, generateRoutes, getConfig, visualizeRoute } from "./api.js";
import { constructionLabel, escapeHtml, formatCount, formatDistance, formatPercent, friendlyLabel, lowOverlapLabel, metricRows } from "./format.js";
import { parseGpx } from "./gpx.js";
import { createIcon, decorateIcons } from "./icons.js";
import { clearRoutes, fitCoordinates, initializeMap, renderCandidates, renderImportedGpx, renderOptionalMarkers, renderRequiredMarkers, renderVisualization, resizeMap } from "./map.js";
import { currentRequest, invalidateCandidates, pointDisplayName, selectedCandidate, state } from "./state.js";

const byId = (id) => document.getElementById(id);
let elapsedTimer = null;
let mapReady = false;

function showError(message, details = "") {
  byId("error-message").textContent = message;
  byId("error-details").textContent = details;
  byId("error-banner").classList.remove("hidden");
}

function hideError() { byId("error-banner").classList.add("hidden"); }

function showMapError(message) {
  byId("map-error-message").textContent = message;
  byId("map-error").classList.remove("hidden");
}

function updateOptionsFromControls() {
  state.options = {
    name: byId("route-name").value.trim() || "Sugarglider route",
    targetDistanceKm: Number(byId("target-distance").value),
    toleranceKm: Number(byId("tolerance").value),
    candidateCount: Number(byId("candidate-count").value),
    seed: Number(byId("seed").value),
    pointOrderMode: byId("point-order-mode").value,
    pathSelectionMode: byId("path-selection-mode").value,
    naturePreference: byId("nature-preference").value,
  };
}

function updateControlsFromOptions() {
  byId("route-name").value = state.options.name;
  byId("target-distance").value = state.options.targetDistanceKm;
  byId("tolerance").value = state.options.toleranceKm;
  byId("candidate-count").value = state.options.candidateCount;
  byId("seed").value = state.options.seed;
  byId("point-order-mode").value = state.options.pointOrderMode;
  byId("path-selection-mode").value = state.options.pathSelectionMode;
  byId("nature-preference").value = state.options.naturePreference;
}

function validPoint(point) {
  return Number.isFinite(point.lat)
    && Number.isFinite(point.lon)
    && Math.abs(point.lat) <= 90
    && Math.abs(point.lon) <= 180;
}

function pointValidation() {
  for (let index = 1; index < state.points.length; index += 1) {
    const previous = state.points[index - 1];
    const current = state.points[index];
    if (previous.lat === current.lat && previous.lon === current.lon) {
      return `Points ${index} and ${index + 1} have identical adjacent coordinates.`;
    }
  }
  if (state.points.some((point) => !validPoint(point))) {
    return "Every point needs valid latitude and longitude coordinates.";
  }
  return "";
}

function invalidateAndRender() {
  if (state.request.status === "running") {
    state.abortController?.abort();
    state.request = {
      status: "cancelled",
      id: state.request.id + 1,
      startedAt: null,
    };
    state.abortController = null;
    window.clearInterval(elapsedTimer);
    byId("request-status").textContent = "Generation cancelled because the route changed.";
  }
  invalidateCandidates();
  clearRoutes();
  if (state.selectedPointIndex !== null && state.selectedPointIndex >= state.points.length) {
    state.selectedPointIndex = state.points.length ? state.points.length - 1 : null;
  }
  render();
}

function iconButton(action, icon, label, disabled = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.action = action;
  button.disabled = disabled;
  button.setAttribute("aria-label", label);
  button.title = label;
  button.append(createIcon(icon));
  button.addEventListener("click", (event) => event.stopPropagation());
  return button;
}

function candidateVisitOrders() {
  const candidate = selectedCandidate();
  return new Map(
    (candidate?.required_point_order ?? []).map((visit, index) => [
      visit.original_index,
      index + 1,
    ]),
  );
}

function updatePoiSelection(scrollSelected = false) {
  const list = byId("poi-list");
  list.querySelectorAll(".poi-row").forEach((row) => {
    const selected = Number(row.dataset.pointIndex) === state.selectedPointIndex;
    row.classList.toggle("selected", selected);
    if (selected) row.setAttribute("aria-current", "true");
    else row.removeAttribute("aria-current");
    if (selected && scrollSelected) {
      const rowTop = row.offsetTop;
      const rowBottom = rowTop + row.offsetHeight;
      if (rowTop < list.scrollTop) list.scrollTop = rowTop;
      else if (rowBottom > list.scrollTop + list.clientHeight) {
        list.scrollTop = rowBottom - list.clientHeight;
      }
    }
  });
}

function selectPoint(index, { scrollSelected = false, requestPopup = false } = {}) {
  if (!Number.isInteger(index) || index < 0 || index >= state.points.length) return;
  state.selectedPointIndex = index;
  if (requestPopup) state.pendingPointPopupIndex = index;
  updatePoiSelection(scrollSelected);
  renderMapData();
}

function renderPoiEditor() {
  const list = byId("poi-list");
  const visitOrders = candidateVisitOrders();
  list.replaceChildren();
  state.points.forEach((point, index) => {
    const visitOrder = visitOrders.get(index) ?? index + 1;
    const row = document.createElement("div");
    row.className = `poi-row${index === 0 ? " start" : ""}${index === state.selectedPointIndex ? " selected" : ""}${validPoint(point) ? "" : " invalid"}`;
    row.dataset.pointIndex = String(index);
    row.tabIndex = 0;
    row.role = "listitem";
    if (index === state.selectedPointIndex) row.setAttribute("aria-current", "true");

    const identity = document.createElement("div");
    identity.className = "poi-identity";
    const number = document.createElement("span");
    number.className = "poi-number";
    number.textContent = String(visitOrder);
    identity.append(number);
    if (index === 0) {
      const start = document.createElement("span");
      start.className = "poi-start-label";
      start.textContent = "Start/end";
      identity.append(start);
    }

    const main = document.createElement("div");
    main.className = "poi-main";
    const name = document.createElement("strong");
    name.className = "poi-name";
    name.textContent = pointDisplayName(point, index);
    main.append(name);
    const fields = document.createElement("div");
    fields.className = "poi-fields";
    const fieldDefinitions = [
      ["name", "Edit point name", "text", point.name ?? ""],
      ["lat", "Latitude", "number", point.lat],
      ["lon", "Longitude", "number", point.lon],
    ];
    fieldDefinitions.forEach(([field, labelText, type, value]) => {
      const label = document.createElement("label");
      if (field === "name") label.className = "name";
      label.textContent = labelText;
      const input = document.createElement("input");
      input.dataset.field = field;
      input.type = type;
      input.value = String(value);
      if (field === "name") input.maxLength = 120;
      if (field === "lat") { input.min = "-90"; input.max = "90"; input.step = "0.000001"; }
      if (field === "lon") { input.min = "-180"; input.max = "180"; input.step = "0.000001"; }
      input.addEventListener("focus", () => selectPoint(index));
      input.addEventListener("change", () => {
        state.points[index] = {
          ...state.points[index],
          [field]: field === "name" ? input.value : Number(input.value),
        };
        invalidateAndRender();
      });
      label.append(input);
      fields.append(label);
    });
    main.append(fields);
    const metadata = document.createElement("div");
    metadata.className = "poi-meta";
    const originalIndex = Number.isInteger(point.originalIndex) ? point.originalIndex : index;
    metadata.textContent = visitOrder === index + 1
      ? `Original request point ${originalIndex + 1}`
      : `Request position ${index + 1} · optimized visit ${visitOrder} · original ${originalIndex + 1}`;
    main.append(metadata);

    const actions = document.createElement("div");
    actions.className = "poi-actions";
    const up = iconButton("up", "up", `Move ${pointDisplayName(point, index)} up`, index === 0);
    const down = iconButton("down", "down", `Move ${pointDisplayName(point, index)} down`, index === state.points.length - 1);
    const remove = iconButton("remove", "delete", `Remove ${pointDisplayName(point, index)}`);
    up.addEventListener("click", () => movePoint(index, index - 1));
    down.addEventListener("click", () => movePoint(index, index + 1));
    remove.addEventListener("click", () => removePoint(index));
    actions.append(up, down, remove);

    row.addEventListener("click", (event) => {
      if (event.target.closest("input, button, label")) return;
      selectPoint(index, { requestPopup: true });
    });
    row.addEventListener("keydown", (event) => {
      if (event.target !== row) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const delta = event.key === "ArrowDown" ? 1 : -1;
        const next = Math.max(0, Math.min(state.points.length - 1, index + delta));
        selectPoint(next, { scrollSelected: true });
        byId("poi-list").querySelector(`[data-point-index="${next}"]`)?.focus();
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectPoint(index, { requestPopup: true });
      }
    });
    row.append(identity, main, actions);
    list.append(row);
  });
  byId("poi-count").textContent = `${state.points.length} / ${state.config?.max_required_points ?? 30}`;
  byId("poi-validation").textContent = pointValidation();
}

function movePoint(from, to) {
  if (to < 0 || to >= state.points.length) return;
  const selectedPoint = state.selectedPointIndex === null ? null : state.points[state.selectedPointIndex];
  const [point] = state.points.splice(from, 1);
  state.points.splice(to, 0, point);
  state.selectedPointIndex = selectedPoint ? state.points.indexOf(selectedPoint) : null;
  invalidateAndRender();
}

function removePoint(index) {
  const selectedPoint = state.selectedPointIndex === null ? null : state.points[state.selectedPointIndex];
  state.points.splice(index, 1);
  if (selectedPoint && state.points.includes(selectedPoint)) {
    state.selectedPointIndex = state.points.indexOf(selectedPoint);
  } else {
    state.selectedPointIndex = state.points.length ? Math.min(index, state.points.length - 1) : null;
  }
  invalidateAndRender();
}

function renderMapData() {
  if (!mapReady) return;
  const candidate = selectedCandidate();
  const popupIndex = state.pendingPointPopupIndex;
  state.pendingPointPopupIndex = null;
  renderRequiredMarkers(
    state.points,
    candidate?.required_point_order,
    state.selectedPointIndex,
    popupIndex,
    state.request.status === "running",
    {
      onDrag: (index, coordinate) => {
        state.points[index] = { ...state.points[index], ...coordinate };
        state.selectedPointIndex = index;
        invalidateAndRender();
      },
      onActivate: (index) => selectPoint(index, {
        scrollSelected: true,
        requestPopup: true,
      }),
    },
  );
  renderOptionalMarkers(candidate?.optional_points ?? []);
  renderImportedGpx(state.importedGpx);
  renderCandidates(
    state.generationResult?.candidates ?? [],
    state.selectedSignature,
    state.showAllCandidates,
    selectCandidate,
  );
  renderVisualization(
    candidate ? state.visualizationCache.get(candidate.signature) ?? null : null,
    state.showNatureContext,
  );
}

function candidateBadges(candidate, search) {
  const values = [];
  if (candidate.rank === 1) values.push('<span class="badge recommended">Recommended</span>');
  values.push(`<span class="badge ${candidate.within_tolerance ? "good" : "warn"}">${candidate.within_tolerance ? "Within tolerance" : "Outside tolerance"}</span>`);
  if (search.low_overlap_requested) values.push(`<span class="badge">${escapeHtml(lowOverlapLabel(candidate))}</span>`);
  return values.join("");
}

function metricBar(label, share, className, displayValue) {
  if (share === null || share === undefined) {
    return `<div class="bar-metric ${className} not-evaluated"><div class="bar-heading"><span>${escapeHtml(label)}</span><strong>not evaluated</strong></div><div class="metric-track" aria-hidden="true"></div></div>`;
  }
  const percentage = Math.max(0, Math.min(100, Number(share) * 100));
  return `<div class="bar-metric ${className}"><div class="bar-heading"><span>${escapeHtml(label)}</span><strong>${escapeHtml(displayValue)}</strong></div><div class="metric-track" role="img" aria-label="${escapeHtml(`${label}: ${displayValue}`)}"><div class="metric-fill" style="--metric-value:${percentage.toFixed(3)}%"></div></div></div>`;
}

function renderCandidatesPanel() {
  const container = byId("candidate-list");
  const result = state.generationResult;
  if (!result?.candidates.length) {
    container.innerHTML = '<p class="empty-copy">Returned routes will appear here in ranked order.</p>';
    byId("search-summary").textContent = result ? friendlyLabel(result.search.status) : "";
    return;
  }
  byId("search-summary").textContent = `${friendlyLabel(result.search.status)} · ${result.candidates.length} returned`;
  container.replaceChildren();
  result.candidates.forEach((candidate) => {
    const analysis = candidate.route.analysis;
    const nature = analysis.nature;
    const repeatedDistance = analysis.repetition.repeated_distance.distance_m;
    const nonImmediate = Math.max(repeatedDistance - analysis.immediate_backtrack.distance_m, 0);
    const nonImmediateShare = candidate.route.summary.distance_m > 0
      ? nonImmediate / candidate.route.summary.distance_m
      : 0;
    const selected = candidate.signature === state.selectedSignature;
    const card = document.createElement("article");
    card.className = `candidate-card${selected ? " selected" : ""}${candidate.rank === 1 ? " recommended" : ""}`;
    card.setAttribute("aria-label", `Candidate ${candidate.rank}${candidate.rank === 1 ? ", recommended" : ""}`);

    const selector = document.createElement("button");
    selector.type = "button";
    selector.className = "candidate-select";
    selector.setAttribute("aria-pressed", String(selected));
    selector.setAttribute("aria-label", `Select candidate ${candidate.rank}, ${formatDistance(candidate.route.summary.distance_m)}`);
    selector.innerHTML = `<div class="candidate-title"><h3>Candidate ${candidate.rank}</h3><strong>${formatDistance(candidate.route.summary.distance_m)}</strong></div><div class="candidate-badges">${candidateBadges(candidate, result.search)}</div><p class="candidate-construction">${escapeHtml(constructionLabel(candidate.construction))}</p><div class="candidate-key-metrics"><span>Target error</span><strong>${formatDistance(candidate.target_error_m)}</strong><span>Other repetition</span><strong>${formatDistance(nonImmediate)} · ${formatPercent(nonImmediateShare)}</strong><span>Major road</span><strong>${formatPercent(analysis.major_road.share)}</strong></div>${metricBar("Total repetition", analysis.repetition.repeated_distance.share, "repetition", formatPercent(analysis.repetition.repeated_distance.share))}${metricBar("Immediate backtracking", analysis.immediate_backtrack.share, "backtrack", formatPercent(analysis.immediate_backtrack.share))}${metricBar("Trail-like", analysis.trail_like.share, "trail", formatPercent(analysis.trail_like.share))}${metricBar("Paved", analysis.paved.share, "paved", formatPercent(analysis.paved.share))}${metricBar("Mapped nature", nature ? nature.nature_score / 100 : null, "nature", nature ? `${nature.nature_score.toFixed(1)} / 100` : "not evaluated")}`;
    selector.addEventListener("click", () => selectCandidate(candidate.signature));
    card.append(selector);

    const warningCodes = [...new Set([
      ...result.search.warnings,
      ...analysis.warnings,
      ...(nature?.warnings ?? []),
    ])];
    if (warningCodes.length) {
      const warnings = document.createElement("ul");
      warnings.className = "card-warnings";
      warningCodes.forEach((warning) => {
        const item = document.createElement("li");
        item.textContent = friendlyLabel(warning);
        warnings.append(item);
      });
      card.append(warnings);
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "Raw warning codes";
      const code = document.createElement("code");
      code.textContent = warningCodes.join("\n");
      details.append(summary, code);
      card.append(details);
    }
    container.append(card);
  });
}

function section(title, rows) {
  return `<section><h3>${escapeHtml(title)}</h3>${metricRows(rows)}</section>`;
}

function natureSection(nature, search) {
  if (!nature) {
    return section("Mapped nature context", [
      ["Index available", search.nature_index_available ? "Yes" : "No"],
      ["Nature analysis", "not evaluated"],
    ]) + '<p class="context-note">Nature metrics are not zero: they were not evaluated because the local OSM nature index or analysis was unavailable.</p>';
  }
  const breakdown = nature.score_breakdown;
  const component = (value) => `${value.points >= 0 ? "+" : ""}${value.points.toFixed(1)} points · weight ${value.weight.toFixed(2)} × ${formatPercent(value.share)}`;
  const waterBuffer = state.config?.nature_water_buffer_m ?? 100;
  const warnings = nature.warnings.map((warning) => friendlyLabel(warning)).join("; ") || "None";
  return section("Mapped nature context", [
    ["Nature score", `${nature.nature_score.toFixed(1)} / 100`],
    ["Base score", breakdown.base_score.toFixed(1)],
    ["Woodland reward", component(breakdown.woodland_reward)],
    ["Open-natural reward", component(breakdown.open_natural_reward)],
    ["Agriculture reward", component(breakdown.agriculture_reward)],
    ["Park/protected reward", component(breakdown.park_or_protected_reward)],
    ["Near-water reward", component(breakdown.near_water_reward)],
    ["Urban penalty", component(breakdown.urban_penalty)],
    ["Unknown penalty", component(breakdown.unknown_penalty)],
    ["Woodland", `${formatDistance(nature.woodland.distance_m)} · ${formatPercent(nature.woodland.share)}`],
    ["Open natural", `${formatDistance(nature.open_natural.distance_m)} · ${formatPercent(nature.open_natural.share)}`],
    ["Agriculture", `${formatDistance(nature.agriculture.distance_m)} · ${formatPercent(nature.agriculture.share)}`],
    ["Water crossing", `${formatDistance(nature.water_crossing.distance_m)} · ${formatPercent(nature.water_crossing.share)}`],
    ["Urban/developed", `${formatDistance(nature.urban.distance_m)} · ${formatPercent(nature.urban.share)}`],
    ["Unknown land cover", `${formatDistance(nature.unknown_landcover.distance_m)} · ${formatPercent(nature.unknown_landcover.share)}`],
    ["Park or protected", `${formatDistance(nature.park_or_protected.distance_m)} · ${formatPercent(nature.park_or_protected.share)}`],
    [`Within ${waterBuffer} m of mapped water`, `${formatDistance(nature.near_water.distance_m)} · ${formatPercent(nature.near_water.share)}`],
    ["Nature warnings", warnings],
    ["Index features", formatCount(nature.index_feature_count)],
  ]) + '<p class="context-note">Derived from local OpenStreetMap polygons. Unknown means unmapped or outside the index. Near water describes proximity to mapped water, not a water view. Protected-area tags do not guarantee public access. The score describes mapped environmental context—not beauty, biodiversity, accessibility, or safety.</p>';
}

function renderMetrics() {
  const candidate = selectedCandidate();
  const result = state.generationResult;
  byId("metrics-empty").classList.toggle("hidden", Boolean(candidate));
  byId("metrics-content").classList.toggle("hidden", !candidate);
  byId("download-gpx").disabled = !candidate || state.request.status === "running";
  if (!candidate || !result) return;
  const analysis = candidate.route.analysis;
  const search = result.search;
  const otherRepeated = Math.max(
    analysis.repetition.repeated_distance.distance_m - analysis.immediate_backtrack.distance_m,
    0,
  );
  const nullable = (value, formatter = formatPercent) => value === null || value === undefined
    ? "Not evaluated"
    : formatter(value);
  const warningCodes = [...new Set([
    ...search.warnings,
    ...analysis.warnings,
    ...(analysis.nature?.warnings ?? []),
  ])];
  const warnings = warningCodes
    .map((warning) => `<li>${escapeHtml(friendlyLabel(warning))}</li>`)
    .join("") || "<li>No route or search warnings.</li>";
  byId("metrics-content").innerHTML = section("Route", [
    ["Distance", formatDistance(candidate.route.summary.distance_m)],
    ["Target", formatDistance(search.target_distance_m)],
    ["Target error", formatDistance(candidate.target_error_m)],
    ["Tolerance", formatDistance(search.tolerance_m)],
    ["Construction", constructionLabel(candidate.construction)],
    ["Mandatory POIs", candidate.route.summary.input_point_count],
    ["Routing points", candidate.routing_points.length],
  ]) + section("Natural loop quality", [
    ["Total repeated", `${formatDistance(analysis.repetition.repeated_distance.distance_m)} · ${formatPercent(analysis.repetition.repeated_distance.share)}`],
    ["Immediate backtracking", `${formatDistance(analysis.immediate_backtrack.distance_m)} · ${formatPercent(analysis.immediate_backtrack.share)}`],
    ["Non-immediate repeated", formatDistance(otherRepeated)],
    ["Repeated edge-ID coverage", formatPercent(analysis.repetition.edge_id_coverage.share)],
    ["Backtracking coverage", formatPercent(analysis.backtrack_edge_id_coverage.share)],
  ]) + section("Trail quality", [
    ["Paved", `${formatDistance(analysis.paved.distance_m)} · ${formatPercent(analysis.paved.share)}`],
    ["Unpaved", `${formatDistance(analysis.unpaved.distance_m)} · ${formatPercent(analysis.unpaved.share)}`],
    ["Unknown surface", `${formatDistance(analysis.unknown_surface.distance_m)} · ${formatPercent(analysis.unknown_surface.share)}`],
    ["Trail-like", formatPercent(analysis.trail_like.share)],
    ["Official hiking network", formatPercent(analysis.official_hiking_network.share)],
    ["Major roads", formatPercent(analysis.major_road.share)],
    ["Car-accessible", formatDistance(analysis.car_accessible.distance_m)],
  ]) + natureSection(analysis.nature, search) + section("Search diagnostics", [
    ["Status", friendlyLabel(search.status)],
    ["Nature preference requested", search.nature_requested ? "Yes" : "No"],
    ["Nature index available", search.nature_index_available ? "Yes" : "No"],
    ["Nature index features", nullable(search.nature_index_feature_count, formatCount)],
    ["Recommended nature score", nullable(search.recommended_nature_score, (value) => `${Number(value).toFixed(1)} / 100`)],
    ["Best available nature score", nullable(search.best_available_nature_score, (value) => `${Number(value).toFixed(1)} / 100`)],
    ["Full-route evaluations", `${formatCount(search.evaluated_candidate_count)} / ${formatCount(search.search_budget)}`],
    ["Mandatory-order evaluations", search.evaluated_order_count],
    ["Alternative-leg requests", `${search.alternative_leg_request_count} / ${search.low_overlap_request_budget}`],
    ["Alternative paths", search.alternative_path_count],
    ["Refined sources", search.low_overlap_refined_source_count],
    ["Low-overlap candidates", search.low_overlap_candidate_count],
    ["Leg budget exhausted", search.low_overlap_budget_exhausted ? "Yes" : "No"],
    ["Pre-refinement repetition", nullable(search.pre_low_overlap_repeated_share)],
    ["Best low-overlap repetition", nullable(search.best_low_overlap_repeated_share)],
    ["Pre-refinement backtracking", nullable(search.pre_low_overlap_backtrack_share)],
    ["Best low-overlap backtracking", nullable(search.best_low_overlap_backtrack_share)],
  ]) + `<section><h3>Warnings</h3><ul class="warning-list">${warnings}</ul><details><summary>Raw warning codes</summary><pre>${escapeHtml(JSON.stringify({ search: search.warnings, route: analysis.warnings, nature: analysis.nature?.warnings ?? [] }, null, 2))}</pre></details></section>`;
}

function renderStatus() {
  const running = state.request.status === "running";
  byId("generate").disabled = running || state.points.length < 2 || Boolean(pointValidation());
  byId("generate-top").disabled = byId("generate").disabled;
  byId("cancel").classList.toggle("hidden", !running);
  byId("generation-state").classList.toggle("hidden", !running);
  document
    .querySelectorAll("#route-form input, #route-form select, #poi-list input, #poi-list button, #add-point-mode, #clear-points")
    .forEach((control) => { control.disabled = running; });
  byId("request-status").classList.toggle("running", running);
  if (!running && state.points.length < 2) {
    byId("request-status").textContent = "Add at least two mandatory points.";
  }
}

function renderEmptyState() {
  const hasWork = state.points.length > 0 || state.importedGpx || state.generationResult;
  byId("planner-empty").classList.toggle("hidden", Boolean(hasWork));
}

function render() {
  renderPoiEditor();
  renderCandidatesPanel();
  renderMetrics();
  renderStatus();
  renderMapData();
  renderEmptyState();
  const imported = state.importedGpx;
  byId("gpx-summary").classList.toggle("hidden", !imported);
  if (imported) {
    byId("gpx-details").textContent = `${imported.filename} · ${formatCount(imported.pointCount)} trackpoints · ${formatDistance(imported.distanceM)} locally calculated`;
  }
}

async function selectCandidate(signature) {
  if (!state.generationResult?.candidates.some((candidate) => candidate.signature === signature)) return;
  state.selectedSignature = signature;
  render();
  const candidate = selectedCandidate();
  if (!candidate) return;
  try {
    let visualization = state.visualizationCache.get(signature);
    if (!visualization) {
      visualization = await visualizeRoute(candidate.route);
      if (!state.generationResult?.candidates.some((current) => current.signature === signature)) return;
      state.visualizationCache.set(signature, visualization);
    }
    if (state.selectedSignature === signature) {
      renderVisualization(visualization, state.showNatureContext);
    }
  } catch (error) {
    handleError(error, "Route highlighting failed.");
  }
}

function validateRequestControls() {
  updateOptionsFromControls();
  const request = currentRequest();
  if (request.target_distance_m < 1000 || request.target_distance_m > 200000) {
    throw new Error("Target distance must be between 1 and 200 km.");
  }
  if (request.tolerance_m < 100 || request.tolerance_m > 10000) {
    throw new Error("Tolerance must be between 0.1 and 10 km.");
  }
  if (pointValidation()) throw new Error(pointValidation());
  return request;
}

async function generate() {
  hideError();
  let request;
  try {
    request = validateRequestControls();
  } catch (error) {
    showError(error.message);
    return;
  }
  const id = state.request.id + 1;
  state.request = { status: "running", id, startedAt: Date.now() };
  state.abortController = new AbortController();
  byId("request-status").textContent = "Planning your loop… 0 s elapsed";
  elapsedTimer = window.setInterval(() => {
    if (state.request.status !== "running" || state.request.startedAt === null) return;
    const seconds = Math.floor((Date.now() - state.request.startedAt) / 1000);
    byId("request-status").textContent = `Planning your loop… ${seconds} s elapsed`;
  }, 1000);
  render();
  try {
    const result = await generateRoutes(request, state.abortController.signal);
    if (state.request.id !== id) return;
    state.generationResult = result;
    state.selectedSignature = result.candidates[0]?.signature ?? null;
    state.visualizationCache.clear();
    state.request = { status: "success", id, startedAt: null };
    byId("request-status").textContent = result.candidates.length
      ? `${result.candidates.length} candidate route${result.candidates.length === 1 ? "" : "s"} generated.`
      : `No candidate returned: ${friendlyLabel(result.search.status)}.`;
    render();
    if (result.candidates.length) {
      fitCoordinates(result.candidates[0].route.geometry);
      await selectCandidate(result.candidates[0].signature);
    }
  } catch (error) {
    if (state.request.id !== id) return;
    const cancelled = error.name === "AbortError";
    state.request = { status: cancelled ? "cancelled" : "error", id, startedAt: null };
    byId("request-status").textContent = cancelled ? "Generation cancelled." : "Generation failed.";
    if (!cancelled) handleError(error, "Route generation failed.");
  } finally {
    window.clearInterval(elapsedTimer);
    if (state.request.id === id) {
      state.abortController = null;
      renderStatus();
      renderMapData();
    }
  }
}

function handleError(error, fallback) {
  if (error instanceof ApiError) showError(error.message, `${error.code}\n${error.details}`);
  else showError(error?.message ?? fallback, error?.stack ?? "");
}

function normalizeImportedRequest(value) {
  if (!value || typeof value !== "object" || !Array.isArray(value.points)) {
    throw new Error("JSON must contain a points array.");
  }
  if (value.points.length < 2 || value.points.length > 31) {
    throw new Error("Request JSON must contain 2–30 mandatory points.");
  }
  let points = value.points.map((point, index) => {
    const lat = Number(point?.lat);
    const lon = Number(point?.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
      throw new Error(`Point ${index + 1} has invalid coordinates.`);
    }
    const suppliedName = typeof point.name === "string" ? point.name.trim() : "";
    return {
      name: suppliedName || `Point ${index + 1}`,
      lat,
      lon,
      originalIndex: index,
    };
  });
  if (
    points.length > 2
    && points[0].lat === points.at(-1).lat
    && points[0].lon === points.at(-1).lon
  ) {
    points = points.slice(0, -1);
  }
  if (points.length > (state.config?.max_required_points ?? 30)) {
    throw new Error("The request exceeds the 30-point limit.");
  }
  const pointOrderMode = value.point_order_mode ?? "fixed";
  const pathSelectionMode = value.path_selection_mode ?? "shortest";
  const requestedNaturePreference = value.nature_preference ?? "off";
  if (
    !["fixed", "optimize_loop"].includes(pointOrderMode)
    || !["shortest", "low_overlap"].includes(pathSelectionMode)
    || !["off", "prefer"].includes(requestedNaturePreference)
  ) {
    throw new Error("The request contains an unsupported generation mode.");
  }
  const naturePreference = state.config?.nature_index_available
    ? requestedNaturePreference
    : "off";
  if (value.close_loop === false || (value.profile !== undefined && value.profile !== "hike")) {
    throw new Error("Only closed-loop hike requests are supported.");
  }
  const targetDistanceM = Number(value.target_distance_m);
  const toleranceM = Number(value.tolerance_m ?? 2000);
  const candidateCount = Number(value.candidate_count ?? 3);
  const seed = Number(value.seed ?? 0);
  if (!Number.isFinite(targetDistanceM) || targetDistanceM < 1000 || targetDistanceM > 200000) {
    throw new Error("Target distance must be between 1,000 and 200,000 metres.");
  }
  if (!Number.isFinite(toleranceM) || toleranceM < 100 || toleranceM > 10000) {
    throw new Error("Tolerance must be between 100 and 10,000 metres.");
  }
  if (!Number.isInteger(candidateCount) || candidateCount < 1 || candidateCount > 5) {
    throw new Error("Candidate count must be an integer from 1 to 5.");
  }
  if (!Number.isInteger(seed)) throw new Error("Seed must be an integer.");
  return {
    points,
    options: {
      name: typeof value.name === "string" ? value.name : "Sugarglider route",
      targetDistanceKm: targetDistanceM / 1000,
      toleranceKm: toleranceM / 1000,
      candidateCount,
      seed,
      pointOrderMode,
      pathSelectionMode,
      naturePreference,
    },
  };
}

async function importRequest(file) {
  try {
    const imported = normalizeImportedRequest(JSON.parse(await file.text()));
    state.points = imported.points;
    state.options = imported.options;
    state.selectedPointIndex = state.points.length ? 0 : null;
    state.pendingPointPopupIndex = null;
    updateControlsFromOptions();
    invalidateAndRender();
    byId("request-status").textContent = `${file.name} loaded. All ${state.points.length} names and required points are ready for review.`;
    fitCoordinates(state.points.map((point) => [point.lon, point.lat]));
  } catch (error) {
    showError("Could not import request JSON.", error.message);
  }
}

async function importGpx(file) {
  try {
    state.importedGpx = parseGpx(await file.text(), file.name);
    render();
    fitCoordinates(state.importedGpx.segments.flat());
  } catch (error) {
    showError("Could not import GPX.", error.message);
  }
}

async function downloadSelected() {
  const candidate = selectedCandidate();
  if (!candidate) return;
  try {
    const { blob, filename } = await exportRoute(candidate.route);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    byId("request-status").textContent = `${filename} downloaded without rerunning generation.`;
  } catch (error) {
    handleError(error, "GPX export failed.");
  }
}

function bindEvents() {
  byId("dismiss-error").addEventListener("click", hideError);
  byId("generate").addEventListener("click", generate);
  byId("generate-top").addEventListener("click", generate);
  byId("cancel").addEventListener("click", () => state.abortController?.abort());
  byId("clear-results").addEventListener("click", invalidateAndRender);
  byId("route-form").addEventListener("change", () => {
    updateOptionsFromControls();
    invalidateAndRender();
  });
  byId("request-file").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (file) importRequest(file);
    event.target.value = "";
  });
  byId("gpx-file").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (file) importGpx(file);
    event.target.value = "";
  });
  byId("clear-gpx").addEventListener("click", () => {
    state.importedGpx = null;
    render();
  });
  byId("add-point-mode").addEventListener("click", () => {
    state.addPointMode = !state.addPointMode;
    byId("add-point-mode").setAttribute("aria-pressed", String(state.addPointMode));
    byId("add-point-mode").lastChild.textContent = state.addPointMode ? " Click map once…" : " Add on map";
  });
  byId("fit-points").addEventListener("click", () => {
    fitCoordinates(state.points.map((point) => [point.lon, point.lat]));
  });
  byId("clear-points").addEventListener("click", () => {
    if (state.points.length > 1 && !window.confirm("Remove all mandatory points and generated results?")) return;
    state.points = [];
    state.selectedPointIndex = null;
    state.pendingPointPopupIndex = null;
    invalidateAndRender();
  });
  byId("show-all").addEventListener("change", (event) => {
    state.showAllCandidates = event.target.checked;
    renderMapData();
  });
  byId("show-nature").addEventListener("change", (event) => {
    state.showNatureContext = event.target.checked;
    renderMapData();
  });
  byId("download-gpx").addEventListener("click", downloadSelected);
  byId("copy-request").addEventListener("click", async () => {
    try {
      updateOptionsFromControls();
      await navigator.clipboard.writeText(JSON.stringify(currentRequest(), null, 2));
      byId("request-status").textContent = "Request JSON copied with every required-point name.";
    } catch (error) {
      showError("Could not copy request JSON.", error.message);
    }
  });
  window.addEventListener("resize", resizeMap);
}

async function start() {
  decorateIcons();
  bindEvents();
  try {
    state.config = await getConfig();
    const natureAvailable = Boolean(state.config.nature_index_available);
    const preferOption = byId("nature-preference").querySelector('option[value="prefer"]');
    preferOption.disabled = !natureAvailable;
    if (!natureAvailable) state.options.naturePreference = "off";
    updateControlsFromOptions();
    byId("nature-availability").textContent = natureAvailable
      ? `Local OSM nature index available. Water proximity uses ${state.config.nature_water_buffer_m} m.`
      : "Local OSM nature index unavailable. Prefer mapped nature is disabled; routing still works.";
    byId("show-nature").disabled = !natureAvailable;
    state.showNatureContext = natureAvailable;
    byId("show-nature").checked = natureAvailable;
    initializeMap(state.config, {
      onReady: () => {
        mapReady = true;
        renderMapData();
      },
      onError: showMapError,
      onMapClick: (coordinate) => {
        if (!state.addPointMode) return;
        if (state.points.length >= state.config.max_required_points) {
          showError("The route already has the maximum 30 mandatory points.");
          return;
        }
        const nextOriginalIndex = state.points.reduce(
          (highest, point) => Math.max(highest, Number.isInteger(point.originalIndex) ? point.originalIndex : -1),
          -1,
        ) + 1;
        state.points.push({
          name: `Point ${state.points.length + 1}`,
          ...coordinate,
          originalIndex: nextOriginalIndex,
        });
        state.selectedPointIndex = state.points.length - 1;
        state.addPointMode = false;
        byId("add-point-mode").setAttribute("aria-pressed", "false");
        byId("add-point-mode").lastChild.textContent = " Add on map";
        invalidateAndRender();
      },
    });
    render();
  } catch (error) {
    handleError(error, "The Sugarglider API is unavailable.");
    showMapError("Map configuration could not be loaded.");
  }
}

window.addEventListener("DOMContentLoaded", start, { once: true });
