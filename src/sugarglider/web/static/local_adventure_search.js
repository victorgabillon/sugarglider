// Bounded proposals for the existing Waypoint producer. Only its injected
// attempt boundary may route; coordinates here are never displayed as a line.
import { analyzeLocalLoopGeometry, generateAdventureControlSkeletons, geometryDiversityDistanceM } from "./local_auto_tour.js";
import { deepFreeze } from "./local_candidate_evaluator.js";
import { haversineDistance } from "./local_plan_geometry.js";
import { unavailableNature } from "./local_region_data.js";
import { publishLocalWaypointStops } from "./local_candidate_enrichment.js";

const distance = (a, b) => haversineDistance([a.lon, a.lat], [b.lon, b.lat]);
const covered = (p, bounds) => p.lon >= bounds[0] && p.lat >= bounds[1] && p.lon <= bounds[2] && p.lat <= bounds[3];
const compareText = (a, b) => a < b ? -1 : a > b ? 1 : 0;
const TERMINAL = new Set(["unsupported_profile", "routing_pack_unavailable", "no_covering_routing_pack",
  "no_compatible_routing_pack", "routing_busy", "routing_pack_identity_changed", "profile_identity_mismatch"]);

export async function searchWaypointAdventure({ request, targets = [], context, phase, maxCalls,
  reference, current, attempt, data = null }) {
  if (!Number.isSafeInteger(maxCalls) || maxCalls < 1 || maxCalls > 16
    || !reference?.pack_id || !Array.isArray(reference.bounds) || reference.bounds.length !== 4
    || !Array.isArray(targets) || targets.length > 30) throw new TypeError("Invalid adventure search inputs.");
  const targetMap = new Map(targets.map(target => [target.id, target]));
  const soft = request.waypoints.map((point, index) => ({ point, index }))
    .filter(({ point }) => point.constraint_strength !== "exact");
  if (targetMap.size !== targets.length || soft.some(({ point }) => {
    const target = targetMap.get(point.id);
    return !target?.approach || target.status !== "grounded" || !point.approach_override
      || distance(point.approach_override, target.approach.coordinate) > 0.001
      || distance(point.coordinate, target.semantic_coordinate) > 0.001
      || ["private", "restricted"].includes(target.approach.access);
  })) throw new TypeError("Adventure targets must have checked local approaches.");
  const hard = request.waypoints.map((point, index) => ({ point, index }))
    .filter(({ point }) => point.constraint_strength === "exact");
  if ([request.start, request.end, ...hard.map(({ point }) => point.coordinate)].filter(Boolean)
    .some(point => !covered(point, reference.bounds))) throw failure("no_covering_routing_pack");
  const startUsed = context.totalUsed, attempts = new Set(), drafts = [], controls = [], rejected = [];
  const reasons = new Map();
  let terminal = null;
  const alive = () => { if (!current()) throw new DOMException("Adventure cancelled.", "AbortError"); };
  const available = () => context.totalUsed - startUsed < maxCalls && !context.snapshot().budget.global_exhausted;
  const targetPoint = index => request.waypoints[index].approach_override ?? request.waypoints[index].coordinate;
  const sequence = indices => [{ coordinate: request.start, index: null },
    ...indices.map(index => ({ coordinate: targetPoint(index), index })),
    { coordinate: request.end ?? request.start, index: null }];
  const hardOrders = [hard.map(({ index }) => index)];
  if (request.waypoint_order === "optimize" && hard.length > 1) {
    const remaining = hard.map(({ index }) => index), nearest = [];
    let point = request.start;
    while (remaining.length) {
      remaining.sort((a, b) => distance(point, targetPoint(a)) - distance(point, targetPoint(b)) || a - b);
      const next = remaining.shift(); nearest.push(next); point = targetPoint(next);
    }
    if (JSON.stringify(nearest) !== JSON.stringify(hardOrders[0])) hardOrders.push(nearest);
  }
  const seeds = hardOrders.map(order => ({ state: sequence(order), skeletonIndex: null }));
  function skeletonState(skeleton) {
    const state = sequence(hardOrders[0]);
    for (const point of skeleton.points.slice(1, -1)) insertCheapest(state, { coordinate: point, index: null });
    return state;
  }
  // No-hard-point loops need useful proposals, rather than Start->Start. Open
  // routes and hard-point loops also get bounded distance-building controls.
  if (request.topology === "loop") {
    const skeletons = generateAdventureControlSkeletons(request);
    // Rank only proposal corridors, using checked local places and bounded
    // insertion estimates. This cannot establish an arrival or route distance.
    // Native routing still supplies every candidate and every displayed metre.
    const corridors = [];
    for (const [index, skeleton] of skeletons.entries()) {
      const state = skeletonState(skeleton);
      if (state.length > 16 || state.some(item => !covered(item.coordinate, reference.bounds))) continue;
      const detour = soft.reduce((sum, { point, index }) => {
        if (!covered(targetPoint(index), reference.bounds)) return sum;
        const copy = state.map(item => ({ ...item }));
        return sum + priority(targetMap.get(point.id)) * insertCheapest(copy, { coordinate: targetPoint(index), index });
      }, 0);
      corridors.push({ state, skeletonIndex: index, detour });
    }
    corridors.sort((a, b) => a.detour - b.detour || a.skeletonIndex - b.skeletonIndex);
    seeds.push(...corridors.slice(0, 8 - seeds.length));
  }
  const usefulSeeds = seeds.filter(({ state }) => state.length > 2 || request.topology !== "loop");
  async function evaluate(state, controlId = null, addedId = null) {
    alive();
    if (!available() || attempts.size >= 32) return null;
    const key = JSON.stringify(state.map(item => [item.coordinate.lat, item.coordinate.lon]));
    if (attempts.has(key)) return null;
    attempts.add(key);
    const order = state.flatMap(item => item.index === null ? [] : [item.index]);
    const proposal = { proposal_id: `adventure/${attempts.size}`, construction: controlId ? "optional_insertion" : "no_optional_control",
      order, points: state.map(item => item.coordinate), point_waypoint_indices: state.map(item => item.index) };
    try {
      const draft = await attempt(proposal); alive();
      if (!draft) return null;
      const metrics = request.topology === "loop" ? analyzeLocalLoopGeometry(draft.geometry, draft.distance_m) : null;
      if (metrics?.degenerate || metrics?.severe_out_and_back && !hard.length) throw failure("unhelpful_loop_geometry");
      const selected = order.filter(index => request.waypoints[index].constraint_strength !== "exact");
      const enriched = { ...draft, geometry_metrics: metrics, source_control_candidate_id: controlId,
        adventure_targets: targets, selected_optional_ids: selected.map(index => request.waypoints[index].id) };
      publishLocalWaypointStops(request, { ...enriched, optional_stop_outcomes: soft.map(({ point }) => ({ id: point.id,
        status: enriched.selected_optional_ids.includes(point.id) ? "reached" : "dropped",
        reason: enriched.selected_optional_ids.includes(point.id) ? null : "not_selected_for_this_candidate" })) });
      const entry = { state, draft: enriched, selected, reward: selected.reduce((sum, index) => sum + priority(targetMap.get(request.waypoints[index].id)), 0) };
      drafts.push(entry);
      return entry;
    } catch (error) {
      alive();
      if (error.name === "AbortError") throw error;
      const code = typeof error.code === "string" && /^[a-z_]{1,80}$/.test(error.code) ? error.code : "invalid_native_reply";
      rejected.push({ code, proposal_id: proposal.proposal_id, details: {} });
      if (addedId) reasons.set(addedId, code === "maximum_distance_exceeded" || code === "strict_distance_tolerance_missed"
        ? "omitted_for_distance" : "route_infeasible");
      if (TERMINAL.has(code)) terminal = code;
      return null;
    }
  }
  // Reserve most of each round for actual optional-stop attempts. Native/cache
  // accounting remains solely in the shared planning context.
  const controlAllowance = Math.min(3, Math.max(1, Math.floor(maxCalls / 3)));
  for (const seed of usefulSeeds) {
    if (context.totalUsed - startUsed >= controlAllowance || terminal || !available()) break;
    const entry = await evaluate(seed.state);
    if (entry) controls.push(entry);
    // Reuse Auto Tour's bounded measured-distance correction. Move only generated
    // proposal controls; exact points, the actual target and routed lines stay fixed.
    if (entry && !entry.draft.within_tolerance && seed.skeletonIndex !== null
      && context.totalUsed - startUsed < controlAllowance && available()) {
      const factor = Math.max(0.7, Math.min(1.3, request.distance_objective.target_m / entry.draft.distance_m));
      if (Math.abs(factor - 1) >= 0.03) {
        const corrected = skeletonState(generateAdventureControlSkeletons(request, factor)[seed.skeletonIndex]);
        if (corrected.every(item => covered(item.coordinate, reference.bounds))) {
          const measured = await evaluate(corrected);
          if (measured) controls.push(measured);
        }
      }
    }
  }
  controls.sort(compareEntries);
  const control = controls[0] ?? null;
  if (control) {
    let beam = controls.slice(0, 2);
    while (available() && !terminal && attempts.size < 32) {
      const proposals = [];
      for (const entry of beam) for (const { point, index } of soft) {
        if (entry.selected.includes(index) || !covered(targetPoint(index), reference.bounds) || entry.state.length >= 16) continue;
        const state = entry.state.map(item => ({ ...item }));
        const delta = insertCheapest(state, { coordinate: targetPoint(index), index });
        const key = JSON.stringify(state.map(item => [item.coordinate.lat, item.coordinate.lon]));
        if (attempts.has(key)) continue;
        const predictedError = Math.abs(entry.draft.distance_m + delta - request.distance_objective.target_m);
        proposals.push({ state, entry, id: point.id, predictedError, reward: entry.reward + priority(targetMap.get(point.id)) });
      }
      proposals.sort((a, b) => Number(a.predictedError > request.distance_objective.tolerance_m)
        - Number(b.predictedError > request.distance_objective.tolerance_m)
        || b.reward - a.reward || a.predictedError - b.predictedError || compareText(a.id, b.id));
      if (!proposals.length) break;
      const next = proposals[0];
      const entry = await evaluate(next.state, control.draft.candidate_id, next.id);
      if (entry) beam = [...beam, entry].sort(compareOptional).slice(0, 3);
    }
  }
  alive();
  const retained = [], seen = new Set();
  let similarOmitted = false;
  // Retain the comparison line independently of the requested alternative count.
  // Final publication puts target eligibility first, then preserves the control
  // gate because unknown repetition cannot justify a POI-based promotion.
  for (const entry of [control, ...drafts.filter(entry => entry.selected.length).sort(compareOptional), ...controls].filter(Boolean)) {
    const forward = JSON.stringify(entry.draft.geometry), reverse = JSON.stringify([...entry.draft.geometry].reverse());
    const key = request.topology === "loop" && reverse < forward ? reverse : forward;
    if (seen.has(key)) continue;
    if (request.topology === "loop" && entry !== control) {
      // Keep the explicit comparison independently. Two claimed adventure
      // alternatives must have distinct sampled native lines, rather than one
      // extra small landmark detour on the same loop. Reuse Auto Tour's proxy;
      // it is not a claim about unavailable edge-ID overlap.
      const threshold = Math.max(150, Math.min(600, request.distance_objective.target_m * 0.025));
      const comparison = entry.selected.length ? retained.filter(other => other.selected.length) : retained;
      if (!entry.selected.length && control?.draft.within_tolerance && !entry.draft.within_tolerance) continue;
      if (comparison.some(other => geometryDiversityDistanceM(other.draft.geometry, entry.draft.geometry) < threshold)) {
        similarOmitted = true; continue;
      }
    }
    seen.add(key); retained.push(entry);
    if (retained.length === Math.max(2, request.candidate_count)) break;
  }
  const candidates = [];
  for (const entry of retained) {
    alive();
    let nature = unavailableNature(entry.draft.distance_m, "nature_index_unavailable");
    try { if (data) nature = await data.analyzeNature(entry.draft); } catch { /* Explicit unavailable metrics. */ }
    alive();
    const outcomes = soft.map(({ point }) => ({ id: point.id, status: entry.draft.selected_optional_ids.includes(point.id) ? "reached" : "dropped",
      reason: entry.draft.selected_optional_ids.includes(point.id) ? null : !covered(point.approach_override, reference.bounds)
        ? "outside_coverage" : reasons.get(point.id) ?? (available() ? "not_selected_for_this_candidate" : "search_budget_exhausted") }));
    candidates.push({ ...entry.draft, nature_analysis: nature, optional_stop_outcomes: outcomes, rank: candidates.length + 1 });
  }
  const counts = {};
  for (const rejection of rejected) counts[rejection.code] = (counts[rejection.code] ?? 0) + 1;
  return deepFreeze({ schema_version: 1, type: "local_waypoint_route_result", profile: request.routing_profile,
    status: candidates.length ? "success" : "no_candidates", code: candidates.length ? null : terminal ?? rejected[0]?.code ?? "no_valid_local_candidate",
    request, candidates, pack_id: candidates[0]?.pack_id ?? null,
    no_optional_control_candidate_id: control?.draft.candidate_id ?? null,
    route_call_count: context.totalUsed, route_call_budget: context.snapshot().budget.total_limit,
    rejected_attempt_counts: counts, rejected_attempts: rejected, search_diagnostics: context.snapshot(),
    warnings: ["exact_edge_repetition_unavailable", "path_attributes_and_access_unavailable",
      "geometry_distinctness_is_not_corridor_diversity",
      ...(similarOmitted ? ["similar_loop_alternatives_omitted"] : []), "optional_detours_not_promoted_without_repetition_evidence"] });
}

function insertCheapest(state, item) {
  let best = 1, delta = Infinity;
  for (let index = 1; index < state.length; index += 1) {
    const before = state[index - 1].coordinate, after = state[index].coordinate;
    const cost = distance(before, item.coordinate) + distance(item.coordinate, after) - distance(before, after);
    if (cost < delta) { best = index; delta = cost; }
  }
  state.splice(best, 0, item);
  return delta;
}
function priority(target) { return 1 + Math.max(0, Math.min(10, target?.priority ?? 0)); }
function compareEntries(a, b) {
  return Number(b.draft.within_tolerance) - Number(a.draft.within_tolerance)
    || a.draft.target_error_m - b.draft.target_error_m || compareText(a.draft.candidate_id, b.draft.candidate_id);
}
function compareOptional(a, b) {
  return Number(b.draft.within_tolerance) - Number(a.draft.within_tolerance)
    || b.reward - a.reward || a.draft.target_error_m - b.draft.target_error_m
    || compareText(a.draft.candidate_id, b.draft.candidate_id);
}
function failure(code) { const error = new Error(code); error.code = code; return error; }
