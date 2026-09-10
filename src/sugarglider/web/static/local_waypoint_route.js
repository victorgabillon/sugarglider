import {
  MAX_ROUTE_POINTS,
  PUBLIC_LOCAL_ROUTE_PROFILES,
  parseLocalRoutingReply,
} from "./local_routing.js";
import { readPlannerOptionsFromControls, waypointPlanRequestSnapshot } from "./state.js";

// Endpoints/closure follow PR35 LOCAL semantics; interiors follow canonical Python.
export const LOCAL_WAYPOINT_HARD_ENDPOINT_SNAP_TOLERANCE_M = 25;
export const LOCAL_WAYPOINT_ROUTE_CLOSURE_TOLERANCE_M = 25;
export const LOCAL_WAYPOINT_EXACT_INTERIOR_FIDELITY_M = 300;
export const LOCAL_WAYPOINT_MAX_DISTANCE_M = 200_000;
export const LOCAL_WAYPOINT_ROUTE_CALL_BUDGET = 16;
export const LOCAL_WAYPOINT_MAX_WAYPOINTS = 14;
const MAX_ORDER_PROPOSALS = 16;
const EARTH_RADIUS_M = 6_371_008.8;
const REQUEST_FIELDS = new Set([
  "schema_version", "kind", "name", "topology", "start", "end", "routing_profile",
  "candidate_count", "seed", "distance_objective", "preferences", "waypoints", "waypoint_order",
]);
const WAYPOINT_FIELDS = new Set([
  "id", "name", "coordinate", "constraint_strength", "access_search_radius_m",
  "maximum_best_effort_distance_m", "approach_override",
]);
const WARNINGS = Object.freeze([
  "experimental_valhalla_profiles_not_graphhopper_equivalent",
  "exact_edge_repetition_unavailable", "path_attributes_and_access_unavailable",
  "nature_and_poi_analysis_unavailable", "alternative_route_parity_unavailable",
  "shortest_selection_does_not_guarantee_globally_shortest_graph_path",
  "geometry_distinctness_is_not_corridor_diversity",
]);
const TERMINAL_FAILURES = new Set([
  "invalid_request", "unsupported_profile", "routing_pack_unavailable",
  "no_covering_routing_pack", "no_compatible_routing_pack", "routing_busy",
]);

export class LocalWaypointRouteValidationError extends Error {
  constructor(code, details = {}) {
    super(code);
    this.name = "LocalWaypointRouteValidationError";
    this.code = code;
    this.details = deepFreeze(details);
  }
}

export function validateLocalWaypointRouteRequest(value) {
  if (value?.kind !== "waypoint_route") fail("unsupported_plan_kind");
  if (!fieldsAllowed(value, REQUEST_FIELDS) || value.schema_version !== 1) fail("invalid_request_fields");
  if (!textWithin(value.name, 200)) fail("invalid_request_name");
  if (!["loop", "point_to_point"].includes(value.topology)) fail("invalid_topology");
  const start = coordinate(value.start);
  const end = value.end == null ? null : coordinate(value.end);
  if (value.topology === "loop" ? end !== null : end === null || sameCoordinate(start, end)) {
    fail("invalid_endpoints");
  }
  if (!PUBLIC_LOCAL_ROUTE_PROFILES.includes(value.routing_profile)) fail("unsupported_profile");
  if (!Number.isSafeInteger(value.seed)) fail("invalid_seed");
  if (!Number.isSafeInteger(value.candidate_count) || !within(value.candidate_count, 1, 5)) {
    fail("invalid_candidate_count");
  }
  if (!["fixed", "optimize"].includes(value.waypoint_order)) fail("invalid_waypoint_order");
  const objective = value.distance_objective;
  if (!fieldsAllowed(objective, new Set(["target_m", "tolerance_m", "maximum_m", "priority"]))
      || !within(objective.target_m, 1_000, LOCAL_WAYPOINT_MAX_DISTANCE_M)
      || !within(objective.tolerance_m, 100, 10_000)
      || !["flexible", "balanced", "strict"].includes(objective.priority)
      || !(objective.maximum_m === null || (
        within(objective.maximum_m, objective.target_m, LOCAL_WAYPOINT_MAX_DISTANCE_M)
      ))
      || (objective.priority === "strict" && (
        objective.maximum_m === null || objective.maximum_m < objective.target_m + objective.tolerance_m
      ))) fail("invalid_distance_objective");
  // Flexible maxima have no unambiguous local contract in this first subset.
  if (objective.priority === "flexible" && objective.maximum_m !== null) {
    fail("unsupported_flexible_maximum");
  }
  const preferences = value.preferences;
  if (!fieldsAllowed(preferences, new Set(["nature", "path_selection", "loop_geometry"]))) {
    fail("invalid_preferences");
  }
  if (preferences.nature !== "off" || preferences.path_selection !== "shortest"
      || preferences.loop_geometry !== "off") {
    fail("unsupported_preference", { supported: { nature: "off", path_selection: "shortest", loop_geometry: "off" } });
  }
  const rawWaypoints = value.waypoints === undefined ? [] : value.waypoints;
  if (!Array.isArray(rawWaypoints)) fail("invalid_waypoints");
  if (rawWaypoints.length + 2 > MAX_ROUTE_POINTS) {
    fail("too_many_waypoints", { maximum: LOCAL_WAYPOINT_MAX_WAYPOINTS });
  }
  if (value.topology === "loop" && rawWaypoints.length === 0) fail("loop_requires_waypoint");
  const identities = new Set();
  const coordinates = new Set([coordinateKey(start), ...(end ? [coordinateKey(end)] : [])]);
  const waypoints = rawWaypoints.map((point, index) => {
    if (!fieldsAllowed(point, WAYPOINT_FIELDS) || !textWithin(point.id, 240) || !textWithin(point.name, 200)) {
      fail("invalid_waypoint", { original_index: index + 1 });
    }
    if ((point.constraint_strength === undefined ? "exact" : point.constraint_strength) !== "exact") {
      fail("unsupported_constraint_strength", { waypoint_id: point.id, strength: point.constraint_strength });
    }
    if (point.approach_override != null) fail("unsupported_approach_override", { waypoint_id: point.id });
    if (point.maximum_best_effort_distance_m != null) fail("unsupported_best_effort_bound", { waypoint_id: point.id });
    const accessRadius = point.access_search_radius_m === undefined ? 500 : point.access_search_radius_m;
    if (!within(accessRadius, 25, 2_000)) fail("invalid_access_search_radius");
    const position = coordinate(point.coordinate);
    if (identities.has(point.id) || coordinates.has(coordinateKey(position))) fail("duplicate_waypoint");
    identities.add(point.id);
    coordinates.add(coordinateKey(position));
    return {
      id: point.id, name: point.name, coordinate: position, constraint_strength: "exact",
      access_search_radius_m: accessRadius,
      maximum_best_effort_distance_m: null, approach_override: null,
    };
  });
  return deepFreeze({
    schema_version: 1, kind: "waypoint_route", name: value.name,
    topology: value.topology, start, end, routing_profile: value.routing_profile,
    candidate_count: value.candidate_count, seed: value.seed,
    distance_objective: {
      target_m: objective.target_m, tolerance_m: objective.tolerance_m,
      maximum_m: objective.maximum_m, priority: objective.priority,
    },
    preferences: { nature: "off", path_selection: "shortest", loop_geometry: "off" },
    waypoints, waypoint_order: value.waypoint_order,
  });
}

export function localWaypointOrderProposals(rawRequest) {
  const request = validateLocalWaypointRouteRequest(rawRequest);
  const original = request.waypoints.map((_, index) => index);
  const proposals = [];
  const seen = new Set();
  function add(order, construction) {
    const key = order.join(",");
    if (seen.has(key) || proposals.length >= MAX_ORDER_PROPOSALS) return;
    if (order.length !== original.length || new Set(order).size !== original.length
        || order.some((index) => !original.includes(index))) fail("invalid_order_proposal");
    seen.add(key);
    proposals.push({ proposal_id: `${construction}:${key || "direct"}`, construction, order });
  }
  add(original, "fixed_control");
  if (request.waypoint_order === "fixed" || original.length < 2) return deepFreeze(proposals);
  const nearest = [];
  const remaining = [...original];
  let current = request.start;
  while (remaining.length) {
    remaining.sort((a, b) => haversine(current, request.waypoints[a].coordinate)
      - haversine(current, request.waypoints[b].coordinate) || a - b);
    const next = remaining.shift();
    nearest.push(next);
    current = request.waypoints[next].coordinate;
  }
  add(nearest, "nearest_neighbor");
  add([...nearest].reverse(), "reverse_nearest");
  add([...original].reverse(), "reverse_control");
  // At most 91 segment reversals for 14 interiors: polynomial proposals only.
  const reversals = [];
  for (let left = 0; left < nearest.length - 1; left += 1) {
    for (let right = left + 1; right < nearest.length; right += 1) {
      const order = [...nearest.slice(0, left), ...nearest.slice(left, right + 1).reverse(), ...nearest.slice(right + 1)];
      reversals.push({ order, length: proposalLength(request, order) });
    }
  }
  reversals.sort((a, b) => a.length - b.length || compareText(a.order.join(","), b.order.join(",")));
  if (reversals.length) add(reversals[0].order, "best_geometric_reversal");
  for (const proposal of seedShuffle(reversals, request.seed)) add(proposal.order, "seeded_reversal");
  return deepFreeze(proposals);
}

export function createLocalWaypointRouteEngine({
  route,
  routeCallBudget = LOCAL_WAYPOINT_ROUTE_CALL_BUDGET,
  isCurrent = () => true,
} = {}) {
  if (typeof route !== "function") throw new TypeError("route function is required");
  if (!Number.isSafeInteger(routeCallBudget) || !within(routeCallBudget, 1, LOCAL_WAYPOINT_ROUTE_CALL_BUDGET)) {
    throw new RangeError("local Waypoint Route budget must be within 1..16");
  }
  let generation = 0;
  let active = null;

  function generate(rawRequest) {
    const request = validateLocalWaypointRouteRequest(rawRequest);
    const identity = JSON.stringify(request);
    if (active !== null) {
      if (active.generation === generation && active.identity === identity) return active.promise;
      fail("local_generation_busy");
    }
    const ownedGeneration = ++generation;
    const promise = search(request, ownedGeneration).finally(() => {
      if (active?.generation === ownedGeneration) active = null;
    });
    active = { generation: ownedGeneration, identity, promise };
    return promise;
  }

  function invalidate() {
    generation += 1;
    // Retain the active promise until its native call drains; no overlapping restart.
  }

  function owns(request, ownedGeneration) {
    try { return generation === ownedGeneration && isCurrent(request); } catch { return false; }
  }

  async function search(request, ownedGeneration) {
    const proposals = localWaypointOrderProposals(request);
    const candidates = [];
    const rejected = new Map();
    const rejectedAttempts = [];
    let routeCalls = 0;
    let selectedPack = null;
    let terminalCode = null;
    const requestId = `local-waypoint-${hashText(JSON.stringify(request))}`;
    const reject = (code, proposalId, details = {}) => {
      rejected.set(code, (rejected.get(code) ?? 0) + 1);
      rejectedAttempts.push({ code, proposal_id: proposalId, details });
    };
    for (const proposal of proposals) {
      if (!owns(request, ownedGeneration)) return null;
      if (routeCalls >= routeCallBudget) break;
      const points = routingPoints(request, proposal.order);
      let rawReply;
      routeCalls += 1;
      try {
        rawReply = await route({ points: points.map(({ lat, lon }) => ({ lat, lon })), profile: request.routing_profile });
      } catch {
        if (!owns(request, ownedGeneration)) return null;
        reject("local_route_exception", proposal.proposal_id);
        continue;
      }
      if (!owns(request, ownedGeneration)) return null;
      let reply = null;
      try { reply = parseLocalRoutingReply(JSON.stringify(rawReply)); } catch { /* invalid native value */ }
      if (reply?.type === "local_route_failure") {
        reject(reply.code, proposal.proposal_id);
        if (TERMINAL_FAILURES.has(reply.code)) { terminalCode = reply.code; break; }
        continue;
      }
      try {
        if (selectedPack === null && reply?.type === "local_route_result" && reply.profile === request.routing_profile) {
          selectedPack = reply.pack_id;
        }
        const validation = validateRoute(reply, request, proposal, points, selectedPack);
        selectedPack = reply.pack_id;
        const error = Math.abs(reply.distance_m - request.distance_objective.target_m);
        const content = JSON.stringify([
          requestId, proposal.order, reply.pack_id, reply.engine, reply.engine_version,
          reply.distance_m, reply.duration_s, reply.geometry, reply.snapped_points,
        ]);
        candidates.push({
          candidate_id: `${requestId}-${proposal.order.join("-") || "direct"}-${hashText(content)}`,
          request_id: requestId, topology: request.topology, profile: request.routing_profile,
          seed: request.seed, pack_id: reply.pack_id, engine: reply.engine, engine_version: reply.engine_version,
          geometry: reply.geometry, distance_m: reply.distance_m, duration_s: reply.duration_s,
          requested_points: points, snapped_points: reply.snapped_points,
          requested_waypoint_order: request.waypoints.map((point) => point.id),
          actual_waypoint_order: proposal.order.map((index) => request.waypoints[index].id),
          original_waypoint_indices: proposal.order.map((index) => index + 1),
          exact_point_outcomes: validation.outcomes, loop_closure_gap_m: validation.closureGap,
          target_error_m: error, within_tolerance: error <= request.distance_objective.tolerance_m,
          construction: proposal, exact_edge_repetition: null, path_attributes: null,
          nature_score: null, poi_quality: null,
          warnings: error > request.distance_objective.tolerance_m ? [...WARNINGS, "target_distance_missed"] : WARNINGS,
        });
      } catch (error) {
        if (!(error instanceof LocalWaypointRouteValidationError)) throw error;
        reject(error.code, proposal.proposal_id, error.details);
        if (error.code === "routing_pack_identity_changed") { terminalCode = error.code; break; }
      }
    }
    if (!owns(request, ownedGeneration)) return null;
    candidates.sort((a, b) => Number(b.within_tolerance) - Number(a.within_tolerance)
      || a.target_error_m - b.target_error_m || a.distance_m - b.distance_m
      || compareText(a.candidate_id, b.candidate_id));
    const seen = new Set();
    const unique = candidates.filter((candidate) => {
      const key = geometryKey(candidate.geometry, request.topology);
      if (seen.has(key)) { reject("duplicate_geometry", candidate.construction.proposal_id); return false; }
      seen.add(key);
      return true;
    });
    const ranked = unique.slice(0, request.candidate_count).map((candidate, index) => ({ ...candidate, rank: index + 1 }));
    const rejections = Object.fromEntries([...rejected].sort(([a], [b]) => compareText(a, b)));
    return deepFreeze({
      schema_version: 1, type: "local_waypoint_route_result",
      status: ranked.length ? "success" : "no_candidates",
      code: ranked.length ? null : terminalCode ?? Object.keys(rejections)[0] ?? "no_valid_local_candidate",
      request_id: requestId, request, topology: request.topology, profile: request.routing_profile,
      seed: request.seed, distance_objective: request.distance_objective,
      requested_waypoint_order: request.waypoints.map((point) => point.id),
      requested_candidate_count: request.candidate_count, candidates: ranked,
      recommended_candidate_id: ranked[0]?.candidate_id ?? null, pack_id: ranked[0]?.pack_id ?? null,
      route_call_count: routeCalls, route_call_budget: routeCallBudget,
      proposed_order_count: proposals.length, unattempted_order_count: proposals.length - routeCalls,
      budget_exhausted: routeCalls === routeCallBudget, rejected_attempt_counts: rejections,
      rejected_attempts: rejectedAttempts,
      warnings: ranked.length < request.candidate_count ? [...WARNINGS, "fewer_candidates_than_requested"] : WARNINGS,
    });
  }

  return Object.freeze({ generate, invalidate });
}

function validateRoute(reply, request, proposal, points, expectedPack) {
  if (reply?.type !== "local_route_result" || reply.engine !== "valhalla-mobile") fail("invalid_native_reply");
  if (reply.profile !== request.routing_profile) fail("profile_identity_mismatch");
  if (expectedPack !== null && reply.pack_id !== expectedPack) fail("routing_pack_identity_changed");
  if (reply.distance_m > LOCAL_WAYPOINT_MAX_DISTANCE_M) fail("route_distance_limit_exceeded");
  const objective = request.distance_objective;
  if (objective.maximum_m !== null && reply.distance_m > objective.maximum_m) fail("maximum_distance_exceeded");
  if (objective.priority === "strict" && Math.abs(reply.distance_m - objective.target_m) > objective.tolerance_m) {
    fail("strict_distance_tolerance_missed");
  }
  if (reply.snapped_points.length !== points.length) fail("snapped_point_count_mismatch");
  const geometry = reply.geometry;
  if (geometry.every((position) => position[0] === geometry[0][0] && position[1] === geometry[0][1])) {
    fail("degenerate_geometry");
  }
  const outcomes = [];
  let cursor = 0;
  for (let position = 0; position < points.length; position += 1) {
    const snap = reply.snapped_points[position];
    const endpoint = position === 0 || position === points.length - 1;
    const threshold = endpoint ? LOCAL_WAYPOINT_HARD_ENDPOINT_SNAP_TOLERANCE_M : LOCAL_WAYPOINT_EXACT_INTERIOR_FIDELITY_M;
    const measured = haversine(points[position], snap);
    if (measured > threshold) fail(endpoint ? "endpoint_not_reached" : "exact_waypoint_not_reached", {
      position, waypoint_id: endpoint ? null : request.waypoints[proposal.order[position - 1]].id,
      profile: request.routing_profile, snap_distance_m: measured, maximum_snap_distance_m: threshold,
      suggestion: "Move or remove the exact point; no weaker retry was performed.",
    });
    // PR34 joins continuous leg shapes; each snap is a real leg-boundary vertex.
    while (cursor < geometry.length && (geometry[cursor][0] !== snap.lon || geometry[cursor][1] !== snap.lat)) cursor += 1;
    if (cursor === geometry.length) fail("snapped_waypoint_not_on_ordered_geometry");
    const originalIndex = endpoint ? (position === 0 || request.topology === "loop" ? 0 : points.length - 1) : proposal.order[position - 1] + 1;
    const waypoint = endpoint ? null : request.waypoints[originalIndex - 1];
    outcomes.push({
      role: position === 0 ? "start" : endpoint ? "end" : "waypoint",
      waypoint_id: waypoint?.id ?? null, name: waypoint?.name ?? points[position].name,
      original_index: originalIndex, route_position: position, status: "reached",
      requested_coordinate: points[position], snapped_coordinate: snap,
      snap_distance_m: measured, maximum_snap_distance_m: threshold, geometry_vertex_index: cursor,
    });
  }
  const closureGap = haversine(reply.snapped_points[0], reply.snapped_points.at(-1));
  if (request.topology === "loop" && closureGap > LOCAL_WAYPOINT_ROUTE_CLOSURE_TOLERANCE_M) fail("route_not_closed");
  if (request.topology === "point_to_point" && sameCoordinate(reply.snapped_points[0], reply.snapped_points.at(-1))) fail("open_route_was_closed");
  return { outcomes, closureGap: request.topology === "loop" ? closureGap : null };
}

// The app and harness use this exact getter, including reads of current controls.
export function readLocalWaypointRouteRequest(planner, byId) {
  if ((planner.savedRouteSnapshotDisplay && planner.savedRouteSnapshot)
      || (planner.outingDisplay && planner.outingSnapshot)) {
    fail("immutable_snapshot");
  }
  if (planner.planningMode !== "waypoint_route") fail("unsupported_plan_kind");
  return waypointPlanRequestSnapshot({
    ...planner,
    routingProfile: byId("profile").value,
    options: readPlannerOptionsFromControls(byId),
    waypointEndpoints: { ...planner.waypointEndpoints, routeTopology: byId("route-topology").value },
  });
}

export function addLocalWaypointProfileOptions(select, capabilities) {
  if (!capabilities?.enabled) return [];
  const profiles = capabilities.supported_profile_ids.filter((id) => PUBLIC_LOCAL_ROUTE_PROFILES.includes(id));
  for (const profile of profiles) {
    let option = [...select.options].find((item) => item.value === profile);
    if (option && !option.disabled) continue; // Preserve every available server label.
    if (!option) {
      option = document.createElement("option");
      option.value = profile;
      select.append(option);
    }
    option.disabled = false;
    option.dataset.localWaypointOnly = "true";
    option.textContent = `${profile} — local experiment only`;
  }
  return profiles;
}

export function createLocalWaypointRouteExperiment({
  bridge, getRequest, renderCandidates = () => {}, clearCandidates = () => {},
  onBusy = () => {}, isBusy = () => false, isEnabled = () => true, elements,
} = {}) {
  let epoch = 0;
  let activePromise = null;
  const engine = createLocalWaypointRouteEngine({
    route: (input) => bridge.route(input),
    isCurrent: (request) => JSON.stringify(validateLocalWaypointRouteRequest(getRequest())) === JSON.stringify(request),
  });

  function requestFromPlanner() {
    if (activePromise !== null) return activePromise;
    let request;
    try {
      if (!isEnabled()) fail("local_routing_unavailable");
      if (isBusy()) fail("local_generation_busy");
      request = validateLocalWaypointRouteRequest(getRequest());
    } catch (error) {
      showFailure(error);
      return Promise.resolve(null);
    }
    const ownedEpoch = ++epoch;
    clearCandidates();
    elements.results.replaceChildren();
    onBusy(true);
    elements.status.textContent = "Generating Local Waypoint Route from the current planner intent…";
    const promise = engine.generate(request).then((result) => {
      if (ownedEpoch !== epoch) return null;
      if (result === null) {
        elements.status.textContent = "Local Waypoint Route invalidated: planner intent changed. Generate again.";
        return null;
      }
      if (result.candidates.length) renderCandidates(result.candidates, result.recommended_candidate_id);
      elements.status.textContent = (
        `Local Waypoint Route · ${result.status}${result.code ? ` (${result.code})` : ""} · `
        + `${result.candidates.length}/${result.requested_candidate_count} candidates · ${result.topology} · `
        + `profile ${result.profile} · pack ${result.pack_id ?? "none"} · `
        + `${result.route_call_count}/${result.route_call_budget} route calls · budget exhausted ${result.budget_exhausted} · `
        + `rejections ${JSON.stringify(result.rejected_attempt_counts)} · ${result.warnings.join(", ")}`
      );
      for (const candidate of result.candidates) {
        const item = document.createElement("li");
        item.textContent = (
          `#${candidate.rank} · ${candidate.candidate_id} · ${(candidate.distance_m / 1_000).toFixed(2)} km · `
          + `${candidate.duration_s === null ? "duration unavailable" : `${Math.round(candidate.duration_s / 60)} min`} · `
          + `target error ${(candidate.target_error_m / 1_000).toFixed(2)} km · within tolerance ${candidate.within_tolerance} · `
          + `order ${candidate.actual_waypoint_order.join(" → ") || "direct"} · ${candidate.construction.proposal_id} · `
          + `hard endpoints within 25 m; ${candidate.actual_waypoint_order.length} exact interiors within 300 m`
          + (candidate.topology === "loop" ? `; graph-derived closure within 25 m` : "")
        );
        elements.results.append(item);
      }
      return result;
    }).catch((error) => {
      if (ownedEpoch === epoch) showFailure(error);
      return null;
    }).finally(() => {
      activePromise = null;
      onBusy(false);
    });
    activePromise = promise;
    return promise;
  }

  function showFailure(error) {
    clearCandidates();
    elements.results.replaceChildren();
    const code = error instanceof LocalWaypointRouteValidationError ? error.code : "invalid_planner_request";
    elements.status.textContent = `Local Waypoint Route rejected (${code}). Use Waypoint Route with exact points, nature/loop geometry off and shortest path selection; no request was weakened.`;
  }

  function invalidate() {
    epoch += 1;
    engine.invalidate();
    clearCandidates();
    elements.results.replaceChildren();
    elements.status.textContent = "Local Waypoint Route cleared; generate again after editing.";
    // Do not release the shared busy gate until the in-flight native promise settles.
  }

  return Object.freeze({
    bind: () => elements.button.addEventListener("click", requestFromPlanner),
    requestFromPlanner, invalidate,
  });
}

function routingPoints(request, order) {
  return [request.start, ...order.map((index) => request.waypoints[index].coordinate), request.end ?? request.start];
}

function proposalLength(request, order) {
  const points = routingPoints(request, order);
  return points.slice(1).reduce((total, point, index) => total + haversine(points[index], point), 0);
}

function haversine(a, b) {
  const rad = Math.PI / 180;
  const h = Math.sin((b.lat - a.lat) * rad / 2) ** 2
    + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin((b.lon - a.lon) * rad / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(Math.min(1, Math.max(0, h))));
}

function seedShuffle(values, seed) {
  const result = [...values];
  let state = Number.parseInt(hashText(String(seed)), 16);
  for (let index = result.length - 1; index > 0; index -= 1) {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    const swap = Math.floor((state / 0x1_0000_0000) * (index + 1));
    [result[index], result[swap]] = [result[swap], result[index]];
  }
  return result;
}

function coordinate(value) {
  if (!fieldsAllowed(value, new Set(["lat", "lon", "name"]))
      || !within(value.lat, -90, 90) || !within(value.lon, -180, 180)
      || !(value.name == null || textWithin(value.name, 200))) fail("invalid_coordinate");
  return { lat: value.lat, lon: value.lon, name: value.name ?? null };
}

function fieldsAllowed(value, allowed) {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).every((key) => allowed.has(key));
}

function geometryKey(geometry, topology) {
  const forward = JSON.stringify(geometry);
  if (topology !== "loop") return forward;
  const reverse = JSON.stringify([...geometry].reverse());
  return forward < reverse ? forward : reverse;
}

function hashText(text) {
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) hash = Math.imul(hash ^ text.charCodeAt(index), 16777619) >>> 0;
  return hash.toString(16).padStart(8, "0");
}

function coordinateKey(point) { return `${point.lat},${point.lon}`; }
function sameCoordinate(a, b) { return a.lat === b.lat && a.lon === b.lon; }
function within(value, minimum, maximum) { return Number.isFinite(value) && value >= minimum && value <= maximum; }
function textWithin(value, maximum) { return typeof value === "string" && value.length >= 1 && value.length <= maximum; }
function compareText(a, b) { return a < b ? -1 : a > b ? 1 : 0; }
function fail(code, details) { throw new LocalWaypointRouteValidationError(code, details); }
function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.values(value).forEach(deepFreeze);
    Object.freeze(value);
  }
  return value;
}
