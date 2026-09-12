import { deepFreeze, evaluateLocalCandidateDraft, LocalCandidateEvaluationError } from "./local_candidate_evaluator.js";
import { canonicalCoordinate } from "./local_plan_geometry.js";

const ROLE_ORDER = ["harmonious", "maximum_requested_coverage", "smooth_low_detour", "distance_focused"];

// Both bounded searches supply retained immutable drafts. Canonical publication
// evaluates each distinct native line once and gives the shared portfolio sole
// ownership of public roles/ranks. It does not issue routing or region requests.
export async function publishLocalPlan(request, search) {
  if (!search || !Array.isArray(search.candidates) || search.candidates.length > 5
    || !search.search_diagnostics || search.profile !== request.routing_profile
    || search.type !== (request.kind === "auto_tour" ? "local_auto_tour_result" : "local_waypoint_route_result")) {
    throw new LocalCandidateEvaluationError("invalid_local_search_result");
  }
  const evaluated = [], rejected = [];
  const sourceIds = new Map();
  for (const draft of search.candidates) {
    try {
      if (draft.pack_id !== search.pack_id) throw new LocalCandidateEvaluationError("routing_pack_identity_changed");
      const candidate = await evaluateLocalCandidateDraft(request, draft);
      sourceIds.set(draft.candidate_id, candidate.id);
      evaluated.push(candidate);
    } catch (error) {
      if (!(error instanceof LocalCandidateEvaluationError) && error.code !== "invalid_local_candidate_enrichment") throw error;
      rejected.push({ source_candidate_id: draft.candidate_id, code: error.code });
    }
  }
  const controlId = request.kind === "auto_tour" ? sourceIds.get(search.no_poi_control_candidate_id) : null;
  // A POI alternative has no independent promotion evidence. If its required
  // control fails final publication, never quietly recommend the detour.
  const pool = request.kind === "auto_tour" && !controlId ? [] : evaluated;
  const candidates = buildLocalPortfolio(pool, { limit: request.candidate_count, controlId });
  const diagnostics = structuredClone(search.search_diagnostics);
  diagnostics.warnings = [...new Set([...(search.warnings ?? []),
    ...(candidates.length < request.candidate_count ? ["fewer_candidates_than_requested"] : []),
    ...(request.kind === "auto_tour" && !controlId && evaluated.length ? ["local_no_poi_control_unavailable"] : [])])].sort();
  diagnostics.details.local_planning = {
    engine: "valhalla-mobile", pack_id: search.pack_id,
    rejected_attempt_counts: search.rejected_attempt_counts,
    rejected_publications: rejected,
    no_poi_control_candidate_id: controlId ?? null,
    preference_status: search.preference_status ?? null,
    regional_data: search.regional_data ?? null,
    poi_outcomes: search.poi_outcomes ?? [],
    distinctness: "routed_geometry_only", exact_repetition_available: false,
  };
  return deepFreeze({ schema_version: 1, kind: request.kind, topology: request.topology,
    routing_profile: request.routing_profile, effective_start: canonicalCoordinate(request.start),
    effective_end: canonicalCoordinate(request.topology === "loop" ? request.start : request.end),
    candidates, search_diagnostics: diagnostics });
}

export function buildLocalPortfolio(candidates, { limit, controlId = null }) {
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 5) throw new TypeError("Invalid portfolio limit.");
  const distinct = new Map();
  for (const candidate of candidates) {
    if (Object.hasOwn(candidate, "rank") || Object.hasOwn(candidate, "roles")) throw new TypeError("Expected an unranked candidate.");
    if (candidate.diagnostics.safety_eligible && !distinct.has(candidate.id)) distinct.set(candidate.id, candidate);
  }
  // Search ordering already applies each mode's target/geometry/POI gates.
  // Retaining it prevents publication from changing native route-call behavior.
  const ordered = [...distinct.values()];
  if (controlId) {
    const index = ordered.findIndex((candidate) => candidate.id === controlId);
    if (index < 0) throw new TypeError("Missing no-POI control.");
    ordered.unshift(...ordered.splice(index, 1));
  }
  const selected = ordered.slice(0, limit);
  if (!selected.length) return Object.freeze([]);
  const roles = new Map(selected.map((candidate) => [candidate.id, new Set()]));
  roles.get(selected[0].id).add("harmonious");
  const maximumCoverage = Math.max(...selected.map((candidate) => candidate.diagnostics.requested_stop_count));
  if (maximumCoverage > 0) for (const candidate of selected) {
    if (candidate.diagnostics.requested_stop_count === maximumCoverage) roles.get(candidate.id).add("maximum_requested_coverage");
  }
  // Missing edge IDs cannot earn a route-quality role from lower-bound zeros.
  const measured = selected.filter((candidate) => candidate.route.analysis.repetition.available
    && candidate.route.analysis.repetition.edge_id_coverage.share === 1
    && candidate.route.analysis.backtrack_edge_id_coverage.share === 1);
  const smooth = [...measured].sort((left, right) => left.diagnostics.immediate_backtracking_m - right.diagnostics.immediate_backtracking_m
    || left.diagnostics.repeated_distance_m - right.diagnostics.repeated_distance_m || compareText(left.id, right.id))[0];
  if (smooth) roles.get(smooth.id).add("smooth_low_detour");
  const distance = [...selected].sort((left, right) => left.diagnostics.target_error_m - right.diagnostics.target_error_m
    || compareText(left.id, right.id))[0];
  roles.get(distance.id).add("distance_focused");
  return deepFreeze(selected.map((candidate, index) => ({ ...candidate, rank: index + 1,
    roles: ROLE_ORDER.filter((role) => roles.get(candidate.id).has(role)) })));
}

function compareText(left, right) { return left < right ? -1 : left > right ? 1 : 0; }
