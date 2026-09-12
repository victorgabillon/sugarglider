import { canonicalFixed } from "./canonical_numbers.js";
import { PUBLIC_PROFILE_METADATA } from "./public_profile_metadata.js";

const GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1";
const EARTH_RADIUS_M = 6_371_008.8;
export const MAX_GPX_VERTICES = 200_000;
export const MAX_GPX_STOPS = 64;
export const MAX_GPX_STOP_EDGE_CHECKS = 2_000_000;

export class LocalGpxExportError extends Error {
  constructor(code) {
    super({
      invalid_export_profile: "This route has an unknown or mismatched activity profile.",
      invalid_export_geometry: "This route does not contain a valid continuous track within the export limit.",
      invalid_export_stops: "This route has inconsistent place information and cannot be exported.",
      invalid_export_approximation: "This route has an invalid approximate stop and cannot be exported.",
      export_limit_exceeded: "This route exceeds the local GPX export limit.",
      export_stop_not_reached: "A selected place is not reached by this track within its recorded tolerance.",
      invalid_export_name: "This route has no valid export name.",
      export_busy: "Another GPX file is being prepared.",
      export_worker_unavailable: "GPX export could not start. Reload the page to try again; your route is unchanged.",
      export_timed_out: "GPX export took too long. Your route is unchanged.",
    }[code] ?? "This route could not be exported.");
    this.name = "LocalGpxExportError";
    this.code = code;
  }
}

// Export reads the already returned canonical candidate. No planning, geometry
// repair, path-detail inference, network call or application-state write occurs.
export function exportCanonicalCandidate(candidate) {
  const route = candidate?.route;
  const profile = Object.hasOwn(PUBLIC_PROFILE_METADATA, route?.routing_profile)
    ? PUBLIC_PROFILE_METADATA[route.routing_profile] : null;
  requireExport(profile && candidate.routing_profile === profile.id, "invalid_export_profile");
  requireExport(text(route.name) && Array.isArray(route.geometry)
    && route.geometry.length >= 2 && route.geometry.length <= MAX_GPX_VERTICES
    && route.geometry.every(validPosition), "invalid_export_geometry");
  requireExport(Array.isArray(candidate.reached_stops) && Array.isArray(candidate.approximated_stops)
    && Array.isArray(candidate.dropped_stops), "invalid_export_stops");
  const stops = [
    ...candidate.reached_stops.map((stop) => ({ stop, approximate: false })),
    ...candidate.approximated_stops.map((stop) => ({ stop, approximate: true })),
  ];
  requireExport(stops.length <= MAX_GPX_STOPS
    && stops.length * (route.geometry.length - 1) <= MAX_GPX_STOP_EDGE_CHECKS, "export_limit_exceeded");
  const dropped = new Set(candidate.dropped_stops.map((stop) => stop?.id));
  const ids = new Set();
  for (const { stop, approximate } of stops) {
    requireExport(stop && text(stop.id) && !ids.has(stop.id) && !dropped.has(stop.id)
      && text(stop.name) && text(stop.category) && bounded(stop.route_progress, 0, 1), "invalid_export_stops");
    ids.add(stop.id);
    const approach = stop.resolved_approach;
    requireExport(approach && text(approach.kind) && validCoordinate(approach.coordinate)
      && Number.isFinite(approach.arrival_tolerance_m) && approach.arrival_tolerance_m > 0,
    "invalid_export_stops");
    if (approximate) {
      requireExport(Number.isFinite(stop.normal_tolerance_m) && stop.normal_tolerance_m > 0
        && Number.isFinite(stop.distance_m) && stop.distance_m > stop.normal_tolerance_m
        && (stop.configured_maximum_m === null || Number.isFinite(stop.configured_maximum_m)
          && stop.configured_maximum_m > 0 && stop.distance_m <= stop.configured_maximum_m),
      "invalid_export_approximation");
    } else requireExport(Number.isFinite(stop.route_to_approach_m) && stop.route_to_approach_m >= 0,
      "invalid_export_stops");
  }
  validateStopArrivals(route.geometry, stops);
  stops.sort((left, right) => left.stop.route_progress - right.stop.route_progress
    || (left.stop.id < right.stop.id ? -1 : left.stop.id > right.stop.id ? 1 : 0));
  const name = xmlText(`${route.name} — ${profile.display_name}`);
  const activity = { walking: "hiking", running: "running", cycling: "cycling" }[profile.activity_kind];
  const parts = [
    '<?xml version="1.0" encoding="utf-8"?>',
    `<gpx xmlns="${GPX_NAMESPACE}" version="1.1" creator="Sugarglider">`,
    `<metadata><name>${name}</name><desc>Route preference based on mapped OpenStreetMap data; conditions, access and suitability must be checked locally.</desc></metadata>`,
  ];
  stops.forEach(({ stop, approximate }, index) => {
    const approach = stop.resolved_approach;
    parts.push(`<wpt lat="${fixedCoordinate(approach.coordinate.lat)}" lon="${fixedCoordinate(approach.coordinate.lon)}">`
      + `<name>${xmlText(`${index + 1}. ${stop.name}${approximate ? " — approximate" : ""}`)}</name>`
      + `<desc>${xmlText(`Visit ${index + 1}; ${stop.category}; approach ${approach.kind}.`)}</desc>`
      + `<type>${xmlText(stop.category)}</type></wpt>`);
  });
  parts.push(`<trk><name>${name}</name><type>${activity}</type><trkseg>`);
  for (const [lon, lat] of route.geometry) {
    parts.push(`<trkpt lat="${fixedCoordinate(lat)}" lon="${fixedCoordinate(lon)}"/>`);
  }
  parts.push("</trkseg></trk></gpx>");
  return { blob: new Blob(parts, { type: "application/gpx+xml" }), filename: localGpxFilename(route.name) };
}

// Same local metric projection and <=2 m reported-distance tolerance as the
// Python GPX trust boundary. This validates arrival, never changes route points.
function validateStopArrivals(geometry, stops) {
  if (!stops.length) return;
  const radians = (degrees) => degrees * (Math.PI / 180);
  const longitudeScale = EARTH_RADIUS_M * Math.cos(radians(geometry[0][1]));
  requireExport(Math.abs(longitudeScale / EARTH_RADIUS_M) >= 1e-12, "invalid_export_geometry");
  const project = ([lon, lat]) => [longitudeScale * radians(lon), EARTH_RADIUS_M * radians(lat)];
  const points = geometry.map(project);
  requireExport(points.some(([x, y]) => x !== points[0][0] || y !== points[0][1]), "invalid_export_geometry");
  for (const { stop, approximate } of stops) {
    const approach = stop.resolved_approach;
    const [x, y] = project([approach.coordinate.lon, approach.coordinate.lat]);
    let distance = Infinity;
    for (let index = 1; index < points.length; index += 1) {
      const [ax, ay] = points[index - 1];
      const [bx, by] = points[index];
      const dx = bx - ax, dy = by - ay;
      const squared = dx * dx + dy * dy;
      const t = squared > 0 ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / squared)) : 0;
      distance = Math.min(distance, Math.hypot(x - (ax + t * dx), y - (ay + t * dy)));
    }
    requireExport(distance <= approach.arrival_tolerance_m
      && (approximate || Math.abs(distance - stop.route_to_approach_m) <= 2), "export_stop_not_reached");
  }
}

// Python's .8f rounds the exact binary float to nearest, ties to even. JS
// toFixed instead rounds exact ties up. Preserve the canonical writer's output,
// including negative zero, without decimal-string or epsilon approximations.
export function fixedCoordinate(value) {
  requireExport(Number.isFinite(value) && Math.abs(value) <= 180, "invalid_export_geometry");
  return canonicalFixed(value, 8);
}

function cleanXmlText(value) { return value.replace(/[\p{Cc}\p{Cs}\uFFFE\uFFFF]/gu, ""); }
function xmlText(value) { return cleanXmlText(value).replace(/&/gu, "&amp;").replace(/</gu, "&lt;").replace(/>/gu, "&gt;"); }
export function localGpxFilename(name) {
  requireExport(text(name), "invalid_export_name");
  const cleaned = cleanXmlText(name).normalize("NFKD").replace(/[^\x00-\x7F]/gu, "").trim()
    .replace(/[<>:"/\\|?*\x00-\x1F\x7F]+/gu, "-").replace(/\s+/gu, "-")
    .replace(/-+/gu, "-").replace(/^[ ._-]+|[ ._-]+$/gu, "");
  return `${(cleaned || "sugarglider-route").slice(0, 100)}.gpx`;
}
function validPosition(point) { return Array.isArray(point) && point.length === 2 && bounded(point[0], -180, 180) && bounded(point[1], -90, 90); }
function validCoordinate(point) { return point && validPosition([point.lon, point.lat]); }
function bounded(value, minimum, maximum) { return Number.isFinite(value) && value >= minimum && value <= maximum; }
function text(value) { return typeof value === "string" && value.length > 0 && value.length <= 1000; }
function requireExport(condition, code) { if (!condition) throw new LocalGpxExportError(code); }
