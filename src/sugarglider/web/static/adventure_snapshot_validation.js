import { parseAdventureProposal, safeAdventureLink } from "./adventure_proposal.js";
import { assessAdventure } from "./adventure_assessment.js";
import { validateLocalWaypointRouteRequest } from "./local_waypoint_route.js";
import { localCandidateTraversal, localCandidateAnalysis } from "./local_candidate_evaluator.js";
import { localCandidateSignature, locateOnRoutedGeometry, routedGeometryDistance } from "./local_plan_geometry.js";
import { measureEndpointAdjustments, endpointAdjustmentFailure } from "./endpoint_snapping.js";
import { exportCanonicalCandidate } from "./local_gpx_export.js";
import { captureRegionalRoutingReference } from "./regional_routing_reference.js";
import { sampleElevationGeometry } from "./elevation_sampling.js";
import { parseRouteElevationReply } from "./route_elevation.js";

export const MAX_ADVENTURE_SNAPSHOT_BYTES = 16 * 1024 * 1024;
const encoder = new TextEncoder();
const fail = () => { throw Error("invalid_adventure_snapshot"); };
const requireValue = condition => { if (!condition) fail(); };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const exact = (v, keys) => v && typeof v === "object" && !Array.isArray(v)
  && Object.keys(v).length === keys.length && keys.every(key => Object.hasOwn(v, key));
const sha = value => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const outputKeys = ["selected_round", "rounds", "chosen", "refinement_improved", "refinement_error", "model_calls", "routing_diagnostics"];

// This is an exact local result, never a model conversation or credential store.
// Validation computes identities and checks evidence; it never routes or ranks.
export async function encodeAdventureSnapshot(output) {
  plain(output);
  const payload = JSON.stringify(output);
  requireValue(encoder.encode(payload).byteLength <= MAX_ADVENTURE_SNAPSHOT_BYTES);
  await validateOutput(output);
  return { schema_version: 1, payload, sha256: await digest(payload) };
}
export async function decodeAdventureSnapshot(record) {
  requireValue(exact(record, ["schema_version", "payload", "sha256", "selected_id"])
    && record.schema_version === 1 && typeof record.payload === "string" && sha(record.sha256)
    && record.payload.length <= MAX_ADVENTURE_SNAPSHOT_BYTES
    && encoder.encode(record.payload).byteLength <= MAX_ADVENTURE_SNAPSHOT_BYTES);
  requireValue(await digest(record.payload) === record.sha256);
  const output = JSON.parse(record.payload);
  plain(output);
  await validateOutput(output);
  requireValue(output.chosen.result.candidates.some(candidate => candidate.id === record.selected_id));
  return { output, selected_id: record.selected_id };
}
async function validateOutput(output) {
  requireValue(exact(output, output.timings === undefined ? outputKeys : [...outputKeys, "timings"]) && Array.isArray(output.rounds) && output.rounds.length >= 1 && output.rounds.length <= 2
    && Number.isSafeInteger(output.selected_round) && output.selected_round >= 0 && output.selected_round < output.rounds.length
    && same(output.chosen, output.rounds[output.selected_round]) && typeof output.refinement_improved === "boolean"
    && (output.refinement_error === null || /^[a-z_]{1,80}$/.test(output.refinement_error))
    && Array.isArray(output.model_calls) && output.model_calls.length >= 1 && output.model_calls.length <= 2);
  for (const call of output.model_calls) {
    requireValue(exact(call, ["phase", "status", "usage", "elapsed_ms", "error", ...(call.timings === undefined ? [] : ["timings"])])
      && ["initial", "refinement", "stories"].includes(call.phase) && ["completed", "failed"].includes(call.status)
      && (call.usage === null || Object.entries(call.usage).every(([key, value]) =>
        ["input_tokens", "output_tokens", "total_tokens"].includes(key) && Number.isSafeInteger(value) && value >= 0))
      && (call.elapsed_ms === null || Number.isFinite(call.elapsed_ms) && call.elapsed_ms >= 0)
      && (call.error === null || /^[a-z_]{1,80}$/.test(call.error)));
  }
  const timingKeys = ["context_preparation_ms", "input_preparation_ms", "structured_validation_ms", "grounding_ms", "routing_and_nature_ms", "elevation_ms", "refinement_ms", "native_routing_ms", "nature_ms", "publication_ms", "total_ms"];
  const modelTimingKeys = ["response_headers_ms", "first_event_ms", "first_text_ms", "research_span_ms", "stream_ms", "request_bytes", "output_chars"];
  if (output.timings !== undefined) requireValue(exact(output.timings, timingKeys) && Object.values(output.timings).every(value => Number.isFinite(value) && value >= 0));
  for (const call of output.model_calls) if (call.timings !== undefined) requireValue(exact(call.timings, modelTimingKeys)
    && Object.values(call.timings).every(value => value === null || Number.isFinite(value) && value >= 0));
  let source = null;
  for (const round of output.rounds) {
    requireValue(exact(round, ["proposal", "grounding", "request", "targets", "bindings", "exclusions", "result", "assessment", "elevations", "endpoint_resolution"]));
    const proposal = parseAdventureProposal(JSON.stringify(round.proposal));
    const request = validateLocalWaypointRouteRequest(round.request, { adventure: true });
    requireValue(exact(round.endpoint_resolution, ["start", "end"]));
    for (const kind of ["start", "end"]) {
      const resolution = round.endpoint_resolution[kind];
      if (resolution === null) continue;
      requireValue(exact(resolution, ["coordinate", "proposed_coordinate", "evidence"])
        && ["unique_exact_local_name", "model_coordinate_unverified"].includes(resolution.evidence)
        && exact(resolution.coordinate, ["name", "lat", "lon"])
        && request[kind] && ["lat", "lon", "name"].every(key => resolution.coordinate[key] === request[kind][key])
        && (kind !== "end" || request.topology === "point_to_point"));
      const proposed = resolution.proposed_coordinate;
      requireValue(exact(proposed, ["name", "lat", "lon"]) && typeof proposed.name === "string" && proposed.name.length >= 1 && proposed.name.length <= 120
        && (proposed.lat === null && proposed.lon === null || Number.isFinite(proposed.lat) && Math.abs(proposed.lat) <= 90 && Number.isFinite(proposed.lon) && Math.abs(proposed.lon) <= 180));
    }
    requireValue(sha(round.grounding?.build_id) && round.grounding.places.length === proposal.places.length
      && round.grounding.places.every((place, index) => place.id === proposal.places[index].id
        && typeof place.location?.name === "string" && typeof place.reason === "string"
        && (place.anecdote === null || typeof place.anecdote === "string")
        && place.sources.every(item => safeAdventureLink(item.url) === item.url && typeof item.title === "string")));
    requireValue(round.result?.schema_version === 1 && round.result.kind === request.kind
      && round.result.topology === request.topology && round.result.routing_profile === request.routing_profile
      && Array.isArray(round.result.candidates) && round.result.candidates.length <= 5);
    const ids = new Set();
    for (const candidate of round.result.candidates) {
      const route = candidate.route, local = candidate.diagnostics?.details?.local_routing;
      const pinned = local?.regional_version;
      requireValue(candidate.kind === request.kind && candidate.topology === request.topology
        && candidate.routing_profile === request.routing_profile && route.routing_profile === request.routing_profile
        && route.name === request.name && local.engine === "valhalla-mobile"
        && pinned?.region_id === round.grounding.region_id && pinned.build_id === round.grounding.build_id
        && pinned.routing_pack_id === local.pack_id && !ids.has(candidate.id)
        && Number.isSafeInteger(candidate.rank) && candidate.rank >= 1 && candidate.rank <= 5
        && candidate.diagnostics.safety_eligible === true
        && Array.isArray(route.geometry) && route.geometry.length >= 2 && route.geometry.length <= 20000
        && route.geometry.every(p => Array.isArray(p) && p.length === 2 && Number.isFinite(p[0]) && Math.abs(p[0]) <= 180 && Number.isFinite(p[1]) && Math.abs(p[1]) <= 90));
      ids.add(candidate.id);
      requireValue(candidate.diagnostics.immediate_backtracking_m === 0 && candidate.diagnostics.repeated_distance_m === 0
        && local.exact_repetition_available === false && local.path_details_available === false
        && exact(route.path_details, [])
        && same(localCandidateAnalysis(request.routing_profile, route.summary.distance_m, routedGeometryDistance(route.geometry),
          route.analysis.nature, route.analysis.warnings), route.analysis));
      const identity = JSON.stringify(pinned);
      requireValue(source === null || identity === source); source = identity;
      const distance = route.summary.distance_m, error = Math.abs(distance - request.distance_objective.target_m);
      requireValue(Number.isFinite(distance) && distance > 0 && distance <= 200000
        && error === candidate.diagnostics.target_error_m
        && candidate.diagnostics.within_tolerance === (error <= request.distance_objective.tolerance_m)
        && (request.distance_objective.priority !== "strict" || candidate.diagnostics.within_tolerance)
        && (request.distance_objective.priority === "flexible" || request.distance_objective.maximum_m === null || distance <= request.distance_objective.maximum_m));
      requireValue(await localCandidateSignature(route.geometry, request.routing_profile, request.topology) === candidate.id);
      const adjustments = measureEndpointAdjustments(request, route.geometry);
      requireValue(!endpointAdjustmentFailure(adjustments) && same(adjustments, local.endpoint_adjustments));
      requireValue(same(localCandidateTraversal(request, route.geometry, candidate.reached_stops, candidate.approximated_stops, adjustments), candidate.traversal));
      const hard = request.waypoints.filter(point => point.constraint_strength === "exact");
      requireValue(hard.every(point => locateOnRoutedGeometry(route.geometry, point.coordinate).distance_m <= 300));
      requireValue(request.waypoint_order !== "fixed" || same(candidate.traversal.anchors.filter(anchor => anchor.kind === "exact_waypoint").map(anchor => anchor.id), hard.map(point => `exact/${point.id}`)));
      const soft = request.waypoints.filter(point => point.constraint_strength !== "exact"), stops = [...candidate.reached_stops, ...candidate.dropped_stops];
      requireValue(candidate.approximated_stops.length === 0 && stops.length === soft.length && new Set(stops.map(point => point.id)).size === soft.length
        && stops.every(stop => soft.some(point => point.id === stop.id && point.name === stop.name && same(point.coordinate, stop.semantic_coordinate))));
      exportCanonicalCandidate(candidate); // Shared strict stop-arrival/GPX boundary.
      const nature = route.analysis.nature;
      if (nature !== null) {
        const classes = ["woodland", "open_natural", "agriculture", "water_crossing", "urban", "unknown_landcover"];
        requireValue(nature.available === true && [...classes, "near_water", "park_or_protected"].every(key => Number.isFinite(nature[key]?.distance_m)
          && nature[key].distance_m >= 0 && nature[key].distance_m <= distance + 1e-6
          && Math.abs(nature[key].share * distance - nature[key].distance_m) < 1e-6)
          && Math.abs(classes.reduce((sum, key) => sum + nature[key].distance_m, 0) - distance) < 1e-6);
      }
      const elevation = round.elevations[candidate.id];
      if (elevation) {
        const valid = parseRouteElevationReply(JSON.stringify(elevation));
        requireValue(valid?.type === "local_elevation_result");
        const reference = captureRegionalRoutingReference(elevation.regional_reference);
        const sampled = await sampleElevationGeometry(route.geometry, distance);
        requireValue(reference.region_id === pinned.region_id && reference.build_id === pinned.build_id && reference.pack_id === pinned.routing_pack_id
          && elevation.candidate_id === candidate.id && elevation.analysis.geometry_sha256 === sampled.geometry_sha256
          && elevation.analysis.route_distance_m === distance && elevation.analysis.routing_profile === candidate.routing_profile
          && elevation.sampling_interval_m === sampled.sampling_interval_m
          && same(elevation.sample_coordinates, sampled.samples.map(p => [p[2], p[1]]))
          && same(elevation.analysis.samples.map(p => p.distance_m), sampled.samples.map(p => p[0])));
      }
    }
    const measured = assessAdventure({ proposal, grounding: round.grounding, request, result: round.result,
      bindings: round.bindings, exclusions: round.exclusions, elevations: round.elevations });
    requireValue(measured.assessments.every(item => same(item, round.assessment.assessments.find(old => old.candidate_id === item.candidate_id))));
  }
  requireValue(output.chosen.result.candidates.length > 0);
}
function plain(root) {
  let count = 0;
  function walk(value, depth) {
    requireValue(++count <= 2000000 && depth <= 32);
    if (value === null || typeof value === "boolean" || typeof value === "string") return;
    if (typeof value === "number") { requireValue(Number.isFinite(value)); return; }
    requireValue(typeof value === "object" && (Array.isArray(value) || [null, Object.prototype].includes(Object.getPrototypeOf(value))));
    for (const [key, child] of Object.entries(value)) {
      requireValue(!/(?:access_?token|refresh_?token|id_?token|authorization|credential|capability|participant_?token|owner_?token|join_?token|raw_?prompt|audio_?data|account_?email)/iu.test(key));
      walk(child, depth + 1);
    }
  }
  walk(root, 0);
}
async function digest(value) {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(value)))].map(byte => byte.toString(16).padStart(2, "0")).join("");
}
