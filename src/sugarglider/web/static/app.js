import { ApiError, exportPlanCandidate, generatePlan, getConfig, getPoiStatus, getRoutingProfiles, searchPois, visualizeRoute } from "./api.js";
import { constructionLabel, escapeHtml, formatCount, formatDistance, formatPercent, friendlyLabel, lowOverlapLabel, metricRows } from "./format.js";
import { parseGpx } from "./gpx.js";
import { createIcon, decorateIcons } from "./icons.js";
import { clearRoutes, currentViewportBounds, fitCoordinates, focusCoordinate, initializeMap, renderCandidates, renderHardEndpoints, renderImportedGpx, renderOptionalMarkers, renderPois, renderRequestedPlaces as renderRequestedPlaceMarkers, renderRequiredMarkers, renderVisualization, resizeMap } from "./map.js";
import { currentPlanRequest, invalidateCandidates, pointDisplayName, requestedPlaceIdentifier, saveActivePoints, selectedCandidate, state, switchPlanningMode } from "./state.js";

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

const GENERATION_SUGGESTION = "Use Auto Tour for approximate places, or remove or move the exact waypoint.";
let lastExactFailure = null;

function showError(message, details = "", code = "", context = "", suggestion = "") {
  const codeElement = byId("error-code");
  const contextElement = byId("error-context");
  const suggestionElement = byId("error-suggestion");
  codeElement.textContent = code ? `Error code: ${code}` : "";
  codeElement.classList.toggle("hidden", !code);
  byId("error-message").textContent = message;
  contextElement.textContent = context;
  contextElement.classList.toggle("hidden", !context);
  suggestionElement.textContent = suggestion;
  suggestionElement.classList.toggle("hidden", !suggestion);
  byId("error-details").textContent = details;
  byId("error-banner").classList.remove("hidden");
  byId("exact-error-actions").classList.toggle(
    "hidden",
    code !== "exact_waypoint_not_reached",
  );
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

function selectPoi(id, { revealMap = false } = {}) {
  const visitFeatures = (selectedCandidate()?.poi_visits ?? []).map((visit) => visit.poi);
  const allFeatures = [...new Map(
    [...state.poiFeatures, ...visitFeatures].map((feature) => [feature.id, feature]),
  ).values()];
  const feature = allFeatures.find((value) => value.id === id);
  if (!feature) return;
  state.selectedPoiId = id;
  renderPois(allFeatures, state.selectedPoiId, selectPoi, poiRenderOptions());
  if (revealMap) {
    focusCoordinate([feature.coordinate.lon, feature.coordinate.lat]);
  }
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
  const eligibleAccess = ["public", "unknown"].includes(feature.access_status);
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
  state.routingProfile = byId("profile").value;
  state.options = {
    name: byId("route-name").value.trim() || "Sugarglider route",
    targetDistanceKm: Number(byId("target-distance").value),
    toleranceKm: Number(byId("tolerance").value),
    candidateCount: Number(byId("candidate-count").value),
    seed: Number(byId("seed").value),
    waypointOrder: byId("point-order-mode").value,
    pathSelectionMode: byId("path-selection-mode").value,
    naturePreference: byId("nature-preference").value,
    loopGeometryPreference: byId("loop-geometry-preference").value,
    freePoiSpurRepeatedM: Number(byId("free-poi-spur").value),
  };
  state.autoTour.directionPreference = byId("direction-preference").value;
  state.autoTour.distancePriority = byId("distance-priority").value;
  state.autoTour.maximumDistanceKm = byId("maximum-distance").value.trim()
    ? Number(byId("maximum-distance").value)
    : null;
  state.autoTour.scenicPreference = byId("scenic-preference").value;
  state.autoTour.drinkingWaterPreference = byId("water-preference").value;
  activeEndpoints().routeTopology = byId("route-topology").value;
}

function updateControlsFromOptions() {
  byId("profile").value = state.routingProfile;
  byId("route-name").value = state.options.name;
  byId("target-distance").value = state.options.targetDistanceKm;
  byId("tolerance").value = state.options.toleranceKm;
  byId("candidate-count").value = state.options.candidateCount;
  byId("seed").value = state.options.seed;
  byId("point-order-mode").value = state.options.waypointOrder;
  byId("path-selection-mode").value = state.options.pathSelectionMode;
  byId("nature-preference").value = state.options.naturePreference;
  byId("loop-geometry-preference").value = state.options.loopGeometryPreference;
  byId("free-poi-spur").value = state.options.freePoiSpurRepeatedM ?? 200;
  byId("direction-preference").value = state.autoTour.directionPreference;
  byId("distance-priority").value = state.autoTour.distancePriority;
  byId("maximum-distance").value = state.autoTour.maximumDistanceKm ?? "";
  byId("scenic-preference").value = state.autoTour.scenicPreference;
  byId("water-preference").value = state.autoTour.drinkingWaterPreference;
  updateProfileDescription();
}

function renderRoutingProfiles() {
  const select = byId("profile");
  select.replaceChildren();
  const groups = new Map([
    ["running", "Running"],
    ["walking", "Walking"],
    ["cycling", "Cycling"],
  ]);
  for (const [kind, label] of groups) {
    const statuses = state.routingProfileCatalog.profiles.filter(
      (status) => status.profile.activity_kind === kind,
    );
    if (!statuses.length) continue;
    const group = document.createElement("optgroup");
    group.label = label;
    statuses.forEach((status) => {
      const option = document.createElement("option");
      option.value = status.profile.id;
      option.textContent = status.available
        ? status.profile.display_name
        : `${status.profile.display_name} — unavailable`;
      option.disabled = !status.available;
      group.append(option);
    });
    select.append(group);
  }
  const selected = selectedProfileStatus();
  if (!selected?.available) {
    state.routingProfile = state.routingProfileCatalog.profiles.find(
      (status) => status.available,
    )?.profile.id ?? null;
  }
  select.value = state.routingProfile ?? "";
  updateProfileDescription();
}

function selectedProfileStatus(profileId = state.routingProfile) {
  return state.routingProfileCatalog?.profiles.find(
    (status) => status.profile.id === profileId,
  ) ?? null;
}

function profileDisplayName(profileId) {
  return selectedProfileStatus(profileId)?.profile.display_name
    ?? friendlyLabel(profileId);
}

function updateProfileDescription() {
  const status = selectedProfileStatus(byId("profile").value);
  byId("profile-description").textContent = status
    ? `${status.profile.short_description} Elevation-aware routing: ${status.profile.capabilities.elevation_aware ? "yes" : "no"}.${status.available ? "" : " This profile is unavailable in the routing backend."}`
    : "Select a routing profile.";
}

function activeEndpoints() {
  return state.planningMode === "auto_tour"
    ? state.autoTour
    : state.waypointEndpoints;
}

function isOpenPlan() {
  const endpoints = activeEndpoints();
  return endpoints.routeTopology === "point_to_point";
}

function assignActiveEndpoint(kind, point) {
  if (state.planningMode === "auto_tour") {
    saveActivePoints();
    state.autoTour[kind] = point;
    if (kind === "start") {
      state.points = point
        ? [point, ...state.autoTour.hardPoints]
        : [...state.autoTour.hardPoints];
    }
  } else {
    state.waypointEndpoints[kind] = point;
  }
}

function endpointFromControls(kind) {
  if (!byId(`hard-${kind}-enabled`).checked) return null;
  const lat = Number(byId(`hard-${kind}-lat`).value);
  const lon = Number(byId(`hard-${kind}-lon`).value);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  return {
    name: byId(`hard-${kind}-name`).value.trim() || `Hard ${kind}`,
    lat,
    lon,
  };
}

function updateEndpointControls() {
  const endpoints = activeEndpoints();
  byId("route-topology").value = endpoints.routeTopology;
  for (const kind of ["start", "end"]) {
    const point = endpoints[kind];
    byId(`hard-${kind}-enabled`).checked = Boolean(point);
    byId(`hard-${kind}-name`).value = point?.name ?? "";
    byId(`hard-${kind}-lat`).value = point?.lat ?? "";
    byId(`hard-${kind}-lon`).value = point?.lon ?? "";
  }
  const topology = endpoints.routeTopology;
  const orderSelect = byId("point-order-mode");
  if (state.planningMode === "waypoint_route") {
    const optimized = orderSelect.querySelector('option[data-optimized="true"]');
    optimized.textContent = topology === "point_to_point"
      ? "Optimize interior waypoints"
      : "Optimize loop waypoints";
    orderSelect.value = state.options.waypointOrder;
  }
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
  const candidate = selectedCandidate();
  const decisions = [
    ...(candidate?.reached_stops ?? [])
      .filter((stop) => stop.selection_origin === "requested")
      .map((stop) => [stop.id, { decision: "reached" }]),
    ...(candidate?.approximated_stops ?? [])
      .filter((stop) => stop.selection_origin === "requested")
      .map((stop) => [stop.id, { decision: "approximated" }]),
    ...(candidate?.dropped_stops ?? [])
      .filter((stop) => stop.selection_origin === "requested")
      .map((stop) => [stop.id, { decision: "dropped" }]),
  ];
  return new Map(decisions);
}

function requestedPlaceStatus(place, index, visits = selectedRequestedVisits()) {
  const visit = visits.get(place.id ?? requestedPlaceIdentifier(place, index));
  return visit?.decision ?? "pending";
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
    label.textContent = `${index + 1}. ${place.name} · access search ${place.accessSearchRadiusM ?? place.visitRadiusM ?? 500} m · ${friendlyLabel(place.importance)}`;
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
    const approach = document.createElement("button");
    approach.type = "button";
    approach.className = "text-button";
    approach.textContent = "Set approach on map";
    approach.addEventListener("click", () => {
      state.settingRequestedApproachId = id;
      state.selectedRequestedPlaceId = id;
      approach.textContent = "Click map once…";
    });
    const clearApproach = document.createElement("button");
    clearApproach.type = "button";
    clearApproach.className = "text-button";
    clearApproach.textContent = "Clear approach";
    clearApproach.disabled = !place.approachOverride;
    clearApproach.addEventListener("click", () => {
      place.approachOverride = null;
      invalidateAndRender();
    });
    item.append(details, approach, clearApproach, remove);
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
  updateEndpointControls();
  renderPreferredPois();
  byId("show-dropped-requested-radii-control").classList.toggle("hidden", !auto);
  renderRequestedPlacesList();
}

function validPoint(point) {
  return Number.isFinite(point.lat)
    && Number.isFinite(point.lon)
    && Math.abs(point.lat) <= 90
    && Math.abs(point.lon) <= 180;
}

function pointValidation() {
  const maximum = state.planningMode === "auto_tour"
    ? 6 + Number(Boolean(state.autoTour.start))
    : (state.config?.max_required_points ?? 30);
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
  const endpoints = activeEndpoints();
  if (!endpoints.start) return "Choose an explicit start.";
  if (endpoints.routeTopology === "loop" && endpoints.end) {
    return "Loop plans must not contain an end.";
  }
  if (endpoints.routeTopology === "point_to_point" && !endpoints.end) {
    return "Point-to-point plans require an explicit end.";
  }
  for (const [label, point] of [["Hard start", endpoints.start], ["Hard end", endpoints.end]]) {
    if (point && !validPoint(point)) return `${label} needs valid coordinates.`;
  }
  if (
    endpoints.routeTopology === "point_to_point"
    && endpoints.start
    && endpoints.end
    && endpoints.start.lat === endpoints.end.lat
    && endpoints.start.lon === endpoints.end.lon
  ) return "Point-to-point start and end must have distinct coordinates.";
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
    (candidate?.diagnostics.details.required_waypoint_order ?? []).map((visit, index) => [
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
  const hardCount = state.planningMode === "auto_tour"
    ? Math.max(state.points.length - Number(Boolean(state.autoTour.start)), 0)
    : state.points.length;
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
  if (state.planningMode === "auto_tour" && state.autoTour.start && index === 0) {
    saveActivePoints();
    state.autoTour.start = null;
    state.points = [...state.autoTour.hardPoints];
    state.selectedPointIndex = state.points.length ? 0 : null;
    invalidateAndRender();
    return;
  }
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
    candidate?.diagnostics.details.required_waypoint_order,
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
    !(state.planningMode === "waypoint_route" && state.waypointEndpoints.start),
  );
  const endpoints = activeEndpoints();
  renderHardEndpoints(
    state.planningMode === "auto_tour" ? null : endpoints.start,
    endpoints.end,
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
    candidate ? state.visualizationCache.get(candidate.id) ?? null : null,
    state.showNatureContext,
  );
  const allFeatures = state.poiFeatures;
  renderPois(allFeatures, state.selectedPoiId, selectPoi, poiRenderOptions());
  const constraintPlaces = state.planningMode === "auto_tour"
    ? state.autoTour.requestedPlaces
    : state.points.filter((point) => point.constraintStrength !== "exact").map((point, index) => ({
      id: point.id ?? `route-waypoint-${index + 1}`,
      name: point.name,
      coordinate: { lat: point.lat, lon: point.lon },
      importance: "must_visit",
      accessSearchRadiusM: point.accessSearchRadiusM ?? 500,
    }));
  const constraintVisits = [
    ...(candidate?.reached_stops ?? []),
    ...(candidate?.approximated_stops ?? []),
    ...(candidate?.dropped_stops ?? []),
  ].filter((stop) => stop.selection_origin === "requested");
  renderRequestedPlaceMarkers(
    constraintPlaces,
    constraintVisits,
    state.selectedRequestedPlaceId,
    state.showDroppedRequestedRadii,
    (id) => {
      if (state.planningMode === "auto_tour") {
        selectRequestedPlace(id, { scrollList: true });
      } else {
        const point = constraintPlaces.find((value) => value.id === id);
        if (point) focusCoordinate([point.coordinate.lon, point.coordinate.lat]);
      }
    },
    requestedPopupId,
  );
}

function candidateBadges(candidate, search) {
  const values = [];
  values.push(`<span class="badge">${escapeHtml(profileDisplayName(candidate.routing_profile))}</span>`);
  for (const role of candidate.roles) {
    values.push(`<span class="badge">${escapeHtml(friendlyLabel(role))}</span>`);
  }
  if (candidate.rank === 1) values.push('<span class="badge recommended">Recommended</span>');
  values.push(`<span class="badge ${candidate.diagnostics.within_tolerance ? "good" : "warn"}">${candidate.diagnostics.within_tolerance ? "Within tolerance" : "Outside tolerance"}</span>`);
  return values.join("");
}

function autoCandidateSummary(candidate, result, nonImmediate, nonImmediateShare) {
  const analysis = candidate.route.analysis;
  const targetDifference = candidate.route.summary.distance_m - state.options.targetDistanceKm * 1000;
  const targetDifferenceLabel = `${targetDifference >= 0 ? "+" : "−"}${formatDistance(Math.abs(targetDifference))}`;
  const requestedTotal = candidate.reached_stops.filter((stop) => stop.selection_origin === "requested").length
    + candidate.approximated_stops.filter((stop) => stop.selection_origin === "requested").length
    + candidate.dropped_stops.filter((stop) => stop.selection_origin === "requested").length;
  const requestedSelected = candidate.diagnostics.requested_stop_count;
  const discoveredSelected = candidate.reached_stops.filter((stop) => stop.selection_origin !== "requested").length;
  const metrics = [
    ["Covered requested stops", `${formatCount(requestedSelected)} / ${formatCount(requestedTotal)}`],
    ["Reached discovered stops", formatCount(discoveredSelected)],
    ["Distance", formatDistance(candidate.route.summary.distance_m)],
    ["Target difference", targetDifferenceLabel],
    ["Immediate backtracking", formatDistance(candidate.diagnostics.immediate_backtracking_m)],
  ].map(([label, value]) => `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`).join("");
  return `<div class="candidate-title"><h3>Candidate ${candidate.rank}</h3><strong>${formatDistance(candidate.route.summary.distance_m)}</strong></div><div class="candidate-badges">${candidateBadges(candidate, result.search_diagnostics)}</div><p class="candidate-construction">${escapeHtml(friendlyLabel(candidate.diagnostics.details.construction ?? result.kind))}</p><div class="candidate-key-metrics">${metrics}</div>${metricBar("Total repetition", analysis.repetition.repeated_distance.share, "repetition", formatPercent(analysis.repetition.repeated_distance.share))}${metricBar("Immediate backtracking", analysis.immediate_backtrack.share, "backtrack", formatPercent(analysis.immediate_backtrack.share))}${metricBar("Outbound/return proximity", analysis.loop_geometry?.outbound_return_proximity.share ?? null, "backtrack", analysis.loop_geometry ? formatPercent(analysis.loop_geometry.outbound_return_proximity.share) : "not evaluated")}${metricBar("Mapped nature", analysis.nature ? analysis.nature.nature_score / 100 : null, "nature", analysis.nature ? `${analysis.nature.nature_score.toFixed(1)} / 100` : "not evaluated")}${loopGeometryCardSummary(analysis.loop_geometry)}`;
}

function metricBar(label, share, className, displayValue) {
  if (share === null || share === undefined) {
    return `<div class="bar-metric ${className} not-evaluated"><div class="bar-heading"><span>${escapeHtml(label)}</span><strong>not evaluated</strong></div><div class="metric-track" aria-hidden="true"></div></div>`;
  }
  const percentage = Math.max(0, Math.min(100, Number(share) * 100));
  return `<div class="bar-metric ${className}"><div class="bar-heading"><span>${escapeHtml(label)}</span><strong>${escapeHtml(displayValue)}</strong></div><div class="metric-track" role="img" aria-label="${escapeHtml(`${label}: ${displayValue}`)}"><div class="metric-fill" style="--metric-value:${percentage.toFixed(3)}%"></div></div></div>`;
}

function primaryQualityMetric(analysis) {
  const quality = analysis.activity_quality;
  const covered = (detail) => Number(quality.detail_coverage?.[detail] ?? 0) > 0;
  if (quality.activity_kind === "walking") return ["Trail-like", covered("road_class") ? quality.trail_like.share : null];
  if (quality.activity_kind === "running") return ["Runnable surface", covered("surface") ? quality.runnable_surface.share : null];
  if (quality.activity_kind === "cycling") {
    return ["Cycling network", covered("bike_network") ? quality.cycling_network.share : null];
  }
  return null;
}

function activityQualitySection(analysis) {
  const quality = analysis.activity_quality;
  const metric = (label, value, detail) => {
    const coverage = Number(quality.detail_coverage?.[detail] ?? 0);
    return [
      label,
      coverage > 0
        ? `${formatDistance(value.distance_m)} · ${formatPercent(value.share)}`
        : "not evaluated",
    ];
  };
  if (quality.activity_kind === "walking") {
    return section("Hiking quality", [
      metric("Trail-like", quality.trail_like, "road_class"),
      metric("Hiking network", quality.official_hiking_network, "foot_network"),
      metric("Technical hiking", quality.technical_hiking, "hike_rating"),
      metric("Steps", quality.steps, "road_class"),
      metric("Poor smoothness", quality.poor_smoothness, "smoothness"),
    ]);
  }
  if (quality.activity_kind === "running") {
    return section("Trail-running quality", [
      metric("Runnable surface", quality.runnable_surface, "surface"),
      metric("Trail-like", quality.trail_like, "road_class"),
      metric("Technical trail", quality.technical_trail, "hike_rating"),
      metric("Steps", quality.steps, "road_class"),
      metric("Poor smoothness", quality.poor_smoothness, "smoothness"),
      metric("Major roads", quality.major_road, "road_class"),
    ]);
  }
  if (quality.activity_kind === "cycling") {
    return section("Cycling quality", [
      metric("Cycling network", quality.cycling_network, "bike_network"),
      metric("Cycleway-like", quality.cycleway_like, "road_class"),
      metric("Paved", quality.paved, "surface"),
      metric("Suitable unpaved", quality.suitable_unpaved, "surface"),
      metric("Tracks", quality.track, "road_class"),
      metric("Rough surface", quality.rough_surface, "surface"),
      metric("Steps", quality.steps, "road_class"),
      metric("Major roads", quality.major_road, "road_class"),
      [
        "MTB-rating coverage",
        Number(quality.detail_coverage?.mtb_rating ?? 0) > 0
          ? formatPercent(quality.mtb_rating.coverage_share)
          : "not evaluated",
      ],
    ]);
  }
  return "";
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
    container.innerHTML = result
      ? '<p class="empty-copy">No route candidate could satisfy the current hard constraints.</p>'
      : '<p class="empty-copy">Returned routes will appear here in ranked order.</p>';
    byId("search-summary").textContent = result
      ? "No safe planning candidates returned"
      : "";
    return;
  }
  byId("search-summary").textContent = `${result.candidates.length} canonical candidate${result.candidates.length === 1 ? "" : "s"} returned`;
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
    const selected = candidate.id === state.selectedSignature;
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
      : (() => { const quality = primaryQualityMetric(analysis); return `<div class="candidate-title"><h3>Candidate ${candidate.rank}</h3><strong>${formatDistance(candidate.route.summary.distance_m)}</strong></div><div class="candidate-badges">${candidateBadges(candidate, result.search_diagnostics)}</div><p class="candidate-construction">${escapeHtml(constructionLabel(candidate.diagnostics.details.construction ?? "route"))}</p><div class="candidate-key-metrics"><span>Target error</span><strong>${formatDistance(candidate.diagnostics.target_error_m)}</strong><span>Other repetition</span><strong>${formatDistance(nonImmediate)} · ${formatPercent(nonImmediateShare)}</strong><span>Major road</span><strong>${formatPercent(analysis.major_road.share)}</strong></div>${metricBar("Total repetition", analysis.repetition.repeated_distance.share, "repetition", formatPercent(analysis.repetition.repeated_distance.share))}${metricBar("Immediate backtracking", analysis.immediate_backtrack.share, "backtrack", formatPercent(analysis.immediate_backtrack.share))}${quality ? metricBar(quality[0], quality[1], "trail", quality[1] == null ? "not evaluated" : formatPercent(quality[1])) : ""}${metricBar("Paved", analysis.paved.share, "paved", formatPercent(analysis.paved.share))}${metricBar("Mapped nature", nature ? nature.nature_score / 100 : null, "nature", nature ? `${nature.nature_score.toFixed(1)} / 100` : "not evaluated")}${loopGeometryCardSummary(loopGeometry)}`; })();
    selector.addEventListener("click", () => selectCandidate(candidate.id));
    card.append(selector);
    card.append(loopGeometryCardDetails(loopGeometry));

    const warningCodes = [...new Set([
      ...result.search_diagnostics.warnings,
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

function constraintItinerary(candidate) {
  const reached = (candidate.reached_stops ?? []).map((stop, index) => {
    return `<li class="itinerary-stop" role="button" tabindex="0" data-itinerary-stop-id="${escapeHtml(stop.id)}" data-itinerary-origin="${escapeHtml(stop.selection_origin)}"><strong>${index + 1}. ${escapeHtml(stop.name)}</strong><span>${escapeHtml(friendlyLabel(stop.category))} · ${escapeHtml(friendlyLabel(stop.resolved_approach.kind))} · arrival ${Number(stop.route_to_approach_m).toFixed(1)} m / ${Number(stop.resolved_approach.arrival_tolerance_m).toFixed(0)} m · ${escapeHtml(friendlyLabel(stop.selection_method))}</span></li>`;
  }).join("");
  const approximated = (candidate.approximated_stops ?? []).map((stop) => `<li class="itinerary-stop approximated" role="button" tabindex="0" data-itinerary-stop-id="${escapeHtml(stop.id)}" data-itinerary-origin="${escapeHtml(stop.selection_origin)}"><strong>${escapeHtml(stop.name)} — approximated</strong><span>${formatDistance(stop.distance_m)} from the semantic place · normal tolerance ${formatDistance(stop.normal_tolerance_m)} · ${escapeHtml(friendlyLabel(stop.reason))} · access ${escapeHtml(friendlyLabel(stop.resolved_approach.access))}</span><div class="button-row"><button type="button" data-compromise-action="exact" data-constraint-id="${escapeHtml(stop.id)}">Make exact</button><button type="button" data-compromise-action="accept" data-constraint-id="${escapeHtml(stop.id)}">Accept approximation</button><button type="button" data-compromise-action="remove" data-constraint-id="${escapeHtml(stop.id)}">Remove stop</button></div></li>`).join("");
  const dropped = (candidate.dropped_stops ?? []).map((stop) => `<li><strong>${escapeHtml(stop.name)}</strong><span>Drop reason: ${escapeHtml(friendlyLabel(stop.reason))}</span></li>`).join("");
  if (!reached && !approximated && !dropped) {
    return "";
  }
  return `<section><h3>Route itinerary</h3><ol class="tour-itinerary">${reached}${approximated}</ol>${dropped ? `<details><summary>Dropped stops (${candidate.dropped_stops.length})</summary><ul class="tour-itinerary dropped">${dropped}</ul></details>` : ""}</section>`;
}

function compromiseSummary(candidate) {
  const target = candidate.compromises.find((item) => item.code === "target_distance_missed");
  return `<section class="compromise-summary" role="status" aria-live="polite"><h3>Route generated</h3>${metricRows([
    ["Reached", formatCount(candidate.reached_stops.length)],
    ["Approximated", formatCount(candidate.approximated_stops.length)],
    ["Dropped", formatCount(candidate.dropped_stops.length)],
    ["Target", target ? `Missed by ${formatDistance(target.distance_m)}` : "Within requested tolerance"],
  ])}</section>`;
}

function endpointSection(result) {
  const visits = result.endpoint_visits ?? [];
  const startVisit = visits[0];
  const endVisit = visits[1];
  const coordinate = (point) => point
    ? `${point.name ? `${point.name} · ` : ""}${Number(point.lat).toFixed(6)}, ${Number(point.lon).toFixed(6)}`
    : "Not available";
  return section("Route endpoints", [
    ["Route topology", friendlyLabel(result.topology ?? "loop")],
    ["Effective start", coordinate(result.effective_start)],
    ["Start source", friendlyLabel(startVisit?.source ?? "explicit")],
    ["Start snap distance", startVisit?.snap_distance_m == null ? "Unknown" : formatDistance(startVisit.snap_distance_m)],
    ["Effective end", coordinate(result.effective_end)],
    [
      "End source",
      friendlyLabel(
        endVisit?.source ?? (result.topology === "point_to_point" ? "explicit" : "loop_closure"),
      ),
    ],
    ["End snap distance", endVisit?.snap_distance_m == null ? "Unknown" : formatDistance(endVisit.snap_distance_m)],
  ]);
}

function renderMetrics() {
  const candidate = selectedCandidate();
  const result = state.generationResult;
  byId("metrics-empty").classList.toggle("hidden", Boolean(candidate));
  byId("metrics-content").classList.toggle("hidden", !candidate);
  byId("download-gpx").disabled = !candidate || state.request.status === "running";
  if (candidate && result) renderCanonicalMetrics(candidate, result);
}
function renderCanonicalMetrics(candidate, result) {
  const analysis = candidate.route.analysis;
  const diagnostics = result.search_diagnostics;
  const phaseRows = Object.entries(diagnostics.budget.phases).map(([phase, usage]) => [
    `${friendlyLabel(phase)} budget`,
    `${usage.used} / ${usage.limit}${usage.exhausted ? " · exhausted" : ""}`,
  ]);
  const scoreRows = Object.entries(candidate.score.components).map(([component, value]) => [
    friendlyLabel(component),
    Number(value).toFixed(6),
  ]);
  const warnings = [...new Set([
    ...diagnostics.warnings,
    ...analysis.warnings,
    ...(analysis.loop_geometry?.warnings ?? []),
    ...(analysis.nature?.warnings ?? []),
  ])];
  byId("metrics-content").innerHTML = compromiseSummary(candidate) + endpointSection(result)
    + section("Canonical candidate", [
      ["Candidate ID", candidate.id],
      ["Routing profile", profileDisplayName(candidate.routing_profile)],
      ["Roles", candidate.roles.map(friendlyLabel).join(", ") || "None"],
      ["Distance", formatDistance(candidate.route.summary.distance_m)],
      ["Target error", formatDistance(candidate.diagnostics.target_error_m)],
      ["Within tolerance", candidate.diagnostics.within_tolerance ? "Yes" : "No"],
      ["Safety eligible", candidate.diagnostics.safety_eligible ? "Yes" : "No"],
      ["Reached / approximated / dropped", `${candidate.reached_stops.length} / ${candidate.approximated_stops.length} / ${candidate.dropped_stops.length}`],
    ])
    + constraintItinerary(candidate)
    + section("Route quality", [
      ["Total repetition", `${formatDistance(analysis.repetition.repeated_distance.distance_m)} · ${formatPercent(analysis.repetition.repeated_distance.share)}`],
      ["Immediate backtracking", `${formatDistance(analysis.immediate_backtrack.distance_m)} · ${formatPercent(analysis.immediate_backtrack.share)}`],
      ["Paved", formatPercent(analysis.paved.share)],
      ["Major roads", formatPercent(analysis.major_road.share)],
    ])
    + activityQualitySection(analysis)
    + section("Score", [["Total", Number(candidate.score.total).toFixed(6)], ...scoreRows])
    + (result.topology === "loop" ? loopGeometrySection(analysis.loop_geometry) : "")
    + natureSection(analysis.nature, { nature_index_available: Boolean(analysis.nature) })
    + section("Search budget", [
      ["Total used", `${diagnostics.budget.total_used} / ${diagnostics.budget.total_limit}`],
      ["Cache hits / misses", `${diagnostics.cache.hit_count} / ${diagnostics.cache.miss_count}`],
      ...phaseRows,
    ])
    + `<section><h3>Warnings</h3><ul class="warning-list">${warnings.length ? warnings.map((warning) => `<li>${escapeHtml(friendlyLabel(warning))}</li>`).join("") : "<li>No route or search warnings.</li>"}</ul></section>`;
  wireCompromiseActions(candidate);
}

function constraintStateById(id) {
  if (state.planningMode === "auto_tour") {
    const index = state.autoTour.requestedPlaces.findIndex((place, position) => (
      requestedPlaceIdentifier(place, position) === id
    ));
    return index < 0 ? null : { collection: state.autoTour.requestedPlaces, index };
  }
  const index = state.points.findIndex((point) => point.id === id);
  return index < 0 ? null : { collection: state.points, index };
}

function wireCompromiseActions(candidate) {
  byId("metrics-content").querySelectorAll(".itinerary-stop[data-itinerary-stop-id]").forEach((item) => {
    const focusStop = () => {
      const id = item.dataset.itineraryStopId;
      const stop = [...candidate.reached_stops, ...candidate.approximated_stops]
        .find((value) => value.id === id);
      if (!stop) return;
      state.selectedRequestedPlaceId = id;
      state.pendingRequestedPlacePopupId = id;
      renderMapData();
      const coordinate = stop.resolved_approach.coordinate;
      focusCoordinate([coordinate.lon, coordinate.lat]);
    };
    item.addEventListener("click", (event) => {
      if (event.target.closest("button")) return;
      focusStop();
    });
    item.addEventListener("keydown", (event) => {
      if (event.target.closest("button") || !["Enter", " "].includes(event.key)) return;
      event.preventDefault();
      focusStop();
    });
  });
  byId("metrics-content").querySelectorAll("[data-compromise-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.dataset.constraintId;
      const target = constraintStateById(id);
      if (!target) return;
      const stop = candidate.approximated_stops.find((value) => value.id === id);
      if (!stop) return;
      const item = target.collection[target.index];
      if (button.dataset.compromiseAction === "remove") {
        target.collection.splice(target.index, 1);
      } else if (button.dataset.compromiseAction === "exact") {
        if (state.planningMode === "auto_tour") {
          target.collection.splice(target.index, 1);
          state.autoTour.hardPoints.push({
            id: stop.id,
            name: stop.name,
            ...stop.semantic_coordinate,
            constraintStrength: "exact",
          });
          state.points = [state.autoTour.start, ...state.autoTour.hardPoints].filter(Boolean);
        } else {
          item.constraintStrength = "exact";
          item.approachOverride = null;
        }
      } else {
        item.constraintStrength = "best_effort";
        item.approachOverride = { ...stop.resolved_approach.coordinate };
      }
      invalidateAndRender();
      byId("request-status").textContent = "Constraint updated. Generate again to apply it.";
    });
  });
}

function renderStatus() {
  const running = state.request.status === "running";
  const endpoints = activeEndpoints();
  const open = isOpenPlan();
  byId("controls-title").textContent = open ? "Build your route" : "Build your loop";
  byId("generation-title").textContent = open ? "Planning your route…" : "Planning your loop…";
  const resolvable = Boolean(
    endpoints.start
    && (endpoints.routeTopology === "loop" || endpoints.end)
    && (
      state.planningMode === "auto_tour"
      || endpoints.routeTopology === "point_to_point"
      || state.points.length >= 1
    )
  );
  const profileAvailable = Boolean(selectedProfileStatus()?.available);
  byId("generate").disabled = running || !resolvable || !profileAvailable || Boolean(pointValidation());
  byId("generate-top").disabled = byId("generate").disabled;
  byId("cancel").classList.toggle("hidden", !running);
  byId("generation-state").classList.toggle("hidden", !running);
  document
    .querySelectorAll("#route-form input, #route-form select, #poi-list input, #poi-list button, #add-point-mode, #clear-points, input[name='planning-mode']")
    .forEach((control) => { control.disabled = running; });
  byId("request-status").classList.toggle("running", running);
  if (!running && !resolvable) {
    byId("request-status").textContent = state.planningMode === "auto_tour"
      ? "Set a hard start or add a place from which the start can be inferred."
      : "Set both hard endpoints or add enough mandatory waypoints to infer them.";
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

async function selectCandidate(candidateId) {
  if (!state.generationResult?.candidates.some((candidate) => candidate.id === candidateId)) return;
  state.selectedSignature = candidateId;
  render();
  const candidate = selectedCandidate();
  if (!candidate) return;
  try {
    let visualization = state.visualizationCache.get(candidateId);
    if (!visualization) {
      visualization = await visualizeRoute(candidate.route);
      if (!state.generationResult?.candidates.some((current) => current.id === candidateId)) return;
      state.visualizationCache.set(candidateId, visualization);
    }
    if (state.selectedSignature === candidateId) {
      renderVisualization(visualization, state.showNatureContext);
    }
  } catch (error) {
    handleError(error, "Route highlighting failed.");
  }
}

function validateRequestControls() {
  updateOptionsFromControls();
  saveActivePoints();
  const request = currentPlanRequest();
  if (request.distance_objective.target_m < 1000 || request.distance_objective.target_m > 200000) {
    throw new Error("Target distance must be between 1 and 200 km.");
  }
  if (request.distance_objective.tolerance_m < 100 || request.distance_objective.tolerance_m > 10000) {
    throw new Error("Tolerance must be between 0.1 and 10 km.");
  }
  if (
    request.distance_objective.maximum_m !== null
    && (!Number.isFinite(request.distance_objective.maximum_m)
      || request.distance_objective.maximum_m <= 0
      || request.distance_objective.maximum_m > 200000)
  ) {
    throw new Error("Maximum distance must be blank or between 0.1 and 200 km.");
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
  const planningLabel = isOpenPlan() ? "Planning your route" : "Planning your loop";
  byId("request-status").textContent = `${planningLabel}… 0 s elapsed`;
  elapsedTimer = window.setInterval(() => {
    if (state.request.status !== "running" || state.request.startedAt === null) return;
    const seconds = Math.floor((Date.now() - state.request.startedAt) / 1000);
    byId("request-status").textContent = `${planningLabel}… ${seconds} s elapsed`;
  }, 1000);
  render();
  try {
    const result = await generatePlan(request, state.abortController.signal);
    if (state.request.id !== id) return;
    state.generationResult = result;
    state.selectedSignature = result.candidates[0]?.id ?? null;
    state.visualizationCache.clear();
    state.request = { status: "success", id, startedAt: null };
    byId("request-status").textContent = result.candidates.length
      ? `${result.candidates.length} candidate route${result.candidates.length === 1 ? "" : "s"} generated.`
      : "No route candidate could satisfy the current hard constraints.";
    render();
    if (result.candidates.length) {
      fitCoordinates(result.candidates[0].route.geometry);
      await selectCandidate(result.candidates[0].id);
    } else {
      showNoCandidateError(result);
    }
  } catch (error) {
    if (state.request.id !== id) return;
    const cancelled = error.name === "AbortError";
    state.request = { status: cancelled ? "cancelled" : "error", id, startedAt: null };
    byId("request-status").textContent = cancelled ? "Generation cancelled." : "Generation failed.";
    if (!cancelled) handleGenerationError(error);
  } finally {
    window.clearInterval(elapsedTimer);
    if (state.request.id === id) {
      state.abortController = null;
      renderStatus();
      renderMapData();
    }
  }
}

function exactWaypointContext(metadata) {
  const name = metadata?.point_name;
  const index = metadata?.point_index;
  const label = name
    ? `Exact mandatory waypoint “${name}”`
    : Number.isInteger(index)
      ? `Exact mandatory point ${index + 1}`
      : "An exact mandatory waypoint";
  const indexText = Number.isInteger(index) ? ` (required-point index ${index})` : "";
  const snap = metadata?.snap_distance_m;
  const maximum = metadata?.maximum_snap_distance_m;
  const distanceText = typeof snap === "number" && typeof maximum === "number"
    ? ` snapped ${snap.toFixed(1)} m away; the permitted threshold is ${maximum.toFixed(1)} m.`
    : " could not be reached within the permitted snap threshold.";
  return `${label}${indexText}${distanceText}`;
}

function safeGenerationDiagnostics(result) {
  const diagnostics = result?.search_diagnostics;
  return JSON.stringify({
    code: "no_route_candidate",
    kind: result?.kind ?? null,
    topology: result?.topology ?? null,
    routing_profile: result?.routing_profile ?? null,
    candidate_count: result?.candidates?.length ?? 0,
    budget: diagnostics ? {
      total_used: diagnostics.budget.total_used,
      total_limit: diagnostics.budget.total_limit,
    } : null,
    cache: diagnostics ? {
      hit_count: diagnostics.cache.hit_count,
      miss_count: diagnostics.cache.miss_count,
      backend_call_count: diagnostics.cache.backend_call_count,
    } : null,
  }, null, 2);
}

function showNoCandidateError(result) {
  showError(
    "No route candidate could satisfy the current hard constraints.",
    safeGenerationDiagnostics(result),
    "no_route_candidate",
    "Every returned candidate was rejected or the search produced no complete route.",
    GENERATION_SUGGESTION,
  );
}

function handleGenerationError(error) {
  if (error instanceof ApiError) {
    const context = error.code === "exact_waypoint_not_reached"
      ? exactWaypointContext(error.metadata)
      : "The planning request was not completed.";
    lastExactFailure = error.code === "exact_waypoint_not_reached" ? error.metadata : null;
    showError(
      error.message,
      error.details,
      error.code,
      context,
      error.metadata?.suggestion ?? GENERATION_SUGGESTION,
    );
    return;
  }
  showError(
    "Route generation failed.",
    "A browser error interrupted generation; no raw traceback is displayed.",
    "browser_generation_error",
    "The planning request was not completed.",
    GENERATION_SUGGESTION,
  );
}

function handleError(error, fallback) {
  if (error instanceof ApiError) showError(error.message, `${error.code}\n${error.details}`);
  else showError(fallback, "A browser error interrupted this action; no raw traceback is displayed.");
}

function normalizeImportedRequest(value) {
  if (!value || typeof value !== "object") {
    throw new Error("Request JSON must contain an object.");
  }
  if (
    value.schema_version !== 1
    || !["auto_tour", "waypoint_route"].includes(value.kind)
  ) {
    throw new Error(
      "Unsupported legacy Sugarglider request.\nConvert it with scripts/migrate_plan_json.py.",
    );
  }
  const commonKeys = new Set([
    "schema_version", "kind", "name", "topology", "start", "end",
    "routing_profile", "candidate_count", "seed", "distance_objective",
    "preferences",
  ]);
  const modeKeys = value.kind === "auto_tour"
    ? ["hard_waypoints", "requested_stops", "preferred_discovered_poi_ids", "free_poi_spur_physical_m"]
    : ["waypoints", "waypoint_order"];
  const unknownKeys = Object.keys(value).filter(
    (key) => !commonKeys.has(key) && !modeKeys.includes(key),
  );
  if (unknownKeys.length) {
    throw new Error(`Canonical request contains unknown fields: ${unknownKeys.join(", ")}.`);
  }
  if (!["loop", "point_to_point"].includes(value.topology)) {
    throw new Error("Canonical request topology must be loop or point_to_point.");
  }
  const profileStatus = state.routingProfileCatalog?.profiles.find(
    (status) => status.profile.id === value.routing_profile,
  );
  if (!profileStatus) {
    throw new Error("Canonical request contains an unknown routing profile.");
  }
  if (!value.start || (value.topology === "point_to_point" && !value.end)) {
    throw new Error("Canonical request endpoints are incomplete.");
  }
  if (value.topology === "loop" && value.end != null) {
    throw new Error("A loop request must not contain an end.");
  }
  const objective = value.distance_objective;
  const preferences = value.preferences;
  if (!objective || !preferences) {
    throw new Error("Canonical distance_objective and preferences are required.");
  }
  const normalize = (point, label) => {
    const lat = Number(point?.lat);
    const lon = Number(point?.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      throw new Error(`${label} has invalid coordinates.`);
    }
    return { ...point, name: point.name || label, lat, lon };
  };
  const start = normalize(value.start, "Start");
  const end = value.end == null ? null : normalize(value.end, "End");
  const autoTour = value.kind === "auto_tour";
  const strength = (raw, fallback) => {
    const resolved = raw ?? fallback;
    if (!["exact", "approach", "best_effort"].includes(resolved)) {
      throw new Error(`Unknown constraint strength: ${resolved}.`);
    }
    return resolved;
  };
  const hardPoints = autoTour
    ? (value.hard_waypoints ?? []).map((point, index) => ({
      ...normalize(point.coordinate, point.name || `Hard waypoint ${index + 1}`),
      id: point.id,
      constraintStrength: "exact",
    }))
    : [];
  const points = autoTour
    ? [start, ...hardPoints]
    : (value.waypoints ?? []).map((point, index) => ({
      ...normalize(point.coordinate, point.name || `Waypoint ${index + 1}`),
      id: point.id,
      constraintStrength: strength(point.constraint_strength, "exact"),
      accessSearchRadiusM: point.access_search_radius_m ?? 500,
      maximumBestEffortDistanceM: point.maximum_best_effort_distance_m,
      approachOverride: point.approach_override == null
        ? null
        : normalize(point.approach_override, `Approach override ${index + 1}`),
    }));
  const requestedPlaces = autoTour
    ? (value.requested_stops ?? []).map((stop, index) => ({
      id: stop.id,
      name: stop.name,
      coordinate: normalize(stop.semantic_coordinate, `Requested stop ${index + 1}`),
      accessSearchRadiusM: stop.access_search_radius_m,
      constraintStrength: strength(stop.constraint_strength, "approach"),
      maximumBestEffortDistanceM: stop.maximum_best_effort_distance_m,
      importance: stop.importance,
      osmReference: stop.osm_reference,
      approachOverride: stop.approach_override == null
        ? null
        : normalize(stop.approach_override, `Approach override ${index + 1}`),
    }))
    : [];
  return {
    points,
    start,
    end,
    hardPoints,
    requestedPlaces,
    autoTourStart: autoTour ? start : null,
    importDiagnostics: {
      supplied_location_count: points.length + requestedPlaces.length + Number(Boolean(end)),
      imported_requested_place_count: requestedPlaces.length,
      consumed_as_start_count: 1,
      consumed_as_end_count: Number(Boolean(end)),
      discarded_count: 0,
    },
    maximumDistanceKm: objective.maximum_m == null ? null : objective.maximum_m / 1000,
    routeTopology: value.topology,
    options: {
      name: value.name,
      targetDistanceKm: objective.target_m / 1000,
      toleranceKm: objective.tolerance_m / 1000,
      candidateCount: value.candidate_count,
      seed: value.seed,
      waypointOrder: value.kind === "waypoint_route" ? value.waypoint_order : "fixed",
      pathSelectionMode: preferences.path_selection,
      naturePreference: preferences.nature,
      loopGeometryPreference: preferences.loop_geometry,
      freePoiSpurRepeatedM: value.free_poi_spur_physical_m ?? 200,
    },
    canonical: value,
  };
}
async function importRequest(file) {
  try {
    const imported = normalizeImportedRequest(JSON.parse(await file.text()));
    state.planningMode = imported.canonical.kind;
    state.routingProfile = imported.canonical.routing_profile;
    document.querySelectorAll('input[name="planning-mode"]').forEach((input) => {
      input.checked = input.value === state.planningMode;
    });
    state.options = imported.options;
    if (state.planningMode === "auto_tour") {
      if (!imported.autoTourStart) throw new Error("Auto Tour JSON needs a resolvable start.");
      state.autoTour.start = imported.autoTourStart;
      state.autoTour.end = imported.end;
      state.autoTour.hardPoints = imported.hardPoints;
      state.autoTour.requestedPlaces = imported.requestedPlaces;
      state.importDiagnostics = imported.importDiagnostics;
      state.autoTour.maximumDistanceKm = imported.maximumDistanceKm;
      state.autoTour.routeTopology = imported.routeTopology;
      state.autoTour.preferredPoiIds = [
        ...(imported.canonical.preferred_discovered_poi_ids ?? []),
      ];
      state.autoTour.distancePriority = imported.canonical.distance_objective.priority;
      state.autoTour.directionPreference = imported.canonical.preferences.direction;
      state.autoTour.scenicPreference = imported.canonical.preferences.scenic;
      state.autoTour.drinkingWaterPreference = imported.canonical.preferences.drinking_water;
      state.autoTourOptions = { ...imported.options };
      state.points = [state.autoTour.start, ...state.autoTour.hardPoints].filter(Boolean);
      state.selectedPointIndex = state.points.length ? 0 : null;
      state.selectedRequestedPlaceId = null;
      state.pendingRequestedPlacePopupId = null;
    } else {
      state.points = imported.points;
      state.waypointPoints = [...imported.points];
      state.waypointEndpoints.start = imported.start;
      state.waypointEndpoints.end = imported.end;
      state.waypointEndpoints.routeTopology = imported.routeTopology;
      state.selectedPointIndex = state.points.length ? 0 : null;
    }
    state.plan = {
      schema_version: 1,
      kind: imported.canonical.kind,
      common: null,
      auto_tour: null,
      waypoint_route: null,
    };
    state.pendingPointPopupIndex = null;
    updateControlsFromOptions();
    invalidateAndRender();
    byId("request-status").textContent = state.planningMode === "auto_tour"
      ? `${file.name} loaded. ${state.importDiagnostics.supplied_location_count} supplied locations: ${state.importDiagnostics.consumed_as_start_count} START, ${state.importDiagnostics.consumed_as_end_count} END, ${state.autoTour.requestedPlaces.length} requested places; ${state.importDiagnostics.discarded_count} discarded.`
      : `${file.name} loaded. All ${state.points.length} named waypoint constraints and strengths are ready for review.`;
    fitCoordinates([
      ...imported.points,
      ...imported.hardPoints,
      imported.start,
      imported.end,
      ...imported.requestedPlaces.map((place) => place.coordinate),
    ].filter(Boolean).map((point) => [point.lon, point.lat]));
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
    const { blob, filename } = await exportPlanCandidate(candidate);
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

function failedExactPoint() {
  const id = lastExactFailure?.point_id;
  if (state.planningMode === "auto_tour") {
    const index = state.autoTour.hardPoints.findIndex((point) => point.id === id);
    return index < 0 ? null : { collection: state.autoTour.hardPoints, index };
  }
  let index = state.points.findIndex((point) => point.id === id);
  if (index < 0 && Number.isInteger(lastExactFailure?.point_index)) {
    index = lastExactFailure.point_index - 1;
  }
  return index < 0 || index >= state.points.length
    ? null
    : { collection: state.points, index };
}

function updateFailedExactPoint(action) {
  const target = failedExactPoint();
  if (!target) return;
  const point = target.collection[target.index];
  if (["nearest", "best_effort"].includes(action)) {
    point.constraintStrength = "best_effort";
    point.accessSearchRadiusM = Math.max(point.accessSearchRadiusM ?? 500, 1000);
    point.maximumBestEffortDistanceM = point.accessSearchRadiusM;
  } else if (action === "remove") {
    target.collection.splice(target.index, 1);
  } else if (action === "requested") {
    target.collection.splice(target.index, 1);
    const wasWaypointRoute = state.planningMode === "waypoint_route";
    state.autoTour.requestedPlaces.push({
      id: point.id,
      name: point.name,
      coordinate: { lat: point.lat, lon: point.lon },
      importance: "must_visit",
      constraintStrength: "approach",
      accessSearchRadiusM: 500,
    });
    if (wasWaypointRoute) {
      state.waypointPoints = [...state.points];
      state.autoTour.start = state.waypointEndpoints.start;
      state.autoTour.end = state.waypointEndpoints.end;
      state.autoTour.routeTopology = state.waypointEndpoints.routeTopology;
      state.autoTour.hardPoints = [];
      state.planningMode = "auto_tour";
      state.points = [state.autoTour.start].filter(Boolean);
      document.querySelector('input[name="planning-mode"][value="auto_tour"]').checked = true;
    }
  } else if (action === "move") {
    state.selectedPointIndex = state.planningMode === "auto_tour"
      ? target.index + 1
      : target.index;
    state.addPointMode = true;
  }
  if (state.planningMode === "auto_tour") {
    state.points = [state.autoTour.start, ...state.autoTour.hardPoints].filter(Boolean);
  }
  hideError();
  invalidateAndRender();
  byId("request-status").textContent = action === "move"
    ? "Drag the selected waypoint or place it on the map, then generate again."
    : "Constraint updated. Generate again to apply it.";
}

function bindEvents() {
  byId("dismiss-error").addEventListener("click", hideError);
  byId("error-use-nearest").addEventListener("click", () => updateFailedExactPoint("nearest"));
  byId("error-best-effort").addEventListener("click", () => updateFailedExactPoint("best_effort"));
  byId("error-requested-place").addEventListener("click", () => updateFailedExactPoint("requested"));
  byId("error-move-waypoint").addEventListener("click", () => updateFailedExactPoint("move"));
  byId("error-remove-waypoint").addEventListener("click", () => updateFailedExactPoint("remove"));
  byId("generate").addEventListener("click", generate);
  byId("generate-top").addEventListener("click", generate);
  byId("cancel").addEventListener("click", () => state.abortController?.abort());
  byId("clear-results").addEventListener("click", invalidateAndRender);
  byId("route-form").addEventListener("change", (event) => {
    if (event.target.id.startsWith("hard-")) return;
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
  for (const kind of ["start", "end"]) {
    for (const suffix of ["enabled", "name", "lat", "lon"]) {
      byId(`hard-${kind}-${suffix}`).addEventListener("change", () => {
        const point = endpointFromControls(kind);
        if (byId(`hard-${kind}-enabled`).checked && !point) return;
        assignActiveEndpoint(kind, point);
        state.selectedPointIndex = kind === "start" && point && state.planningMode === "auto_tour"
          ? 0
          : state.selectedPointIndex;
        invalidateAndRender();
      });
    }
    byId(`set-hard-${kind}`).addEventListener("click", () => {
      state.endpointSetMode = state.endpointSetMode === kind ? null : kind;
      state.addPointMode = false;
      byId(`set-hard-${kind}`).textContent = state.endpointSetMode === kind
        ? `Click map for ${kind}`
        : "Set on map";
    });
    byId(`clear-hard-${kind}`).addEventListener("click", () => {
      assignActiveEndpoint(kind, null);
      if (state.endpointSetMode === kind) state.endpointSetMode = null;
      invalidateAndRender();
    });
  }
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
    const endpoints = activeEndpoints();
    const endpointCoordinates = [endpoints.start, endpoints.end]
      .filter(Boolean)
      .map((point) => [point.lon, point.lat]);
    fitCoordinates([...state.points.map((point) => [point.lon, point.lat]), ...endpointCoordinates, ...requested]);
  });
  byId("clear-points").addEventListener("click", () => {
    if (state.points.length > 1 && !window.confirm("Remove all mandatory points and generated results?")) return;
    state.points = [];
    if (state.planningMode === "auto_tour") {
      state.autoTour.start = null;
      state.autoTour.end = null;
      state.autoTour.requestedPlaces = [];
      state.selectedRequestedPlaceId = null;
      state.pendingRequestedPlacePopupId = null;
    } else {
      state.waypointEndpoints.start = null;
      state.waypointEndpoints.end = null;
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
  byId("show-dropped-requested-radii").addEventListener("change", (event) => {
    state.showDroppedRequestedRadii = event.target.checked;
    renderMapData();
  });
  byId("places-filters").addEventListener("change", () => {
    updatePoiFiltersFromControls();
    schedulePoiRefresh();
  });
  byId("download-gpx").addEventListener("click", downloadSelected);
  byId("export-plan").addEventListener("click", () => {
    try {
      updateOptionsFromControls();
      const request = currentPlanRequest();
      const blob = new Blob([`${JSON.stringify(request, null, 2)}\n`], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "sugarglider-plan.json";
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      byId("request-status").textContent = "Canonical plan JSON exported.";
    } catch (error) {
      showError("Could not export plan JSON.", error.message);
    }
  });
  byId("copy-request").addEventListener("click", async () => {
    try {
      updateOptionsFromControls();
      saveActivePoints();
      const request = currentPlanRequest();
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
    [state.config, state.routingProfileCatalog] = await Promise.all([
      getConfig(),
      getRoutingProfiles(),
    ]);
    renderRoutingProfiles();
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
        if (state.settingRequestedApproachId) {
          const place = state.autoTour.requestedPlaces.find((value, index) => (
            (value.id ?? requestedPlaceIdentifier(value, index))
            === state.settingRequestedApproachId
          ));
          if (place) place.approachOverride = coordinate;
          state.settingRequestedApproachId = null;
          invalidateAndRender();
          return;
        }
        if (state.endpointSetMode) {
          const kind = state.endpointSetMode;
          const existing = activeEndpoints()[kind];
          assignActiveEndpoint(kind, {
            name: byId(`hard-${kind}-name`).value.trim()
              || existing?.name
              || `Hard ${kind}`,
            ...coordinate,
          });
          state.endpointSetMode = null;
          byId(`set-hard-${kind}`).textContent = "Set on map";
          invalidateAndRender();
          return;
        }
        if (!state.addPointMode) return;
        const maximum = state.planningMode === "auto_tour"
          ? 6 + Number(Boolean(state.autoTour.start))
          : state.config.max_required_points;
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
        const point = {
          name: state.planningMode === "auto_tour"
            ? (state.points.length ? `Hard anchor ${state.points.length}` : "Start")
            : `Point ${state.points.length + 1}`,
          ...coordinate,
          originalIndex: nextOriginalIndex,
        };
        if (state.planningMode === "auto_tour" && !state.autoTour.start) {
          assignActiveEndpoint("start", point);
        } else {
          state.points.push(point);
        }
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
