import { ApiError, exportRoute, generateRoutes, getConfig, visualizeRoute } from "./api.js";
import { constructionLabel, escapeHtml, formatCount, formatDistance, formatPercent, friendlyLabel, lowOverlapLabel, metricRows } from "./format.js";
import { parseGpx } from "./gpx.js";
import { clearRoutes, fitCoordinates, initializeMap, renderCandidates, renderImportedGpx, renderOptionalMarkers, renderRequiredMarkers, renderVisualization, resizeMap } from "./map.js";
import { currentRequest, invalidateCandidates, selectedCandidate, state } from "./state.js";

const byId = (id) => document.getElementById(id);
let elapsedTimer = null;
let mapReady = false;

function showError(message, details = "") {
  byId("error-message").textContent = message;
  byId("error-details").textContent = details;
  byId("error-banner").classList.remove("hidden");
}

function hideError() { byId("error-banner").classList.add("hidden"); }
function showMapError(message) { byId("map-error").textContent = message; byId("map-error").classList.remove("hidden"); }

function updateOptionsFromControls() {
  state.options = {
    name: byId("route-name").value.trim() || "Sugarglider route",
    targetDistanceKm: Number(byId("target-distance").value),
    toleranceKm: Number(byId("tolerance").value),
    candidateCount: Number(byId("candidate-count").value),
    seed: Number(byId("seed").value),
    pointOrderMode: byId("point-order-mode").value,
    pathSelectionMode: byId("path-selection-mode").value,
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
}

function pointValidation() {
  for (let index = 1; index < state.points.length; index += 1) {
    const previous = state.points[index - 1];
    const current = state.points[index];
    if (previous.lat === current.lat && previous.lon === current.lon) return `Points ${index} and ${index + 1} have identical adjacent coordinates.`;
  }
  if (state.points.some((point) => !Number.isFinite(point.lat) || !Number.isFinite(point.lon) || Math.abs(point.lat) > 90 || Math.abs(point.lon) > 180)) return "Every point needs valid latitude and longitude coordinates.";
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
  render();
}

function renderPoiEditor() {
  const list = byId("poi-list");
  list.replaceChildren();
  state.points.forEach((point, index) => {
    const row = document.createElement("div");
    row.className = `poi-row${index === 0 ? " start" : ""}`;
    row.innerHTML = `<span class="poi-number">${index + 1}</span><div class="poi-fields"><label class="name">${index === 0 ? "Start/end name" : "Name"}<input data-field="name" value="${escapeHtml(point.name)}"></label><label>Latitude<input data-field="lat" type="number" min="-90" max="90" step="0.000001" value="${point.lat}"></label><label>Longitude<input data-field="lon" type="number" min="-180" max="180" step="0.000001" value="${point.lon}"></label></div><div class="poi-actions"><button data-action="up" type="button" aria-label="Move point ${index + 1} up" ${index === 0 ? "disabled" : ""}>↑</button><button data-action="down" type="button" aria-label="Move point ${index + 1} down" ${index === state.points.length - 1 ? "disabled" : ""}>↓</button><button data-action="remove" type="button" aria-label="Remove point ${index + 1}">×</button></div>`;
    row.querySelectorAll("input").forEach((input) => input.addEventListener("change", () => {
      const field = input.dataset.field;
      state.points[index][field] = field === "name" ? input.value : Number(input.value);
      invalidateAndRender();
    }));
    row.querySelector('[data-action="up"]').addEventListener("click", () => movePoint(index, index - 1));
    row.querySelector('[data-action="down"]').addEventListener("click", () => movePoint(index, index + 1));
    row.querySelector('[data-action="remove"]').addEventListener("click", () => { state.points.splice(index, 1); invalidateAndRender(); });
    list.append(row);
  });
  byId("poi-count").textContent = `${state.points.length} / ${state.config?.max_required_points ?? 30}`;
  byId("poi-validation").textContent = pointValidation();
}

function movePoint(from, to) {
  if (to < 0 || to >= state.points.length) return;
  const [point] = state.points.splice(from, 1);
  state.points.splice(to, 0, point);
  invalidateAndRender();
}

function renderMapData() {
  if (!mapReady) return;
  const candidate = selectedCandidate();
  renderRequiredMarkers(state.points, candidate?.required_point_order, (index, coordinate) => {
    state.points[index] = { ...state.points[index], ...coordinate };
    invalidateAndRender();
  });
  renderOptionalMarkers(candidate?.optional_points ?? []);
  renderImportedGpx(state.importedGpx);
  renderCandidates(state.generationResult?.candidates ?? [], state.selectedSignature, state.showAllCandidates, selectCandidate);
  renderVisualization(candidate ? state.visualizationCache.get(candidate.signature) ?? null : null);
}

function candidateBadges(candidate, search) {
  const values = [];
  if (candidate.rank === 1) values.push('<span class="badge recommended">Recommended</span>');
  values.push(`<span class="badge ${candidate.within_tolerance ? "good" : "warn"}">${candidate.within_tolerance ? "Within tolerance" : "Outside tolerance"}</span>`);
  if (search.low_overlap_requested) values.push(`<span class="badge">${escapeHtml(lowOverlapLabel(candidate))}</span>`);
  return values.join(" ");
}

function renderCandidatesPanel() {
  const container = byId("candidate-list");
  const result = state.generationResult;
  if (!result?.candidates.length) { container.innerHTML = '<p class="empty-copy">Returned routes will appear here in ranked order.</p>'; byId("search-summary").textContent = result ? friendlyLabel(result.search.status) : ""; return; }
  byId("search-summary").textContent = `${friendlyLabel(result.search.status)} · ${result.candidates.length} returned`;
  container.innerHTML = "";
  result.candidates.forEach((candidate) => {
    const analysis = candidate.route.analysis;
    const nonImmediate = Math.max(analysis.repetition.repeated_distance.distance_m - analysis.immediate_backtrack.distance_m, 0);
    const card = document.createElement("button");
    card.type = "button";
    card.className = "candidate-card";
    card.setAttribute("aria-pressed", String(candidate.signature === state.selectedSignature));
    card.innerHTML = `<div class="candidate-title"><h3>Candidate ${candidate.rank}</h3><strong>${formatDistance(candidate.route.summary.distance_m)}</strong></div><p>${candidateBadges(candidate, result.search)}</p><p class="eyebrow">${escapeHtml(constructionLabel(candidate.construction))}</p>${metricRows([["Target error", formatDistance(candidate.target_error_m)], ["Repeated", `${formatDistance(analysis.repetition.repeated_distance.distance_m)} · ${formatPercent(analysis.repetition.repeated_distance.share)}`], ["Immediate return", `${formatDistance(analysis.immediate_backtrack.distance_m)} · ${formatPercent(analysis.immediate_backtrack.share)}`], ["Other repetition", formatDistance(nonImmediate)], ["Paved", formatPercent(analysis.paved.share)], ["Trail-like", formatPercent(analysis.trail_like.share)], ["Major road", formatPercent(analysis.major_road.share)]])}`;
    card.addEventListener("click", () => selectCandidate(candidate.signature));
    container.append(card);
  });
}

function section(title, rows) { return `<section><h3>${escapeHtml(title)}</h3>${metricRows(rows)}</section>`; }

function renderMetrics() {
  const candidate = selectedCandidate();
  const result = state.generationResult;
  byId("metrics-empty").classList.toggle("hidden", Boolean(candidate));
  byId("metrics-content").classList.toggle("hidden", !candidate);
  byId("download-gpx").disabled = !candidate || state.request.status === "running";
  if (!candidate || !result) return;
  const analysis = candidate.route.analysis;
  const search = result.search;
  const otherRepeated = Math.max(analysis.repetition.repeated_distance.distance_m - analysis.immediate_backtrack.distance_m, 0);
  const nullable = (value, formatter = formatPercent) => value === null || value === undefined ? "Not evaluated" : formatter(value);
  const warningCodes = [...new Set([...search.warnings, ...analysis.warnings])];
  const warnings = warningCodes.map((warning) => `<li>${escapeHtml(friendlyLabel(warning))}</li>`).join("") || "<li>No route or search warnings.</li>";
  byId("metrics-content").innerHTML = section("Route", [["Distance", formatDistance(candidate.route.summary.distance_m)], ["Target", formatDistance(search.target_distance_m)], ["Target error", formatDistance(candidate.target_error_m)], ["Tolerance", formatDistance(search.tolerance_m)], ["Construction", constructionLabel(candidate.construction)], ["Mandatory POIs", candidate.route.summary.input_point_count], ["Routing points", candidate.routing_points.length]]) + section("Natural loop quality", [["Total repeated", `${formatDistance(analysis.repetition.repeated_distance.distance_m)} · ${formatPercent(analysis.repetition.repeated_distance.share)}`], ["Immediate backtracking", `${formatDistance(analysis.immediate_backtrack.distance_m)} · ${formatPercent(analysis.immediate_backtrack.share)}`], ["Non-immediate repeated", formatDistance(otherRepeated)], ["Repeated edge-ID coverage", formatPercent(analysis.repetition.edge_id_coverage.share)], ["Backtracking coverage", formatPercent(analysis.backtrack_edge_id_coverage.share)]]) + section("Trail quality", [["Paved", `${formatDistance(analysis.paved.distance_m)} · ${formatPercent(analysis.paved.share)}`], ["Unpaved", `${formatDistance(analysis.unpaved.distance_m)} · ${formatPercent(analysis.unpaved.share)}`], ["Unknown surface", `${formatDistance(analysis.unknown_surface.distance_m)} · ${formatPercent(analysis.unknown_surface.share)}`], ["Trail-like", formatPercent(analysis.trail_like.share)], ["Official hiking network", formatPercent(analysis.official_hiking_network.share)], ["Major roads", formatPercent(analysis.major_road.share)], ["Car-accessible", formatDistance(analysis.car_accessible.distance_m)]]) + section("Search diagnostics", [["Status", friendlyLabel(search.status)], ["Full-route evaluations", `${formatCount(search.evaluated_candidate_count)} / ${formatCount(search.search_budget)}`], ["Mandatory-order evaluations", search.evaluated_order_count], ["Alternative-leg requests", `${search.alternative_leg_request_count} / ${search.low_overlap_request_budget}`], ["Alternative paths", search.alternative_path_count], ["Refined sources", search.low_overlap_refined_source_count], ["Low-overlap candidates", search.low_overlap_candidate_count], ["Leg budget exhausted", search.low_overlap_budget_exhausted ? "Yes" : "No"], ["Pre-refinement repetition", nullable(search.pre_low_overlap_repeated_share)], ["Best low-overlap repetition", nullable(search.best_low_overlap_repeated_share)], ["Pre-refinement backtracking", nullable(search.pre_low_overlap_backtrack_share)], ["Best low-overlap backtracking", nullable(search.best_low_overlap_backtrack_share)]]) + `<section><h3>Warnings</h3><ul class="warning-list">${warnings}</ul><details><summary>Raw warning codes</summary><pre>${escapeHtml(JSON.stringify({ search: search.warnings, route: analysis.warnings }, null, 2))}</pre></details></section>`;
}

function renderStatus() {
  const running = state.request.status === "running";
  byId("generate").disabled = running || state.points.length < 2 || Boolean(pointValidation());
  byId("generate-top").disabled = byId("generate").disabled;
  byId("cancel").classList.toggle("hidden", !running);
  document.querySelectorAll("#route-form input, #route-form select, #poi-list input, #poi-list button, #add-point-mode, #clear-points").forEach((control) => { control.disabled = running; });
  byId("request-status").classList.toggle("running", running);
  if (!running && state.points.length < 2) byId("request-status").textContent = "Add at least two mandatory points.";
}

function render() {
  renderPoiEditor();
  renderCandidatesPanel();
  renderMetrics();
  renderStatus();
  renderMapData();
  const imported = state.importedGpx;
  byId("gpx-summary").classList.toggle("hidden", !imported);
  if (imported) byId("gpx-details").textContent = `${imported.filename} · ${formatCount(imported.pointCount)} trackpoints · ${formatDistance(imported.distanceM)} locally calculated`;
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
    if (state.selectedSignature === signature) renderVisualization(visualization);
  } catch (error) { handleError(error, "Route highlighting failed."); }
}

function validateRequestControls() {
  updateOptionsFromControls();
  const request = currentRequest();
  if (request.target_distance_m < 1000 || request.target_distance_m > 200000) throw new Error("Target distance must be between 1 and 200 km.");
  if (request.tolerance_m < 100 || request.tolerance_m > 10000) throw new Error("Tolerance must be between 0.1 and 10 km.");
  if (pointValidation()) throw new Error(pointValidation());
  return request;
}

async function generate() {
  hideError();
  let request;
  try { request = validateRequestControls(); } catch (error) { showError(error.message); return; }
  const id = state.request.id + 1;
  state.request = { status: "running", id, startedAt: Date.now() };
  state.abortController = new AbortController();
  byId("request-status").textContent = "Generating routes… 0 s elapsed";
  elapsedTimer = window.setInterval(() => {
    const seconds = Math.floor((Date.now() - state.request.startedAt) / 1000);
    byId("request-status").textContent = `Generating routes… ${seconds} s elapsed`;
  }, 1000);
  render();
  try {
    const result = await generateRoutes(request, state.abortController.signal);
    if (state.request.id !== id) return;
    state.generationResult = result;
    state.selectedSignature = result.candidates[0]?.signature ?? null;
    state.visualizationCache.clear();
    state.request = { status: "success", id, startedAt: null };
    byId("request-status").textContent = result.candidates.length ? `${result.candidates.length} candidate route${result.candidates.length === 1 ? "" : "s"} generated.` : `No candidate returned: ${friendlyLabel(result.search.status)}.`;
    render();
    if (result.candidates.length) { fitCoordinates(result.candidates[0].route.geometry); await selectCandidate(result.candidates[0].signature); }
  } catch (error) {
    if (state.request.id !== id) return;
    const cancelled = error.name === "AbortError";
    state.request = { status: cancelled ? "cancelled" : "error", id, startedAt: null };
    byId("request-status").textContent = cancelled ? "Generation cancelled." : "Generation failed.";
    if (!cancelled) handleError(error, "Route generation failed.");
  } finally {
    window.clearInterval(elapsedTimer);
    if (state.request.id === id) { state.abortController = null; renderStatus(); }
  }
}

function handleError(error, fallback) {
  if (error instanceof ApiError) showError(error.message, `${error.code}\n${error.details}`);
  else showError(error?.message ?? fallback, error?.stack ?? "");
}

function normalizeImportedRequest(value) {
  if (!value || typeof value !== "object" || !Array.isArray(value.points)) throw new Error("JSON must contain a points array.");
  if (value.points.length < 2 || value.points.length > 31) throw new Error("Request JSON must contain 2–30 mandatory points.");
  let points = value.points.map((point, index) => {
    const lat = Number(point?.lat); const lon = Number(point?.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) throw new Error(`Point ${index + 1} has invalid coordinates.`);
    return { name: typeof point.name === "string" ? point.name : `Point ${index + 1}`, lat, lon };
  });
  if (points.length > 2 && points[0].lat === points.at(-1).lat && points[0].lon === points.at(-1).lon) points = points.slice(0, -1);
  if (points.length > (state.config?.max_required_points ?? 30)) throw new Error("The request exceeds the 30-point limit.");
  const pointOrderMode = value.point_order_mode ?? "fixed";
  const pathSelectionMode = value.path_selection_mode ?? "shortest";
  if (!["fixed", "optimize_loop"].includes(pointOrderMode) || !["shortest", "low_overlap"].includes(pathSelectionMode)) throw new Error("The request contains an unsupported generation mode.");
  if (value.close_loop === false || (value.profile !== undefined && value.profile !== "hike")) throw new Error("Only closed-loop hike requests are supported.");
  const targetDistanceM = Number(value.target_distance_m);
  const toleranceM = Number(value.tolerance_m ?? 2000);
  const candidateCount = Number(value.candidate_count ?? 3);
  const seed = Number(value.seed ?? 0);
  if (!Number.isFinite(targetDistanceM) || targetDistanceM < 1000 || targetDistanceM > 200000) throw new Error("Target distance must be between 1,000 and 200,000 metres.");
  if (!Number.isFinite(toleranceM) || toleranceM < 100 || toleranceM > 10000) throw new Error("Tolerance must be between 100 and 10,000 metres.");
  if (!Number.isInteger(candidateCount) || candidateCount < 1 || candidateCount > 5) throw new Error("Candidate count must be an integer from 1 to 5.");
  if (!Number.isInteger(seed)) throw new Error("Seed must be an integer.");
  return { points, options: { name: typeof value.name === "string" ? value.name : "Sugarglider route", targetDistanceKm: targetDistanceM / 1000, toleranceKm: toleranceM / 1000, candidateCount, seed, pointOrderMode, pathSelectionMode } };
}

async function importRequest(file) {
  try {
    const imported = normalizeImportedRequest(JSON.parse(await file.text()));
    state.points = imported.points; state.options = imported.options;
    updateControlsFromOptions(); invalidateAndRender();
    byId("request-status").textContent = `${file.name} loaded. Review it before generating.`;
    fitCoordinates(state.points.map((point) => [point.lon, point.lat]));
  } catch (error) { showError("Could not import request JSON.", error.message); }
}

async function importGpx(file) {
  try {
    state.importedGpx = parseGpx(await file.text(), file.name);
    render();
    fitCoordinates(state.importedGpx.segments.flat());
  } catch (error) { showError("Could not import GPX.", error.message); }
}

async function downloadSelected() {
  const candidate = selectedCandidate(); if (!candidate) return;
  try {
    const { blob, filename } = await exportRoute(candidate.route);
    const url = URL.createObjectURL(blob); const link = document.createElement("a");
    link.href = url; link.download = filename; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 0);
    byId("request-status").textContent = `${filename} downloaded without rerunning generation.`;
  } catch (error) { handleError(error, "GPX export failed."); }
}

function bindEvents() {
  byId("dismiss-error").addEventListener("click", hideError);
  byId("generate").addEventListener("click", generate); byId("generate-top").addEventListener("click", generate);
  byId("cancel").addEventListener("click", () => state.abortController?.abort());
  byId("clear-results").addEventListener("click", invalidateAndRender);
  byId("route-form").addEventListener("change", () => { updateOptionsFromControls(); invalidateAndRender(); });
  byId("request-file").addEventListener("change", (event) => { const file = event.target.files[0]; if (file) importRequest(file); event.target.value = ""; });
  byId("gpx-file").addEventListener("change", (event) => { const file = event.target.files[0]; if (file) importGpx(file); event.target.value = ""; });
  byId("clear-gpx").addEventListener("click", () => { state.importedGpx = null; render(); });
  byId("add-point-mode").addEventListener("click", () => { state.addPointMode = !state.addPointMode; byId("add-point-mode").setAttribute("aria-pressed", String(state.addPointMode)); byId("add-point-mode").textContent = state.addPointMode ? "Click map once…" : "Add point on map"; });
  byId("fit-points").addEventListener("click", () => fitCoordinates(state.points.map((point) => [point.lon, point.lat])));
  byId("clear-points").addEventListener("click", () => { if (state.points.length > 1 && !window.confirm("Remove all mandatory points and generated results?")) return; state.points = []; invalidateAndRender(); });
  byId("show-all").addEventListener("change", (event) => { state.showAllCandidates = event.target.checked; renderMapData(); });
  byId("download-gpx").addEventListener("click", downloadSelected);
  byId("copy-request").addEventListener("click", async () => { try { updateOptionsFromControls(); await navigator.clipboard.writeText(JSON.stringify(currentRequest(), null, 2)); byId("request-status").textContent = "Request JSON copied."; } catch (error) { showError("Could not copy request JSON.", error.message); } });
  window.addEventListener("resize", resizeMap);
}

async function start() {
  bindEvents();
  try {
    state.config = await getConfig();
    initializeMap(state.config, {
      onReady: () => { mapReady = true; renderMapData(); },
      onError: showMapError,
      onMapClick: (coordinate) => {
        if (!state.addPointMode) return;
        if (state.points.length >= state.config.max_required_points) { showError("The route already has the maximum 30 mandatory points."); return; }
        state.points.push({ name: `Point ${state.points.length + 1}`, ...coordinate });
        state.addPointMode = false; byId("add-point-mode").setAttribute("aria-pressed", "false"); byId("add-point-mode").textContent = "Add point on map";
        invalidateAndRender();
      },
    });
    render();
  } catch (error) { handleError(error, "The Sugarglider API is unavailable."); showMapError("Map configuration could not be loaded."); }
}

window.addEventListener("DOMContentLoaded", start, { once: true });
