// Bounded proposals for the existing Waypoint producer. Only its injected
// attempt boundary may route; coordinates here are never displayed as a line.
import { analyzeLocalLoopGeometry, generateAdventureControlSkeletons, geometryDiversityDistanceM } from "./local_auto_tour.js";
import { deepFreeze } from "./local_candidate_evaluator.js";
import { haversineDistance } from "./local_plan_geometry.js";
import { unavailableNature } from "./local_region_data.js";
import { publishLocalWaypointStops } from "./local_candidate_enrichment.js";
import { strongWoodlandPreference, compareWoodlandTradeoff } from "./adventure_assessment.js";

const distance = (a, b) => haversineDistance([a.lon, a.lat], [b.lon, b.lat]);
const covered = (p, bounds) => p.lon >= bounds[0] && p.lat >= bounds[1] && p.lon <= bounds[2] && p.lat <= bounds[3];
const compareText = (a, b) => a < b ? -1 : a > b ? 1 : 0;
const TERMINAL = new Set(["unsupported_profile", "routing_pack_unavailable", "no_covering_routing_pack",
  "no_compatible_routing_pack", "routing_busy", "routing_pack_identity_changed", "profile_identity_mismatch"]);

export async function searchWaypointAdventure({ request, targets = [], context, phase, maxCalls,
  reference, current, attempt, data = null, wishes = [] }) {
  if (!Number.isSafeInteger(maxCalls) || maxCalls < 1 || maxCalls > 16
    || !reference?.pack_id || !Array.isArray(reference.bounds) || reference.bounds.length !== 4
    || !Array.isArray(targets) || targets.length > 30) throw new TypeError("Invalid adventure search inputs.");
  const targetMap = new Map(targets.map(target => [target.id, target]));
  const forest = Boolean(strongWoodlandPreference(wishes));
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
  let woodlandGuidance = { available: false, queried_point_count: 0, woodland_point_count: 0, unknown_point_count: 0, operation_count: null };
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
  async function loopSeeds(factor = 1, guide = false) {
    const skeletons = generateAdventureControlSkeletons(request, factor);
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
    if (guide && data?.queryWoodlandPoints) {
      // A mapped woodland point can guide a heading, never establish forest
      // coverage along a proposed line. All final shares use native geometry.
      try {
        const points = [...new Map(corridors.flatMap(corridor => corridor.state.slice(1, -1))
          .map(item => [JSON.stringify(item.coordinate), { lat: item.coordinate.lat, lon: item.coordinate.lon }])).values()];
        const guidance = await data.queryWoodlandPoints({ points }); alive();
        if (guidance.identity.routing_pack_id !== reference.pack_id || guidance.identity.build_id !== reference.build_id
          || guidance.woodland.length !== points.length) throw failure("regional_data_changed");
        woodlandGuidance = { available: guidance.available, queried_point_count: points.length,
          woodland_point_count: guidance.woodland.filter(value => value === true).length,
          unknown_point_count: guidance.woodland.filter(value => value === null).length, operation_count: guidance.operation_count };
        if (guidance.available) {
          const hints = new Map(points.map((point, index) => [JSON.stringify([point.lat, point.lon]), guidance.woodland[index]]));
          corridors.forEach(corridor => { const controls = corridor.state.slice(1, -1);
            corridor.woodland_hint = controls.filter(item => hints.get(JSON.stringify([item.coordinate.lat, item.coordinate.lon])) === true).length / controls.length;
          });
        }
      } catch { alive(); /* Missing guidance never prevents native routing. */ }
    }
    corridors.sort((a, b) => (b.woodland_hint ?? 0) - (a.woodland_hint ?? 0)
      || a.detour - b.detour || a.skeletonIndex - b.skeletonIndex);
    // Explore another heading before spending every insertion on one corridor.
    // This ranks proposals only; all feasibility and distances come from native routing.
    const shortlist = corridors.splice(0, guide ? corridors.length : Math.min(corridors.length, 4));
    corridors.length = 0; corridors.push(...shortlist);
    const diverse = [];
    while (corridors.length && diverse.length < 8 - hardOrders.length) {
      const bestHint = Math.max(...corridors.map(corridor => corridor.woodland_hint ?? 0));
      const index = !diverse.length ? 0 : corridors.reduce((best, corridor, index) => {
        if (bestHint && (corridor.woodland_hint === bestHint) !== (corridors[best].woodland_hint === bestHint)) return corridor.woodland_hint === bestHint ? index : best;
        const separation = item => Math.min(...diverse.map(other => geometryDiversityDistanceM(
          other.state.map(item => [item.coordinate.lon, item.coordinate.lat]), item.state.map(item => [item.coordinate.lon, item.coordinate.lat]))));
        return separation(corridor) > separation(corridors[best]) ? index : best;
      }, 0);
      diverse.push(corridors.splice(index, 1)[0]);
    }
    return diverse;
  }
  if (request.topology === "loop") seeds.push(...await loopSeeds());
  const usefulSeeds = seeds.filter(({ state }) => state.length > 2 || request.topology !== "loop");
  async function evaluate(state, controlId = null, addedId = null, rootId = null) {
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
      // These are complete, arrival-validated native routes, never insertion
      // estimates. The shared regional worker/cache owns the bounded analysis.
      if (forest) enriched.nature_analysis = await measureNature(enriched);
      const entry = { state, draft: enriched, selected, root: rootId ?? draft.candidate_id, reward: selected.reduce((sum, index) => sum + priority(targetMap.get(request.waypoints[index].id)), 0) };
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
  async function measureNature(draft) {
    let nature = unavailableNature(draft.distance_m, "nature_index_unavailable");
    try { if (data) nature = await data.analyzeNature(draft); } catch { /* Explicit unavailable metrics. */ }
    alive(); return nature;
  }
  const compareForestedEntries = (a, b) => compareForestedDrafts(a.draft, b.draft, wishes)
    || b.reward - a.reward || compareText(a.draft.candidate_id, b.draft.candidate_id);
  // Reserve at least three calls for optional stops in the forest lane, half
  // the round otherwise. Native/cache
  // accounting remains solely in the shared planning context.
  const controlAllowance = forest ? Math.max(1, Math.min(5, maxCalls - 3))
    : Math.min(4, Math.max(1, request.candidate_count >= 3 ? Math.ceil(maxCalls / 2) : Math.floor(maxCalls / 3)));
  for (const seed of usefulSeeds) {
    if (context.totalUsed - startUsed >= controlAllowance || terminal || !available()) break;
    if (forest && controls.length) break;
    const entry = await evaluate(seed.state);
    if (entry) { entry.skeletonIndex = seed.skeletonIndex; controls.push(entry); }
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
  if (forest && request.topology === "loop" && controls.length) {
    // Preserve the original control/correction, then use its measured native
    // detour factor to size other headings. Point hints guide proposals only.
    const factor = Math.max(0.7, Math.min(1.3, request.distance_objective.target_m / controls[0].draft.distance_m));
    const alternatives = await loopSeeds(factor, true);
    for (const seed of alternatives) {
      if (context.totalUsed - startUsed >= controlAllowance || terminal || !available()) break;
      const entry = await evaluate(seed.state); if (entry) controls.push(entry);
    }
  }
  controls.sort(compareEntries);
  const control = controls[0] ?? null;
  if (control) {
    let beam = (controls.some(entry => entry.draft.within_tolerance) ? controls.filter(entry => entry.draft.within_tolerance) : controls)
      .sort(forest ? compareForestedEntries : compareEntries)
      .slice(0, Math.min(3, request.candidate_count));
    const branchAttempts = new Map();
    let bundledAttempts = 0;
    while (available() && !terminal && attempts.size < 32) {
      const proposals = [];
      for (const entry of beam) for (const { point, index } of soft) {
        if (entry.selected.includes(index) || reasons.get(point.id) === "route_infeasible" || !covered(targetPoint(index), reference.bounds) || entry.state.length >= 16) continue;
        const state = entry.state.map(item => ({ ...item }));
        const delta = insertCheapest(state, { coordinate: targetPoint(index), index });
        const key = JSON.stringify(state.map(item => [item.coordinate.lat, item.coordinate.lon]));
        if (attempts.has(key)) continue;
        const predictedError = Math.abs(entry.draft.distance_m + delta - request.distance_objective.target_m);
        proposals.push({ state, entry, id: point.id, predictedError, reward: entry.reward + priority(targetMap.get(point.id)) });
      }
      // Try a small useful group in one complete native call instead of always
      // paying one call per added stop. Failed groups retain single-stop probes.
      for (const entry of bundledAttempts >= 2 || bundledAttempts === 1 && !reasons.size ? [] : beam) {
        const state = entry.state.map(item => ({ ...item }));
        const remaining = soft.filter(({ index }) => !entry.selected.includes(index) && reasons.get(request.waypoints[index].id) !== "route_infeasible" && covered(targetPoint(index), reference.bounds));
        let delta = 0, reward = entry.reward, added = [];
        while (remaining.length && added.length < 3 && state.length < 16) {
          const ranked = remaining.map(item => {
            const copy = state.map(item => ({ ...item }));
            return { ...item, delta: insertCheapest(copy, { coordinate: targetPoint(item.index), index: item.index }) };
          }).sort((a, b) => priority(targetMap.get(b.point.id)) - priority(targetMap.get(a.point.id)) || a.delta - b.delta || a.index - b.index);
          const next = ranked.find(item => Math.abs(entry.draft.distance_m + delta + item.delta - request.distance_objective.target_m) <= request.distance_objective.tolerance_m);
          if (!next) break;
          delta += insertCheapest(state, { coordinate: targetPoint(next.index), index: next.index });
          reward += priority(targetMap.get(next.point.id)); added.push(next.point.id);
          remaining.splice(remaining.findIndex(item => item.index === next.index), 1);
        }
        const key = JSON.stringify(state.map(item => [item.coordinate.lat, item.coordinate.lon]));
        if (added.length > 1 && !attempts.has(key)) proposals.push({ state, entry, id: added.at(-1),
          predictedError: Math.abs(entry.draft.distance_m + delta - request.distance_objective.target_m), reward, bundle: true });
      }
      proposals.sort((a, b) => Number((branchAttempts.get(a.entry.root) ?? 0) > 0) - Number((branchAttempts.get(b.entry.root) ?? 0) > 0)
        || Number(a.predictedError > request.distance_objective.tolerance_m)
        - Number(b.predictedError > request.distance_objective.tolerance_m)
        || (forest ? compareForestedEntries(a.entry, b.entry) : 0)
        || b.reward - a.reward || a.predictedError - b.predictedError || compareText(a.id, b.id));
      if (!proposals.length) break;
      const next = proposals[0];
      branchAttempts.set(next.entry.root, (branchAttempts.get(next.entry.root) ?? 0) + 1);
      if (next.bundle) bundledAttempts++;
      const entry = await evaluate(next.state, control.draft.candidate_id, next.bundle ? null : next.id, next.entry.root);
      if (entry) {
        const untried = beam.filter(item => !branchAttempts.has(item.root));
        beam = [...new Set([...untried, ...[...beam, entry].sort(forest ? compareForestedEntries : compareOptional)])].slice(0, 3);
      }
    }
  }
  alive();
  const retained = [], seen = new Set();
  let similarOmitted = 0;
  // Retain the comparison line independently of the requested alternative count.
  // Final publication puts target eligibility first, then preserves the control
  // gate because unknown repetition cannot justify a POI-based promotion.
  for (const entry of (forest ? drafts : [control, ...drafts.filter(entry => entry.selected.length).sort(compareOptional), ...controls]).filter(Boolean)) {
    const forward = JSON.stringify(entry.draft.geometry), reverse = JSON.stringify([...entry.draft.geometry].reverse());
    const key = request.topology === "loop" && reverse < forward ? reverse : forward;
    if (seen.has(key)) continue;
    if (!forest && request.topology === "loop" && entry !== control) {
      // Keep the explicit comparison independently. Two claimed adventure
      // alternatives must have distinct sampled native lines, rather than one
      // extra small landmark detour on the same loop. Reuse Auto Tour's proxy;
      // it is not a claim about unavailable edge-ID overlap.
      const threshold = Math.max(150, Math.min(600, request.distance_objective.target_m * 0.025));
      const comparison = entry.selected.length ? retained.filter(other => other.selected.length) : retained;
      if (!entry.selected.length && control?.draft.within_tolerance && !entry.draft.within_tolerance) continue;
      if (comparison.some(other => geometryDiversityDistanceM(other.draft.geometry, entry.draft.geometry) < threshold)) {
        similarOmitted++; continue;
      }
    }
    seen.add(key); retained.push(entry);
    if (!forest && retained.length === Math.min(5, Math.max(2, request.candidate_count + (wishes.length ? 2 : 0)))) break;
  }
  const candidates = [];
  for (const entry of retained) {
    alive();
    const nature = entry.draft.nature_analysis ?? await measureNature(entry.draft);
    alive();
    const outcomes = soft.map(({ point }) => ({ id: point.id, status: entry.draft.selected_optional_ids.includes(point.id) ? "reached" : "dropped",
      reason: entry.draft.selected_optional_ids.includes(point.id) ? null : !covered(point.approach_override, reference.bounds)
        ? "outside_coverage" : reasons.get(point.id) ?? (available() ? "not_selected_for_this_candidate" : "search_budget_exhausted") }));
    candidates.push({ ...entry.draft, nature_analysis: nature, optional_stop_outcomes: outcomes, rank: candidates.length + 1 });
  }
  // Nature belongs only to complete, validated routes. Unknown coverage never earns
  // a preference improvement, and hard distance/loop gates precede soft wishes.
  const noOptional = candidates.find(candidate => candidate.candidate_id === control?.draft.candidate_id);
  const options = candidates.filter(candidate => candidate !== noOptional).sort((a, b) => {
    const base = Number(b.within_tolerance) - Number(a.within_tolerance)
      || (!a.within_tolerance && !b.within_tolerance ? a.target_error_m - b.target_error_m : 0)
      || (a.geometry_metrics && b.geometry_metrics ? a.geometry_metrics.geometry_penalty - b.geometry_metrics.geometry_penalty : 0);
    if (base) return base;
    const preference = candidate => wishes.reduce((sum, wish) => {
      const metric = { woodland: "woodland", urban: "urban", water: "near_water" }[wish.metric];
      if (!metric || !a.nature_analysis.available || !b.nature_analysis.available) return sum;
      const share = candidate.nature_analysis[metric]?.share;
      if (!Number.isFinite(share)) return sum;
      const value = wish.goal === "target" ? Math.abs(share * 100 - wish.value) / 100
        : ["minimize", "avoid"].includes(wish.goal) ? share : -share;
      return sum + value * ({ hard: 8, high: 4, medium: 2, low: 1 }[wish.importance] ?? 1);
    }, 0);
    return preference(a) - preference(b) || b.selected_optional_ids.length - a.selected_optional_ids.length
      || a.target_error_m - b.target_error_m || compareText(a.candidate_id, b.candidate_id);
  });
  const selected = forest ? selectForestTradeoffs(candidates, noOptional, request, wishes, targetMap)
    : [noOptional, ...options].filter(Boolean).slice(0, Math.max(2, request.candidate_count));
  if (forest) similarOmitted = candidates.filter(candidate => !selected.includes(candidate)
    && !distinctAdventureRouteFamilies([...selected, candidate], request.topology, request.distance_objective.target_m).includes(candidate.candidate_id)).length;
  selected.forEach((candidate, index) => { candidate.rank = index + 1; });
  const families = distinctAdventureRouteFamilies(selected, request.topology, request.distance_objective.target_m);
  const counts = {};
  for (const rejection of rejected) counts[rejection.code] = (counts[rejection.code] ?? 0) + 1;
  return deepFreeze({ schema_version: 1, type: "local_waypoint_route_result", profile: request.routing_profile,
    status: candidates.length ? "success" : "no_candidates", code: candidates.length ? null : terminal ?? rejected[0]?.code ?? "no_valid_local_candidate",
    request, candidates: selected, pack_id: selected[0]?.pack_id ?? null,
    adventure_diagnostics: { requested_count: request.candidate_count, distinct_candidate_ids: families, distinct_route_count: families.length,
      comparison_variant_count: selected.length - families.length, evaluated_sequences: attempts.size,
      validated_drafts: drafts.length, nature_finalists: retained.length, diversity_omitted: similarOmitted,
      ...(forest ? { preference_strategy: "strong_woodland", nature_measured_complete_routes: retained.length, woodland_guidance: woodlandGuidance } : {}),
      returned_count: selected.length, within_tolerance_count: selected.filter(candidate => candidate.within_tolerance).length,
      budget_finished: !available(), rejected_attempt_counts: counts },
    no_optional_control_candidate_id: control?.draft.candidate_id ?? null,
    route_call_count: context.totalUsed, route_call_budget: context.snapshot().budget.total_limit,
    rejected_attempt_counts: counts, rejected_attempts: rejected, search_diagnostics: context.snapshot(),
    warnings: ["exact_edge_repetition_unavailable", "path_attributes_and_access_unavailable",
      "geometry_distinctness_is_not_corridor_diversity",
      ...(similarOmitted ? ["similar_loop_alternatives_omitted"] : []),
      ...(families.length < selected.length ? ["similar_comparison_variants_retained"] : []), "optional_detours_not_promoted_without_repetition_evidence"] });
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
    || (!a.draft.within_tolerance && !b.draft.within_tolerance ? a.draft.target_error_m - b.draft.target_error_m : 0)
    || b.reward - a.reward || a.draft.target_error_m - b.draft.target_error_m
    || compareText(a.draft.candidate_id, b.draft.candidate_id);
}
function measuredDraft(draft) {
  return { within_distance_tolerance: draft.within_tolerance, distance_m: draft.distance_m,
    target_error_m: draft.target_error_m, loop_geometry: draft.geometry_metrics,
    nature: draft.nature_analysis?.available ? { woodland: draft.nature_analysis.woodland.share, urban: draft.nature_analysis.urban.share } : null };
}
function compareForestedDrafts(a, b, wishes) {
  return Number(b.within_tolerance) - Number(a.within_tolerance)
    || (!a.within_tolerance && !b.within_tolerance ? a.target_error_m - b.target_error_m : 0)
    || compareWoodlandTradeoff(measuredDraft(a), measuredDraft(b), wishes)
    || (a.geometry_metrics && b.geometry_metrics ? a.geometry_metrics.geometry_penalty - b.geometry_metrics.geometry_penalty : 0)
    || a.target_error_m - b.target_error_m || compareText(a.candidate_id, b.candidate_id);
}
function selectForestTradeoffs(candidates, control, request, wishes, targets) {
  let pool = candidates.some(candidate => candidate.within_tolerance) ? candidates.filter(candidate => candidate.within_tolerance) : [...candidates];
  const useful = candidate => !candidate.geometry_metrics?.degenerate && !candidate.geometry_metrics?.severe_out_and_back;
  if (pool.some(useful)) pool = pool.filter(useful);
  const forestOrder = (a, b) => compareForestedDrafts(a, b, wishes);
  pool.sort(forestOrder);
  const selected = [];
  const add = ordered => {
    const candidate = ordered.find(candidate => !selected.includes(candidate)
      && distinctAdventureRouteFamilies([...selected, candidate], request.topology, request.distance_objective.target_m).includes(candidate.candidate_id));
    if (candidate) selected.push(candidate);
  };
  add(pool); // Most useful measured woodland tradeoff.
  const historical = candidate => candidate.selected_optional_ids.filter(id => ["castle", "ruins", "archaeological_site"].includes(targets.get(id)?.local_category)).length;
  const visits = (a, b) => historical(b) - historical(a) || b.selected_optional_ids.length - a.selected_optional_ids.length || forestOrder(a, b);
  if (selected.length < request.candidate_count) {
    const highlights = [...pool].sort(visits)[0];
    // A worthwhile checked-place detour may share its forest loop. Keep it as
    // an explicitly counted variant, never as another independent family.
    if (highlights && !selected.includes(highlights) && highlights.selected_optional_ids.length > (selected[0]?.selected_optional_ids.length ?? 0)) selected.push(highlights);
    else add([...pool].sort(visits));
  }
  // A balanced alternative keeps within ten percentage points of the best
  // measured woodland line, then favors checked places. This describes an
  // actual tradeoff; it does not manufacture a third category or route family.
  const bestWoodland = Math.max(...pool.map(candidate => candidate.nature_analysis?.available ? candidate.nature_analysis.woodland.share : -Infinity));
  if (selected.length < request.candidate_count) add(pool.filter(candidate => candidate.nature_analysis?.available
    && candidate.nature_analysis.woodland.share >= bestWoodland - 0.1).sort(visits));
  while (distinctAdventureRouteFamilies(selected, request.topology, request.distance_objective.target_m).length < request.candidate_count
    && selected.length < Math.min(4, request.candidate_count + 1)) {
    const count = selected.length; add(pool); if (selected.length === count) break;
  }
  // The comparison is independently exposed, rather than taking the last slot
  // from a requested alternative. Publication retains its existing promotion gate.
  if (control && !selected.includes(control)) selected.push(control);
  return selected.slice(0, 5);
}
function failure(code) { const error = new Error(code); error.code = code; return error; }

// Diversity evidence only, never edge repetition or corridor-equivalence claims.
// Keep the useful no-POI comparison even when a landmark detour is its variant,
// but do not count both toward a request for genuinely different loops.
export function distinctAdventureRouteFamilies(candidates, topology, targetM) {
  if (topology !== "loop") return candidates.map(candidate => candidate.candidate_id);
  const threshold = Math.max(150, Math.min(600, targetM * 0.025));
  const edges = candidates.map(candidate => {
    const segments = candidate.geometry.slice(1).map((point, index) => {
      const before = candidate.geometry[index], pair = [JSON.stringify(before), JSON.stringify(point)].sort();
      return { key: pair.join("/"), length: haversineDistance(before, point) };
    });
    return { candidate, segments, keys: new Set(segments.map(segment => segment.key)), total: segments.reduce((sum, segment) => sum + segment.length, 0) };
  });
  const representatives = [];
  for (const entry of edges) {
    const shared = (a, b) => a.total > 0 ? a.segments.reduce((sum, segment) => sum + (b.keys.has(segment.key) ? segment.length : 0), 0) / a.total : 1;
    if (representatives.some(other => geometryDiversityDistanceM(entry.candidate.geometry, other.candidate.geometry) < threshold
      || Math.min(shared(entry, other), shared(other, entry)) >= 0.85)) continue;
    representatives.push(entry);
  }
  return representatives.map(entry => entry.candidate.candidate_id);
}
