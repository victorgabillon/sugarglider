import { emptyOutingLiveState } from "./outing_live_state.js";

export const state = {
  plan: {
    schema_version: 1,
    kind: "auto_tour",
    common: null,
    auto_tour: null,
    waypoint_route: null,
  },
  config: null,
  routingProfileCatalog: null,
  routingProfile: null,
  planningMode: "auto_tour",
  points: [],
  waypointPoints: [],
  autoTour: {
    start: null,
    end: null,
    routeTopology: "loop",
    hardPoints: [],
    requestedPlaces: [],
    maximumDistanceKm: null,
    preferredPoiIds: [],
    distancePriority: "flexible",
    directionPreference: "any",
    scenicPreference: "prefer",
    drinkingWaterPreference: "prefer",
  },
  waypointEndpoints: {
    start: null,
    end: null,
    routeTopology: "loop",
  },
  options: {
    name: "Sugarglider route",
    targetDistanceKm: 20,
    toleranceKm: 2,
    maximumDistanceKm: null,
    distancePriority: "flexible",
    candidateCount: 3,
    seed: 0,
    waypointOrder: "fixed",
    pathSelectionMode: "low_overlap",
    naturePreference: "prefer",
    loopGeometryPreference: "prefer",
    freePoiSpurRepeatedM: 200,
  },
  autoTourOptions: null,
  importDiagnostics: null,
  waypointOptions: {
    name: "Sugarglider route",
    targetDistanceKm: 20,
    toleranceKm: 2,
    maximumDistanceKm: null,
    distancePriority: "flexible",
    candidateCount: 3,
    seed: 0,
    waypointOrder: "fixed",
    pathSelectionMode: "shortest",
    naturePreference: "off",
    loopGeometryPreference: "off",
  },
  generationResult: null,
  generationSourceRequest: null,
  savedRouteSnapshot: null,
  savedRouteSnapshotDisplay: false,
  savedRouteReceipt: null,
  forkedSavedCandidate: null,
  outingSnapshot: null,
  outingDisplay: false,
  selectedOutingParticipantId: null,
  outingOwnerReceipt: null,
  outingParticipantReceipt: null,
  outingInviteToken: null,
  outingLiveState: emptyOutingLiveState(),
  outingLiveConnectionStatus: "closed",
  outingTrackingStatus: "inactive",
  outingTrackingMessage: "Position sharing stopped",
  outingTrackingLastPublishedAt: null,
  outingTrackingActive: false,
  outingTrackingTransitionPending: false,
  outingTrackingClearFailed: false,
  outingTrackingBackend: "browser",
  nativeTrackingAvailable: false,
  nativeTrackingIdentity: null,
  nativeServiceStatus: null,
  nativeTrackingOtherActive: false,
  outingClosed: false,
  pwaSupported: false,
  pwaStatus: "idle",
  pwaUpdateAvailable: false,
  networkStatus: "online",
  offlineSnapshotKind: null,
  offlineSnapshotSlug: null,
  offlineCopySaved: false,
  storagePersistenceStatus: "unknown",
  participantRemembered: false,
  durableOutboxPresent: false,
  selectedSignature: null,
  selectedPointIndex: null,
  pendingPointPopupIndex: null,
  selectedRequestedPlaceId: null,
  pendingRequestedPlacePopupId: null,
  settingRequestedApproachId: null,
  importedGpx: null,
  request: { status: "idle", id: 0, startedAt: null },
  abortController: null,
  visualizationCache: new Map(),
  addPointMode: false,
  endpointSetMode: null,
  showAllCandidates: true,
  showNatureContext: false,
  showDirectionArrows: true,
  showDroppedRequestedRadii: false,
  poiFeatures: [],
  selectedPoiId: null,
  poiIndexStatus: null,
  poiRequest: { status: "idle", id: 0 },
  poiAbortController: null,
  poiFilters: {
    scenic: true,
    verifiedWater: true,
    unknownWater: false,
    broadAttractions: false,
    restrictedAccess: false,
    includePrivate: false,
    nonPotable: false,
  },
};

const ROUTE_TOPOLOGIES = new Set(["loop", "point_to_point"]);
const PLANNING_MODES = new Set(["auto_tour", "waypoint_route"]);

function requireRouteTopology(routeTopology) {
  if (!ROUTE_TOPOLOGIES.has(routeTopology)) {
    throw new Error(`Unsupported route topology: ${routeTopology}`);
  }
}

export function setRouteTopology(endpoints, routeTopology) {
  requireRouteTopology(routeTopology);
  const clearedExplicitEnd = routeTopology === "loop"
    && endpoints.end !== null
    && endpoints.end !== undefined;
  endpoints.routeTopology = routeTopology;
  if (routeTopology === "loop") endpoints.end = null;
  return clearedExplicitEnd;
}

export function assignRouteEndpoint(endpoints, kind, point) {
  if (!["start", "end"].includes(kind)) {
    throw new Error(`Unsupported route endpoint: ${kind}`);
  }
  if (kind === "end" && endpoints.routeTopology === "loop" && point !== null) {
    endpoints.end = null;
    return false;
  }
  endpoints[kind] = point;
  return true;
}

export function nextImplicitEndpointKind({
  endpoints,
  settingRequestedApproachId = null,
  endpointSetMode = null,
  addPointMode = false,
}) {
  requireRouteTopology(endpoints.routeTopology);
  if (settingRequestedApproachId || endpointSetMode || addPointMode) return null;
  if (!endpoints.start) return "start";
  if (endpoints.routeTopology === "point_to_point" && !endpoints.end) {
    return "end";
  }
  return null;
}

export function applyImplicitEndpointMapClick({
  endpoints,
  coordinate,
  assignEndpoint,
  settingRequestedApproachId = null,
  endpointSetMode = null,
  addPointMode = false,
}) {
  const kind = nextImplicitEndpointKind({
    endpoints,
    settingRequestedApproachId,
    endpointSetMode,
    addPointMode,
  });
  if (!kind) return null;
  const assigned = assignEndpoint(kind, {
    name: kind === "start" ? "Hard start" : "Hard end",
    ...coordinate,
  });
  return assigned === false ? null : kind;
}

export function routeEndpointPresentation(routeTopology) {
  requireRouteTopology(routeTopology);
  const loop = routeTopology === "loop";
  return {
    hardEndAvailable: !loop,
    loopEndExplanationVisible: loop,
  };
}

export function renderEndpointTopologyControls(
  hardEndControl,
  loopEndExplanation,
  routeTopology,
  { controlsDisabled = false } = {},
) {
  const presentation = routeEndpointPresentation(routeTopology);
  hardEndControl.hidden = !presentation.hardEndAvailable;
  hardEndControl.classList.toggle("hidden", !presentation.hardEndAvailable);
  hardEndControl.disabled = controlsDisabled || !presentation.hardEndAvailable;
  hardEndControl.setAttribute(
    "aria-hidden",
    String(!presentation.hardEndAvailable),
  );
  loopEndExplanation.hidden = !presentation.loopEndExplanationVisible;
  loopEndExplanation.classList.toggle(
    "hidden",
    !presentation.loopEndExplanationVisible,
  );
  return presentation;
}

export function generationAvailability({
  planningMode,
  routeTopology,
  start,
  end,
  mandatoryPointCount,
  pointValidationMessage,
  profileAvailable,
}) {
  requireRouteTopology(routeTopology);
  if (!PLANNING_MODES.has(planningMode)) {
    throw new Error(`Unsupported planning mode: ${planningMode}`);
  }
  if (pointValidationMessage) {
    return { enabled: false, reason: pointValidationMessage };
  }
  if (!start) {
    return {
      enabled: false,
      reason: "Click the map to choose your start point.",
    };
  }
  if (routeTopology === "point_to_point" && !end) {
    return {
      enabled: false,
      reason: "Now click the map to choose your end point.",
    };
  }
  if (
    planningMode === "waypoint_route"
    && routeTopology === "loop"
    && mandatoryPointCount < 1
  ) {
    return {
      enabled: false,
      reason: "Add at least one required waypoint for this loop.",
    };
  }
  if (!profileAvailable) {
    return {
      enabled: false,
      reason: "The selected routing profile is unavailable.",
    };
  }
  return { enabled: true, reason: "" };
}

export function saveActivePoints() {
  if (state.planningMode === "auto_tour") {
    if (state.autoTour.start) {
      state.autoTour.start = state.points[0] ?? state.autoTour.start;
      state.autoTour.hardPoints = state.points.slice(1);
    } else {
      state.autoTour.hardPoints = [...state.points];
    }
    state.autoTourOptions = { ...state.options };
  } else {
    state.waypointPoints = [...state.points];
    state.waypointOptions = { ...state.options };
  }
}

export function switchPlanningMode(mode) {
  if (mode === state.planningMode || !["auto_tour", "waypoint_route"].includes(mode)) return;
  saveActivePoints();
  state.planningMode = mode;
  state.points = mode === "auto_tour"
    ? [state.autoTour.start, ...state.autoTour.hardPoints].filter(Boolean)
    : [...state.waypointPoints];
  state.options = mode === "auto_tour"
    ? { ...(state.autoTourOptions ?? state.options) }
    : { ...state.waypointOptions };
  state.selectedPointIndex = state.points.length ? 0 : null;
  state.pendingPointPopupIndex = null;
  invalidateCandidates();
}

export function invalidateCandidates() {
  state.generationResult = null;
  state.generationSourceRequest = null;
  state.forkedSavedCandidate = null;
  state.selectedSignature = null;
  state.visualizationCache.clear();
}

export function requestedPlaceIdentifier(place, fallbackIndex = 0) {
  const stableId = place?.id ?? place?.stable_id;
  if (typeof stableId === "string" && stableId.trim()) return stableId.trim();
  const coordinate = place?.coordinate ?? {};
  const originalIndex = place?.originalIndex
    ?? place?.original_index
    ?? fallbackIndex + 1;
  const latitude = Number(coordinate.lat);
  const longitude = Number(coordinate.lon);
  return `requested-${originalIndex}-${latitude.toFixed(6)}-${longitude.toFixed(6)}`;
}

export function selectedCandidate() {
  if (state.outingDisplay && state.outingSnapshot) {
    return state.outingSnapshot.participants.find(
      (participant) => (
        participant.participant_id === state.selectedOutingParticipantId
      ),
    )?.planned_route.candidate ?? null;
  }
  return currentDisplayedCandidates().find(
    (candidate) => candidate.id === state.selectedSignature,
  ) ?? null;
}

export function currentDisplayedCandidates() {
  if (state.outingDisplay && state.outingSnapshot) {
    return state.outingSnapshot.participants.map(
      (participant) => participant.planned_route.candidate,
    );
  }
  if (state.savedRouteSnapshotDisplay && state.savedRouteSnapshot) {
    return [state.savedRouteSnapshot.candidate];
  }
  return state.generationResult?.candidates
    ?? (state.forkedSavedCandidate ? [state.forkedSavedCandidate] : []);
}

export function currentDisplayContext() {
  if (state.outingDisplay && state.outingSnapshot) {
    const participant = state.outingSnapshot.participants.find(
      (value) => value.participant_id === state.selectedOutingParticipantId,
    ) ?? state.outingSnapshot.participants[0];
    if (!participant) return null;
    const request = participant.planned_route.source_request;
    return {
      kind: request.kind,
      topology: request.topology,
      routing_profile: request.routing_profile,
      effective_start: request.start,
      effective_end: request.end ?? request.start,
    };
  }
  if (state.savedRouteSnapshotDisplay && state.savedRouteSnapshot) {
    const request = state.savedRouteSnapshot.source_request;
    return {
      kind: request.kind,
      topology: request.topology,
      routing_profile: request.routing_profile,
      effective_start: request.start,
      effective_end: request.end ?? request.start,
    };
  }
  if (state.forkedSavedCandidate && state.savedRouteSnapshot) {
    const request = state.savedRouteSnapshot.source_request;
    return {
      kind: request.kind,
      topology: request.topology,
      routing_profile: request.routing_profile,
      effective_start: request.start,
      effective_end: request.end ?? request.start,
    };
  }
  return state.generationResult;
}

export function currentSearchDiagnostics() {
  return state.savedRouteSnapshotDisplay || state.outingDisplay
    ? null
    : state.generationResult?.search_diagnostics ?? null;
}

export function isSavedRouteSnapshotDisplay() {
  return Boolean(state.savedRouteSnapshotDisplay && state.savedRouteSnapshot);
}

export function isImmutableSnapshotDisplay() {
  return isSavedRouteSnapshotDisplay()
    || Boolean(state.outingDisplay && state.outingSnapshot);
}

export function pointDisplayName(point, index) {
  const name = typeof point?.name === "string" ? point.name.trim() : "";
  return name || `Point ${index + 1}`;
}

export function readPlannerOptionsFromControls(byId) {
  return {
    name: byId("route-name").value.trim() || "Sugarglider route",
    targetDistanceKm: Number(byId("target-distance").value),
    toleranceKm: Number(byId("tolerance").value),
    maximumDistanceKm: byId("maximum-distance").value.trim()
      ? Number(byId("maximum-distance").value)
      : null,
    distancePriority: byId("distance-priority").value,
    candidateCount: Number(byId("candidate-count").value),
    seed: Number(byId("seed").value),
    waypointOrder: byId("point-order-mode").value,
    pathSelectionMode: byId("path-selection-mode").value,
    naturePreference: byId("nature-preference").value,
    loopGeometryPreference: byId("loop-geometry-preference").value,
    freePoiSpurRepeatedM: Number(byId("free-poi-spur").value),
  };
}

function commonPlanState(endpoints, planner = state) {
  requireRouteTopology(endpoints.routeTopology);
  const priority = planner.options.distancePriority ?? planner.autoTour.distancePriority;
  return {
    name: planner.options.name,
    topology: endpoints.routeTopology,
    start: coordinatePayload(endpoints.start, "Start"),
    end: endpoints.routeTopology === "point_to_point"
      ? coordinatePayload(endpoints.end, "End")
      : null,
    routing_profile: planner.routingProfile,
    candidate_count: planner.options.candidateCount,
    seed: planner.options.seed,
    distance_objective: {
      target_m: planner.options.targetDistanceKm * 1000,
      tolerance_m: planner.options.toleranceKm * 1000,
      maximum_m: planner.options.maximumDistanceKm == null
        ? null
        : planner.options.maximumDistanceKm * 1000,
      priority,
    },
    preferences: planner.planningMode === "auto_tour" ? {
      nature: planner.options.naturePreference,
      path_selection: planner.options.pathSelectionMode,
      scenic: planner.autoTour.scenicPreference,
      drinking_water: planner.autoTour.drinkingWaterPreference,
      loop_geometry: endpoints.routeTopology === "loop"
        ? planner.options.loopGeometryPreference
        : "off",
      direction: endpoints.routeTopology === "loop"
        ? planner.autoTour.directionPreference
        : "any",
    } : {
      nature: planner.options.naturePreference,
      path_selection: planner.options.pathSelectionMode,
      loop_geometry: endpoints.routeTopology === "loop"
        ? planner.options.loopGeometryPreference
        : "off",
    },
  };
}

function waypointPlanState(points, options) {
  return {
    waypoints: points.map((point, index) => ({
      id: point.id ?? `route-waypoint-${index + 1}`,
      name: pointDisplayName(point, index),
      coordinate: coordinatePayload(point, pointDisplayName(point, index)),
      constraint_strength: point.constraintStrength ?? "exact",
      access_search_radius_m: point.accessSearchRadiusM ?? 500,
      maximum_best_effort_distance_m: point.constraintStrength === "best_effort"
        ? point.maximumBestEffortDistanceM ?? point.accessSearchRadiusM ?? 500
        : null,
      approach_override: point.approachOverride
        ? coordinatePayload(point.approachOverride, "Approach override")
        : null,
    })),
    waypoint_order: options.waypointOrder,
  };
}

export function waypointPlanRequestSnapshot(planner) {
  const endpoints = planner.waypointEndpoints;
  const common = commonPlanState(endpoints, planner);
  const modeState = waypointPlanState(planner.points, planner.options);
  // Preserve unsupported intent for local validation, rather than canonicalizing
  // away an explicit loop end, an open-route shape preference, or an exact bound.
  common.end = endpoints.end == null ? null : coordinatePayload(endpoints.end, "End");
  common.preferences.loop_geometry = planner.options.loopGeometryPreference;
  modeState.waypoints.forEach((waypoint, index) => {
    const point = planner.points[index];
    if (point.constraintStrength !== undefined) waypoint.constraint_strength = point.constraintStrength;
    if (point.maximumBestEffortDistanceM != null) {
      waypoint.maximum_best_effort_distance_m = point.maximumBestEffortDistanceM;
    }
  });
  return { schema_version: 1, kind: "waypoint_route", ...common, ...modeState };
}

export function currentPlanRequest() {
  saveActivePoints();
  const endpoints = state.planningMode === "auto_tour"
    ? state.autoTour
    : state.waypointEndpoints;
  setRouteTopology(endpoints, endpoints.routeTopology);
  const common = commonPlanState(endpoints);
  const modeState = state.planningMode === "auto_tour"
    ? {
      hard_waypoints: state.autoTour.hardPoints.map((point, index) => ({
        id: point.id ?? `hard-waypoint-${index + 1}`,
        name: pointDisplayName(point, index + 1),
        coordinate: coordinatePayload(point, pointDisplayName(point, index + 1)),
      })),
      requested_stops: state.autoTour.requestedPlaces.map((place, index) => ({
        id: requestedPlaceIdentifier(place, index),
        name: place.name || `Requested stop ${index + 1}`,
        semantic_coordinate: coordinatePayload(
          place.coordinate,
          place.name || `Requested stop ${index + 1}`,
        ),
        importance: place.importance,
        constraint_strength: place.constraintStrength ?? "approach",
        osm_reference: place.osmReference ?? null,
        access_search_radius_m: place.accessSearchRadiusM ?? 500,
        maximum_best_effort_distance_m: place.constraintStrength === "best_effort"
          ? place.maximumBestEffortDistanceM ?? place.accessSearchRadiusM ?? 500
          : null,
        approach_override: place.approachOverride
          ? coordinatePayload(place.approachOverride, "Approach override")
          : null,
      })),
      preferred_discovered_poi_ids: [...state.autoTour.preferredPoiIds],
      free_poi_spur_physical_m: state.options.freePoiSpurRepeatedM ?? 200,
    }
    : waypointPlanState(state.points, state.options);
  state.plan = {
    schema_version: 1,
    kind: state.planningMode,
    common,
    auto_tour: state.planningMode === "auto_tour" ? modeState : null,
    waypoint_route: state.planningMode === "waypoint_route" ? modeState : null,
  };
  return {
    schema_version: 1,
    kind: state.planningMode,
    ...common,
    ...modeState,
  };
}

function coordinatePayload(point, fallbackName) {
  return {
    name: typeof point.name === "string" && point.name.trim()
      ? point.name.trim()
      : fallbackName,
    lat: point.lat,
    lon: point.lon,
  };
}
