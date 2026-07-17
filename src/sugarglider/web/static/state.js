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
  },
  generationResult: null,
  selectedSignature: null,
  importedGpx: null,
  request: { status: "idle", id: 0, startedAt: null },
  abortController: null,
  visualizationCache: new Map(),
  addPointMode: false,
  showAllCandidates: true,
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

export function currentRequest() {
  return {
    name: state.options.name,
    points: state.points.map(({ name, lat, lon }) => ({ name, lat, lon })),
    target_distance_m: state.options.targetDistanceKm * 1000,
    tolerance_m: state.options.toleranceKm * 1000,
    candidate_count: state.options.candidateCount,
    seed: state.options.seed,
    close_loop: true,
    profile: "hike",
    point_order_mode: state.options.pointOrderMode,
    path_selection_mode: state.options.pathSelectionMode,
  };
}
