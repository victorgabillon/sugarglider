import { deepFreeze } from "./local_candidate_evaluator.js";
import { validateLocalWaypointRouteRequest } from "./local_waypoint_route.js";
import { haversineDistance } from "./local_plan_geometry.js";

export class AdventureIntentError extends Error {
  constructor(code, message) { super(message); this.name = "AdventureIntentError"; this.code = code; }
}
const key = coordinate => JSON.stringify([coordinate.lat, coordinate.lon]);

// Model labels do not confer hard authority. Only explicit confirmation may
// turn a suggested mandatory place into an exact point. Existing exact points
// keep their identity, order, coordinate and name.
export function buildAdventureIntent(proposal, grounding, { start, end = null, hardWaypoints = [],
  confirmedMandatoryIds = [], endpointSnapPolicy = { start: "near", end: "near" }, seed = 0, fixed = null } = {}) {
  if (!start || !Number.isFinite(start.lat) || !Number.isFinite(start.lon)) {
    throw new AdventureIntentError("adventure_start_required", "Choose a Start before planning this adventure.");
  }
  for (const [suggested, chosen] of [[proposal.intent.start, fixed?.start ?? start],
    [proposal.intent.end, fixed?.end ?? end]]) {
    if (suggested?.lat !== null && Number.isFinite(suggested?.lat) && chosen
      && haversineDistance([suggested.lon, suggested.lat], [chosen.lon, chosen.lat]) > 1) {
      throw new AdventureIntentError("adventure_endpoint_review_required", "The proposed endpoint differs from your chosen point. Review the location before routing.");
    }
  }
  if (grounding.places.length !== proposal.places.length || grounding.places.some(place => !proposal.places.some(p => p.id === place.id))) {
    throw new TypeError("Grounded places must match the proposal.");
  }
  const mandatory = proposal.places.filter(place => place.importance === "mandatory").map(place => place.id);
  if (new Set(confirmedMandatoryIds).size !== confirmedMandatoryIds.length
    || mandatory.some(id => !confirmedMandatoryIds.includes(id)) || confirmedMandatoryIds.some(id => !mandatory.includes(id))) {
    throw new AdventureIntentError("adventure_mandatory_confirmation_required", "Review and explicitly confirm the required places before routing.");
  }
  if (hardWaypoints.some(point => point.constraint_strength !== undefined && point.constraint_strength !== "exact")) {
    throw new TypeError("Only existing exact points may enter the hard-anchor list.");
  }
  const waypoints = hardWaypoints.map(point => ({ ...structuredClone(point), constraint_strength: "exact" }));
  if (waypoints.some(point => point.approach_override != null || point.maximum_best_effort_distance_m != null)
    || new Set(waypoints.map(point => point.id)).size !== waypoints.length) throw new TypeError("Invalid existing exact points.");
  const byCoordinate = new Map(waypoints.map(point => [key(point.coordinate), point.id]));
  // Model IDs are data, including strings such as "__proto__". They never
  // address an object's prototype or inherited JavaScript properties.
  const bindings = Object.create(null), targets = [], exclusions = Object.create(null);
  for (const place of grounding.places.filter(place => confirmedMandatoryIds.includes(place.id))) {
    if (place.status !== "grounded" || !place.approach || ["private", "restricted"].includes(place.access_status)) {
      throw new AdventureIntentError("adventure_mandatory_unresolved", `The required place “${place.location.name}” has no checked usable approach in this region.`);
    }
    const coordinate = place.approach.coordinate, duplicate = byCoordinate.get(key(coordinate));
    const id = duplicate ?? `adventure/${place.id}`;
    bindings[place.id] = id;
    if (!duplicate) {
      waypoints.push({ id, name: place.local_name ?? place.location.name, coordinate, constraint_strength: "exact",
        access_search_radius_m: 500, maximum_best_effort_distance_m: null, approach_override: null });
      byCoordinate.set(key(coordinate), id);
    }
  }
  // Stable priority ordering bounds the canonical request without losing a
  // proposed-place outcome in the companion assessment.
  const optional = grounding.places.filter(place => !confirmedMandatoryIds.includes(place.id))
    .sort((a, b) => b.priority - a.priority || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  for (const place of optional) {
    if (place.status !== "grounded" || !place.approach) { exclusions[place.id] = place.status; continue; }
    const duplicate = byCoordinate.get(key(place.semantic_coordinate));
    if (duplicate) { bindings[place.id] = duplicate; continue; }
    if (waypoints.length >= 30) { exclusions[place.id] = "higher_priority_request_limit"; continue; }
    const id = `adventure/${place.id}`;
    if (waypoints.some(point => point.id === id)) throw new TypeError("Adventure and existing point identities conflict.");
    waypoints.push({ id, name: place.local_name ?? place.location.name, coordinate: place.semantic_coordinate,
      constraint_strength: "approach", access_search_radius_m: 500, maximum_best_effort_distance_m: null,
      approach_override: place.approach.coordinate });
    targets.push({ ...place, id, proposal_id: place.id }); bindings[place.id] = id;
    byCoordinate.set(key(place.semantic_coordinate), id);
  }
  if (fixed && (proposal.intent.activity !== fixed.routing_profile || proposal.intent.topology !== fixed.topology
    || proposal.intent.target_distance_m !== fixed.distance_objective.target_m || proposal.intent.tolerance_m !== fixed.distance_objective.tolerance_m
    || proposal.intent.order !== fixed.waypoint_order)) throw new AdventureIntentError("adventure_hard_intent_changed", "The revision changed confirmed route requirements.");
  const topology = fixed?.topology ?? proposal.intent.topology;
  const request = validateLocalWaypointRouteRequest({ schema_version: 1, kind: "waypoint_route", name: proposal.name,
    start: fixed?.start ?? start, end: topology === "loop" ? null : fixed?.end ?? end,
    topology, routing_profile: fixed?.routing_profile ?? proposal.intent.activity,
    candidate_count: fixed?.candidate_count ?? proposal.intent.alternatives, seed: fixed?.seed ?? seed,
    endpoint_snap_policy: fixed?.endpoint_snap_policy ?? endpointSnapPolicy,
    distance_objective: fixed?.distance_objective ?? { target_m: proposal.intent.target_distance_m,
      tolerance_m: proposal.intent.tolerance_m, maximum_m: null, priority: "balanced" },
    preferences: fixed?.preferences ?? { nature: proposal.wishes.some(w => ["woodland", "urban", "water"].includes(w.metric)) ? "prefer" : "off",
      path_selection: "shortest", loop_geometry: topology === "loop" ? "prefer" : "off" },
    waypoint_order: fixed?.waypoint_order ?? proposal.intent.order, waypoints,
  }, { adventure: true });
  return deepFreeze({ request, targets, bindings, exclusions });
}
