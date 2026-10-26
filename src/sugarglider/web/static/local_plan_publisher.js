import { deepFreeze, evaluateLocalCandidateDraft, LocalCandidateEvaluationError } from "./local_candidate_evaluator.js";
import { canonicalCoordinate } from "./local_plan_geometry.js";
import { captureRegionalRoutingReference } from "./regional_routing_reference.js";

const ROLE_ORDER = ["harmonious", "maximum_requested_coverage", "smooth_low_detour", "distance_focused"];

// Both bounded searches supply retained immutable drafts. Canonical publication
// evaluates each distinct native line once and gives the shared portfolio sole
// ownership of public roles/ranks. It does not issue routing or region requests.
export async function publishLocalPlan(request, search, regionalReference = null) {
  if (!search || !Array.isArray(search.candidates) || search.candidates.length > 5
    || !search.search_diagnostics || search.profile !== request.routing_profile
    || search.type !== (request.kind === "auto_tour" ? "local_auto_tour_result" : "local_waypoint_route_result")) {
    throw new LocalCandidateEvaluationError("invalid_local_search_result");
  }
  const reference = regionalReference === null ? null : captureRegionalRoutingReference(regionalReference);
  if (reference && search.pack_id !== reference.pack_id
    && !(search.candidates.length === 0 && search.pack_id === null)) {
    throw new LocalCandidateEvaluationError("routing_pack_identity_changed");
  }
  const regionalVersion = reference ? deepFreeze({ region_id: reference.region_id, build_id: reference.build_id,
    routing_pack_id: reference.pack_id }) : null;
  const evaluated = [], rejected = [];
  const sourceIds = new Map();
  for (const draft of search.candidates) {
    try {
      if (draft.pack_id !== search.pack_id) throw new LocalCandidateEvaluationError("routing_pack_identity_changed");
      const candidate = await evaluateLocalCandidateDraft(request, draft);
      sourceIds.set(draft.candidate_id, candidate.id);
      evaluated.push(regionalVersion ? deepFreeze({ ...candidate, diagnostics: { ...candidate.diagnostics,
        details: { ...candidate.diagnostics.details, local_routing: { ...candidate.diagnostics.details.local_routing,
          regional_version: regionalVersion } } } }) : candidate);
    } catch (error) {
      if (!(error instanceof LocalCandidateEvaluationError) && error.code !== "invalid_local_candidate_enrichment") throw error;
      rejected.push({ source_candidate_id: draft.candidate_id, code: error.code });
    }
  }
  const adventure = Object.hasOwn(search, "no_optional_control_candidate_id");
  const hasControl = request.kind === "auto_tour" || adventure;
  const controlId = sourceIds.get(search.no_poi_control_candidate_id ?? search.no_optional_control_candidate_id) ?? null;
  // A POI alternative has no independent promotion evidence. If its required
  // control fails final publication, never quietly recommend the detour.
  const pool = hasControl && !controlId ? [] : evaluated;
  const candidates = buildLocalPortfolio(pool, { limit: search.adventure_diagnostics?.preference_strategy === "strong_woodland"
    ? Math.min(5, Math.max(2, request.candidate_count + 2)) : adventure ? Math.max(2, request.candidate_count) : request.candidate_count,
    controlId, adventure });
  const diagnostics = structuredClone(search.search_diagnostics);
  diagnostics.warnings = [...new Set([...(search.warnings ?? []),
    ...(candidates.length < request.candidate_count ? ["fewer_candidates_than_requested"] : []),
    ...(adventure && candidates.length > request.candidate_count ? ["adventure_comparison_route_retained"] : []),
    ...(hasControl && !controlId && evaluated.length ? ["local_no_poi_control_unavailable"] : [])])].sort();
  const proposals = search.endpoint_proposals ?? search.rejected_attempts?.find(item => item.code === "endpoint_review_required")?.details.endpoint_proposals ?? [];
  const proposalPack = search.rejected_attempts?.find(item => item.code === "endpoint_review_required")?.details.pack_id;
  const endpointProposals = candidates.length ? [] : proposals.slice(0, 2).filter(item =>
    !reference || (item.pack_id ?? proposalPack) === reference.pack_id);
  const publishedFamilies = search.adventure_diagnostics?.distinct_candidate_ids.map(id => sourceIds.get(id)).filter(id => candidates.some(candidate => candidate.id === id)) ?? [];
  diagnostics.details.local_planning = {
    endpoint_proposals: endpointProposals,
    engine: "valhalla-mobile", pack_id: search.pack_id,
    rejected_attempt_counts: search.rejected_attempt_counts,
    rejected_attempts: search.rejected_attempts ?? [],
    failure_code: candidates.length ? null : search.code
      ?? Object.keys(search.rejected_attempt_counts ?? {})[0]?.replace(/^local_route_/, "")
      ?? rejected[0]?.code ?? "no_valid_local_candidate",
    rejected_publications: rejected,
    no_poi_control_candidate_id: controlId ?? null,
    preference_status: search.preference_status ?? null,
    regional_data: search.regional_data ?? null,
    poi_outcomes: search.poi_outcomes ?? [],
    distinctness: "routed_geometry_only", exact_repetition_available: false,
    ...(adventure ? { adventure_search: search.adventure_diagnostics ? { ...search.adventure_diagnostics,
      distinct_candidate_ids: publishedFamilies, distinct_route_count: publishedFamilies.length,
      comparison_variant_count: candidates.length - publishedFamilies.length,
      within_tolerance_count: candidates.filter(candidate => candidate.diagnostics.within_tolerance).length } : null } : {}),
  };
  if (regionalVersion) diagnostics.details.local_planning.regional_version = regionalVersion;
  return deepFreeze({ schema_version: 1, kind: request.kind, topology: request.topology,
    routing_profile: request.routing_profile, effective_start: canonicalCoordinate(request.start),
    effective_end: canonicalCoordinate(request.topology === "loop" ? request.start : request.end),
    candidates, search_diagnostics: diagnostics });
}

export function buildLocalPortfolio(candidates, { limit, controlId = null, adventure = false }) {
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
  // AI search retains its comparison route even when a checked optional route
  // meets a target the comparison misses. POI rewards cannot establish a quality
  // improvement within the same tolerance class; the control still leads there.
  if (adventure) ordered.sort((a, b) => Number(b.diagnostics.within_tolerance) - Number(a.diagnostics.within_tolerance));
  const selected = ordered.slice(0, limit);
  if (controlId && adventure && !selected.some(candidate => candidate.id === controlId)) {
    selected[selected.length - 1] = ordered.find(candidate => candidate.id === controlId);
  }
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
