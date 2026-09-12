import { createLocalAutoTourEngine, validateLocalAutoTourRequest } from "./local_auto_tour.js";
import { createLocalWaypointRouteEngine, validateLocalWaypointRouteRequest } from "./local_waypoint_route.js";
import { createLocalPlanPublisher } from "./local_plan_client.js";
import { PUBLIC_PROFILE_METADATA } from "./public_profile_metadata.js";
import { deepFreeze } from "./local_candidate_evaluator.js";
import { RegionalDataError } from "./regional_manifest.js";

export class LocalPlannerError extends Error {
  constructor(code) {
    super({
      local_routing_unavailable: "On-device routing is unavailable in this app build.",
      routing_pack_unavailable: "Download a supported offline region before planning a route.",
      no_covering_routing_pack: "The selected offline region does not cover all requested points. Choose another installed region or move the points.",
      regional_required: "Download an offline region before planning a route.",
      regional_selection_required: "Choose an installed offline region before planning a route.",
      regional_install_incomplete: "This region is not fully installed. Open Offline regions to finish or remove the incomplete installation.",
      regional_routing_unavailable: "Routing data for this region is unavailable. Open Offline regions to check the installation.",
      regional_components_unavailable: "Some data for this region is unavailable. Open Offline regions to check the installation.",
      regional_checksum_mismatch: "The installed region failed its integrity check. Open Offline regions to remove and reinstall it.",
      regional_identity_mismatch: "The installed regional components do not match. Open Offline regions to check the installation.",
      regional_storage_unavailable: "Offline storage is unavailable in this app session.",
      no_compatible_routing_pack: "No installed region supports the selected activity at these points.",
      no_route: "No connected route was found in the installed regional graph for these points.",
      routing_busy: "An on-device route calculation is still finishing. Try again shortly.",
      routing_failure: "The on-device routing engine could not finish this route.",
      endpoint_not_reached: "A required endpoint could not be reached within its strict snap limit for this activity.",
      exact_waypoint_not_reached: "An exact waypoint could not be reached within its permitted snap limit for this activity.",
      unsupported_preference: "Local Waypoint Route currently supports Shortest with nature and loop-shape preferences off. Your settings are unchanged.",
      unsupported_constraint_strength: "Local Waypoint Route currently supports exact points. Your approach or best-effort point is unchanged.",
      unsupported_profile: "The installed region does not support the selected activity.",
      unsupported_local_auto_tour_topology: "Local Auto Tour currently creates loops. Use Waypoint Route for a route with a different end point.",
      unsupported_local_auto_tour_hard_points: "Local Auto Tour does not yet support required interior points. Use Waypoint Route to preserve those exact points.",
      unsupported_local_auto_tour_requested_stops: "Local Auto Tour does not yet resolve imported requested places. Your places are unchanged; use indexed preferred places or Waypoint Route.",
      unsupported_local_excursion_allowance: "A custom POI excursion allowance is unavailable without exact edge repetition data.",
      local_generation_busy: "The previous on-device route calculation is still finishing. Try again when it finishes.",
      invalid_local_plan_request: "The local planner cannot use these request settings.",
    }[code] ?? `On-device planning could not finish (${code}).`);
    this.name = "LocalPlannerError";
    this.code = code;
  }
}

// The normal planner owns one mode search and one canonical publication per
// request. Native failures never select the web API or another routing engine.
export function createLocalPlanner({ bridge, getRegionData = async () => null, withRegion = null,
  publisher = createLocalPlanPublisher(), lifecycleTarget = globalThis } = {}) {
  const enterRegion = withRegion ?? ((run) => run({ bridge, getRegionData, reference: null }));
  let requestRegion = null;
  const route = (input) => requestRegion.bridge.route(input);
  const waypoint = createLocalWaypointRouteEngine({ route });
  const autoTour = createLocalAutoTourEngine({ route, getRegionData: (packId) => requestRegion.getRegionData(packId) });
  let active = null, generation = 0;
  function generate(rawRequest, signal) {
    if (signal?.aborted) return Promise.reject(new DOMException("Planning cancelled.", "AbortError"));
    let request, modeRequest;
    try {
      request = deepFreeze(structuredClone(rawRequest));
      modeRequest = request.kind === "waypoint_route" ? validateLocalWaypointRouteRequest(request)
        : validateLocalAutoTourPlanRequest(request);
    } catch (error) { return Promise.reject(error instanceof LocalPlannerError ? error
      : new LocalPlannerError(/^[a-z_]{1,80}$/.test(error.code) ? error.code : "invalid_local_plan_request")); }
    const identity = JSON.stringify(request);
    if (active) return active.identity === identity && active.generation === generation
      ? active.promise : Promise.reject(new LocalPlannerError("local_generation_busy"));
    const ownedGeneration = ++generation;
    const abort = () => { if (generation === ownedGeneration) invalidate(); };
    signal?.addEventListener("abort", abort, { once: true });
    const promise = search(request, modeRequest, ownedGeneration).catch((error) => {
      if (error instanceof RegionalDataError) throw new LocalPlannerError(error.code);
      throw error;
    }).finally(() => {
      signal?.removeEventListener("abort", abort);
      if (active?.generation === ownedGeneration) active = null;
    });
    active = { identity, generation: ownedGeneration, promise };
    return promise;
  }
  async function search(request, modeRequest, ownedGeneration) {
    return enterRegion(async (region) => {
      requireCurrent(ownedGeneration);
      requestRegion = region;
      try {
        const capabilities = await region.bridge.capabilities();
        requireCurrent(ownedGeneration);
        if (!capabilities?.enabled) throw new LocalPlannerError("local_routing_unavailable");
        if (!capabilities.installed_pack_count) throw new LocalPlannerError("routing_pack_unavailable");
        if (!capabilities.supported_profile_ids.includes(request.routing_profile)) throw new LocalPlannerError("unsupported_profile");
        const search = await (request.kind === "waypoint_route" ? waypoint : autoTour).generate(modeRequest);
        requireCurrent(ownedGeneration);
        if (!search) throw new DOMException("Planning cancelled.", "AbortError");
        const result = await publisher.publish(request, search, region.reference ?? null);
        requireCurrent(ownedGeneration);
        return result;
      } finally { if (requestRegion === region) requestRegion = null; }
    });
  }
  function requireCurrent(ownedGeneration) {
    if (ownedGeneration !== generation) throw new DOMException("Planning cancelled.", "AbortError");
  }
  function invalidate() {
    generation += 1;
    waypoint.invalidate(); autoTour.invalidate(); publisher.invalidate();
    // An outstanding native route drains before active clears. Cancelling the
    // page operation must not authorize an overlapping native restart.
  }
  lifecycleTarget?.addEventListener?.("pagehide", invalidate);
  return Object.freeze({ generate, invalidate });
}

export function validateLocalAutoTourPlanRequest(request) {
  const fields = ["schema_version", "kind", "name", "topology", "start", "end", "routing_profile", "candidate_count", "seed",
    "distance_objective", "preferences", "hard_waypoints", "requested_stops", "preferred_discovered_poi_ids", "free_poi_spur_physical_m"];
  requireRequest(exactFields(request, fields) && request.schema_version === 1 && request.kind === "auto_tour"
    && typeof request.name === "string" && request.name.trim().length > 0 && request.name.length <= 200
    && Object.hasOwn(PUBLIC_PROFILE_METADATA, request.routing_profile));
  if (request.topology !== "loop" || request.end !== null) throw new LocalPlannerError("unsupported_local_auto_tour_topology");
  requireRequest(Array.isArray(request.hard_waypoints) && Array.isArray(request.requested_stops));
  if (request.hard_waypoints.length) throw new LocalPlannerError("unsupported_local_auto_tour_hard_points");
  if (request.requested_stops.length) throw new LocalPlannerError("unsupported_local_auto_tour_requested_stops");
  if (request.free_poi_spur_physical_m !== 200) throw new LocalPlannerError("unsupported_local_excursion_allowance");
  const objective = request.distance_objective;
  requireRequest(exactFields(objective, ["target_m", "tolerance_m", "maximum_m", "priority"])
    && ["flexible", "balanced", "strict"].includes(objective.priority)
    && (objective.maximum_m === null || Number.isFinite(objective.maximum_m)
      && objective.maximum_m >= objective.target_m && objective.maximum_m <= 200_000)
    && (objective.priority !== "strict" || objective.maximum_m !== null && objective.maximum_m >= objective.target_m + objective.tolerance_m));
  const preferences = request.preferences;
  requireRequest(exactFields(preferences, ["nature", "path_selection", "scenic", "drinking_water", "loop_geometry", "direction"])
    && ["off", "prefer"].includes(preferences.scenic) && ["off", "prefer"].includes(preferences.drinking_water)
    && ["off", "prefer"].includes(preferences.loop_geometry) && ["shortest", "low_overlap"].includes(preferences.path_selection));
  requireRequest(exactFields(request.start, ["lat", "lon", "name"])
    && (request.start.name === null || typeof request.start.name === "string" && request.start.name.length <= 200));
  return validateLocalAutoTourRequest({ start: { lat: request.start.lat, lon: request.start.lon },
    profile: request.routing_profile, target_distance_m: objective.target_m, tolerance_m: objective.tolerance_m,
    candidate_count: request.candidate_count, seed: request.seed, direction_preference: preferences.direction,
    preferences: { nature: preferences.nature, scenic: preferences.scenic === "prefer", water: preferences.drinking_water === "prefer",
      requested_poi_ids: request.preferred_discovered_poi_ids } });
}

function exactFields(value, fields) {
  return value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === fields.length && fields.every((field) => Object.hasOwn(value, field));
}
function requireRequest(value) { if (!value) throw new LocalPlannerError("invalid_local_plan_request"); }
