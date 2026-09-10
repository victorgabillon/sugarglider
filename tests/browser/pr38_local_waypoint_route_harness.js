import {
  LOCAL_WAYPOINT_MAX_WAYPOINTS,
  LOCAL_WAYPOINT_ROUTE_CALL_BUDGET,
  LocalWaypointRouteValidationError,
  addLocalWaypointProfileOptions,
  createLocalWaypointRouteEngine,
  createLocalWaypointRouteExperiment,
  localWaypointOrderProposals,
  readLocalWaypointRouteRequest,
  validateLocalWaypointRouteRequest,
} from "../../src/sugarglider/web/static/local_waypoint_route.js";
import { createLocalRoutingExperiment, PUBLIC_LOCAL_ROUTE_PROFILES } from "../../src/sugarglider/web/static/local_routing.js";
import { currentPlanRequest, state } from "../../src/sugarglider/web/static/state.js";

export async function runPr38LocalWaypointRouteHarness() {
  const scenarios = [];
  for (const [name, run] of [
    ["fixed_point_to_point_exact_order", () => fixedScenario("point_to_point")],
    ["fixed_loop_exact_order", () => fixedScenario("loop")],
    ["direct_point_to_point", directScenario],
    ["canonical_planner_and_server_state_unchanged", canonicalScenario],
    ["readonly_ui_rejection_preserves_shared_state_and_controls", () => readonlyUiScenario(false)],
    ["readonly_ui_supported_snapshot_preserves_shared_state_and_controls", () => readonlyUiScenario(true)],
    ["readonly_ui_never_normalizes_unsupported_intent", readonlyUnsupportedScenario],
    ["bounded_endpoint_safe_optimized_orders", proposalScenario],
    ["identical_seed_and_native_responses_are_deterministic", determinismScenario],
    ["different_seed_changes_bounded_proposals", seedScenario],
    ["target_first_stable_candidate_ranking", rankingScenario],
    ["strict_sequential_route_call_budget", budgetScenario],
    ["native_failures_and_exceptions_are_counted", failuresScenario],
    ["duplicate_start_and_invalidation_drain", singleFlightScenario],
    ["stale_generation_cannot_render", staleScenario],
    ["changed_intent_stops_further_native_calls", changedIntentScenario],
    ["invalid_native_reply_rejected", invalidReplyScenario],
    ["unsupported_constraints_never_weakened", unsupportedScenario],
    ["strict_request_validation", invalidRequestScenario],
    ["fourteen_interiors_and_sixteen_point_limit", maximumScenario],
    ["graph_derived_loop_closure", closureScenario],
    ["hard_start_25m_boundary", () => endpointsScenario("start")],
    ["hard_point_to_point_end_25m_boundary", () => endpointsScenario("end")],
    ["hard_loop_return_25m_boundary", () => endpointsScenario("loop_return")],
    ["exact_waypoint_300m_boundary", exactScenario],
    ["ordered_snaps_must_exist_in_geometry", orderedGeometryScenario],
    ["no_covering_or_compatible_pack_is_terminal", regionalFailureScenario],
    ["all_six_profiles_and_marly_paris_propagation", profilesScenario],
    ["one_pack_identity_per_generation", packIdentityScenario],
    ["duplicate_geometry_returns_fewer_candidates", diversityScenario],
    ["soft_and_strict_distance_objectives", distanceScenario],
    ["no_fetch_fallback_or_fabricated_geometry", noFallbackScenario],
    ["debug_capability_and_shared_experiment_busy_gate", debugGateScenario],
    ["offline_debug_profiles_do_not_fake_server_availability", localProfileOptionsScenario],
  ]) {
    await run();
    scenarios.push(name);
  }
  return scenarios;
}

async function fixedScenario(topology) {
  const input = request({ topology, ...(topology === "loop" ? { end: null } : {}) });
  const before = JSON.stringify(input);
  const calls = [];
  const native = [];
  const result = await engine((value) => {
    calls.push(value);
    const reply = routed(value);
    native.push(reply);
    return reply;
  }).generate(input);
  equal(result.route_call_count, 1, "fixed order routes exactly once");
  equal(calls[0].points, rawPoints(input), "topology-derived native point order");
  equal(result.candidates[0].actual_waypoint_order, input.waypoints.map((point) => point.id), "interior identities stay ordered");
  equal(result.candidates[0].original_waypoint_indices, [1, 2], "original indices retained");
  equal(result.candidates[0].geometry, native[0].geometry, "only native geometry is published");
  assert(result.candidates[0].exact_point_outcomes.every((outcome) => outcome.status === "reached" && outcome.snap_distance_m === 0), "exact outcomes");
  assert(Object.isFrozen(result.candidates[0].geometry[0]), "nested geometry immutable");
  assert(!Object.isFrozen(input), "caller input not frozen");
  equal(JSON.stringify(input), before, "caller intent not mutated");
}

async function directScenario() {
  const result = await engine().generate(request({ waypoints: [], waypoint_order: "optimize" }));
  equal(result.route_call_count, 1, "no pointless ordering calls for a direct route");
  equal(result.candidates[0].requested_points.length, 2, "two endpoints");
  equal(result.candidates[0].actual_waypoint_order, [], "no invented interior");
}

async function canonicalScenario() {
  const saved = structuredClone({
    planningMode: state.planningMode, points: state.points, waypointPoints: state.waypointPoints,
    waypointEndpoints: state.waypointEndpoints, options: state.options,
    waypointOptions: state.waypointOptions, plan: state.plan, routingProfile: state.routingProfile,
  });
  const serverResult = state.generationResult;
  const raw = request();
  try {
    state.planningMode = "waypoint_route";
    state.routingProfile = raw.routing_profile;
    state.waypointEndpoints = { start: raw.start, end: raw.end, routeTopology: raw.topology };
    state.points = raw.waypoints.map((point) => ({ id: point.id, name: point.name, ...point.coordinate, constraintStrength: "exact" }));
    state.options = { ...state.waypointOptions, targetDistanceKm: 12, toleranceKm: .5 };
    const canonical = currentPlanRequest();
    const before = JSON.stringify(canonical);
    const result = await engine().generate(canonical);
    equal(result.requested_waypoint_order, raw.waypoints.map((point) => point.id), "real canonical state accepted");
    equal(JSON.stringify(currentPlanRequest()), before, "local core did not rewrite canonical intent");
    assert(state.generationResult === serverResult, "server results untouched");
  } finally { Object.assign(state, saved); }
}

function proposalScenario() {
  for (const topology of ["loop", "point_to_point"]) {
    const raw = request({ topology, ...(topology === "loop" ? { end: null } : {}), waypoints: waypoints(8), waypoint_order: "optimize" });
    const orders = localWaypointOrderProposals(raw);
    assert(orders.length <= 16 && orders.length > 1, "bounded nontrivial proposals");
    equal(orders[0].order, raw.waypoints.map((_, index) => index), "fixed control first");
    for (const proposal of orders) equal([...proposal.order].sort((a, b) => a - b), orders[0].order, "no missing or duplicated exact point");
    assert(orders.some((proposal) => proposal.construction === "nearest_neighbor"), "useful nearest-neighbor proposal");
  }
}

async function readonlyUiScenario(supported) {
  const previous = { ...state };
  const raw = request();
  const controls = plannerControls(raw);
  // The controls deliberately differ from cached options: this must read current
  // values without copying them back into any shared planner state.
  controls.get("nature-preference").value = supported ? "off" : "prefer";
  try {
    Object.assign(state, {
      planningMode: "waypoint_route", routingProfile: "road_bike",
      options: { ...state.waypointOptions, name: "Cached options", seed: 999 },
      waypointEndpoints: { start: raw.start, end: raw.end, routeTopology: raw.topology },
      points: raw.waypoints.map((point) => ({ ...point.coordinate, id: point.id, name: point.name, constraintStrength: "exact" })),
      plan: { unchanged: "previous canonical plan" },
      generationResult: { candidates: [{ id: "server-selected" }] },
      selectedSignature: "server-selected", request: { status: "success", id: 38, startedAt: null },
      savedRouteSnapshotDisplay: false, outingDisplay: false,
    });
    const references = { ...state };
    const before = JSON.stringify(state);
    const beforeControls = controlsSnapshot(controls);
    // This is the exact exported getter wired into app.js, not a fake raw request.
    const getRequest = () => readLocalWaypointRouteRequest(state, (id) => controls.get(id));
    const snapshot = getRequest();
    const expected = {
      ...raw,
      start: { ...raw.start, name: "Start" }, end: { ...raw.end, name: "End" },
      waypoints: raw.waypoints.map((point) => ({ ...point, coordinate: { ...point.coordinate, name: point.name } })),
      preferences: { ...raw.preferences, nature: supported ? "off" : "prefer" },
    };
    if (supported) {
      equal(validateLocalWaypointRouteRequest(snapshot), validateLocalWaypointRouteRequest(expected), "current controls and identified planner points serialized correctly");
      snapshot.start.lat += 1;
      snapshot.waypoints[0].coordinate.lon += 1;
      snapshot.preferences.nature = "prefer";
    } else {
      equal(snapshot.preferences.nature, "prefer", "unsupported preference not rewritten");
    }
    let calls = 0;
    const elements = uiElements();
    const experiment = createLocalWaypointRouteExperiment({
      bridge: { route: (input) => { calls += 1; return routed(input); } },
      getRequest, elements,
    });
    const result = await experiment.requestFromPlanner();
    equal(calls, supported ? 1 : 0, "unsupported UI intent never reaches local_route");
    if (supported) {
      equal(result.request, validateLocalWaypointRouteRequest(expected), "local result uses current read-only intent");
    } else {
      equal(result, null, "rejected UI generation");
      assert(elements.status.textContent.includes("unsupported_preference"), "useful stable UI rejection code");
    }
    equal(JSON.stringify(state), before, "all shared state contents unchanged, including canonical plan and server lifecycle");
    for (const key of Object.keys(references)) assert(state[key] === references[key], `shared ${key} identity unchanged`);
    equal(controlsSnapshot(controls), beforeControls, "all control values and DOM unchanged");
  } finally { Object.assign(state, previous); }
}

function readonlyUnsupportedScenario() {
  for (const [change, code] of [
    [(planner, controls) => { controls.get("path-selection-mode").value = "low_overlap"; }, "unsupported_preference"],
    [(planner, controls) => { controls.get("loop-geometry-preference").value = "prefer"; }, "unsupported_preference"],
    [(planner, controls) => { controls.get("maximum-distance").value = "20"; }, "unsupported_flexible_maximum"],
    [(planner) => { planner.points[0].constraintStrength = "approach"; }, "unsupported_constraint_strength"],
    [(planner) => { planner.points[0].constraintStrength = "best_effort"; }, "unsupported_constraint_strength"],
    [(planner) => { planner.points[0].constraintStrength = null; }, "unsupported_constraint_strength"],
    [(planner) => { planner.points[0].approachOverride = { lat: 48.88, lon: 2.12 }; }, "unsupported_approach_override"],
    [(planner) => { planner.points[0].maximumBestEffortDistanceM = 500; }, "unsupported_best_effort_bound"],
  ]) {
    const raw = request();
    const controls = plannerControls(raw);
    const planner = {
      planningMode: "waypoint_route", autoTour: state.autoTour,
      waypointEndpoints: { start: raw.start, end: raw.end, routeTopology: raw.topology },
      points: raw.waypoints.map((point) => ({ ...point.coordinate, id: point.id, name: point.name, constraintStrength: "exact" })),
    };
    change(planner, controls);
    const before = JSON.stringify(planner);
    const beforeControls = controlsSnapshot(controls);
    rejects(readLocalWaypointRouteRequest(planner, (id) => controls.get(id)), code);
    equal(JSON.stringify(planner), before, "unsupported intent retained in planner");
    equal(controlsSnapshot(controls), beforeControls, "unsupported control values retained");
  }
}

async function determinismScenario() {
  const raw = request({ waypoints: waypoints(8), waypoint_order: "optimize" });
  const planning = engine();
  equal(await planning.generate(raw), await planning.generate(structuredClone(raw)), "complete result determinism");
}

function seedScenario() {
  const raw = request({ waypoints: waypoints(8), waypoint_order: "optimize" });
  const a = localWaypointOrderProposals(raw);
  const b = localWaypointOrderProposals({ ...raw, seed: 39 });
  assert(JSON.stringify(a) !== JSON.stringify(b), "seed changes bounded exploration");
  equal(a[0], b[0], "seed cannot move the fixed control");
}

async function rankingScenario() {
  const raw = request({ waypoints: waypoints(8), waypoint_order: "optimize", candidate_count: 5 });
  let count = 0;
  const result = await engine((input) => routed(input, { distance_m: 13_000 - count++ * 100 })).generate(raw);
  equal(result.candidates.length, 5, "bounded portfolio size");
  equal(result.candidates[0].target_error_m, 0, "target distance is primary");
  equal(result.recommended_candidate_id, result.candidates[0].candidate_id, "rank owns recommendation");
  equal(result.candidates.map((candidate) => candidate.rank), [1, 2, 3, 4, 5], "stable ranks");
  assert(result.candidates.every((candidate) => candidate.exact_edge_repetition === null && candidate.path_attributes === null && candidate.nature_score === null && candidate.poi_quality === null), "no fabricated scores or facts");
}

async function budgetScenario() {
  const raw = request({ waypoints: waypoints(8), waypoint_order: "optimize" });
  let active = 0;
  let maximum = 0;
  let count = 0;
  const planning = createLocalWaypointRouteEngine({ routeCallBudget: 2, route: async (input) => {
    count += 1;
    maximum = Math.max(maximum, ++active);
    await Promise.resolve();
    active -= 1;
    return routed(input);
  } });
  const result = await planning.generate(raw);
  equal([count, maximum, result.route_call_count, result.route_call_budget], [2, 1, 2, 2], "one authoritative sequential budget");
  assert(result.budget_exhausted && result.unattempted_order_count > 0, "exhaustion explicit");
  equal(LOCAL_WAYPOINT_ROUTE_CALL_BUDGET, 16, "smaller than PR35 24-call cap");
  throws(() => createLocalWaypointRouteEngine({ route: routed, routeCallBudget: 17 }), RangeError);
}

async function failuresScenario() {
  let count = 0;
  const result = await engine((input) => {
    count += 1;
    if (count === 1) throw new Error("native call rejected");
    if (count === 2) return failure("no_route");
    return routed(input);
  }).generate(request({ waypoints: waypoints(8), waypoint_order: "optimize" }));
  equal(result.route_call_count, count, "throws consume a call");
  equal(result.rejected_attempt_counts.local_route_exception, 1, "exception counted");
  equal(result.rejected_attempt_counts.no_route, 1, "failure counted");
  assert(result.candidates.length > 0, "other orders may succeed without weakening points");
}

async function singleFlightScenario() {
  const pending = deferred();
  let calls = 0;
  let firstInput;
  const planning = engine((input) => {
    calls += 1;
    firstInput ??= input;
    return calls === 1 ? pending.promise : routed(input);
  });
  const raw = request({ waypoint_order: "optimize" });
  const first = planning.generate(raw);
  assert(first === planning.generate(raw), "duplicate starts share one promise");
  rejectsCall(() => planning.generate({ ...raw, seed: 999 }), "local_generation_busy");
  planning.invalidate();
  rejectsCall(() => planning.generate(raw), "local_generation_busy");
  equal(calls, 1, "invalidation does not launch another native operation");
  pending.resolve(routed(firstInput));
  equal(await first, null, "stale result discarded");
  equal(calls, 1, "no later proposal after invalidation");
  assert((await planning.generate(raw)).candidates.length > 0, "restart after native drain");
}

async function staleScenario() {
  const pending = deferred();
  const raw = request();
  const rendered = [];
  const busy = [];
  let input;
  const experiment = createLocalWaypointRouteExperiment({
    bridge: { route: (value) => { input = value; return pending.promise; } },
    getRequest: () => raw, elements: uiElements(),
    renderCandidates: (candidates) => rendered.push(candidates), onBusy: (value) => busy.push(value),
  });
  const first = experiment.requestFromPlanner();
  assert(first === experiment.requestFromPlanner(), "UI duplicate single flight");
  experiment.invalidate();
  equal(busy, [true], "busy ownership retained until native settles");
  pending.resolve(routed(input));
  equal(await first, null, "invalidated UI result ignored");
  equal(rendered, [], "stale candidate cannot render");
  equal(busy, [true, false], "busy released exactly after settling");
}

async function changedIntentScenario() {
  let raw = request({ waypoint_order: "optimize", waypoints: waypoints(8) });
  let count = 0;
  const rendered = [];
  const experiment = createLocalWaypointRouteExperiment({
    bridge: { route: async (input) => { count += 1; raw = { ...raw, seed: 777 }; return routed(input); } },
    getRequest: () => raw, elements: uiElements(), renderCandidates: (value) => rendered.push(value),
  });
  equal(await experiment.requestFromPlanner(), null, "snapshot ownership detects edits even without UI invalidation");
  equal([count, rendered.length], [1, 0], "no native follow-on or stale render");
}

async function invalidReplyScenario() {
  for (const mutate of [
    () => null,
    (reply) => ({ ...reply, distance_m: Infinity }),
    (reply) => ({ ...reply, duration_s: -1 }),
    (reply) => ({ ...reply, pack_id: "" }),
    (reply) => ({ ...reply, profile: "walking" }),
    (reply) => ({ ...reply, geometry: [[2, 91], ...reply.geometry.slice(1)] }),
    (reply) => ({ ...reply, geometry: Array.from({ length: 20_001 }, () => [2, 48]) }),
    (reply) => ({ ...reply, geometry: [reply.geometry[0], [NaN, 48]] }),
    (reply) => ({ ...reply, extra_field: true }),
    (reply) => ({ ...reply, engine: "graphhopper" }),
  ]) {
    const result = await engine((input) => mutate(routed(input))).generate(request());
    equal(result.candidates, [], "invalid native evidence never published");
    equal(result.route_call_count, 1, "no fallback retry");
    equal(result.code, "invalid_native_reply", "stable invalid-native error");
  }
  const mismatch = await engine((input) => routed(input, { profile: "road_bike" })).generate(request());
  equal(mismatch.code, "profile_identity_mismatch", "valid but wrong public profile rejected");
}

function unsupportedScenario() {
  const raw = request();
  for (const strength of ["approach", "best_effort", null, "unknown"]) {
    rejects({ ...raw, waypoints: [{ ...raw.waypoints[0], constraint_strength: strength }] }, "unsupported_constraint_strength");
  }
  rejects({ ...raw, waypoints: [{ ...raw.waypoints[0], approach_override: raw.start }] }, "unsupported_approach_override");
  rejects({ ...raw, waypoints: [{ ...raw.waypoints[0], maximum_best_effort_distance_m: 500 }] }, "unsupported_best_effort_bound");
  for (const preferences of [
    { ...raw.preferences, nature: "prefer" }, { ...raw.preferences, path_selection: "low_overlap" },
    { ...raw.preferences, loop_geometry: "prefer" },
  ]) rejects({ ...raw, preferences }, "unsupported_preference");
  rejects({ ...raw, kind: "auto_tour" }, "unsupported_plan_kind");
  rejects({ ...raw, distance_objective: { ...raw.distance_objective, maximum_m: 20_000 } }, "unsupported_flexible_maximum");
}

function invalidRequestScenario() {
  const raw = request();
  for (const [patch, code] of [
    [{ extra: true }, "invalid_request_fields"], [{ schema_version: 2 }, "invalid_request_fields"],
    [{ candidate_count: 6 }, "invalid_candidate_count"], [{ seed: 1.5 }, "invalid_seed"],
    [{ seed: Number.MAX_SAFE_INTEGER + 1 }, "invalid_seed"], [{ routing_profile: "walking" }, "unsupported_profile"],
    [{ waypoint_order: "nearest" }, "invalid_waypoint_order"], [{ topology: "open" }, "invalid_topology"],
    [{ end: null }, "invalid_endpoints"], [{ end: raw.start }, "invalid_endpoints"],
    [{ topology: "loop" }, "invalid_endpoints"], [{ topology: "loop", end: null, waypoints: [] }, "loop_requires_waypoint"],
    [{ waypoints: null }, "invalid_waypoints"], [{ start: { lat: NaN, lon: 2 } }, "invalid_coordinate"],
    [{ start: { ...raw.start, extra: true } }, "invalid_coordinate"],
    [{ waypoints: [raw.waypoints[0], raw.waypoints[0]] }, "duplicate_waypoint"],
    [{ waypoints: [{ ...raw.waypoints[0], coordinate: raw.start }] }, "duplicate_waypoint"],
    [{ distance_objective: { ...raw.distance_objective, target_m: 999 } }, "invalid_distance_objective"],
    [{ distance_objective: { ...raw.distance_objective, priority: "strict" } }, "invalid_distance_objective"],
  ]) rejects({ ...raw, ...patch }, code);
}

async function maximumScenario() {
  equal(LOCAL_WAYPOINT_MAX_WAYPOINTS, 14, "exact supported local limit");
  for (const topology of ["loop", "point_to_point"]) {
    const raw = request({ topology, ...(topology === "loop" ? { end: null } : {}), waypoints: waypoints(14) });
    const result = await engine().generate(raw);
    equal(result.candidates[0].requested_points.length, 16, "16 native points including endpoints");
    equal(result.candidates[0].actual_waypoint_order.length, 14, "nothing silently dropped");
    rejects({ ...raw, waypoints: waypoints(15) }, "too_many_waypoints");
    rejects({ ...raw, waypoints: waypoints(30) }, "too_many_waypoints");
  }
}

async function closureScenario() {
  const raw = request({ topology: "loop", end: null });
  for (const gap of [24.9, 25.1]) {
    assert(gap / 2 < 25, "both individual endpoint snaps are within the hard 25 m limit");
    const result = await engine((input) => {
      const reply = routed(input);
      replaceSnap(reply, 0, northOffset(input.points[0], -gap / 2));
      replaceSnap(reply, reply.snapped_points.length - 1, northOffset(input.points[0], gap / 2));
      return reply;
    }).generate(raw);
    if (gap < 25) {
      equal(result.status, "success", "graph-derived closure just below 25 m accepted");
      assert(Math.abs(result.candidates[0].loop_closure_gap_m - gap) < .001, "native closure gap reported, not filled");
    } else {
      equal(result.code, "route_not_closed", "closure alone rejects a gap just above 25 m");
    }
  }
  const open = await engine((input) => {
    const reply = routed(input);
    replaceSnap(reply, reply.snapped_points.length - 1, input.points[0]);
    return reply;
  }).generate(request({ end: { lat: 48.8701, lon: 2.1001 } }));
  equal(open.code, "open_route_was_closed", "point-to-point cannot collapse to a loop");
}

async function endpointsScenario(role) {
  for (const meters of [24.9, 25.1, 1_111]) {
    const raw = role === "loop_return" ? request({ topology: "loop", end: null }) : request();
    const which = role === "start" ? 0 : raw.waypoints.length + 1;
    const result = await engine((input) => {
      const reply = routed(input);
      replaceSnap(reply, which, northOffset(input.points[which], meters));
      return reply;
    }).generate(raw);
    if (meters < 25) {
      equal(result.status, "success", `${role} 24.9 m accepted`);
      const outcome = result.candidates[0].exact_point_outcomes[which];
      equal(outcome.maximum_snap_distance_m, 25, "endpoint threshold explicit");
      assert(Math.abs(outcome.snap_distance_m - meters) < .001, "actual displacement retained");
    } else {
      equal(result.code, "endpoint_not_reached", `${role} ${meters} m rejected`);
      equal(result.rejected_attempts[0].details.maximum_snap_distance_m, 25, "rejection uses strict local endpoint threshold");
    }
  }
}

async function exactScenario() {
  for (const meters of [299.9, 300.1]) {
    const result = await engine((input) => {
      const reply = routed(input);
      replaceSnap(reply, 1, northOffset(input.points[1], meters));
      return reply;
    }).generate(request());
    if (meters < 300) {
      equal(result.status, "success", "existing 300 m exact semantics, not PR35 25 m hard-start policy");
      assert(result.candidates[0].exact_point_outcomes[1].snap_distance_m > 299, "measured displacement truthful");
    } else {
      equal(result.code, "exact_waypoint_not_reached", "exact snap beyond established threshold rejected");
      equal(result.rejected_attempts[0].details.waypoint_id, "waypoint-1", "failure identity retained");
      equal(result.rejected_attempts[0].details.maximum_snap_distance_m, 300, "threshold explicit");
    }
  }
}

async function orderedGeometryScenario() {
  const missing = await engine((input) => {
    const reply = routed(input);
    reply.geometry = reply.geometry.filter((_, index) => index !== 2);
    return reply;
  }).generate(request());
  equal(missing.code, "snapped_waypoint_not_on_ordered_geometry", "native success cannot omit an exact via from geometry");
  const wrongOrder = await engine((input) => {
    const reply = routed(input);
    [reply.geometry[2], reply.geometry[4]] = [reply.geometry[4], reply.geometry[2]];
    return reply;
  }).generate(request());
  equal(wrongOrder.code, "snapped_waypoint_not_on_ordered_geometry", "geometry must reach native snaps in requested order");
  const count = await engine((input) => {
    const reply = routed(input);
    reply.snapped_points.splice(1, 1);
    return reply;
  }).generate(request());
  equal(count.code, "snapped_point_count_mismatch", "count must match exact sequence");
}

async function regionalFailureScenario() {
  for (const code of ["no_covering_routing_pack", "no_compatible_routing_pack", "routing_pack_unavailable", "routing_busy"]) {
    const result = await engine(() => failure(code)).generate(request({ waypoint_order: "optimize", waypoints: waypoints(8) }));
    equal([result.code, result.route_call_count], [code, 1], "regional failure propagated without retry or stitching");
    equal(result.candidates, [], "no fallback geometry");
  }
}

async function profilesScenario() {
  const planning = engine();
  for (const profile of PUBLIC_LOCAL_ROUTE_PROFILES) {
    for (const offset of [0, .24, 0]) {
      const raw = request({ routing_profile: profile });
      raw.start.lon += offset;
      raw.end.lon += offset;
      raw.waypoints.forEach((point) => { point.coordinate.lon += offset; });
      const result = await planning.generate(raw);
      equal(result.profile, profile, "public profile preserved");
      equal(result.pack_id, offset ? "paris-dev-v1" : "marly-dev-v1", "native regional identity propagated across generations");
      assert(result.candidates.every((candidate) => candidate.profile === profile && candidate.pack_id === result.pack_id), "candidate profile and pack consistent");
    }
  }
}

async function packIdentityScenario() {
  let calls = 0;
  const result = await engine((input) => routed(input, { pack_id: ++calls === 1 ? "marly-dev-v1" : "paris-dev-v1" })).generate(request({ waypoint_order: "optimize", waypoints: waypoints(8) }));
  equal(result.rejected_attempt_counts.routing_pack_identity_changed, 1, "one generation cannot mix packs");
  equal(calls, 2, "pack identity change ends search");
  assert(result.candidates.every((candidate) => candidate.pack_id === "marly-dev-v1"), "retained control not overwritten");
}

async function diversityScenario() {
  const raw = request({ topology: "loop", end: null, waypoint_order: "optimize", candidate_count: 5 });
  const result = await engine((input) => {
    const reply = routed(input);
    // A two-interior loop has only two orders; reversed native shapes count once.
    reply.geometry = input.points.map(({ lon, lat }) => [lon, lat]);
    return reply;
  }).generate(raw);
  equal(result.candidates.length, 1, "same loop traced in reverse does not fill another slot");
  equal(result.rejected_attempt_counts.duplicate_geometry, 1, "duplicate counted");
  assert(result.warnings.includes("fewer_candidates_than_requested"), "shortfall truthful");
}

async function distanceScenario() {
  const raw = request();
  for (const priority of ["flexible", "balanced"]) {
    const result = await engine((input) => routed(input, { distance_m: 15_000 })).generate({ ...raw, distance_objective: { ...raw.distance_objective, priority } });
    equal(result.status, "success", "soft tolerance does not reject graph-valid route");
    assert(!result.candidates[0].within_tolerance && result.candidates[0].warnings.includes("target_distance_missed"), "soft miss explicit");
  }
  const strict = await engine((input) => routed(input, { distance_m: 15_000 })).generate({ ...raw, distance_objective: { ...raw.distance_objective, priority: "strict", maximum_m: 20_000 } });
  equal(strict.code, "strict_distance_tolerance_missed", "strict tolerance is hard");
  const maximum = await engine((input) => routed(input, { distance_m: 15_000 })).generate({ ...raw, distance_objective: { ...raw.distance_objective, priority: "balanced", maximum_m: 13_000 } });
  equal(maximum.code, "maximum_distance_exceeded", "explicit balanced maximum is hard");
  const size = await engine((input) => routed(input, { distance_m: 200_001 })).generate(raw);
  equal(size.code, "route_distance_limit_exceeded", "explicit local result ceiling");
}

async function noFallbackScenario() {
  const previous = globalThis.fetch;
  let networkCalls = 0;
  let returned;
  globalThis.fetch = () => { networkCalls += 1; throw new Error("No backend/network routing allowed"); };
  try {
    const result = await engine((input) => { returned = routed(input); return returned; }).generate(request());
    equal(result.candidates[0].geometry, returned.geometry, "every published vertex came from native response");
    assert(result.candidates[0].geometry.length > result.candidates[0].requested_points.length, "native bends retained rather than connecting proposals");
    equal((await engine(() => failure("no_route")).generate(request())).candidates, [], "no geometry from failed request");
    equal(networkCalls, 0, "no fetch attempt");
  } finally { globalThis.fetch = previous; }
}

async function debugGateScenario() {
  const elements = parentElements();
  let calls = 0;
  const disabled = createLocalRoutingExperiment({
    bridge: { capabilities: async () => ({ enabled: false }), route: () => { calls += 1; } },
    getWaypointRequest: () => request(), renderRoute: () => {}, clearRoute: () => {}, elements,
  });
  equal(await disabled.initialize(), false, "release capability unavailable");
  await disabled.requestLocalWaypointRoute();
  equal(calls, 0, "disabled capability cannot start native work");
  assert(elements.container.classList.contains("hidden"), "release panel stays hidden");
  const pending = deferred();
  let rawInput;
  const parent = createLocalRoutingExperiment({
    bridge: {
      capabilities: async () => ({ enabled: true, installed_pack_count: 1, supported_profile_ids: PUBLIC_LOCAL_ROUTE_PROFILES, pack_capabilities: [{ pack_id: "marly-dev-v1", access_modes: ["foot", "bicycle"] }] }),
      route: (input) => { calls += 1; rawInput = input; return pending.promise; },
    },
    getWaypointRequest: () => request(), renderRoute: () => {}, clearRoute: () => {}, elements: parentElements(),
  });
  await parent.initialize();
  const rawOperation = parent.requestSmokeTest();
  await parent.requestLocalWaypointRoute();
  equal(calls, 1, "PR38 cannot overlap another local experiment");
  pending.resolve(routed(rawInput));
  await rawOperation;
}

function request(overrides = {}) {
  return {
    schema_version: 1, kind: "waypoint_route", name: "PR38 test", topology: "point_to_point",
    start: { lat: 48.87, lon: 2.10 }, end: { lat: 48.89, lon: 2.15 },
    routing_profile: "hike", candidate_count: 3, seed: 38,
    distance_objective: { target_m: 12_000, tolerance_m: 500, maximum_m: null, priority: "flexible" },
    preferences: { nature: "off", path_selection: "shortest", loop_geometry: "off" },
    waypoints: waypoints(2), waypoint_order: "fixed", ...overrides,
  };
}

function plannerControls(raw) {
  const values = {
    profile: raw.routing_profile, "route-name": raw.name,
    "target-distance": raw.distance_objective.target_m / 1_000,
    tolerance: raw.distance_objective.tolerance_m / 1_000,
    "maximum-distance": raw.distance_objective.maximum_m == null ? "" : raw.distance_objective.maximum_m / 1_000,
    "distance-priority": raw.distance_objective.priority,
    "candidate-count": raw.candidate_count, seed: raw.seed,
    "point-order-mode": raw.waypoint_order, "path-selection-mode": raw.preferences.path_selection,
    "nature-preference": raw.preferences.nature, "loop-geometry-preference": raw.preferences.loop_geometry,
    "free-poi-spur": 200, "route-topology": raw.topology,
  };
  return new Map(Object.entries(values).map(([id, value]) => {
    const element = document.createElement("input");
    element.id = id;
    element.value = String(value);
    return [id, element];
  }));
}

function controlsSnapshot(controls) {
  return [...controls].map(([id, control]) => [id, control.value, control.checked, control.disabled, control.outerHTML]);
}

function northOffset(point, meters) {
  return { ...point, lat: point.lat + meters / 6_371_008.8 * 180 / Math.PI };
}

function localProfileOptionsScenario() {
  const select = document.createElement("select");
  equal(addLocalWaypointProfileOptions(select, { enabled: false }), [], "release does not add local options");
  equal(select.options.length, 0, "release remains unchanged");
  const available = document.createElement("option");
  available.value = "hike";
  available.textContent = "Server Hike";
  select.append(available);
  const catalog = { profiles: [{ profile: { id: "hike" }, available: true }, { profile: { id: "road_bike" }, available: false }] };
  const before = JSON.stringify(catalog);
  const capabilities = { enabled: true, supported_profile_ids: PUBLIC_LOCAL_ROUTE_PROFILES };
  addLocalWaypointProfileOptions(select, capabilities);
  addLocalWaypointProfileOptions(select, capabilities);
  equal(select.options.length, 6, "one ordinary control, all native profiles, no duplicates");
  equal(available.textContent, "Server Hike", "available server label unchanged");
  const bicycle = [...select.options].find((option) => option.value === "road_bike");
  assert(!bicycle.disabled && bicycle.dataset.localWaypointOnly === "true", "explicit local-only option can be selected");
  equal(JSON.stringify(catalog), before, "server profile availability never rewritten");
}

function waypoints(count) {
  return Array.from({ length: count }, (_, index) => ({
    id: `waypoint-${index + 1}`, name: `Exact ${index + 1}`,
    coordinate: { lat: 48.872 + index * .001, lon: 2.105 + ((index * 5 + 1) % count) * .002 },
    constraint_strength: "exact", access_search_radius_m: 500,
    maximum_best_effort_distance_m: null, approach_override: null,
  }));
}

function rawPoints(raw) {
  return [raw.start, ...raw.waypoints.map((point) => point.coordinate), raw.end ?? raw.start].map(({ lat, lon }) => ({ lat, lon }));
}

function routed(input, overrides = {}) {
  const points = input.points.map(({ lat, lon }) => ({ lat, lon }));
  const geometry = [[points[0].lon, points[0].lat]];
  for (let index = 1; index < points.length; index += 1) {
    geometry.push([(points[index - 1].lon + points[index].lon) / 2 + .00003, (points[index - 1].lat + points[index].lat) / 2]);
    geometry.push([points[index].lon, points[index].lat]);
  }
  return {
    schema_version: 1, request_id: "pr38-native-fixture", type: "local_route_result",
    profile: input.profile, engine: "valhalla-mobile", engine_version: "0.5.1/valhalla-3.6.3",
    pack_id: points[0].lon > 2.25 ? "paris-dev-v1" : "marly-dev-v1",
    distance_m: 12_000, duration_s: 3_000, geometry, snapped_points: points,
    measurements: { cold_start: false, engine_initialization_ms: 0, route_ms: 1,
      memory_before_initialization_bytes: 0, memory_after_initialization_bytes: 0, memory_after_route_bytes: 0 },
    ...overrides,
  };
}

function replaceSnap(reply, position, coordinate) {
  const snap = { lat: coordinate.lat, lon: coordinate.lon };
  reply.snapped_points[position] = snap;
  reply.geometry[position * 2] = [snap.lon, snap.lat];
}

function failure(code) { return { schema_version: 1, request_id: "pr38-failure", type: "local_route_failure", code }; }
function engine(route = routed) { return createLocalWaypointRouteEngine({ route }); }
function uiElements() { return { button: document.createElement("button"), status: document.createElement("p"), results: document.createElement("ol") }; }
function parentElements() {
  const elements = { container: document.createElement("section"), status: document.createElement("p"), profileSelect: document.createElement("select"), waypointRoute: uiElements() };
  elements.container.classList.add("hidden");
  for (const profile of PUBLIC_LOCAL_ROUTE_PROFILES) {
    const option = document.createElement("option");
    option.value = profile;
    elements.profileSelect.append(option);
  }
  elements.profileSelect.value = "hike";
  for (const name of ["button", "smokeButton", "parisSmokeButton", "viaSmokeButton", "crossPackButton"]) elements[name] = document.createElement("button");
  return elements;
}
function deferred() { let resolve; const promise = new Promise((yes) => { resolve = yes; }); return { promise, resolve }; }
function rejects(value, code) {
  const before = JSON.stringify(value);
  rejectsCall(() => validateLocalWaypointRouteRequest(value), code);
  equal(JSON.stringify(value), before, "rejection must not weaken or mutate intent");
}
function rejectsCall(action, code) {
  try { action(); } catch (error) {
    assert(error instanceof LocalWaypointRouteValidationError && error.code === code, `expected ${code}, got ${error}`);
    return;
  }
  throw new Error(`Expected ${code}`);
}
function throws(action, kind) { try { action(); } catch (error) { assert(error instanceof kind, "error class"); return; } throw new Error("Expected exception"); }
function equal(actual, expected, message) { assert(JSON.stringify(actual) === JSON.stringify(expected), `${message}: ${JSON.stringify(actual)} !== ${JSON.stringify(expected)}`); }
function assert(value, message) { if (!value) throw new Error(message); }
