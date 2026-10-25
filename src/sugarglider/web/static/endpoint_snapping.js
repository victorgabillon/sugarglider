// One bounded policy for native endpoint validation and canonical publication.
// Displacement is an explanation, never routed geometry or a routing fallback.
import { haversineDistance } from "./local_plan_geometry.js";

export const EXACT_ENDPOINT_M = 25;
export const NEAR_ENDPOINT_M = 150;
export const LOOP_CLOSURE_M = 25;

export function endpointSnapPolicy(value) {
  if (value === undefined) return { start: "exact", end: "exact" };
  if (!value || Array.isArray(value) || Object.keys(value).length !== 2 || !Object.hasOwn(value, "start") || !Object.hasOwn(value, "end")
    || !["near", "exact"].includes(value.start) || !["near", "exact"].includes(value.end)) {
    const error = new Error("Invalid endpoint snap policy."); error.code = "invalid_endpoint_snap_policy"; throw error;
  }
  return { start: value.start, end: value.end };
}

export function measureEndpointAdjustments(request, geometry) {
  const policy = endpointSnapPolicy(request.endpoint_snap_policy);
  return ["start", "end"].map((role, index) => {
    const requested = role === "start" || request.topology === "loop" ? request.start : request.end;
    const selectedPolicy = request.topology === "loop" ? policy.start : policy[role];
    const position = index === 0 ? geometry[0] : geometry.at(-1);
    const distance = haversineDistance([requested.lon, requested.lat], position);
    const maximum = selectedPolicy === "near" ? NEAR_ENDPOINT_M : EXACT_ENDPOINT_M;
    return { role, endpoint: request.topology === "loop" ? "start" : role,
      policy: selectedPolicy, requested_coordinate: { lat: requested.lat, lon: requested.lon, name: requested.name ?? null },
      routed_coordinate: { lat: position[1], lon: position[0], name: requested.name ?? null },
      distance_m: distance, normal_tolerance_m: EXACT_ENDPOINT_M, maximum_distance_m: maximum,
      status: exceedsSnapLimit(distance, maximum) ? "review_required" : exceedsSnapLimit(distance, EXACT_ENDPOINT_M) ? "adjusted" : "reached" };
  });
}

// One micrometre absorbs floating-point error at an inclusive metre boundary.
export function exceedsSnapLimit(distance, limit) { return distance - limit > 0.000001; }

export function endpointAdjustmentFailure(adjustments) {
  const failed = adjustments.find(item => item.status === "review_required" && item.policy === "exact")
    ?? adjustments.find(item => item.status === "review_required");
  if (!failed) return null;
  return { code: failed.policy === "near" ? "endpoint_review_required" : "endpoint_not_reached",
    details: { position: failed.role === "start" ? 0 : -1, profile: null,
      snap_distance_m: failed.distance_m, maximum_snap_distance_m: failed.maximum_distance_m,
      endpoint_proposals: adjustments.filter(item => item.status === "review_required" && item.policy === "near") } };
}

// Imports without a policy retain strict intent, including when edited later.
export function restoreEndpointSnapIntent(request, start, end) {
  const policy = endpointSnapPolicy(request.endpoint_snap_policy);
  start.snapPolicy = policy.start;
  if (end) end.snapPolicy = policy.end;
}
