import { createLocalPlanningContext } from "./local_planning_context.js";
import { PUBLIC_LOCAL_ROUTE_PROFILES } from "./local_routing.js";
import { eligibleLocalPoi, unavailableNature } from "./local_region_data.js";
import { containsPosition } from "./regional_manifest.js";

const EARTH_RADIUS_M = 6_371_008.8;
const REQUEST_FIELDS = new Set([
  "start", "target_distance_m", "tolerance_m", "candidate_count", "seed",
  "profile", "direction_preference", "preferences",
]);
const COORDINATE_FIELDS = new Set(["lat", "lon"]);
const DIRECTIONS = Object.freeze(["any", "clockwise", "counterclockwise"]);
const ROUTED_DIRECTIONS = Object.freeze(["clockwise", "counterclockwise"]);
const MIN_TARGET_DISTANCE_M = 2_000;
const MAX_TARGET_DISTANCE_M = 60_000;
const MIN_TOLERANCE_M = 100;
const MAX_TOLERANCE_M = 15_000;
const MAX_TOLERANCE_SHARE = 0.5;
const MIN_CANDIDATE_COUNT = 1;
const MAX_CANDIDATE_COUNT = 3;
const MAX_SEED = 0xffff_ffff;
const ROUTE_CLOSURE_TOLERANCE_M = 25;
const HARD_START_SNAP_TOLERANCE_M = 25;
const GENERATED_CONTROL_SNAP_TOLERANCE_M = 300;
const ANALYSIS_MAX_POINTS = 256;
const DIVERSITY_SAMPLE_COUNT = 32;
const OUTBOUND_RETURN_SAMPLE_COUNT = 96;
const OUTBOUND_RETURN_PROXIMITY_M = 150;
const OUTBOUND_RETURN_ENDPOINT_EXCLUSION_M = 250;
const MIN_CORRECTION_FACTOR = 0.7;
const MAX_CORRECTION_FACTOR = 1.3;
const MIN_USEFUL_CORRECTION = 0.03;
const RESULT_WARNINGS = Object.freeze([
  "exact_edge_repetition_unavailable",
  "path_attributes_unavailable",
  "nature_analysis_unavailable",
  "poi_optimization_unavailable",
  "geometry_overlap_metrics_are_sampled_approximations",
]);
const TERMINAL_FAILURE_CODES = new Set([
  "invalid_request", "unsupported_profile", "routing_pack_unavailable",
  "no_compatible_routing_pack", "routing_busy",
]);
const SKELETON_FAMILIES = Object.freeze([
  Object.freeze({
    id: "triangle",
    controls: Object.freeze([[1, 0], [0.5, 0.8660254037844386]]),
  }),
  Object.freeze({
    id: "asymmetric-triangle",
    controls: Object.freeze([[1, 0.15], [0.35, 0.9]]),
  }),
  Object.freeze({
    id: "diamond",
    controls: Object.freeze([[0.55, -0.7], [1.1, 0], [0.55, 0.7]]),
  }),
]);
const HEADINGS_DEGREES = Object.freeze([0, 45, 90, 135, 180, 225, 270, 315]);

export const LOCAL_AUTO_TOUR_ROUTE_CALL_BUDGET = 24;

export const MARLY_LOCAL_AUTO_TOUR_FIXTURE = deepFreeze({
  start: { lat: 48.8715, lon: 2.0965 },
  target_distance_m: 12_000,
  tolerance_m: 2_500,
  candidate_count: 2,
  seed: 35,
  profile: "hike",
  direction_preference: "any",
});

export class LocalAutoTourValidationError extends Error {
  constructor(code) {
    super(code);
    this.name = "LocalAutoTourValidationError";
    this.code = code;
  }
}

export function validateLocalAutoTourRequest(value) {
  if (plainObject(value)) value = { preferences: { nature: "off", scenic: false, water: false, requested_poi_ids: [] }, ...value };
  if (!plainObject(value) || !exactFields(value, REQUEST_FIELDS)) {
    throw new LocalAutoTourValidationError("invalid_request_fields");
  }
  if (!validCoordinate(value.start) || Math.abs(value.start.lat) > 85) {
    throw new LocalAutoTourValidationError("invalid_start");
  }
  if (!boundedFinite(
    value.target_distance_m,
    MIN_TARGET_DISTANCE_M,
    MAX_TARGET_DISTANCE_M,
  )) {
    throw new LocalAutoTourValidationError("invalid_target_distance");
  }
  if (!boundedFinite(value.tolerance_m, MIN_TOLERANCE_M, MAX_TOLERANCE_M)
      || value.tolerance_m > value.target_distance_m * MAX_TOLERANCE_SHARE) {
    throw new LocalAutoTourValidationError("invalid_tolerance");
  }
  if (!Number.isSafeInteger(value.candidate_count)
      || value.candidate_count < MIN_CANDIDATE_COUNT
      || value.candidate_count > MAX_CANDIDATE_COUNT) {
    throw new LocalAutoTourValidationError("invalid_candidate_count");
  }
  if (!Number.isSafeInteger(value.seed) || value.seed < 0 || value.seed > MAX_SEED) {
    throw new LocalAutoTourValidationError("invalid_seed");
  }
  if (!PUBLIC_LOCAL_ROUTE_PROFILES.includes(value.profile)) {
    throw new LocalAutoTourValidationError("unsupported_profile");
  }
  if (!DIRECTIONS.includes(value.direction_preference)) {
    throw new LocalAutoTourValidationError("invalid_direction_preference");
  }
  const preferences = value.preferences;
  if (!plainObject(preferences)
      || !exactFields(preferences, new Set(["nature", "scenic", "water", "requested_poi_ids"]))
      || !["off", "prefer"].includes(preferences.nature)
      || typeof preferences.scenic !== "boolean" || typeof preferences.water !== "boolean"
      || !Array.isArray(preferences.requested_poi_ids) || preferences.requested_poi_ids.length > 8
      || preferences.requested_poi_ids.some((id) => typeof id !== "string" || !/^(node|way|relation)\/\d{1,16}$/u.test(id))
      || new Set(preferences.requested_poi_ids).size !== preferences.requested_poi_ids.length) {
    throw new LocalAutoTourValidationError("invalid_local_preferences");
  }
  return deepFreeze({
    start: { lat: value.start.lat, lon: value.start.lon },
    target_distance_m: value.target_distance_m,
    tolerance_m: value.tolerance_m,
    candidate_count: value.candidate_count,
    seed: value.seed,
    profile: value.profile,
    direction_preference: value.direction_preference,
    preferences: { ...preferences, requested_poi_ids: [...preferences.requested_poi_ids] },
  });
}

export function generateLocalAutoTourSkeletons(rawRequest) {
  const request = validateLocalAutoTourRequest(rawRequest);
  const directions = request.direction_preference === "any"
    ? ROUTED_DIRECTIONS
    : [request.direction_preference];
  const skeletons = [];
  for (const family of SKELETON_FAMILIES) {
    const template = [[0, 0], ...family.controls, [0, 0]];
    const unitPerimeter = polylineLength(template);
    const targetScaleM = request.target_distance_m / unitPerimeter;
    for (const heading of HEADINGS_DEGREES) {
      for (const direction of directions) {
        const controls = direction === "clockwise"
          ? [...family.controls].reverse()
          : [...family.controls];
        const offsets = controls.map(([x, y]) => rotateOffset(
          x * targetScaleM,
          y * targetScaleM,
          heading,
        ));
        skeletons.push(makeSkeleton({
          request,
          familyId: family.id,
          heading,
          direction,
          offsets,
          correctionStep: 0,
          correctionFactor: 1,
        }));
      }
    }
  }
  return deepFreeze(seedShuffle(skeletons, request.seed));
}

export function rescaleLocalAutoTourSkeleton(skeleton, factor) {
  if (!plainObject(skeleton)
      || !boundedFinite(factor, MIN_CORRECTION_FACTOR, MAX_CORRECTION_FACTOR)) {
    throw new LocalAutoTourValidationError("invalid_scale_correction");
  }
  const request = validateLocalAutoTourRequest(skeleton.request);
  const offsets = skeleton.control_offsets_m.map(([x, y]) => [x * factor, y * factor]);
  return makeSkeleton({
    request,
    familyId: skeleton.family,
    heading: skeleton.heading_degrees,
    direction: skeleton.direction,
    offsets,
    correctionStep: skeleton.correction_step + 1,
    correctionFactor: skeleton.correction_factor * factor,
  });
}

export function analyzeLocalLoopGeometry(geometry, routeDistanceM) {
  if (!validGeometry(geometry) || !positiveFinite(routeDistanceM)) {
    throw new LocalAutoTourValidationError("invalid_routed_geometry");
  }
  const metric = projectGeometry(geometry);
  const sampled = resampleMetricPolyline(metric, ANALYSIS_MAX_POINTS);
  const startEndGapM = distance(metric[0], metric.at(-1));
  const closed = startEndGapM <= ROUTE_CLOSURE_TOLERANCE_M;
  const signedAreaM2 = closed ? signedArea(metric) : 0;
  const absoluteSignedAreaM2 = Math.abs(signedAreaM2);
  const signedAreaCompactness = closed
    ? clampShare(4 * Math.PI * absoluteSignedAreaM2 / (routeDistanceM ** 2))
    : 0;
  const sampledSelfCrossingCount = sampledSelfCrossings(sampled, closed);
  const angularMonotonicity = angularMonotonicityOf(metric);
  const sampledOutboundReturnProximityShare = outboundReturnProximity(metric);
  const grossReversalShare = grossImmediateReversalShare(metric, routeDistanceM);
  const maxRadiusM = Math.max(...metric.map((point) => distance(metric[0], point)));
  const sectorBalance = sectorBalanceOf(metric);
  const degenerate = maxRadiusM < 100
    || absoluteSignedAreaM2 < 1_000
    || signedAreaCompactness < 0.01;
  const severeOutAndBack = sampledOutboundReturnProximityShare >= 0.55
    || grossReversalShare >= 0.35;
  const direction = angularMonotonicity < 0.55 || absoluteSignedAreaM2 < 1
    ? "mixed"
    : signedAreaM2 < 0 ? "clockwise" : "counterclockwise";
  const geometryPenalty = (
    (1 - angularMonotonicity) * 2
    + sampledOutboundReturnProximityShare * 3
    + grossReversalShare * 3
    + Math.min(sampledSelfCrossingCount, 8) * 0.25
    + (1 - sectorBalance) * 0.75
    + (1 - signedAreaCompactness) * 0.5
  );
  return deepFreeze({
    closed,
    start_end_gap_m: startEndGapM,
    signed_area_m2: signedAreaM2,
    absolute_signed_area_m2: absoluteSignedAreaM2,
    signed_area_compactness: signedAreaCompactness,
    angular_monotonicity: angularMonotonicity,
    sector_balance: sectorBalance,
    max_radius_m: maxRadiusM,
    sampled_self_crossing_count: sampledSelfCrossingCount,
    sampled_outbound_return_proximity_share: sampledOutboundReturnProximityShare,
    gross_immediate_reversal_share: grossReversalShare,
    degenerate,
    severe_out_and_back: severeOutAndBack,
    routed_direction: direction,
    geometry_penalty: geometryPenalty,
    analysis_sample_count: sampled.length,
  });
}

export function rankLocalAutoTourCandidates(candidates, request) {
  const validated = validateLocalAutoTourRequest(request);
  return [...candidates].sort((left, right) => compareKeys(
    candidateRankKey(left, validated),
    candidateRankKey(right, validated),
  ));
}

export function createLocalAutoTourEngine({
  route,
  getRegionData = async () => null,
  now = () => globalThis.performance?.now?.() ?? Date.now(),
  routeCallBudget = LOCAL_AUTO_TOUR_ROUTE_CALL_BUDGET,
} = {}) {
  if (typeof route !== "function") throw new TypeError("route function is required");
  if (!Number.isSafeInteger(routeCallBudget)
      || routeCallBudget < 1
      || routeCallBudget > LOCAL_AUTO_TOUR_ROUTE_CALL_BUDGET) {
    throw new RangeError("local Auto Tour route budget must be within 1..24");
  }
  let generation = 0;
  let active = null;

  function generate(rawRequest) {
    const request = validateLocalAutoTourRequest(rawRequest);
    const identity = JSON.stringify(request);
    if (active !== null) {
      if (active.identity === identity) return active.promise;
      throw new LocalAutoTourValidationError("local_generation_busy");
    }
    const ownedGeneration = ++generation;
    const promise = runSearch(request, ownedGeneration).finally(() => {
      if (active?.generation === ownedGeneration) active = null;
    });
    active = { generation: ownedGeneration, identity, promise };
    return promise;
  }

  function invalidate() {
    generation += 1;
  }

  async function runSearch(request, ownedGeneration) {
    const startedAt = now();
    const state = {
      context: createLocalPlanningContext({ profile: request.profile, route, totalLimit: routeCallBudget,
        phaseLimits: { control: routeCallBudget, poi: Math.min(6, routeCallBudget) } }),
      rejected: new Map(),
      budgetExhausted: false,
      terminalFailure: false,
      packId: null,
    };
    const candidates = [];
    const skeletons = generateLocalAutoTourSkeletons(request);
    const desiredPoolSize = Math.min(6, request.candidate_count * 2);
    for (const skeleton of skeletons) {
      if (ownedGeneration !== generation) return null;
      if (state.context.totalUsed >= routeCallBudget) {
        state.budgetExhausted = true;
        break;
      }
      const candidate = await evaluateSkeleton(request, skeleton, state, ownedGeneration);
      if (ownedGeneration !== generation) return null;
      if (candidate !== null) retainDiverseCandidate(candidates, candidate, request, state);
      if (state.terminalFailure || candidates.length >= desiredPoolSize) break;
    }
    if (state.context.totalUsed >= routeCallBudget && candidates.length < desiredPoolSize) {
      state.budgetExhausted = true;
    }
    const controlRouteCalls = state.context.totalUsed;
    let regionData = null;
    try { regionData = await getRegionData(state.packId); } catch { /* Explicit unavailable evidence below. */ }
    if (ownedGeneration !== generation) return null;
    if (regionData?.identity.routing_pack_id !== state.packId) regionData = null;
    const enriched = [];
    for (const candidate of candidates) {
      if (ownedGeneration !== generation) return null;
      enriched.push(await enrichCandidate(candidate, regionData));
    }
    const controls = rankLocalAutoTourCandidates(enriched, request);
    const control = controls[0] ?? null;
    const poiResults = await explorePois(request, control, regionData, state, ownedGeneration);
    if (ownedGeneration !== generation) return null;
    // Exact edge repetition/backtracking is unavailable from the current mobile
    // wrapper. No POI reward may promote a detour over its no-POI control.
    const ranked = controls
      .slice(0, request.candidate_count)
      .map((candidate, index) => deepFreeze({ ...candidate, rank: index + 1,
        role: index === 0 ? "no_poi_control" : "alternative", poi_outcomes: candidatePoiOutcomes(candidate, poiResults.outcomes) }));
    if (poiResults.candidates.length && request.candidate_count > 1) {
      const selected = poiResults.candidates.slice(0, request.candidate_count - 1);
      ranked.splice(1, ranked.length - 1, ...selected.map((candidate, index) => deepFreeze({
        ...candidate, rank: index + 2, role: "poi_alternative", promotion_blocked_reason: "exact_repetition_backtracking_unavailable",
        poi_outcomes: candidatePoiOutcomes(candidate, poiResults.outcomes),
      })));
    }
    const recommended = ranked[0] ?? null;
    const finishedAt = now();
    const searchDiagnostics = state.context.snapshot();
    return deepFreeze({
      schema_version: 1,
      type: "local_auto_tour_result",
      request_id: requestIdentity(request),
      seed: request.seed,
      profile: request.profile,
      pack_id: recommended?.pack_id ?? null,
      target_distance_m: request.target_distance_m,
      tolerance_m: request.tolerance_m,
      requested_candidate_count: request.candidate_count,
      candidates: ranked,
      recommended_candidate_id: recommended?.candidate_id ?? null,
      route_call_count: state.context.totalUsed,
      route_call_budget: routeCallBudget,
      budget_exhausted: state.budgetExhausted || state.context.totalUsed >= routeCallBudget,
      rejected_attempt_counts: rejectionRecord(state.rejected),
      total_latency_ms: Math.max(0, Math.round(finishedAt - startedAt)),
      warnings: RESULT_WARNINGS.filter((warning) => (
        warning !== "nature_analysis_unavailable" || !control?.nature_analysis.available
      )).filter((warning) => warning !== "poi_optimization_unavailable" || !regionData),
      preferences: request.preferences,
      regional_data: regionData?.identity ?? null,
      no_poi_control_candidate_id: control?.candidate_id ?? null,
      no_poi_control: ranked[0] ?? null,
      poi_outcomes: recommended?.poi_outcomes ?? poiResults.outcomes,
      poi_search_outcomes: poiResults.outcomes,
      preference_status: {
        nature: request.preferences.nature === "off" ? "off" : control?.nature_analysis.available ? "scored_below_loop_quality" : "unavailable",
        scenic: !request.preferences.scenic ? "off" : regionData ? "bounded_search_with_control_gate" : "unavailable",
        water: !request.preferences.water ? "off" : regionData ? "verified_mapped_sources_only" : "unavailable",
      },
      phase_route_calls: { control: searchDiagnostics.budget.phases.control.used, poi: searchDiagnostics.budget.phases.poi.used },
      poi_route_call_budget: Math.min(6, Math.max(0, routeCallBudget - controlRouteCalls)),
      cache: searchDiagnostics.cache,
      search_diagnostics: searchDiagnostics,
    });
  }

  async function evaluateSkeleton(request, skeleton, state, ownedGeneration) {
    const initial = await routedAttempt(request, skeleton, state, state.packId);
    if (ownedGeneration !== generation) return null;
    if (initial === null || initial.failure !== null) return initial?.candidate ?? null;
    let best = initial.candidate;
    if (best.within_tolerance || state.context.totalUsed >= routeCallBudget) return best;
    const correctionFactor = clamp(
      request.target_distance_m / best.distance_m,
      MIN_CORRECTION_FACTOR,
      MAX_CORRECTION_FACTOR,
    );
    if (Math.abs(correctionFactor - 1) < MIN_USEFUL_CORRECTION) return best;
    const correctedSkeleton = rescaleLocalAutoTourSkeleton(skeleton, correctionFactor);
    const corrected = await routedAttempt(
      request,
      correctedSkeleton,
      state,
      best.pack_id,
    );
    if (corrected?.candidate
        && corrected.candidate.target_error_m < best.target_error_m) {
      best = corrected.candidate;
    }
    return best;
  }

  async function routedAttempt(request, skeleton, state, expectedPackId, phase = "control") {
    if (state.context.totalUsed >= routeCallBudget) {
      state.budgetExhausted = true;
      return null;
    }
    let reply;
    try { reply = await state.context.requestRoute(skeleton.points, phase); }
    catch { reply = { type: "local_route_failure", code: "exception" }; }
    if (reply?.type === "local_route_failure") {
      const reason = `local_route_${reply.code ?? "invalid_reply"}`;
      reject(state, reason);
      if (TERMINAL_FAILURE_CODES.has(reply.code)) state.terminalFailure = true;
      return { candidate: null, failure: reason };
    }
    const validation = validateRoutedAttempt(
      reply,
      skeleton.points,
      request,
      expectedPackId,
    );
    if (!validation.valid) {
      reject(state, validation.reason);
      return { candidate: null, failure: validation.reason };
    }
    state.packId ??= reply.pack_id;
    return {
      candidate: candidateFrom(reply, skeleton, request, validation.metrics),
      failure: null,
    };
  }

  async function enrichCandidate(candidate, data) {
    let nature = unavailableNature(candidate.distance_m, "nature_index_unavailable");
    try { if (data) nature = await data.analyzeNature(candidate); }
    catch { nature = unavailableNature(candidate.distance_m, "nature_analysis_unavailable"); }
    return deepFreeze({ ...candidate, nature_analysis: nature, selected_pois: [] });
  }

  function candidatePoiOutcomes(candidate, outcomes) {
    const selected = new Set(candidate.selected_pois.map((poi) => poi.poi_id));
    return outcomes.map((outcome) => selected.has(outcome.poi_id)
      ? { ...outcome, status: "reached", candidate_id: candidate.candidate_id, reason: null }
      : { ...outcome, status: "dropped", reason: outcome.status === "dropped" ? outcome.reason : "not_selected_for_this_candidate" });
  }

  async function explorePois(request, control, data, state, ownedGeneration) {
    const preferences = request.preferences;
    const outcomes = [];
    const alternatives = [];
    if (!preferences.scenic && !preferences.water && !preferences.requested_poi_ids.length) return { candidates: [], outcomes };
    if (!data || !control) {
      for (const id of preferences.requested_poi_ids) outcomes.push({ poi_id: id, status: "dropped", reason: data ? "no_valid_control" : "poi_index_unavailable" });
      return { candidates: [], outcomes };
    }
    let query;
    try { query = await data.queryPois({ center: request.start, radius_m: Math.min(60_000, request.target_distance_m / 2), limit: 64, requested_ids: preferences.requested_poi_ids }); }
    catch {
      for (const id of preferences.requested_poi_ids) outcomes.push({ poi_id: id, status: "dropped", reason: "poi_index_unavailable" });
      return { candidates: [], outcomes };
    }
    const considered = new Map(query.requested.map(({ id, feature }) => [id, feature]));
    for (const feature of query.features) {
      if (preferences.scenic && feature.group === "scenic" || preferences.water && feature.group === "hydration") considered.set(feature.id, feature);
    }
    const limit = Math.min(routeCallBudget, state.context.totalUsed + 6);
    for (const [id, feature] of considered) {
      if (ownedGeneration !== generation) return { candidates: [], outcomes: [] };
      let reason = eligibleLocalPoi(feature, data.identity.bounds);
      if (reason === null && state.context.totalUsed >= limit) reason = "poi_route_budget_exhausted";
      let retained = null;
      if (reason === null) {
        const approaches = feature.approach_candidates.filter((approach) => containsPosition(data.identity.bounds, [approach.coordinate.lon, approach.coordinate.lat]));
        // Try at most two meaningful approaches per feature, sharing six calls
        // across the entire POI lane. Coordinates remain proposals until routed.
        for (const approach of approaches.slice(0, 2)) {
          if (state.context.totalUsed >= limit || ownedGeneration !== generation) break;
          const point = { lat: approach.coordinate.lat, lon: approach.coordinate.lon };
          const positions = control.requested_points;
          let insertion = 1;
          let bestCost = Infinity;
          for (let index = 1; index < positions.length; index += 1) {
            const cost = haversineDistanceM(positions[index - 1], point) + haversineDistanceM(point, positions[index]) - haversineDistanceM(positions[index - 1], positions[index]);
            if (cost < bestCost) { bestCost = cost; insertion = index; }
          }
          const points = [...positions.slice(0, insertion), point, ...positions.slice(insertion)];
          const skeleton = { ...control.construction, points, skeleton_id: `${control.construction.skeleton_id}-poi-${approach.id}`,
            direction: control.construction.requested_direction };
          const attempt = await routedAttempt(request, skeleton, state, control.pack_id, "poi");
          if (ownedGeneration !== generation) return { candidates: [], outcomes: [] };
          if (!attempt?.candidate) { reason = attempt?.failure ?? "poi_route_budget_exhausted"; continue; }
          const candidate = attempt.candidate;
          const arrival = haversineDistanceM(point, candidate.snapped_points[insertion]);
          const tolerance = feature.group === "hydration" ? 15 : 25;
          if (arrival > tolerance) { reason = "poi_arrival_tolerance_exceeded"; continue; }
          const fidelity = candidate.geometry_metrics;
          const base = control.geometry_metrics;
          if (control.within_tolerance && !candidate.within_tolerance
              || fidelity.severe_out_and_back && !base.severe_out_and_back
              || fidelity.degenerate || fidelity.sampled_self_crossing_count > base.sampled_self_crossing_count
              || fidelity.geometry_penalty > base.geometry_penalty + 1e-9
              || fidelity.gross_immediate_reversal_share > base.gross_immediate_reversal_share + 1e-9
              || fidelity.sampled_outbound_return_proximity_share > base.sampled_outbound_return_proximity_share + 1e-9) {
            reason = "poi_loop_quality_gate"; continue;
          }
          const enriched = await enrichCandidate(candidate, data);
          const selected = { poi_id: id, name: feature.display_name, category: feature.category, potability: feature.potability,
            status: "reached", semantic_coordinate: feature.coordinate, approach_coordinate: point,
            routed_coordinate: candidate.snapped_points[insertion], arrival_distance_m: arrival,
            arrival_tolerance_m: tolerance, approach_id: approach.id, visit_index: insertion,
            approach, selection_origin: preferences.requested_poi_ids.includes(id) ? "user_preferred" : "discovered" };
          retained = deepFreeze({ ...enriched, selected_pois: [selected], source_control_candidate_id: control.candidate_id });
          reason = null;
          break;
        }
      }
      if (retained) alternatives.push(retained);
      const identity = feature ? { name: feature.display_name, category: feature.category,
        semantic_coordinate: feature.coordinate,
        selection_origin: preferences.requested_poi_ids.includes(id) ? "user_preferred" : "discovered" } : {};
      outcomes.push(retained ? { ...identity, poi_id: id, status: "reached", candidate_id: retained.candidate_id, reason: null }
        : { ...identity, poi_id: id, status: "dropped", reason: reason ?? "poi_no_routed_approach" });
    }
    const selected = rankLocalAutoTourCandidates(alternatives, request).slice(0, Math.max(0, request.candidate_count - 1));
    const selectedIds = new Set(selected.flatMap((candidate) => candidate.selected_pois.map((poi) => poi.poi_id)));
    return { candidates: selected, outcomes: outcomes.map((outcome) => outcome.status === "reached" && !selectedIds.has(outcome.poi_id)
      ? { ...outcome, status: "dropped", reason: "poi_portfolio_limit" } : outcome) };
  }

  return Object.freeze({ generate, invalidate });
}

export function createLocalAutoTourExperiment({
  bridge,
  getRegionData = async () => null,
  engine = createLocalAutoTourEngine({ route: (input) => bridge.route(input), getRegionData }),
  getStart = () => null,
  getProfile = () => "hike",
  renderCandidates = () => {},
  clearCandidates = () => {},
  onBusy = () => {},
  elements,
} = {}) {
  if (!bridge || !elements) throw new TypeError("bridge and elements are required");
  let epoch = 0;
  let activePromise = null;

  function bind() {
    elements.button.addEventListener("click", requestFromPlanner);
    elements.smokeButton.addEventListener("click", requestMarlySmokeTest);
  }

  function requestFromPlanner() {
    const start = getStart();
    if (!validCoordinate(start)) {
      elements.status.textContent = "Choose a valid first planner point for local Auto Tour.";
      return Promise.resolve(null);
    }
    return run(start);
  }

  function requestMarlySmokeTest() {
    return run(MARLY_LOCAL_AUTO_TOUR_FIXTURE.start);
  }

  function run(start) {
    if (activePromise !== null) return activePromise;
    let request;
    try {
      request = requestFromControls(start);
    } catch (error) {
      const code = error instanceof LocalAutoTourValidationError
        ? error.code
        : "invalid_request";
      elements.status.textContent = `Local Auto Tour request rejected (${code}).`;
      return Promise.resolve(null);
    }
    const ownedEpoch = ++epoch;
    setBusy(true);
    elements.status.textContent = "Generating bounded graph-routed local loops…";
    clearCandidates();
    const operation = engine.generate(request).then((result) => {
      if (ownedEpoch !== epoch || result === null) return null;
      if (result.candidates.length === 0) {
        clearCandidates();
        elements.results.replaceChildren();
        elements.status.textContent = (
          `No valid local loop survived · ${result.route_call_count}/`
          + `${result.route_call_budget} route calls · rejected ${rejectionSummary(result)}.`
        );
        return result;
      }
      renderCandidates(result.candidates, result.recommended_candidate_id);
      renderCandidateSummary(result);
      const recommended = result.candidates[0];
      elements.status.textContent = (
        `Local Auto Tour · ${result.candidates.length} retained · recommended `
        + `${recommended.candidate_id} · profile ${result.profile} · pack ${result.pack_id} · `
        + `target ${(result.target_distance_m / 1_000).toFixed(1)} km · `
        + `${result.route_call_count}/${result.route_call_budget} route calls · `
        + `${result.total_latency_ms} ms total · nature ${result.preference_status?.nature ?? "off"} · `
        + `scenic ${result.preference_status?.scenic ?? "off"} · water ${result.preference_status?.water ?? "off"} · exact edge repetition unavailable.`
      );
      return result;
    }).catch((error) => {
      if (ownedEpoch !== epoch) return null;
      clearCandidates();
      elements.results.replaceChildren();
      const code = error instanceof LocalAutoTourValidationError
        ? error.code
        : "generation_failure";
      elements.status.textContent = `Local Auto Tour failed explicitly (${code}).`;
      return null;
    }).finally(() => {
      if (activePromise === operation) {
        activePromise = null;
        setBusy(false);
      }
    });
    activePromise = operation;
    return operation;
  }

  function requestFromControls(start) {
    return validateLocalAutoTourRequest({
      start: { lat: start.lat, lon: start.lon },
      target_distance_m: Number(elements.targetDistanceInput.value) * 1_000,
      tolerance_m: Number(elements.toleranceInput.value) * 1_000,
      candidate_count: Number(elements.candidateCountSelect.value),
      seed: Number(elements.seedInput.value),
      profile: getProfile(),
      direction_preference: elements.directionSelect.value,
      preferences: {
        nature: elements.natureSelect?.value ?? "off",
        scenic: elements.scenicInput?.checked ?? false,
        water: elements.waterInput?.checked ?? false,
        requested_poi_ids: (elements.requestedPoisInput?.value ?? "").split(",").map((value) => value.trim()).filter(Boolean),
      },
    });
  }

  function renderCandidateSummary(result) {
    elements.results.replaceChildren();
    for (const candidate of result.candidates) {
      const item = document.createElement("li");
      const metrics = candidate.geometry_metrics;
      const recommended = candidate.candidate_id === result.recommended_candidate_id;
      item.textContent = (
        `${recommended ? "Recommended · " : ""}#${candidate.rank} `
        + `${(candidate.distance_m / 1_000).toFixed(2)} km · error `
        + `${(candidate.target_error_m / 1_000).toFixed(2)} km · `
        + `${candidate.construction.skeleton_id} · ${metrics.routed_direction} · `
        + `${metrics.sampled_self_crossing_count} sampled crossings · `
        + `${Math.round(metrics.sampled_outbound_return_proximity_share * 100)}% `
        + `sampled outbound/return proximity`
        + (candidate.nature_analysis?.available ? ` · nature ${candidate.nature_analysis.nature_score.toFixed(1)}/100 · woodland ${(candidate.nature_analysis.woodland.share * 100).toFixed(0)}% · unknown ${(candidate.nature_analysis.unknown_landcover.share * 100).toFixed(0)}%` : " · nature unavailable")
        + (candidate.selected_pois?.length ? ` · reached ${candidate.selected_pois.map((poi) => poi.name).join(", ")} · recommendation blocked: exact repetition/backtracking unavailable` : " · no-POI control")
      );
      if (recommended) item.className = "recommended";
      elements.results.append(item);
    }
    for (const outcome of result.poi_outcomes ?? []) {
      if (outcome.status !== "dropped") continue;
      const item = document.createElement("li");
      item.textContent = `${outcome.poi_id}: dropped (${outcome.reason}).`;
      elements.results.append(item);
    }
  }

  function setBusy(busy) {
    for (const element of [
      elements.button,
      elements.smokeButton,
      elements.targetDistanceInput,
      elements.toleranceInput,
      elements.candidateCountSelect,
      elements.seedInput,
      elements.directionSelect,
      elements.natureSelect, elements.scenicInput, elements.waterInput, elements.requestedPoisInput,
    ].filter(Boolean)) {
      element.disabled = busy;
    }
    elements.button.setAttribute("aria-busy", String(busy));
    elements.smokeButton.setAttribute("aria-busy", String(busy));
    onBusy(busy);
  }

  function invalidate() {
    epoch += 1;
    engine.invalidate();
    clearCandidates();
    elements.results.replaceChildren();
    if (activePromise === null) setBusy(false);
  }

  return Object.freeze({
    bind,
    requestFromPlanner,
    requestMarlySmokeTest,
    invalidate,
  });
}

function validateRoutedAttempt(reply, points, request, expectedPackId) {
  if (!plainObject(reply) || reply.type !== "local_route_result") {
    return invalid("invalid_local_route_reply");
  }
  if (reply.profile !== request.profile) return invalid("profile_identity_mismatch");
  if (typeof reply.pack_id !== "string" || reply.pack_id.length < 1) {
    return invalid("pack_identity_missing");
  }
  if (expectedPackId !== null && reply.pack_id !== expectedPackId) {
    return invalid("pack_identity_changed_during_correction");
  }
  if (!positiveFinite(reply.distance_m) || reply.distance_m > hardMaximumDistance(request)) {
    return invalid("hard_maximum_distance_exceeded");
  }
  if (!(reply.duration_s === null || nonNegativeFinite(reply.duration_s))) {
    return invalid("invalid_route_duration");
  }
  if (!validGeometry(reply.geometry)) return invalid("invalid_routed_geometry");
  if (!Array.isArray(reply.snapped_points)
      || reply.snapped_points.length !== points.length
      || !reply.snapped_points.every(validCoordinate)) {
    return invalid("snapped_point_count_mismatch");
  }
  const firstSnap = reply.snapped_points[0];
  const lastSnap = reply.snapped_points.at(-1);
  const firstGeometry = reply.geometry[0];
  const lastGeometry = reply.geometry.at(-1);
  if (firstGeometry[0] !== firstSnap.lon || firstGeometry[1] !== firstSnap.lat
      || lastGeometry[0] !== lastSnap.lon || lastGeometry[1] !== lastSnap.lat) {
    return invalid("geometry_snap_boundary_mismatch");
  }
  if (haversineDistanceM(request.start, firstSnap) > HARD_START_SNAP_TOLERANCE_M
      || haversineDistanceM(request.start, lastSnap) > HARD_START_SNAP_TOLERANCE_M) {
    return invalid("hard_start_snap_too_far");
  }
  for (let index = 1; index < points.length - 1; index += 1) {
    if (haversineDistanceM(points[index], reply.snapped_points[index])
        > GENERATED_CONTROL_SNAP_TOLERANCE_M) {
      return invalid("generated_control_snap_too_far");
    }
  }
  let vertex = 0;
  for (const snap of reply.snapped_points) {
    while (vertex < reply.geometry.length && (reply.geometry[vertex][0] !== snap.lon || reply.geometry[vertex][1] !== snap.lat)) vertex += 1;
    if (vertex === reply.geometry.length) return invalid("snapped_point_missing_from_ordered_geometry");
  }
  let metrics;
  try {
    metrics = analyzeLocalLoopGeometry(reply.geometry, reply.distance_m);
  } catch {
    return invalid("invalid_routed_geometry");
  }
  if (!metrics.closed) return invalid("route_not_closed");
  return { valid: true, reason: null, metrics };
}

function candidateFrom(reply, skeleton, request, metrics) {
  const targetErrorM = Math.abs(reply.distance_m - request.target_distance_m);
  const geometrySignature = geometryIdentity(reply.geometry);
  const signature = hashText([
    request.profile,
    reply.pack_id,
    skeleton.skeleton_id,
    Math.round(reply.distance_m * 10),
    reply.geometry[0].map((value) => value.toFixed(6)).join(","),
    geometrySignature,
  ].join("|"));
  return deepFreeze({
    candidate_id: `local-auto-${signature}`,
    geometry_signature: geometrySignature,
    profile: reply.profile,
    pack_id: reply.pack_id,
    engine: reply.engine,
    engine_version: reply.engine_version,
    distance_m: reply.distance_m,
    duration_s: reply.duration_s,
    target_error_m: targetErrorM,
    within_tolerance: targetErrorM <= request.tolerance_m,
    geometry: reply.geometry.map((position) => [...position]),
    snapped_points: reply.snapped_points.map(({ lat, lon }) => ({ lat, lon })),
    requested_points: skeleton.points.map(({ lat, lon }) => ({ lat, lon })),
    construction: {
      family: skeleton.family,
      skeleton_id: skeleton.skeleton_id,
      requested_direction: skeleton.direction,
      heading_degrees: skeleton.heading_degrees,
      correction_step: skeleton.correction_step,
      correction_factor: skeleton.correction_factor,
    },
    geometry_metrics: metrics,
    exact_edge_repetition: null,
    path_attributes: null,
    measurements: reply.measurements ?? null,
  });
}

function retainDiverseCandidate(candidates, candidate, request, state) {
  const thresholdM = Math.max(150, Math.min(600, request.target_distance_m * 0.025));
  const duplicateIndex = candidates.findIndex((existing) => (
    geometryDiversityDistanceM(existing.geometry, candidate.geometry) < thresholdM
  ));
  if (duplicateIndex < 0) {
    candidates.push(candidate);
    return;
  }
  reject(state, "insufficient_geometry_diversity");
  if (compareKeys(
    candidateRankKey(candidate, request),
    candidateRankKey(candidates[duplicateIndex], request),
  ) < 0) {
    candidates[duplicateIndex] = candidate;
  }
}

function candidateRankKey(candidate, request) {
  const metrics = candidate.geometry_metrics;
  const directionMismatch = request.direction_preference !== "any"
    && metrics.routed_direction !== request.direction_preference;
  return [
    candidate.within_tolerance ? 0 : 1,
    metrics.severe_out_and_back ? 1 : 0,
    metrics.degenerate ? 1 : 0,
    Math.min(metrics.sampled_self_crossing_count, 8),
    directionMismatch ? 1 : 0,
    metrics.geometry_penalty,
    request.preferences.nature === "prefer" && candidate.nature_analysis?.available ? -candidate.nature_analysis.nature_score : 0,
    candidate.target_error_m,
    candidate.candidate_id,
  ];
}

function makeSkeleton({
  request,
  familyId,
  heading,
  direction,
  offsets,
  correctionStep,
  correctionFactor,
}) {
  const controls = offsets.map((offset) => coordinateAtOffset(request.start, offset));
  const suffix = correctionStep === 0
    ? "base"
    : `correction-${correctionStep}-${Math.round(correctionFactor * 1_000)}`;
  return deepFreeze({
    request,
    skeleton_id: `${familyId}-h${heading}-${direction}-${suffix}`,
    family: familyId,
    direction,
    heading_degrees: heading,
    correction_step: correctionStep,
    correction_factor: correctionFactor,
    control_offsets_m: offsets.map((offset) => [...offset]),
    points: [request.start, ...controls, request.start],
  });
}

function coordinateAtOffset(start, [eastM, northM]) {
  const latitudeRadians = toRadians(start.lat);
  return {
    lat: start.lat + toDegrees(northM / EARTH_RADIUS_M),
    lon: start.lon + toDegrees(eastM / (EARTH_RADIUS_M * Math.cos(latitudeRadians))),
  };
}

function rotateOffset(x, y, headingDegrees) {
  const angle = toRadians(headingDegrees);
  return [x * Math.cos(angle) - y * Math.sin(angle), x * Math.sin(angle) + y * Math.cos(angle)];
}

function hardMaximumDistance(request) {
  return Math.min(
    120_000,
    request.target_distance_m
      + Math.max(request.target_distance_m * 0.5, request.tolerance_m * 3),
  );
}

function projectGeometry(geometry) {
  const referenceLatitude = geometry[0][1];
  const referenceLongitude = geometry[0][0];
  const longitudeScale = EARTH_RADIUS_M * Math.cos(toRadians(referenceLatitude));
  return geometry.map(([lon, lat]) => [
    longitudeScale * toRadians(lon - referenceLongitude),
    EARTH_RADIUS_M * toRadians(lat - referenceLatitude),
  ]);
}

function geometryIdentity(geometry) {
  const sampled = resampleMetricPolyline(projectGeometry(geometry), DIVERSITY_SAMPLE_COUNT);
  const normalized = sampled.map(([x, y]) => [Math.round(x), Math.round(y)]);
  const reversed = [...normalized].reverse();
  const forwardText = JSON.stringify(normalized);
  const reverseText = JSON.stringify(reversed);
  return hashText(forwardText < reverseText ? forwardText : reverseText);
}

function geometryDiversityDistanceM(left, right) {
  const leftSamples = resampleMetricPolyline(projectGeometry(left), DIVERSITY_SAMPLE_COUNT);
  const rightSamples = resampleMetricPolyline(projectGeometry(right), DIVERSITY_SAMPLE_COUNT);
  const reversed = [...rightSamples].reverse();
  return Math.min(
    meanPointDistance(leftSamples, rightSamples),
    meanPointDistance(leftSamples, reversed),
  );
}

function meanPointDistance(left, right) {
  return left.reduce((total, point, index) => total + distance(point, right[index]), 0)
    / left.length;
}

function resampleMetricPolyline(points, maximumPoints) {
  if (points.length <= 2) return points.map((point) => [...point]);
  const cumulative = [0];
  for (let index = 1; index < points.length; index += 1) {
    cumulative.push(cumulative.at(-1) + distance(points[index - 1], points[index]));
  }
  const total = cumulative.at(-1);
  if (total <= 0) return [points[0], points.at(-1)].map((point) => [...point]);
  const count = Math.max(2, maximumPoints);
  const sampled = [];
  let segment = 1;
  for (let index = 0; index < count; index += 1) {
    const target = total * index / (count - 1);
    while (segment < cumulative.length - 1 && cumulative[segment] < target) segment += 1;
    const before = cumulative[segment - 1];
    const after = cumulative[segment];
    const share = after > before ? (target - before) / (after - before) : 0;
    sampled.push([
      points[segment - 1][0] + (points[segment][0] - points[segment - 1][0]) * share,
      points[segment - 1][1] + (points[segment][1] - points[segment - 1][1]) * share,
    ]);
  }
  return sampled;
}

function sampledSelfCrossings(points, closed) {
  const intersections = new Set();
  const lastSegment = points.length - 2;
  for (let left = 0; left < points.length - 1; left += 1) {
    for (let right = left + 2; right < points.length - 1; right += 1) {
      if (closed && left === 0 && right === lastSegment) continue;
      const point = properSegmentIntersection(
        points[left],
        points[left + 1],
        points[right],
        points[right + 1],
      );
      if (point !== null) {
        intersections.add(`${Math.round(point[0] * 10)},${Math.round(point[1] * 10)}`);
      }
    }
  }
  return intersections.size;
}

function properSegmentIntersection(a, b, c, d) {
  const denominator = (a[0] - b[0]) * (c[1] - d[1])
    - (a[1] - b[1]) * (c[0] - d[0]);
  if (Math.abs(denominator) <= 1e-9) return null;
  const leftDeterminant = a[0] * b[1] - a[1] * b[0];
  const rightDeterminant = c[0] * d[1] - c[1] * d[0];
  const x = (leftDeterminant * (c[0] - d[0])
    - (a[0] - b[0]) * rightDeterminant) / denominator;
  const y = (leftDeterminant * (c[1] - d[1])
    - (a[1] - b[1]) * rightDeterminant) / denominator;
  const epsilon = 1e-7;
  if (!insideOpenSegment(x, y, a, b, epsilon)
      || !insideOpenSegment(x, y, c, d, epsilon)) return null;
  return [x, y];
}

function insideOpenSegment(x, y, start, end, epsilon) {
  return x > Math.min(start[0], end[0]) + epsilon
    && x < Math.max(start[0], end[0]) - epsilon
    || y > Math.min(start[1], end[1]) + epsilon
      && y < Math.max(start[1], end[1]) - epsilon;
}

function angularMonotonicityOf(points) {
  if (points.length < 4) return 0;
  const ring = points.slice(0, -1);
  const center = [
    ring.reduce((sum, point) => sum + point[0], 0) / ring.length,
    ring.reduce((sum, point) => sum + point[1], 0) / ring.length,
  ];
  const area = signedArea(points);
  if (Math.abs(area) <= 1e-9) return 0;
  const expectedSign = area > 0 ? 1 : -1;
  let matchingDistance = 0;
  let angularDistance = 0;
  for (let index = 1; index < points.length; index += 1) {
    const left = points[index - 1];
    const right = points[index];
    const segmentLength = distance(left, right);
    if (segmentLength <= 0) continue;
    const leftAngle = Math.atan2(left[1] - center[1], left[0] - center[0]);
    const rightAngle = Math.atan2(right[1] - center[1], right[0] - center[0]);
    const delta = normalizedAngle(rightAngle - leftAngle);
    if (Math.abs(delta) <= 1e-12) continue;
    angularDistance += segmentLength;
    if (delta * expectedSign > 0) matchingDistance += segmentLength;
  }
  return clampShare(angularDistance > 0 ? matchingDistance / angularDistance : 0);
}

function outboundReturnProximity(points) {
  const sampled = resampleMetricPolyline(points, OUTBOUND_RETURN_SAMPLE_COUNT);
  const start = sampled[0];
  let splitIndex = 1;
  for (let index = 2; index < sampled.length - 1; index += 1) {
    if (distance(start, sampled[index]) > distance(start, sampled[splitIndex])) {
      splitIndex = index;
    }
  }
  const spacing = polylineLength(sampled) / Math.max(1, sampled.length - 1);
  const exclusionCount = Math.ceil(OUTBOUND_RETURN_ENDPOINT_EXCLUSION_M / Math.max(1, spacing));
  const outbound = sampled.slice(exclusionCount, Math.max(exclusionCount, splitIndex - exclusionCount));
  const returning = sampled.slice(
    Math.min(sampled.length, splitIndex + exclusionCount),
    Math.max(0, sampled.length - exclusionCount),
  );
  if (outbound.length < 2 || returning.length < 2) return 0;
  const outboundShare = nearPointShare(outbound, returning);
  const returnShare = nearPointShare(returning, outbound);
  return clampShare((outboundShare + returnShare) / 2);
}

function nearPointShare(source, opposite) {
  return source.filter((point) => Math.min(
    ...opposite.map((candidate) => distance(point, candidate)),
  ) <= OUTBOUND_RETURN_PROXIMITY_M).length / source.length;
}

function grossImmediateReversalShare(points, routeDistanceM) {
  let reversalDistance = 0;
  for (let index = 1; index < points.length - 1; index += 1) {
    const incoming = [
      points[index][0] - points[index - 1][0],
      points[index][1] - points[index - 1][1],
    ];
    const outgoing = [
      points[index + 1][0] - points[index][0],
      points[index + 1][1] - points[index][1],
    ];
    const incomingLength = Math.hypot(...incoming);
    const outgoingLength = Math.hypot(...outgoing);
    if (incomingLength <= 0 || outgoingLength <= 0) continue;
    const cosine = clamp(
      (incoming[0] * outgoing[0] + incoming[1] * outgoing[1])
        / (incomingLength * outgoingLength),
      -1,
      1,
    );
    if (Math.acos(cosine) >= toRadians(150)) {
      reversalDistance += 2 * Math.min(incomingLength, outgoingLength);
    }
  }
  return clampShare(reversalDistance / routeDistanceM);
}

function sectorBalanceOf(points) {
  const distances = Array(8).fill(0);
  const start = points[0];
  let total = 0;
  for (let index = 1; index < points.length; index += 1) {
    const left = points[index - 1];
    const right = points[index];
    const length = distance(left, right);
    if (length <= 0) continue;
    const midpoint = [(left[0] + right[0]) / 2, (left[1] + right[1]) / 2];
    const angle = (Math.atan2(midpoint[1] - start[1], midpoint[0] - start[0])
      + 2 * Math.PI) % (2 * Math.PI);
    const sector = Math.min(7, Math.floor(angle / (Math.PI / 4)));
    distances[sector] += length;
    total += length;
  }
  if (total <= 0) return 0;
  return clampShare(-distances
    .filter((value) => value > 0)
    .map((value) => value / total)
    .reduce((sum, share) => sum + share * Math.log(share), 0) / Math.log(8));
}

function signedArea(points) {
  let doubled = 0;
  for (let index = 1; index < points.length; index += 1) {
    doubled += points[index - 1][0] * points[index][1]
      - points[index][0] * points[index - 1][1];
  }
  return doubled / 2;
}

function requestIdentity(request) {
  return `local-auto-request-${hashText(JSON.stringify(request))}`;
}

function seedShuffle(values, seed) {
  const shuffled = [...values];
  const random = seededRandom(seed);
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const swap = Math.floor(random() * (index + 1));
    [shuffled[index], shuffled[swap]] = [shuffled[swap], shuffled[index]];
  }
  return shuffled;
}

function seededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4_294_967_296;
  };
}

function hashText(value) {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

function rejectionRecord(rejected) {
  return Object.fromEntries([...rejected.entries()].sort(([left], [right]) => (
    left.localeCompare(right)
  )));
}

function rejectionSummary(result) {
  const entries = Object.entries(result.rejected_attempt_counts);
  return entries.length > 0
    ? entries.map(([reason, count]) => `${reason}=${count}`).join(", ")
    : "none";
}

function reject(state, reason) {
  state.rejected.set(reason, (state.rejected.get(reason) ?? 0) + 1);
}

function invalid(reason) {
  return { valid: false, reason, metrics: null };
}

function compareKeys(left, right) {
  for (let index = 0; index < Math.min(left.length, right.length); index += 1) {
    if (left[index] < right[index]) return -1;
    if (left[index] > right[index]) return 1;
  }
  return left.length - right.length;
}

function normalizedAngle(value) {
  const fullTurn = 2 * Math.PI;
  return ((value + Math.PI) % fullTurn + fullTurn) % fullTurn - Math.PI;
}

function polylineLength(points) {
  let length = 0;
  for (let index = 1; index < points.length; index += 1) {
    length += distance(points[index - 1], points[index]);
  }
  return length;
}

function distance(left, right) {
  return Math.hypot(right[0] - left[0], right[1] - left[1]);
}

function haversineDistanceM(left, right) {
  const deltaLatitude = toRadians(right.lat - left.lat);
  const deltaLongitude = toRadians(right.lon - left.lon);
  const value = Math.sin(deltaLatitude / 2) ** 2
    + Math.cos(toRadians(left.lat)) * Math.cos(toRadians(right.lat))
      * Math.sin(deltaLongitude / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.atan2(
    Math.sqrt(value),
    Math.sqrt(Math.max(0, 1 - value)),
  );
}

function validGeometry(value) {
  return Array.isArray(value)
    && value.length >= 2
    && value.length <= 20_000
    && value.every((coordinate) => (
      Array.isArray(coordinate)
      && coordinate.length === 2
      && coordinate.every(Number.isFinite)
      && coordinate[0] >= -180 && coordinate[0] <= 180
      && coordinate[1] >= -90 && coordinate[1] <= 90
    ));
}

function validCoordinate(value) {
  return plainObject(value)
    && exactFields(value, COORDINATE_FIELDS)
    && Number.isFinite(value.lat) && value.lat >= -90 && value.lat <= 90
    && Number.isFinite(value.lon) && value.lon >= -180 && value.lon <= 180;
}

function exactFields(value, expected) {
  const fields = Object.keys(value);
  return fields.length === expected.size && fields.every((field) => expected.has(field));
}

function plainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function boundedFinite(value, minimum, maximum) {
  return Number.isFinite(value) && value >= minimum && value <= maximum;
}

function positiveFinite(value) {
  return Number.isFinite(value) && value > 0;
}

function nonNegativeFinite(value) {
  return Number.isFinite(value) && value >= 0;
}

function clampShare(value) {
  return clamp(value, 0, 1);
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function toRadians(value) {
  return value * Math.PI / 180;
}

function toDegrees(value) {
  return value * 180 / Math.PI;
}

function deepFreeze(value) {
  if (value === null || typeof value !== "object" || Object.isFrozen(value)) return value;
  Object.values(value).forEach(deepFreeze);
  return Object.freeze(value);
}
