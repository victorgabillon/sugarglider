import { ApiError, exportRoute, generateAutoTour, generateRoutes, getConfig, getPoiStatus, searchPois, visualizeRoute } from "./api.js";
import { constructionLabel, escapeHtml, formatCount, formatDistance, formatPercent, friendlyLabel, lowOverlapLabel, metricRows } from "./format.js";
import { parseGpx } from "./gpx.js";
import { createIcon, decorateIcons } from "./icons.js";
import { clearRoutes, currentViewportBounds, fitCoordinates, initializeMap, renderCandidates, renderImportedGpx, renderOptionalMarkers, renderPois, renderRequestedPlaces as renderRequestedPlaceMarkers, renderRequiredMarkers, renderVisualization, resizeMap } from "./map.js";
import { currentAutoTourRequest, currentRequest, invalidateCandidates, pointDisplayName, requestedPlaceIdentifier, saveActivePoints, selectedCandidate, state, switchPlanningMode } from "./state.js";

const byId = (id) => document.getElementById(id);
let elapsedTimer = null;
let mapReady = false;
let poiDebounceTimer = null;
let pendingPoiBounds = null;

const PRIMARY_SCENIC_CATEGORIES = [
  "viewpoint",
  "observation_tower",
  "castle",
  "archaeological_site",
  "ruins",
];
const HYDRATION_CATEGORIES = ["drinking_water", "fountain", "water_tap"];

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

function updatePoiFiltersFromControls() {
  state.poiFilters = {
    scenic: byId("place-scenic").checked,
    verifiedWater: byId("place-verified-water").checked,
    unknownWater: byId("place-unknown-water").checked,
    broadAttractions: byId("place-broad").checked,
    restrictedAccess: byId("place-restricted").checked,
    includePrivate: byId("place-private").checked,
    nonPotable: byId("place-non-potable").checked,
  };
}

function poiCategoriesAndPotability() {
  const categories = [];
  const potability = [];
  if (state.poiFilters.scenic) categories.push(...PRIMARY_SCENIC_CATEGORIES);
  if (state.poiFilters.broadAttractions) categories.push("tourism_attraction");
  if (state.poiFilters.verifiedWater) {
    categories.push("drinking_water");
    potability.push("verified");
  }
  if (state.poiFilters.unknownWater) {
    categories.push("fountain", "water_tap");
    potability.push("unknown");
  }
  if (state.poiFilters.nonPotable) {
    categories.push(...HYDRATION_CATEGORIES);
    potability.push("non_potable");
  }
  return {
    categories: [...new Set(categories)],
    potability: [...new Set(potability)],
  };
}

function normalizedViewportBounds(bounds) {
  if (!bounds) return null;
  const normalized = {
    west: Math.max(-180, bounds.west),
    south: Math.max(-90, bounds.south),
    east: Math.min(180, bounds.east),
    north: Math.min(90, bounds.north),
  };
  if (normalized.west >= normalized.east || normalized.south >= normalized.north) return null;
  return normalized;
}

function clearPoiFeatures(status) {
  state.poiFeatures = [];
  state.selectedPoiId = null;
  byId("places-count").textContent = "";
  byId("places-status").textContent = status;
  if (mapReady) renderPois([], null, selectPoi, poiRenderOptions());
}

function poiRequestBody(bounds) {
  const filters = poiCategoriesAndPotability();
  if (!filters.categories.length) return null;
  const groups = [];
  if (filters.categories.some((category) => PRIMARY_SCENIC_CATEGORIES.includes(category) || category === "tourism_attraction")) {
    groups.push("scenic");
  }
  if (filters.categories.some((category) => HYDRATION_CATEGORIES.includes(category))) {
    groups.push("hydration");
  }
  const access = ["public", "unknown"];
  if (state.poiFilters.restrictedAccess) access.push("restricted");
  if (state.poiFilters.includePrivate) access.push("private");
  return {
    bbox: bounds,
    groups,
    categories: filters.categories,
    potability: filters.potability,
    access,
    include_private: state.poiFilters.includePrivate,
    limit: Math.min(state.config.poi_default_limit, state.config.poi_max_limit),
  };
}

function selectPoi(id) {
  if (!state.poiFeatures.some((feature) => feature.id === id)) return;
  state.selectedPoiId = id;
  renderPois(state.poiFeatures, state.selectedPoiId, selectPoi, poiRenderOptions());
}

function selectedVisitedPoiIds() {
  return (selectedCandidate()?.poi_visits ?? []).map((visit) => visit.poi.id);
}

function poiRenderOptions() {
  return {
    onPrefer: preferPoi,
    preferredIds: state.autoTour.preferredPoiIds,
    visitedIds: selectedVisitedPoiIds(),
  };
}

function preferPoi(feature) {
  const eligibleAccess = ["public", "restricted"].includes(feature.access_status);
  const scenic = PRIMARY_SCENIC_CATEGORIES.includes(feature.category) || feature.category === "tourism_attraction";
  const verifiedWater = feature.category === "drinking_water" && feature.potability === "verified";
  if (!eligibleAccess || (!scenic && !verifiedWater) || feature.potability === "non_potable") return;
  if (state.autoTour.preferredPoiIds.includes(feature.id)) return;
  if (state.autoTour.preferredPoiIds.length >= 8) {
    showError("Auto Tour supports at most eight preferred places.");
    return;
  }
  state.autoTour.preferredPoiIds.push(feature.id);
  invalidateAndRender();
  byId("request-status").textContent = `${feature.display_name} added as a soft Auto Tour preference.`;
}

async function fetchViewportPois(id, bounds) {
  if (!state.config?.poi_index_available) return;
  const normalized = normalizedViewportBounds(bounds);
  const request = normalized ? poiRequestBody(normalized) : null;
  if (!request) {
    state.poiRequest = { status: "idle", id };
    clearPoiFeatures(normalized ? "Place filters are off." : "This viewport cannot be searched.");
    return;
  }
  const controller = new AbortController();
  state.poiAbortController = controller;
  state.poiRequest = { status: "loading", id };
  byId("places-status").textContent = "Loading mapped places for this viewport…";
  try {
    const response = await searchPois(request, controller.signal);
    if (state.poiRequest.id !== id) return;
    state.poiFeatures = response.features;
    if (!state.poiFeatures.some((feature) => feature.id === state.selectedPoiId)) {
      state.selectedPoiId = null;
    }
    state.poiRequest = { status: "success", id };
    renderPois(state.poiFeatures, state.selectedPoiId, selectPoi, poiRenderOptions());
    byId("places-count").textContent = String(response.returned_count);
    if (!response.available) {
      byId("places-status").textContent = "POI index unavailable. Routing still works.";
    } else if (!response.returned_count) {
      byId("places-status").textContent = "No matching mapped places in this viewport.";
    } else if (response.truncated) {
      byId("places-status").textContent = `Showing ${response.returned_count} of ${response.total_matching} matches — zoom in to narrow the viewport.`;
    } else {
      byId("places-status").textContent = `${response.returned_count} mapped place${response.returned_count === 1 ? "" : "s"} in this viewport.`;
    }
  } catch (error) {
    if (state.poiRequest.id !== id || error.name === "AbortError") return;
    state.poiRequest = { status: "error", id };
    byId("places-status").textContent = "Places could not be loaded; routing still works.";
  } finally {
    if (state.poiRequest.id === id) state.poiAbortController = null;
  }
}

function schedulePoiRefresh(bounds = currentViewportBounds()) {
  if (!state.config?.poi_index_available) return;
  pendingPoiBounds = bounds;
  window.clearTimeout(poiDebounceTimer);
  state.poiAbortController?.abort();
  state.poiAbortController = null;
  const id = state.poiRequest.id + 1;
  state.poiRequest = { status: "scheduled", id };
  poiDebounceTimer = window.setTimeout(() => fetchViewportPois(id, pendingPoiBounds), 250);
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
    loopGeometryPreference: byId("loop-geometry-preference").value,
  };
  state.autoTour.directionPreference = byId("direction-preference").value;
  state.autoTour.distancePriority = byId("distance-priority").value;
  state.autoTour.scenicPreference = byId("scenic-preference").value;
  state.autoTour.drinkingWaterPreference = byId("water-preference").value;
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
  byId("loop-geometry-preference").value = state.options.loopGeometryPreference;
  byId("direction-preference").value = state.autoTour.directionPreference;
  byId("distance-priority").value = state.autoTour.distancePriority;
  byId("scenic-preference").value = state.autoTour.scenicPreference;
  byId("water-preference").value = state.autoTour.drinkingWaterPreference;
}

function updateAutoStartInputs() {
  byId("auto-start-lat").value = state.autoTour.start?.lat ?? "";
  byId("auto-start-lon").value = state.autoTour.start?.lon ?? "";
}

function renderPreferredPois() {
  const ids = state.autoTour.preferredPoiIds;
  byId("preferred-poi-count").textContent = `${ids.length} / 8`;
  byId("preferred-poi-empty").classList.toggle("hidden", ids.length > 0);
  const list = byId("preferred-poi-list");
  list.replaceChildren();
  ids.forEach((id) => {
    const feature = state.poiFeatures.find((item) => item.id === id);
    const item = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = feature?.display_name ?? id;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Remove";
    remove.setAttribute("aria-label", `Remove preferred place ${label.textContent}`);
    remove.addEventListener("click", () => {
      state.autoTour.preferredPoiIds = ids.filter((value) => value !== id);
      invalidateAndRender();
    });
    item.append(label, remove);
    list.append(item);
  });
}

function selectedRequestedVisits() {
  return new Map((selectedCandidate()?.requested_place_visits ?? []).map(
    (visit, index) => [
      requestedPlaceIdentifier({
        coordinate: visit.requested_place.coordinate,
        originalIndex: visit.requested_place.original_index,
      }, index),
      visit,
    ],
  ));
}

function requestedPlaceStatus(place, index, visits = selectedRequestedVisits()) {
  const visit = visits.get(place.id ?? requestedPlaceIdentifier(place, index));
  return visit ? (visit.satisfied ? "satisfied" : "missed") : "pending";
}

function scrollRequestedPlaceIntoView(id) {
  const row = byId("requested-place-list").querySelector(
    `[data-requested-place-id="${CSS.escape(id)}"]`,
  );
  row?.scrollIntoView({ block: "nearest" });
}

function selectRequestedPlace(
  id,
  { revealMap = false, scrollList = false } = {},
) {
  if (!state.autoTour.requestedPlaces.some((place, index) => (
    (place.id ?? requestedPlaceIdentifier(place, index)) === id
  ))) return;
  state.selectedRequestedPlaceId = id;
  if (revealMap) state.pendingRequestedPlacePopupId = id;
  renderRequestedPlacesList();
  if (scrollList) scrollRequestedPlaceIntoView(id);
  renderMapData();
}

function renderRequestedPlacesList() {
  const places = state.autoTour.requestedPlaces;
  const visits = selectedRequestedVisits();
  byId("requested-place-count").textContent = `${places.length} / 30`;
  byId("requested-place-empty").classList.toggle("hidden", places.length > 0);
  const list = byId("requested-place-list");
  list.replaceChildren();
  places.forEach((place, index) => {
    const id = place.id ?? requestedPlaceIdentifier(place, index);
    const status = requestedPlaceStatus(place, index, visits);
    const item = document.createElement("li");
    item.className = `requested-place-row requested-status-${status}${id === state.selectedRequestedPlaceId ? " selected" : ""}`;
    item.dataset.requestedPlaceId = id;
    item.tabIndex = 0;
    item.setAttribute("role", "button");
    item.setAttribute("aria-label", `Show requested place ${index + 1}, ${place.name}, ${status}`);
    if (id === state.selectedRequestedPlaceId) item.setAttribute("aria-current", "true");
    const label = document.createElement("span");
    label.textContent = `${index + 1}. ${place.name} · ${place.visitRadiusM} m · ${friendlyLabel(place.importance)}`;
    const statusLabel = document.createElement("span");
    statusLabel.className = "requested-place-status";
    statusLabel.textContent = friendlyLabel(status);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Remove";
    remove.setAttribute("aria-label", `Remove requested place ${place.name}`);
    remove.addEventListener("click", () => {
      state.autoTour.requestedPlaces = places.filter((_value, placeIndex) => placeIndex !== index);
      if (state.selectedRequestedPlaceId === id) {
        state.selectedRequestedPlaceId = null;
        state.pendingRequestedPlacePopupId = null;
      }
      invalidateAndRender();
    });
    item.addEventListener("click", (event) => {
      if (event.target.closest("button")) return;
      selectRequestedPlace(id, { revealMap: true });
    });
    item.addEventListener("keydown", (event) => {
      if (!["Enter", " "].includes(event.key)) return;
      event.preventDefault();
      selectRequestedPlace(id, { revealMap: true });
    });
    const details = document.createElement("span");
    details.className = "requested-place-copy";
    details.append(label, statusLabel);
    item.append(details, remove);
    list.append(item);
  });
}

function renderModeControls() {
  const auto = state.planningMode === "auto_tour";
  document.querySelectorAll('input[name="planning-mode"]').forEach((input) => {
    input.checked = input.value === state.planningMode;
  });
  byId("auto-tour-fields").classList.toggle("hidden", !auto);
  byId("waypoint-order-field").classList.toggle("hidden", auto);
  byId("preferred-pois").classList.toggle("hidden", !auto);
  byId("requested-places").classList.toggle("hidden", !auto);
  byId("point-editor-title").textContent = auto ? "Start and hard anchors" : "Required POIs";
  byId("generate").textContent = auto ? "Generate Auto Tour" : "Generate routes";
  byId("generate-top").textContent = auto ? "Generate Auto Tour" : "Generate";
  byId("places-explanation").textContent = auto
    ? "Browse mapped places and optionally prefer eligible places for Auto Tour. Simply selecting a place never changes the route."
    : "Discovery only: shown places never alter mandatory points, generation, ranking, or GPX output.";
  updateAutoStartInputs();
  renderPreferredPois();
  byId("show-missed-requested-radii-control").classList.toggle("hidden", !auto);
  renderRequestedPlacesList();
}

function validPoint(point) {
  return Number.isFinite(point.lat)
    && Number.isFinite(point.lon)
    && Math.abs(point.lat) <= 90
    && Math.abs(point.lon) <= 180;
}

function pointValidation() {
  const maximum = state.planningMode === "auto_tour" ? 7 : (state.config?.max_required_points ?? 30);
  if (state.points.length > maximum) return `This mode supports at most ${maximum} points.`;
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
  saveActivePoints();
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
    const auto = state.planningMode === "auto_tour";
    const up = iconButton("up", "up", `Move ${pointDisplayName(point, index)} up`, auto || index === 0);
    const down = iconButton("down", "down", `Move ${pointDisplayName(point, index)} down`, auto || index === state.points.length - 1);
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
  const maximum = state.planningMode === "auto_tour" ? 7 : (state.config?.max_required_points ?? 30);
  const hardCount = state.planningMode === "auto_tour" ? Math.max(state.points.length - 1, 0) : state.points.length;
  byId("poi-count").textContent = state.planningMode === "auto_tour"
    ? `${hardCount} / 6 anchors`
    : `${state.points.length} / ${maximum}`;
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
  const requestedPopupId = state.pendingRequestedPlacePopupId;
  state.pendingRequestedPlacePopupId = null;
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
  const visitFeatures = (candidate?.poi_visits ?? []).map((visit) => visit.poi);
  const allFeatures = [...new Map(
    [...state.poiFeatures, ...visitFeatures].map((feature) => [feature.id, feature]),
  ).values()];
  renderPois(allFeatures, state.selectedPoiId, selectPoi, poiRenderOptions());
  renderRequestedPlaceMarkers(
    state.planningMode === "auto_tour" ? state.autoTour.requestedPlaces : [],
    state.planningMode === "auto_tour"
      ? candidate?.requested_place_visits ?? []
      : [],
    state.selectedRequestedPlaceId,
    state.showMissedRequestedRadii,
    (id) => selectRequestedPlace(id, { scrollList: true }),
    requestedPopupId,
  );
}

function candidateBadges(candidate, search) {
  const values = [];
  if (candidate.rank === 1) values.push('<span class="badge recommended">Recommended</span>');
  values.push(`<span class="badge ${candidate.within_tolerance ? "good" : "warn"}">${candidate.within_tolerance ? "Within tolerance" : "Outside tolerance"}</span>`);
  if (search.low_overlap_requested) values.push(`<span class="badge">${escapeHtml(lowOverlapLabel(candidate))}</span>`);
  if (search.control_signature && candidate.signature === search.control_signature) {
    values.push('<span class="badge">No-POI control</span>');
  }
  return values.join("");
}

function autoCandidateSummary(candidate, result, nonImmediate, nonImmediateShare) {
  const analysis = candidate.route.analysis;
  return `<div class="candidate-title"><h3>Candidate ${candidate.rank}</h3><strong>${formatDistance(candidate.route.summary.distance_m)}</strong></div><div class="candidate-badges">${candidateBadges(candidate, result.search)}</div><p class="candidate-construction">${escapeHtml(`${friendlyLabel(candidate.skeleton_method)} · ${friendlyLabel(candidate.direction)}`)}</p><div class="candidate-key-metrics"><span>Target error</span><strong>${formatDistance(candidate.target_error_m)}</strong><span>Requested must visits</span><strong>${formatCount(candidate.satisfied_must_visit_count)}</strong><span>Requested preferences</span><strong>${formatCount(candidate.satisfied_preferred_place_count)}</strong><span>Other repetition</span><strong>${formatDistance(nonImmediate)} · ${formatPercent(nonImmediateShare)}</strong><span>Backtracking</span><strong>${formatPercent(analysis.immediate_backtrack.share)}</strong><span>Scenic visits</span><strong>${formatCount(candidate.selected_scenic_count)}</strong><span>Verified water</span><strong>${formatCount(candidate.selected_verified_water_count)}</strong><span>POI reward</span><strong>${Number(candidate.total_poi_reward).toFixed(2)}</strong></div>${metricBar("Total repetition", analysis.repetition.repeated_distance.share, "repetition", formatPercent(analysis.repetition.repeated_distance.share))}${metricBar("Immediate backtracking", analysis.immediate_backtrack.share, "backtrack", formatPercent(analysis.immediate_backtrack.share))}${metricBar("Outbound/return proximity", analysis.loop_geometry?.outbound_return_proximity.share ?? null, "backtrack", analysis.loop_geometry ? formatPercent(analysis.loop_geometry.outbound_return_proximity.share) : "not evaluated")}${metricBar("Mapped nature", analysis.nature ? analysis.nature.nature_score / 100 : null, "nature", analysis.nature ? `${analysis.nature.nature_score.toFixed(1)} / 100` : "not evaluated")}${loopGeometryCardSummary(analysis.loop_geometry)}`;
}

function metricBar(label, share, className, displayValue) {
  if (share === null || share === undefined) {
    return `<div class="bar-metric ${className} not-evaluated"><div class="bar-heading"><span>${escapeHtml(label)}</span><strong>not evaluated</strong></div><div class="metric-track" aria-hidden="true"></div></div>`;
  }
  const percentage = Math.max(0, Math.min(100, Number(share) * 100));
  return `<div class="bar-metric ${className}"><div class="bar-heading"><span>${escapeHtml(label)}</span><strong>${escapeHtml(displayValue)}</strong></div><div class="metric-track" role="img" aria-label="${escapeHtml(`${label}: ${displayValue}`)}"><div class="metric-fill" style="--metric-value:${percentage.toFixed(3)}%"></div></div></div>`;
}

function loopGeometryCardSummary(geometry) {
  if (!geometry) {
    return '<div class="loop-geometry-card not-evaluated"><div class="loop-geometry-heading"><strong>Loop geometry</strong><span>not evaluated</span></div><p>Shape metrics are unknown, not zero.</p></div>';
  }
  return `<div class="loop-geometry-card"><div class="loop-geometry-heading"><strong>Loop geometry</strong><span>${geometry.penalty_breakdown.total.toFixed(4)} · lower is better</span></div><dl><dt>Compactness</dt><dd>${geometry.compactness.toFixed(4)}</dd><dt>Sector balance</dt><dd>${geometry.sector_balance.toFixed(4)}</dd><dt>Near-parallel</dt><dd>${formatPercent(geometry.near_parallel.share)}</dd><dt>Self-crossings</dt><dd>${formatCount(geometry.self_crossing_count)}</dd></dl></div>`;
}

function loopGeometryCardDetails(geometry) {
  const details = document.createElement("details");
  details.className = "loop-geometry-details";
  const summary = document.createElement("summary");
  summary.textContent = "Loop geometry details";
  const content = document.createElement("div");
  content.innerHTML = geometry
    ? metricRows([
      ["Elongation", geometry.elongation.toFixed(4)],
      ["Enclosed area", `${geometry.enclosed_area_m2.toFixed(2)} m²`],
      ["Maximum radius", `${geometry.max_radius_m.toFixed(2)} m`],
    ])
    : metricRows([
      ["Elongation", "not evaluated"],
      ["Enclosed area", "not evaluated"],
      ["Maximum radius", "not evaluated"],
    ]);
  details.append(summary, content);
  return details;
}

function renderCandidatesPanel() {
  const container = byId("candidate-list");
  const result = state.generationResult;
  if (!result?.candidates.length) {
    container.innerHTML = '<p class="empty-copy">Returned routes will appear here in ranked order.</p>';
    byId("search-summary").textContent = result
      ? (state.planningMode === "auto_tour" ? "No Auto Tour candidates returned" : friendlyLabel(result.search.status))
      : "";
    return;
  }
  byId("search-summary").textContent = state.planningMode === "auto_tour"
    ? `${result.candidates.length} returned · no-POI control ${result.search.control_retained ? "retained" : "unavailable"}`
    : `${friendlyLabel(result.search.status)} · ${result.candidates.length} returned`;
  container.replaceChildren();
  result.candidates.forEach((candidate) => {
    const analysis = candidate.route.analysis;
    const nature = analysis.nature;
    const loopGeometry = analysis.loop_geometry;
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
    selector.innerHTML = state.planningMode === "auto_tour"
      ? autoCandidateSummary(candidate, result, nonImmediate, nonImmediateShare)
      : `<div class="candidate-title"><h3>Candidate ${candidate.rank}</h3><strong>${formatDistance(candidate.route.summary.distance_m)}</strong></div><div class="candidate-badges">${candidateBadges(candidate, result.search)}</div><p class="candidate-construction">${escapeHtml(constructionLabel(candidate.construction))}</p><div class="candidate-key-metrics"><span>Target error</span><strong>${formatDistance(candidate.target_error_m)}</strong><span>Other repetition</span><strong>${formatDistance(nonImmediate)} · ${formatPercent(nonImmediateShare)}</strong><span>Major road</span><strong>${formatPercent(analysis.major_road.share)}</strong></div>${metricBar("Total repetition", analysis.repetition.repeated_distance.share, "repetition", formatPercent(analysis.repetition.repeated_distance.share))}${metricBar("Immediate backtracking", analysis.immediate_backtrack.share, "backtrack", formatPercent(analysis.immediate_backtrack.share))}${metricBar("Trail-like", analysis.trail_like.share, "trail", formatPercent(analysis.trail_like.share))}${metricBar("Paved", analysis.paved.share, "paved", formatPercent(analysis.paved.share))}${metricBar("Mapped nature", nature ? nature.nature_score / 100 : null, "nature", nature ? `${nature.nature_score.toFixed(1)} / 100` : "not evaluated")}${loopGeometryCardSummary(loopGeometry)}`;
    selector.addEventListener("click", () => selectCandidate(candidate.signature));
    card.append(selector);
    card.append(loopGeometryCardDetails(loopGeometry));

    const warningCodes = [...new Set([
      ...result.search.warnings,
      ...(candidate.warnings ?? []),
      ...analysis.warnings,
      ...(loopGeometry?.warnings ?? []),
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

function loopGeometrySection(geometry) {
  const sectorGrid = (shares) => `<ol class="loop-sector-grid">${Array.from({ length: 8 }, (_, index) => `<li><span>Sector ${index + 1}</span><strong>${shares ? shares[index].toFixed(6) : "not evaluated"}</strong></li>`).join("")}</ol>`;
  if (!geometry) {
    return `<section class="loop-geometry-panel"><h3>Loop geometry</h3>${metricRows([
      ["Shape penalty (lower is better)", "not evaluated"],
      ["Compactness", "not evaluated"],
      ["Sector balance", "not evaluated"],
      ["Near-parallel corridor", "not evaluated"],
      ["Outbound/return proximity", "not evaluated"],
      ["Self-crossings", "not evaluated"],
    ])}<details class="loop-geometry-exact"><summary>Exact geometry details</summary>${sectorGrid(null)}${metricRows([
      ["Elongation", "not evaluated"],
      ["Angular monotonicity", "not evaluated"],
      ["Maximum sector share", "not evaluated"],
      ["Occupied sectors", "not evaluated"],
      ["Enclosed area", "not evaluated"],
      ["Convex-hull area", "not evaluated"],
      ["Mean radius", "not evaluated"],
      ["Maximum radius", "not evaluated"],
      ["Start/end gap", "not evaluated"],
      ["Closed within 25 m", "not evaluated"],
      ["Crossing component", "not evaluated"],
      ["Near-parallel component", "not evaluated"],
      ["Compactness component", "not evaluated"],
      ["Sector-imbalance component", "not evaluated"],
      ["Elongation component", "not evaluated"],
    ])}</details><p class="context-note">Loop-geometry metrics are unknown, not numeric zero.</p></section>`;
  }
  const penalty = geometry.penalty_breakdown;
  return `<section class="loop-geometry-panel"><h3>Loop geometry</h3>${metricRows([
    ["Shape penalty (lower is better)", penalty.total.toFixed(6)],
    ["Compactness", geometry.compactness.toFixed(6)],
    ["Sector balance", geometry.sector_balance.toFixed(6)],
    ["Near-parallel corridor", `${geometry.near_parallel.distance_m.toFixed(2)} m · ${formatPercent(geometry.near_parallel.share)}`],
    ["Outbound/return proximity", `${geometry.outbound_return_proximity.distance_m.toFixed(2)} m · ${formatPercent(geometry.outbound_return_proximity.share)}`],
    ["Self-crossings", formatCount(geometry.self_crossing_count)],
  ])}<details class="loop-geometry-exact"><summary>Exact geometry details</summary>${sectorGrid(geometry.sector_distance_shares)}${metricRows([
    ["Elongation", geometry.elongation.toFixed(6)],
    ["Angular monotonicity", geometry.angular_monotonicity.toFixed(6)],
    ["Maximum sector share", formatPercent(geometry.maximum_sector_distance_share)],
    ["Occupied sectors", `${geometry.occupied_sector_count} / ${geometry.sector_count}`],
    ["Enclosed area", `${geometry.enclosed_area_m2.toFixed(2)} m²`],
    ["Convex-hull area", `${geometry.convex_hull_area_m2.toFixed(2)} m²`],
    ["Mean radius", `${geometry.mean_radius_m.toFixed(2)} m`],
    ["Maximum radius", `${geometry.max_radius_m.toFixed(2)} m`],
    ["Start/end gap", `${geometry.start_end_gap_m.toFixed(2)} m`],
    ["Closed within 25 m", geometry.closed ? "Yes" : "No"],
    ["Crossing component", `${penalty.crossing_penalty.toFixed(6)} = ${penalty.crossing_penalty_per_crossing.toFixed(2)} × ${penalty.crossing_count_input}`],
    ["Near-parallel component", `${penalty.near_parallel_penalty.toFixed(6)} = ${penalty.near_parallel_penalty_weight.toFixed(2)} × ${penalty.near_parallel_share_input.toFixed(6)}`],
    ["Compactness component", `${penalty.compactness_penalty.toFixed(6)} = ${penalty.compactness_penalty_weight.toFixed(2)} × (1 − ${penalty.compactness_input.toFixed(6)})`],
    ["Sector-imbalance component", `${penalty.sector_imbalance_penalty.toFixed(6)} = ${penalty.sector_imbalance_penalty_weight.toFixed(2)} × (1 − ${penalty.sector_balance_input.toFixed(6)})`],
    ["Elongation component", `${penalty.elongation_penalty.toFixed(6)} = ${penalty.elongation_penalty_weight.toFixed(2)} × (1 − ${penalty.elongation_input.toFixed(6)})`],
  ])}</details><p class="context-note">These projected shape diagnostics do not measure scenic beauty, safety or accessibility. Dense networks and routed geometry resolution can affect corridor detection.</p></section>`;
}

function autoTourItinerary(candidate) {
  const requested = (candidate.requested_place_visits ?? []).map((visit) => `<li><strong>${escapeHtml(visit.requested_place.name)}</strong><span>${visit.satisfied ? "satisfied" : "missed"} · closest ${Number(visit.measured_distance_m).toFixed(1)} m / ${Number(visit.requested_place.visit_radius_m).toFixed(0)} m · ${escapeHtml(friendlyLabel(visit.requested_place.importance))} · ${escapeHtml(friendlyLabel(visit.reason))}</span></li>`).join("");
  const discovered = candidate.poi_visits.map((visit) => `<li><strong>${escapeHtml(visit.poi.display_name)}</strong><span>${formatPercent(visit.route_progress_share)} around route · ${escapeHtml(friendlyLabel(visit.poi.category))} · ${visit.inserted ? "inserted" : "already on route"} · reward ${Number(visit.reward).toFixed(2)}</span></li>`).join("");
  if (!requested && !discovered) {
    return '<section><h3>Accepted-place itinerary</h3><p class="context-note">No scenic or hydration POI is claimed for this route.</p></section>';
  }
  return `<section><h3>Requested and accepted places</h3><ol class="tour-itinerary">${requested}${discovered}</ol></section>`;
}

function renderAutoTourMetrics(candidate, result) {
  const analysis = candidate.route.analysis;
  const search = result.search;
  const warnings = [...new Set([
    ...search.warnings,
    ...(candidate.warnings ?? []),
    ...analysis.warnings,
    ...(analysis.loop_geometry?.warnings ?? []),
    ...(analysis.nature?.warnings ?? []),
  ])];
  const warningItems = warnings.map((warning) => `<li>${escapeHtml(friendlyLabel(warning))}</li>`).join("") || "<li>No route or search warnings.</li>";
  byId("metrics-content").innerHTML = section("Auto Tour", [
    ["Distance", formatDistance(candidate.route.summary.distance_m)],
    ["Target error", formatDistance(candidate.target_error_m)],
    ["Within tolerance", candidate.within_tolerance ? "Yes" : "No"],
    ["Distance priority", friendlyLabel(candidate.distance_priority)],
    ["Soft-distance penalty", Number(candidate.soft_distance_penalty).toFixed(6)],
    ["Safety maximum", formatDistance(candidate.maximum_distance_m)],
    ["Direction", friendlyLabel(candidate.direction)],
    ["Skeleton", `${friendlyLabel(candidate.skeleton_method)} · ${candidate.skeleton_id}`],
    ["Construction", friendlyLabel(candidate.construction)],
    ["No-POI control retained", search.control_retained ? "Yes" : "No"],
    ["This candidate is control", candidate.signature === search.control_signature ? "Yes" : "No"],
  ]) + section("Places", [
    ["Scenic POIs visited", formatCount(candidate.selected_scenic_count)],
    ["Verified water visited", formatCount(candidate.selected_verified_water_count)],
    ["Total POI reward", Number(candidate.total_poi_reward).toFixed(3)],
    ["Inserted POI reward", Number(candidate.inserted_poi_reward).toFixed(3)],
    ["Must-visit requested places", `${candidate.satisfied_must_visit_count} satisfied`],
    ["Preferred requested places", `${candidate.satisfied_preferred_place_count} satisfied`],
    ["Safe against control", candidate.control_comparison.eligible ? "Yes" : "No"],
  ]) + autoTourItinerary(candidate) + section("Natural loop quality", [
    ["Total repetition", `${formatDistance(analysis.repetition.repeated_distance.distance_m)} · ${formatPercent(analysis.repetition.repeated_distance.share)}`],
    ["Immediate backtracking", `${formatDistance(analysis.immediate_backtrack.distance_m)} · ${formatPercent(analysis.immediate_backtrack.share)}`],
    ["Major roads", formatPercent(analysis.major_road.share)],
  ]) + loopGeometrySection(analysis.loop_geometry) + natureSection(analysis.nature, {
    nature_index_available: Boolean(analysis.nature),
  }) + section("Bounded search accounting", [
    ["Isochrone requests", `${search.isochrone_request_count} / 1`],
    ["Round-trip controls", `${search.round_trip_control_request_count} / 8`],
    ["Sampled fallback skeletons", search.sampled_fallback_skeleton_count],
    ["Skeleton route calls", `${search.skeleton_route_request_count} / 24`],
    ["Retained skeletons", `${search.retained_skeleton_count} / 6`],
    ["POI route evaluations", `${search.poi_route_evaluation_count} / 24`],
    ["Local repairs", `${search.local_repair_evaluation_count} / 12`],
    ["Corridor continuation repairs", search.corridor_repair_evaluation_count],
    ["Alternative-leg requests", `${search.alternative_leg_request_count} / 24`],
    ["Total route requests", `${search.total_route_request_count} / ${search.total_route_request_budget}`],
    ["Route-cache hits", search.route_cache_hit_count],
    ["Budget exhausted", search.budget_exhausted ? "Yes" : "No"],
    ["Total time", `${Number(search.timings.total_seconds).toFixed(3)} s`],
  ]) + `<section><h3>Warnings</h3><ul class="warning-list">${warningItems}</ul></section>`;
}

function renderMetrics() {
  const candidate = selectedCandidate();
  const result = state.generationResult;
  byId("metrics-empty").classList.toggle("hidden", Boolean(candidate));
  byId("metrics-content").classList.toggle("hidden", !candidate);
  byId("download-gpx").disabled = !candidate || state.request.status === "running";
  if (!candidate || !result) return;
  if (state.planningMode === "auto_tour") {
    renderAutoTourMetrics(candidate, result);
    return;
  }
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
    ...(analysis.loop_geometry?.warnings ?? []),
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
  ]) + loopGeometrySection(analysis.loop_geometry) + natureSection(analysis.nature, search) + section("Search diagnostics", [
    ["Status", friendlyLabel(search.status)],
    ["Loop shape requested", search.loop_geometry_requested ? "Yes" : "No"],
    ["Recommended shape penalty", nullable(search.recommended_loop_geometry_penalty, (value) => Number(value).toFixed(6))],
    ["Best available shape penalty", nullable(search.best_available_loop_geometry_penalty, (value) => Number(value).toFixed(6))],
    ["Nature preference requested", search.nature_requested ? "Yes" : "No"],
    ["Nature index available", search.nature_index_available ? "Yes" : "No"],
    ["Nature index features", nullable(search.nature_index_feature_count, formatCount)],
    ["Recommended nature score", nullable(search.recommended_nature_score, (value) => `${Number(value).toFixed(1)} / 100`)],
    ["Best available nature score", nullable(search.best_available_nature_score, (value) => `${Number(value).toFixed(1)} / 100`)],
    ["Full-route evaluations", `${formatCount(search.evaluated_candidate_count)} / ${formatCount(search.search_budget)}`],
    ["Base evaluation budget", formatCount(search.base_search_budget)],
    ["Base evaluations", formatCount(search.evaluated_candidate_count - search.loop_geometry_extra_evaluated_count)],
    ["Geometry extra budget", formatCount(search.loop_geometry_extra_evaluation_budget)],
    ["Geometry extra evaluations", formatCount(search.loop_geometry_extra_evaluated_count)],
    ["Geometry extra successes", formatCount(search.loop_geometry_extra_successful_count)],
    ["Geometry extra rejections", formatCount(search.loop_geometry_extra_rejected_count)],
    ["Round-trip proposal calls", search.round_trip_proposal_count],
    ["Derived proposal sequences", search.derived_proposal_sequence_count],
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
  ]) + `<section><h3>Warnings</h3><ul class="warning-list">${warnings}</ul><details><summary>Raw warning codes</summary><pre>${escapeHtml(JSON.stringify({ search: search.warnings, route: analysis.warnings, loop_geometry: analysis.loop_geometry?.warnings ?? [], nature: analysis.nature?.warnings ?? [] }, null, 2))}</pre></details></section>`;
}

function renderStatus() {
  const running = state.request.status === "running";
  const minimumPoints = state.planningMode === "auto_tour" ? 1 : 2;
  byId("generate").disabled = running || state.points.length < minimumPoints || Boolean(pointValidation());
  byId("generate-top").disabled = byId("generate").disabled;
  byId("cancel").classList.toggle("hidden", !running);
  byId("generation-state").classList.toggle("hidden", !running);
  document
    .querySelectorAll("#route-form input, #route-form select, #poi-list input, #poi-list button, #add-point-mode, #clear-points, input[name='planning-mode']")
    .forEach((control) => { control.disabled = running; });
  byId("request-status").classList.toggle("running", running);
  if (!running && state.points.length < minimumPoints) {
    byId("request-status").textContent = state.planningMode === "auto_tour"
      ? "Choose an Auto Tour start point."
      : "Add at least two mandatory points.";
  }
}

function renderEmptyState() {
  const hasWork = state.points.length > 0 || state.importedGpx || state.generationResult;
  byId("planner-empty").classList.toggle("hidden", Boolean(hasWork));
}

function render() {
  renderModeControls();
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
  saveActivePoints();
  const request = state.planningMode === "auto_tour" ? currentAutoTourRequest() : currentRequest();
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
    const result = state.planningMode === "auto_tour"
      ? await generateAutoTour(request, state.abortController.signal)
      : await generateRoutes(request, state.abortController.signal);
    if (state.request.id !== id) return;
    state.generationResult = result;
    state.selectedSignature = result.candidates[0]?.signature ?? null;
    state.visualizationCache.clear();
    state.request = { status: "success", id, startedAt: null };
    byId("request-status").textContent = result.candidates.length
      ? `${result.candidates.length} candidate route${result.candidates.length === 1 ? "" : "s"} generated.`
      : state.planningMode === "auto_tour"
        ? "No safe Auto Tour candidate was returned."
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
      category: typeof point.category === "string" ? point.category : null,
      potability: typeof point.potability === "string" ? point.potability : null,
      visitRadiusM: Number(point.visit_radius_m),
      importance: point.importance,
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
  const loopGeometryPreference = value.loop_geometry_preference ?? "off";
  if (
    !["fixed", "optimize_loop"].includes(pointOrderMode)
    || !["shortest", "low_overlap"].includes(pathSelectionMode)
    || !["off", "prefer"].includes(requestedNaturePreference)
    || !["off", "prefer"].includes(loopGeometryPreference)
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
      loopGeometryPreference,
    },
  };
}

function importedVisitRadius(point) {
  if (Number.isFinite(point.visitRadiusM) && point.visitRadiusM >= 25 && point.visitRadiusM <= 500) {
    return point.visitRadiusM;
  }
  if (point.category === "castle") return 200;
  if (point.category === "viewpoint") return 125;
  if (point.category === "drinking_water" && point.potability === "verified") return 50;
  return 100;
}

async function importRequest(file) {
  try {
    const imported = normalizeImportedRequest(JSON.parse(await file.text()));
    state.options = imported.options;
    if (state.planningMode === "auto_tour") {
      const [start, ...requested] = imported.points;
      state.autoTour.start = start;
      state.autoTour.hardPoints = [];
      state.autoTour.requestedPlaces = requested.map((point, index) => ({
        id: requestedPlaceIdentifier({
          coordinate: { lat: point.lat, lon: point.lon },
          originalIndex: point.originalIndex ?? index + 1,
        }, index),
        name: point.name,
        coordinate: { lat: point.lat, lon: point.lon },
        visitRadiusM: importedVisitRadius(point),
        importance: ["must_visit", "prefer"].includes(point.importance)
          ? point.importance
          : "must_visit",
        originalIndex: point.originalIndex ?? index + 1,
      }));
      state.autoTourOptions = { ...imported.options };
      state.points = [start];
      state.selectedPointIndex = 0;
      state.selectedRequestedPlaceId = null;
      state.pendingRequestedPlacePopupId = null;
    } else {
      state.points = imported.points;
      state.waypointPoints = [...imported.points];
      state.selectedPointIndex = state.points.length ? 0 : null;
    }
    state.pendingPointPopupIndex = null;
    updateControlsFromOptions();
    invalidateAndRender();
    byId("request-status").textContent = state.planningMode === "auto_tour"
      ? `${file.name} loaded. The first point is the exact start; ${state.autoTour.requestedPlaces.length} ordered places are close-enough Auto Tour objectives.`
      : `${file.name} loaded. All ${state.points.length} names and exact required points are ready for review.`;
    fitCoordinates(imported.points.map((point) => [point.lon, point.lat]));
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
  byId("route-form").addEventListener("change", (event) => {
    if (
      ["auto-start-lat", "auto-start-lon"].includes(event.target.id)
      && (!byId("auto-start-lat").value || !byId("auto-start-lon").value)
    ) return;
    updateOptionsFromControls();
    invalidateAndRender();
  });
  document.querySelectorAll('input[name="planning-mode"]').forEach((input) => {
    input.addEventListener("change", () => {
      if (!input.checked) return;
      updateOptionsFromControls();
      switchPlanningMode(input.value);
      updateControlsFromOptions();
      invalidateAndRender();
    });
  });
  ["auto-start-lat", "auto-start-lon"].forEach((id) => {
    byId(id).addEventListener("change", () => {
      if (!byId("auto-start-lat").value || !byId("auto-start-lon").value) return;
      const lat = Number(byId("auto-start-lat").value);
      const lon = Number(byId("auto-start-lon").value);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
      const existing = state.points[0] ?? { name: "Start", originalIndex: 0 };
      const start = { ...existing, lat, lon };
      if (state.points.length) state.points[0] = start;
      else state.points.push(start);
      state.selectedPointIndex = 0;
      invalidateAndRender();
    });
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
    const requested = state.planningMode === "auto_tour"
      ? state.autoTour.requestedPlaces.map((place) => [place.coordinate.lon, place.coordinate.lat])
      : [];
    fitCoordinates([...state.points.map((point) => [point.lon, point.lat]), ...requested]);
  });
  byId("clear-points").addEventListener("click", () => {
    if (state.points.length > 1 && !window.confirm("Remove all mandatory points and generated results?")) return;
    state.points = [];
    if (state.planningMode === "auto_tour") {
      state.autoTour.requestedPlaces = [];
      state.selectedRequestedPlaceId = null;
      state.pendingRequestedPlacePopupId = null;
    }
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
  byId("show-missed-requested-radii").addEventListener("change", (event) => {
    state.showMissedRequestedRadii = event.target.checked;
    renderMapData();
  });
  byId("places-filters").addEventListener("change", () => {
    updatePoiFiltersFromControls();
    schedulePoiRefresh();
  });
  byId("download-gpx").addEventListener("click", downloadSelected);
  byId("copy-request").addEventListener("click", async () => {
    try {
      updateOptionsFromControls();
      saveActivePoints();
      const request = state.planningMode === "auto_tour" ? currentAutoTourRequest() : currentRequest();
      await navigator.clipboard.writeText(JSON.stringify(request, null, 2));
      byId("request-status").textContent = state.planningMode === "auto_tour"
        ? "Auto Tour request copied with requested places, distance priority, and POI preferences."
        : "Request JSON copied with every required-point name.";
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
    try {
      state.poiIndexStatus = await getPoiStatus();
    } catch {
      state.poiIndexStatus = { available: false, feature_count: null };
    }
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
    const poiAvailable = Boolean(
      state.config.poi_index_available && state.poiIndexStatus?.available,
    );
    state.config.poi_index_available = poiAvailable;
    byId("places-filters").querySelectorAll("input").forEach((input) => {
      input.disabled = !poiAvailable;
    });
    byId("places-status").textContent = poiAvailable
      ? `Local OSM places index ready · ${formatCount(state.poiIndexStatus.feature_count)} regional features.`
      : "POI index unavailable. Place discovery is disabled; routing still works.";
    initializeMap(state.config, {
      onReady: () => {
        mapReady = true;
        renderMapData();
      },
      onError: showMapError,
      onViewportChange: schedulePoiRefresh,
      onMapClick: (coordinate) => {
        if (!state.addPointMode) return;
        const maximum = state.planningMode === "auto_tour" ? 7 : state.config.max_required_points;
        if (state.points.length >= maximum) {
          showError(state.planningMode === "auto_tour"
            ? "Auto Tour already has a start and the maximum six hard anchors."
            : "The route already has the maximum 30 mandatory points.");
          return;
        }
        const nextOriginalIndex = state.points.reduce(
          (highest, point) => Math.max(highest, Number.isInteger(point.originalIndex) ? point.originalIndex : -1),
          -1,
        ) + 1;
        state.points.push({
          name: state.planningMode === "auto_tour"
            ? (state.points.length ? `Hard anchor ${state.points.length}` : "Start")
            : `Point ${state.points.length + 1}`,
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
