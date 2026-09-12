import { canonicalFixed } from "./canonical_numbers.js";
import { PUBLIC_PROFILE_METADATA } from "./public_profile_metadata.js";

export const EARTH_RADIUS_M = 6_371_008.8;
const RADIANS = Math.PI / 180;

export function routedGeometryDistance(geometry) {
  let total = 0;
  for (let index = 1; index < geometry.length; index += 1) {
    total += haversineDistance(geometry[index - 1], geometry[index]);
  }
  return total;
}

export function haversineDistance([startLon, startLat], [endLon, endLat]) {
  const latDelta = (endLat - startLat) * RADIANS;
  const lonDelta = (endLon - startLon) * RADIANS;
  const value = Math.sin(latDelta / 2) ** 2
    + Math.cos(startLat * RADIANS) * Math.cos(endLat * RADIANS) * Math.sin(lonDelta / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(Math.min(1, value)));
}

export function localMetricProjection(referenceLatitude) {
  const cosine = Math.cos(referenceLatitude * RADIANS);
  if (!Number.isFinite(referenceLatitude) || Math.abs(referenceLatitude) > 90 || Math.abs(cosine) < 1e-12) {
    throw new TypeError("Invalid local projection reference latitude.");
  }
  const longitudeScale = EARTH_RADIUS_M * cosine;
  return Object.freeze({
    project: ([lon, lat]) => [longitudeScale * (lon * RADIANS), EARTH_RADIUS_M * (lat * RADIANS)],
    unproject: ([x, y]) => [(x / longitudeScale) * (180 / Math.PI), (y / EARTH_RADIUS_M) * (180 / Math.PI)],
  });
}

// Geometry signatures use precisely the public Python signature contract.
// Rounding is only for identity text; the stored/exported line stays untouched.
export async function localCandidateSignature(geometry, profile, topology) {
  if (!Object.hasOwn(PUBLIC_PROFILE_METADATA, profile) || !["loop", "point_to_point"].includes(topology)) {
    throw new TypeError("Invalid local candidate identity.");
  }
  const source = `${topology}:${profile}:geometry:` + geometry
    .map(([lon, lat]) => `${canonicalFixed(lon, 6)},${canonicalFixed(lat, 6)}`).join(";");
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(source));
  return "geometry:" + Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

// Same classification as planning/direction/analysis.py, on complete routed
// geometry. These thresholds describe orientation, never graph overlap.
export function canonicalRouteDirection(geometry, topology) {
  if (topology === "point_to_point") return "start_to_end";
  if (geometry.length < 4 || haversineDistance(geometry[0], geometry.at(-1)) > 50) return "complex_loop";
  const positions = samePosition(geometry[0], geometry.at(-1)) ? geometry.slice(0, -1) : geometry;
  if (positions.length < 3) return "complex_loop";
  const projection = localMetricProjection(positions[0][1]);
  const origin = projection.project(positions[0]);
  const projected = positions.map((point) => {
    const [x, y] = projection.project(point);
    return [x - origin[0], y - origin[1]];
  });
  let signedArea = 0, absoluteArea = 0, perimeter = 0;
  for (let index = 0; index < projected.length; index += 1) {
    const left = projected[index], right = projected[(index + 1) % projected.length];
    const cross = left[0] * right[1] - right[0] * left[1];
    signedArea += cross;
    absoluteArea += Math.abs(cross);
    perimeter += Math.hypot(right[0] - left[0], right[1] - left[1]);
  }
  signedArea /= 2; absoluteArea /= 2;
  if (Math.abs(signedArea) < 1_000 || perimeter <= 0
    || Math.abs(signedArea) / (perimeter * perimeter) < 0.002
    || absoluteArea <= 0 || Math.abs(signedArea) / absoluteArea < 0.35) return "complex_loop";
  return signedArea > 0 ? "counterclockwise" : "clockwise";
}

export function locateOnRoutedGeometry(geometry, coordinate) {
  const projection = localMetricProjection(geometry[0][1]);
  const points = geometry.map(projection.project);
  const [x, y] = projection.project([coordinate.lon, coordinate.lat]);
  const lengths = [];
  let total = 0, bestDistance = Infinity, along = 0;
  for (let index = 1; index < points.length; index += 1) {
    const [ax, ay] = points[index - 1], [bx, by] = points[index];
    const dx = bx - ax, dy = by - ay, squared = dx * dx + dy * dy;
    const length = Math.sqrt(squared);
    const t = squared > 0 ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / squared)) : 0;
    const distance = (x - (ax + t * dx)) ** 2 + (y - (ay + t * dy)) ** 2;
    if (distance < bestDistance) { bestDistance = distance; along = total + length * t; }
    lengths.push(length); total += length;
  }
  // Match linear referencing followed by interpolation, including first-match
  // ties. Do not use semantic proximity as evidence that a stop was reached.
  let traversed = 0, located = points[0];
  for (let index = 0; index < lengths.length; index += 1) {
    const length = lengths[index];
    if (length > 0 && along <= traversed + length) {
      const t = Math.max(0, Math.min(1, (along - traversed) / length));
      const left = points[index], right = points[index + 1];
      located = [left[0] + t * (right[0] - left[0]), left[1] + t * (right[1] - left[1])];
      break;
    }
    traversed += length;
    located = points[index + 1];
  }
  const [lon, lat] = projection.unproject(located);
  return { route_progress: total > 0 ? along / total : 0, coordinate: { lat, lon, name: null }, distance_m: Math.sqrt(bestDistance) };
}

export function canonicalTraversal(request, geometry, reachedStops = [], approximatedStops = []) {
  const anchors = [{
    id: "endpoint/start", name: request.start.name || "Start", kind: "start",
    routed_coordinate: coordinateFromPosition(geometry[0], request.start.name),
    semantic_coordinate: canonicalCoordinate(request.start), route_progress: 0,
    constraint_strength: "exact", outcome: "reached",
  }];
  const exact = request.kind === "auto_tour" ? request.hard_waypoints
    : request.waypoints.filter((waypoint) => waypoint.constraint_strength === "exact");
  for (const waypoint of exact) {
    const located = locateOnRoutedGeometry(geometry, waypoint.coordinate);
    anchors.push({ id: `exact/${waypoint.id}`, name: waypoint.name, kind: "exact_waypoint",
      routed_coordinate: located.coordinate, semantic_coordinate: canonicalCoordinate(waypoint.coordinate),
      route_progress: located.route_progress, constraint_strength: "exact", outcome: "reached" });
  }
  const soft = request.kind === "auto_tour" ? request.requested_stops
    : request.waypoints.filter((waypoint) => waypoint.constraint_strength !== "exact");
  const strengths = new Map(soft.map((stop) => [stop.id, stop.constraint_strength]));
  for (const stop of reachedStops) {
    if (!["requested", "user_preferred"].includes(stop.selection_origin) && stop.selection_method === "already_reached") continue;
    anchors.push({ id: `stop/${stop.id}`, name: stop.name,
      kind: stop.selection_origin === "requested" ? "requested_stop" : "deliberate_discovered_stop",
      routed_coordinate: canonicalCoordinate(stop.resolved_approach.coordinate), semantic_coordinate: canonicalCoordinate(stop.semantic_coordinate),
      route_progress: stop.route_progress, constraint_strength: strengths.get(stop.id) ?? null, outcome: "reached" });
  }
  for (const stop of approximatedStops) {
    anchors.push({ id: `stop/${stop.id}`, name: stop.name, kind: "approximated_stop",
      routed_coordinate: canonicalCoordinate(stop.resolved_approach.coordinate), semantic_coordinate: canonicalCoordinate(stop.semantic_coordinate),
      route_progress: stop.route_progress, constraint_strength: strengths.get(stop.id) ?? "best_effort", outcome: "approximated" });
  }
  if (request.topology === "point_to_point") {
    anchors.push({ id: "endpoint/end", name: request.end.name || "End", kind: "end",
      routed_coordinate: coordinateFromPosition(geometry.at(-1), request.end.name),
      semantic_coordinate: canonicalCoordinate(request.end), route_progress: 1,
      constraint_strength: "exact", outcome: "reached" });
  }
  const kindOrder = (anchor) => anchor.kind === "start" ? 0 : anchor.kind === "end" ? 2 : 1;
  anchors.sort((left, right) => left.route_progress - right.route_progress
    || kindOrder(left) - kindOrder(right) || (left.id < right.id ? -1 : left.id > right.id ? 1 : 0));
  return { direction: canonicalRouteDirection(geometry, request.topology), anchors };
}

export function canonicalCoordinate(value) { return { lat: value.lat, lon: value.lon, name: value.name ?? null }; }
function coordinateFromPosition([lon, lat], name) { return { lat, lon, name: name ?? null }; }
function samePosition(left, right) { return left[0] === right[0] && left[1] === right[1]; }
