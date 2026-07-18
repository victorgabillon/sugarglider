export const state = {
  config: null,
  points: [],
  options: {
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
  importedGpx: null,
  request: { status: "idle", id: 0, startedAt: null },
  abortController: null,
  visualizationCache: new Map(),
  addPointMode: false,
  showAllCandidates: true,
  showNatureContext: false,
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

export function invalidateCandidates() {
  state.generationResult = null;
  state.selectedSignature = null;
  state.visualizationCache.clear();
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
