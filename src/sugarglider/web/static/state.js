export const state = {
  config: null,
  planningMode: "auto_tour",
  points: [],
  waypointPoints: [],
  autoTour: {
    start: null,
    hardPoints: [],
    requestedPlaces: [],
    preferredPoiIds: [],
    distancePriority: "flexible",
    directionPreference: "any",
    scenicPreference: "prefer",
    drinkingWaterPreference: "prefer",
  },
  options: {
    name: "Sugarglider route",
    targetDistanceKm: 20,
    toleranceKm: 2,
    candidateCount: 3,
    seed: 0,
    pointOrderMode: "fixed",
    pathSelectionMode: "low_overlap",
    naturePreference: "prefer",
    loopGeometryPreference: "prefer",
  },
  autoTourOptions: null,
  waypointOptions: {
    name: "Sugarglider route",
    targetDistanceKm: 20,
    toleranceKm: 2,
    candidateCount: 3,
    seed: 0,
    pointOrderMode: "fixed",
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
  importedGpx: null,
  request: { status: "idle", id: 0, startedAt: null },
  abortController: null,
  visualizationCache: new Map(),
  addPointMode: false,
  showAllCandidates: true,
  showNatureContext: false,
  showMissedRequestedRadii: false,
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
    state.autoTour.start = state.points[0] ?? null;
    state.autoTour.hardPoints = state.points.slice(1);
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
    (candidate) => candidate.signature === state.selectedSignature,
  ) ?? null;
}

export function pointDisplayName(point, index) {
  const name = typeof point?.name === "string" ? point.name.trim() : "";
  return name || `Point ${index + 1}`;
}

export function currentRequest() {
  return {
    name: state.options.name,
    points: state.points.map((point, index) => ({
      name: pointDisplayName(point, index),
      lat: point.lat,
      lon: point.lon,
    })),
    target_distance_m: state.options.targetDistanceKm * 1000,
    tolerance_m: state.options.toleranceKm * 1000,
    candidate_count: state.options.candidateCount,
    seed: state.options.seed,
    close_loop: true,
    profile: "hike",
    point_order_mode: state.options.pointOrderMode,
    path_selection_mode: state.options.pathSelectionMode,
    nature_preference: state.options.naturePreference,
    loop_geometry_preference: state.options.loopGeometryPreference,
  };
}

export function currentAutoTourRequest() {
  saveActivePoints();
  if (!state.autoTour.start) throw new Error("Auto Tour needs a valid start point.");
  return {
    name: state.options.name,
    start: {
      name: pointDisplayName(state.autoTour.start, 0),
      lat: state.autoTour.start.lat,
      lon: state.autoTour.start.lon,
    },
    target_distance_m: state.options.targetDistanceKm * 1000,
    tolerance_m: state.options.toleranceKm * 1000,
    candidate_count: state.options.candidateCount,
    seed: state.options.seed,
    hard_points: state.autoTour.hardPoints.map((point, index) => ({
      name: pointDisplayName(point, index + 1),
      lat: point.lat,
      lon: point.lon,
    })),
    requested_places: state.autoTour.requestedPlaces.map((place, index) => ({
      name: place.name || `Requested place ${index + 1}`,
      coordinate: {
        name: place.name || `Requested place ${index + 1}`,
        lat: place.coordinate.lat,
        lon: place.coordinate.lon,
      },
      visit_radius_m: place.visitRadiusM,
      importance: place.importance,
      original_index: place.originalIndex ?? index + 1,
    })),
    preferred_poi_ids: [...state.autoTour.preferredPoiIds],
    distance_priority: state.autoTour.distancePriority,
    direction_preference: state.autoTour.directionPreference,
    scenic_preference: state.autoTour.scenicPreference,
    drinking_water_preference: state.autoTour.drinkingWaterPreference,
    nature_preference: state.options.naturePreference,
    path_selection_mode: state.options.pathSelectionMode,
    loop_geometry_preference: state.options.loopGeometryPreference,
    profile: "hike",
  };
}
