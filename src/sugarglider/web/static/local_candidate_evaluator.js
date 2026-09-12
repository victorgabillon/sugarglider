import { UNKNOWN_DETAIL_ANALYSIS } from "./local_analysis_templates.js";
import { publishLocalNature, publishLocalStops } from "./local_candidate_enrichment.js";
import { PUBLIC_PROFILE_METADATA } from "./public_profile_metadata.js";
import { canonicalTraversal, haversineDistance, localCandidateSignature, locateOnRoutedGeometry, routedGeometryDistance } from "./local_plan_geometry.js";

export class LocalCandidateEvaluationError extends Error {
  constructor(code) {
    super(code);
    this.name = "LocalCandidateEvaluationError";
    this.code = code;
  }
}

// Complete native lines enter the shared evaluator. It builds an unranked
// canonical candidate; only the portfolio may assign public rank and roles.
export async function evaluateLocalCandidateDraft(request, draft) {
  const profile = PUBLIC_PROFILE_METADATA[request.routing_profile];
  requireCandidate(Object.hasOwn(PUBLIC_PROFILE_METADATA, request.routing_profile)
    && draft.profile === request.routing_profile && draft.engine === "valhalla-mobile"
    && typeof draft.pack_id === "string" && draft.pack_id.length > 0, "local_candidate_identity_mismatch");
  requireCandidate(Array.isArray(draft.geometry) && draft.geometry.length >= 2
    && draft.geometry.length <= 200_000 && draft.geometry.every(validPosition)
    && Number.isFinite(draft.distance_m) && draft.distance_m > 0
    && Number.isFinite(draft.duration_s) && draft.duration_s >= 0,
  "invalid_local_candidate_geometry");
  requireCandidate(Array.isArray(draft.requested_points) && draft.requested_points.length >= 2
    && Array.isArray(draft.snapped_points) && draft.snapped_points.length === draft.requested_points.length
    && draft.snapped_points.every((point) => validPosition([point.lon, point.lat])),
  "invalid_local_candidate_snaps");
  const start = [request.start.lon, request.start.lat];
  const end = request.topology === "loop" ? start : [request.end.lon, request.end.lat];
  requireCandidate(haversineDistance(start, draft.geometry[0]) <= 25
    && haversineDistance(end, draft.geometry.at(-1)) <= 25, "local_hard_endpoint_not_reached");
  if (request.topology === "loop") requireCandidate(
    haversineDistance(draft.geometry[0], draft.geometry.at(-1)) <= 25, "local_route_not_closed");
  const exact = request.kind === "auto_tour" ? request.hard_waypoints
    : request.waypoints.filter((waypoint) => waypoint.constraint_strength === "exact");
  for (const waypoint of exact) requireCandidate(
    locateOnRoutedGeometry(draft.geometry, waypoint.coordinate).distance_m <= 300,
    "local_exact_waypoint_not_reached");
  const durationMs = Math.round(draft.duration_s * 1000);
  requireCandidate(Number.isSafeInteger(durationMs), "invalid_local_candidate_duration");
  const distance = draft.distance_m;
  const targetError = Math.abs(distance - request.distance_objective.target_m);
  const withinTolerance = targetError <= request.distance_objective.tolerance_m;
  const objective = request.distance_objective;
  requireCandidate(objective.priority !== "strict" || withinTolerance, "strict_distance_tolerance_missed");
  requireCandidate(objective.priority === "flexible" || objective.maximum_m === null
    || distance <= objective.maximum_m, "maximum_distance_exceeded");
  const geometryDistance = routedGeometryDistance(draft.geometry);
  requireCandidate(Number.isFinite(geometryDistance) && geometryDistance > 0, "invalid_local_candidate_geometry");
  const analysis = structuredClone(UNKNOWN_DETAIL_ANALYSIS[profile.activity_kind]);
  analysis.route_distance_m = distance;
  analysis.geometry_distance_m = geometryDistance;
  analysis.distance_scale_factor = distance / geometryDistance;
  analysis.unknown_surface.distance_m = distance;
  analysis.spurs.warnings = ["spur_analysis_unavailable"];
  requireCandidate(request.kind === "waypoint_route"
    ? request.waypoints.every((waypoint) => waypoint.constraint_strength === "exact")
    : !request.requested_stops.length, "local_requested_stop_publication_unavailable");
  const { reached: reachedStops, approximated: approximatedStops, dropped: droppedStops } =
    request.kind === "auto_tour" ? publishLocalStops(request, draft) : { reached: [], approximated: [], dropped: [] };
  analysis.nature = publishLocalNature(draft);
  analysis.warnings = [...new Set([...analysis.warnings, ...(draft.nature_analysis?.warnings ?? [])])].sort();
  const route = {
    name: request.name, routing_profile: request.routing_profile,
    summary: { distance_m: distance, duration_ms: durationMs, ascend_m: null, descend_m: null,
      input_point_count: draft.requested_points.length, routed_point_count: draft.geometry.length },
    geometry: draft.geometry,
    snapped_points: draft.snapped_points.map(({ lon, lat }) => [lon, lat]),
    path_details: {}, analysis,
  };
  const compromises = withinTolerance ? [] : [{
    code: "target_distance_missed", severity: "warning", constraint_id: null,
    constraint_name: null, semantic_coordinate: null, routed_coordinate: null,
    distance_m: distance, normal_tolerance_m: request.distance_objective.tolerance_m,
    configured_maximum_m: request.distance_objective.maximum_m,
    reason: "The routed distance is outside the requested target tolerance.",
    profile: request.routing_profile,
    suggestion: "Adjust the target distance or edit the requested points and generate a new plan.",
  }];
  const unmet = [];
  if (request.preferences.path_selection === "low_overlap") unmet.push(
    "Exact edge repetition is unavailable, so the low-overlap preference could not be evaluated.");
  if (request.preferences.nature === "prefer" && !analysis.nature) unmet.push(
    "Mapped nature could not be evaluated with the installed regional data.");
  if (request.preferences.loop_geometry === "prefer") unmet.push(draft.geometry_metrics
    ? "Local shape screening was used; complete loop-geometry analysis is unavailable."
    : "Loop-geometry preference could not be evaluated for this local route.");
  for (const reason of unmet) compromises.push({ code: "optional_preference_unmet", severity: "info",
    constraint_id: null, constraint_name: null, semantic_coordinate: null, routed_coordinate: null,
    distance_m: null, normal_tolerance_m: null, configured_maximum_m: null, reason,
    profile: request.routing_profile, suggestion: "Review the routed line and the available analysis before using this route." });
  const id = await localCandidateSignature(route.geometry, request.routing_profile, request.topology);
  const requestedOrder = request.kind === "waypoint_route" ? request.waypoints.map((point) => point.id) : [];
  const actualOrder = draft.actual_waypoint_order ?? requestedOrder;
  requireCandidate(actualOrder.length === requestedOrder.length && new Set(actualOrder).size === requestedOrder.length
    && actualOrder.every((value) => requestedOrder.includes(value)), "invalid_local_waypoint_order");
  const requiredVisits = request.kind === "waypoint_route" ? actualOrder.map((value) => {
    const index = requestedOrder.indexOf(value), point = request.waypoints[index];
    return { original_index: index, coordinate: { ...point.coordinate, name: point.name } };
  }) : [{ original_index: 0, coordinate: request.start }];
  return deepFreeze({
    id, kind: request.kind, topology: request.topology, routing_profile: request.routing_profile,
    route, score: { total: targetError / Math.max(1, objective.target_m),
      components: { target_distance_error_ratio: targetError / Math.max(1, objective.target_m) } },
    traversal: canonicalTraversal(request, route.geometry, reachedStops, approximatedStops),
    reached_stops: reachedStops, approximated_stops: approximatedStops, dropped_stops: droppedStops,
    compromises,
    diagnostics: { safety_eligible: true, target_error_m: targetError, within_tolerance: withinTolerance,
      requested_stop_count: reachedStops.filter((stop) => stop.selection_origin === "requested").length,
      approximated_stop_count: approximatedStops.length, dropped_stop_count: droppedStops.length,
      immediate_backtracking_m: 0, repeated_distance_m: 0, spur_count: 0,
      spur_repeated_distance_m: 0, longest_spur_distance_m: 0,
      details: { construction: draft.construction?.construction ?? draft.construction?.family ?? "local_routed_path",
        required_waypoint_order: requiredVisits,
        local_routing: { engine: draft.engine, engine_version: draft.engine_version,
        pack_id: draft.pack_id, source_candidate_id: draft.candidate_id,
        source_control_candidate_id: draft.source_control_candidate_id ?? null,
        waypoint_order: draft.actual_waypoint_order ?? [], original_waypoint_indices: draft.original_waypoint_indices ?? [],
        loop_geometry: draft.geometry_metrics ?? null,
        poi_outcomes: draft.poi_outcomes ?? [],
        nature: draft.nature_analysis ? { identity: draft.nature_analysis.identity,
          method: draft.nature_analysis.method, operation_count: draft.nature_analysis.operation_count,
          operation_budget: draft.nature_analysis.operation_budget } : null,
        path_details_available: false, exact_repetition_available: false,
        score_model: "local_target_distance_v1" } } },
  });
}

export function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  Object.values(value).forEach(deepFreeze);
  return Object.freeze(value);
}
function validPosition(point) {
  return Array.isArray(point) && point.length === 2 && Number.isFinite(point[0]) && Math.abs(point[0]) <= 180
    && Number.isFinite(point[1]) && Math.abs(point[1]) <= 90;
}
function requireCandidate(condition, code) { if (!condition) throw new LocalCandidateEvaluationError(code); }
