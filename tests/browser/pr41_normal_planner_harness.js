import { createLocalPlanner, validateLocalAutoTourPlanRequest } from "../../src/sugarglider/web/static/local_planner.js";
import { PUBLIC_PROFILE_METADATA } from "../../src/sugarglider/web/static/public_profile_metadata.js";

export const publishedPlans = [];
const profiles = Object.keys(PUBLIC_PROFILE_METADATA);
const capabilities = { enabled: true, installed_pack_count: 1, supported_profile_ids: profiles };
function assert(condition, message) { if (!condition) throw new Error(message); }
function same(left, right, message) { assert(JSON.stringify(left) === JSON.stringify(right), message); }
async function rejected(operation, code) {
  const error = await operation.then(() => null, (value) => value);
  const actual = typeof error?.code === "string" ? error.code : error?.name;
  assert(actual === code, `Expected ${code}, got ${actual}`);
}
export function nativeReply(input) {
  return { schema_version: 1, request_id: "synthetic-request", type: "local_route_result", profile: input.profile,
    engine: "valhalla-mobile", engine_version: "synthetic-test", pack_id: "synthetic-region", distance_m: 4000,
    duration_s: 1200, geometry: input.points.map(({ lon, lat }) => [lon, lat]),
    snapped_points: input.points.map(({ lon, lat }) => ({ lon, lat })), measurements: {
      cold_start: false, engine_initialization_ms: 0, route_ms: 0,
      memory_before_initialization_bytes: 0, memory_after_initialization_bytes: 0, memory_after_route_bytes: 0 } };
}
export function request(kind, profile = "hike") {
  const common = { schema_version: 1, kind, name: "Normal local planner", topology: "loop", start: { lat: 48, lon: 2, name: "Start" },
    end: null, routing_profile: profile, candidate_count: 2, seed: 35,
    distance_objective: { target_m: 4000, tolerance_m: 500, maximum_m: null, priority: "balanced" } };
  return kind === "auto_tour" ? { ...common,
    preferences: { nature: "prefer", path_selection: "low_overlap", loop_geometry: "prefer", scenic: "prefer", drinking_water: "prefer", direction: "any" },
    hard_waypoints: [], requested_stops: [], preferred_discovered_poi_ids: [], free_poi_spur_physical_m: 200 }
    : { ...common, topology: "point_to_point", end: { lat: 48.02, lon: 2.03, name: "End" },
      preferences: { nature: "off", path_selection: "shortest", loop_geometry: "off" }, waypoint_order: "fixed",
      waypoints: [{ id: "point-1", name: "Named exact place", coordinate: { lat: 48.01, lon: 2.01, name: "Named exact place" },
        constraint_strength: "exact", access_search_radius_m: 500, maximum_best_effort_distance_m: null, approach_override: null }] };
}

export async function runPr41NormalPlannerHarness() {
  const scenarios = [];
  for (const kind of ["waypoint_route", "auto_tour"]) for (const profile of profiles) {
    const calls = [], source = request(kind, profile), before = JSON.stringify(source);
    const planner = createLocalPlanner({ lifecycleTarget: null, bridge: { capabilities: async () => capabilities,
      route: async (input) => { calls.push(input); return nativeReply(input); } } });
    const result = await planner.generate(source);
    assert(result.candidates.length > 0, `${kind}/${profile} canonical candidates`);
    assert(result.search_diagnostics.cache.backend_call_count === calls.length, "authoritative calls through gateway");
    assert(calls.every((call) => call.profile === profile), "profile explicit on every native call");
    assert(JSON.stringify(source) === before && Object.isFrozen(result.candidates[0]), "source unchanged and canonical result immutable");
    if (kind === "auto_tour") {
      assert(result.candidates[0].compromises.some((item) => item.code === "optional_preference_unmet"), "unsupported optional analysis remains explicit");
      assert(result.candidates[0].reached_stops.length === 0, "missing index cannot invent stops");
    }
    publishedPlans.push({ request: source, result });
    planner.invalidate(); scenarios.push(`normal_${kind}_${profile}`);
  }
  for (const [value, code] of [[null, "local_routing_unavailable"], [{ ...capabilities, enabled: false }, "local_routing_unavailable"],
    [{ ...capabilities, installed_pack_count: 0 }, "routing_pack_unavailable"], [{ ...capabilities, supported_profile_ids: [] }, "unsupported_profile"]]) {
    let calls = 0;
    const planner = createLocalPlanner({ lifecycleTarget: null, bridge: { capabilities: async () => value, route: () => { calls += 1; } } });
    await rejected(planner.generate(request("waypoint_route")), code);assert(calls === 0, "unavailable capability cannot route");planner.invalidate();
  }
  scenarios.push("capability_missing_region_and_profile_failures_before_routing");
  const failed = createLocalPlanner({ lifecycleTarget: null, bridge: { capabilities: async () => capabilities,
    route: async () => ({ schema_version: 1, request_id: "synthetic-request", type: "local_route_failure", code: "no_covering_routing_pack" }) } });
  const outside = await failed.generate(request("waypoint_route"));
  assert(!outside.candidates.length && outside.search_diagnostics.details.local_planning.failure_code === "no_covering_routing_pack", "outside coverage is explicit canonical failure");
  assert(outside.search_diagnostics.cache.backend_call_count === 1, "no hidden retry or other backend");failed.invalidate();
  scenarios.push("outside_region_no_backend_fallback");
  const displaced = createLocalPlanner({ lifecycleTarget: null, bridge: { capabilities: async () => capabilities,
    route: async (input) => { const reply = nativeReply(input);reply.snapped_points[0].lat += .001;
      reply.geometry[0][1] = reply.snapped_points[0].lat;return reply; } } });
  const displacedResult = await displaced.generate(request("waypoint_route"));
  const failedSnap = displacedResult.search_diagnostics.details.local_planning.rejected_attempts[0];
  assert(!displacedResult.candidates.length && failedSnap.code === "endpoint_not_reached", "strict endpoint rejection preserved");
  assert(failedSnap.details.snap_distance_m > 100 && failedSnap.details.maximum_snap_distance_m === 25
    && failedSnap.details.position === 0, "actual failed endpoint distance and threshold remain public");
  assert(displacedResult.search_diagnostics.cache.backend_call_count === 1, "no weakened retry after exact failure");
  displaced.invalidate();scenarios.push("failed_exact_endpoint_keeps_measured_snap_evidence");
  const orderedRequest = request("waypoint_route");
  orderedRequest.topology = "loop";orderedRequest.end = null;orderedRequest.waypoint_order = "optimize";
  orderedRequest.waypoints.push({ ...structuredClone(orderedRequest.waypoints[0]), id: "point-2", name: "Second named place",
    coordinate: { lat: 48.01, lon: 1.99, name: "Second named place" } });
  orderedRequest.waypoints.push({ ...structuredClone(orderedRequest.waypoints[0]), id: "point-3", name: "Third named place",
    coordinate: { lat: 47.99, lon: 2.015, name: "Third named place" } });
  const orderedPlanner = createLocalPlanner({ lifecycleTarget: null,
    bridge: { capabilities: async () => capabilities, route: async (input) => nativeReply(input) } });
  const orderedResult = await orderedPlanner.generate(orderedRequest);
  assert(orderedResult.candidates.length === 2, "two distinct bounded visit sequences retained");
  for (const candidate of orderedResult.candidates) {
    const visits = candidate.diagnostics.details.required_waypoint_order;
    same([...visits.map((visit) => visit.original_index)].sort(), [0, 1, 2], "required original indices retained once");
    for (const visit of visits) same(visit.coordinate, { ...orderedRequest.waypoints[visit.original_index].coordinate,
      name: orderedRequest.waypoints[visit.original_index].name }, "name stays attached to original coordinate");
    same(visits.map((visit) => orderedRequest.waypoints[visit.original_index].id),
      candidate.diagnostics.details.local_routing.waypoint_order, "marker ordering follows native visit sequence");
  }
  publishedPlans.push({ request: orderedRequest, result: orderedResult });
  orderedPlanner.invalidate();scenarios.push("optimized_required_marker_order_names_and_indices");
  for (const [mutate, code] of [
    [(value) => { value.hard_waypoints = [{ id: "keep", name: "Keep", coordinate: value.start }]; }, "unsupported_local_auto_tour_hard_points"],
    [(value) => { value.requested_stops = [{ id: "keep" }]; }, "unsupported_local_auto_tour_requested_stops"],
    [(value) => { value.topology = "point_to_point"; value.end = { lat: 49, lon: 2, name: "End" }; }, "unsupported_local_auto_tour_topology"],
    [(value) => { value.free_poi_spur_physical_m = 100; }, "unsupported_local_excursion_allowance"],
    [(value) => { value.distance_objective = { ...value.distance_objective, priority: "strict", maximum_m: null }; }, "invalid_local_plan_request"],
  ]) {
    const source = request("auto_tour");mutate(source);const before = JSON.stringify(source);
    let error;try { validateLocalAutoTourPlanRequest(source); } catch (caught) { error = caught; }
    assert(error?.code === code && JSON.stringify(source) === before, "unsupported intent is retained and explicit");
  }
  scenarios.push("unsupported_intent_and_strict_maximum_never_silently_rewritten");
  let finish, calls = 0;
  const active = createLocalPlanner({ lifecycleTarget: null, bridge: { capabilities: async () => capabilities,
    route: (input) => { calls += 1; return new Promise((resolve) => { finish = () => resolve(nativeReply(input)); }); } } });
  const source = request("waypoint_route"), controller = new AbortController();
  const first = active.generate(source, controller.signal);
  assert(active.generate(source) === first, "identical operation coalesces");
  while (!finish) await Promise.resolve();
  const outcome = rejected(first, "AbortError");controller.abort();
  await rejected(active.generate(request("auto_tour")), "local_generation_busy");
  assert(calls === 1, "cancelled native work must drain before another mode starts");finish();await outcome;
  const next = active.generate(source);while (calls < 2) await Promise.resolve();finish();await next;
  active.invalidate();scenarios.push("cross_mode_single_flight_cancellation_and_native_drain");
  const input = request("waypoint_route");
  let callsAfterAbort = 0;
  const cancelled = createLocalPlanner({ lifecycleTarget: null, bridge: { capabilities: async () => { callsAfterAbort += 1;return capabilities; }, route: nativeReply } });
  await rejected(cancelled.generate(input, AbortSignal.abort()), "AbortError");assert(callsAfterAbort === 0, "pre-abort does not inspect or route");
  cancelled.invalidate();scenarios.push("preaborted_request_performs_no_native_work");
  return scenarios;
}
