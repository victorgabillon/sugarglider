import { haversineDistance } from "./local_plan_geometry.js";
import { canonicalFixed } from "./canonical_numbers.js";

export const ELEVATION_SAMPLING_VERSION = "routed-distance-v1";
export const MAX_ELEVATION_SAMPLES = 2048;
export const MAX_ELEVATION_VERTICES = 20000;

// Exact-coordinate identity: magic + BE uint32 count + BE binary64 lon/lat.
// Unlike candidate signatures, no coordinate rounding enters this digest.
export async function elevationGeometryDigest(geometry) {
  validateGeometry(geometry);
  const magic = new TextEncoder().encode("sugarglider-route-geometry-v1\0");
  const bytes = new Uint8Array(magic.length + 4 + geometry.length * 16); bytes.set(magic);
  const view = new DataView(bytes.buffer); view.setUint32(magic.length, geometry.length);
  geometry.forEach(([lon, lat], index) => {
    view.setFloat64(magic.length + 4 + index * 16, lon === 0 ? 0 : lon);
    view.setFloat64(magic.length + 12 + index * 16, lat === 0 ? 0 : lat);
  });
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, "0")).join("");
}

export async function sampleElevationGeometry(geometry, distance) {
  validateGeometry(geometry);
  if (!Number.isFinite(distance) || distance <= 0 || distance > 200000) throw Error("elevation_route_distance_unsupported");
  const interval = Math.max(50, distance / 2047);
  const count = distance > 50 * 2047 ? 2048 : Math.ceil(distance / 50) + 1;
  const lengths = []; let measured = 0;
  for (let i = 1; i < geometry.length; i++) {
    if (Math.abs(geometry[i][0] - geometry[i - 1][0]) > 180) throw Error("elevation_dateline_unsupported");
    const length = haversineDistance(geometry[i - 1], geometry[i]); lengths.push(length); measured += length;
  }
  if (!(measured > 0)) throw Error("elevation_geometry_degenerate");
  const cumulative = [0];
  for (const length of lengths) cumulative.push(cumulative.at(-1) + length * distance / measured);
  cumulative[cumulative.length - 1] = distance;
  let edge = 0; const samples = [];
  for (let index = 0; index < count; index++) {
    const progress = index === count - 1 ? distance : index * interval;
    while (edge < lengths.length - 1 && cumulative[edge + 1] <= progress) edge++;
    const width = cumulative[edge + 1] - cumulative[edge];
    const fraction = width > 0 ? Math.min(1, Math.max(0, (progress - cumulative[edge]) / width)) : 1;
    const start = geometry[edge], end = geometry[edge + 1];
    const coordinate = index === 0 ? geometry[0] : index === count - 1 ? geometry.at(-1)
      : [start[0] + fraction * (end[0] - start[0]), start[1] + fraction * (end[1] - start[1])];
    samples.push([progress, Number(canonicalFixed(coordinate[1], 6)), Number(canonicalFixed(coordinate[0], 6))]);
  }
  return { geometry_sha256: await elevationGeometryDigest(geometry), sampling_interval_m: interval, samples };
}
function validateGeometry(geometry) {
  if (!Array.isArray(geometry) || geometry.length < 2 || geometry.length > MAX_ELEVATION_VERTICES
    || !geometry.every(p => Array.isArray(p) && p.length === 2 && Number.isFinite(p[0]) && Math.abs(p[0]) <= 180
      && Number.isFinite(p[1]) && Math.abs(p[1]) <= 90)) throw Error("invalid_elevation_geometry");
}
