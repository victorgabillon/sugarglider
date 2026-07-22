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
    candidateCount: 3,
    seed: 0,
    waypointOrder: "fixed",
    pathSelectionMode: "shortest",
    naturePreference: "off",
    loopGeometryPreference: "off",
  },
  generationResult: null,
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
  return state.generationResult?.candidates.find(
    (candidate) => candidate.id === state.selectedSignature,
  ) ?? null;
}

export function pointDisplayName(point, index) {
  const name = typeof point?.name === "string" ? point.name.trim() : "";
  return name || `Point ${index + 1}`;
}

function commonPlanState(endpoints) {
  const priority = state.planningMode === "auto_tour"
    ? state.autoTour.distancePriority
    : "flexible";
  return {
    name: state.options.name,
    topology: endpoints.routeTopology,
    start: coordinatePayload(endpoints.start, "Start"),
    end: endpoints.routeTopology === "point_to_point"
      ? coordinatePayload(endpoints.end, "End")
      : null,
    routing_profile: state.routingProfile,
    candidate_count: state.options.candidateCount,
    seed: state.options.seed,
    distance_objective: {
      target_m: state.options.targetDistanceKm * 1000,
      tolerance_m: state.options.toleranceKm * 1000,
      maximum_m: state.planningMode === "auto_tour"
        ? state.autoTour.maximumDistanceKm == null
          ? null
          : state.autoTour.maximumDistanceKm * 1000
        : null,
      priority,
    },
    preferences: state.planningMode === "auto_tour" ? {
      nature: state.options.naturePreference,
      path_selection: state.options.pathSelectionMode,
      scenic: state.autoTour.scenicPreference,
      drinking_water: state.autoTour.drinkingWaterPreference,
      loop_geometry: endpoints.routeTopology === "loop"
        ? state.options.loopGeometryPreference
        : "off",
      direction: endpoints.routeTopology === "loop"
        ? state.autoTour.directionPreference
        : "any",
    } : {
      nature: state.options.naturePreference,
      path_selection: state.options.pathSelectionMode,
      loop_geometry: endpoints.routeTopology === "loop"
        ? state.options.loopGeometryPreference
        : "off",
    },
  };
}

export function currentPlanRequest() {
  saveActivePoints();
  const endpoints = state.planningMode === "auto_tour"
    ? state.autoTour
    : state.waypointEndpoints;
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
    : {
      waypoints: state.points.map((point, index) => ({
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
      waypoint_order: state.options.waypointOrder,
    };
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
