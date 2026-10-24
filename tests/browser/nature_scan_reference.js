// Test-only full-scan reference extracted from d894ef7. No boundary index,
// pruning optimization or production import uses this mathematical oracle.
// Compare in the same JS engine: trig/haversine rounding differs between V8
// releases, so cross-engine JSON float equality is not an algorithm test.
import { RegionalDataError, freezeData, requireData } from "../../src/sugarglider/web/static/regional_manifest.js";
const EARTH_RADIUS_M = 6_371_008.8;
const MAX_ANALYSIS_OPERATIONS = 4_000_000;
const PRIMARY_CLASSES = ["urban", "water", "woodland", "open_natural", "agriculture"];
const LOCAL_NATURE_WEIGHTS = { woodland: 1, open_natural: .85, agriculture: .3,
  park_or_protected: .2, near_water: .15, urban: -1, unknown: -.1 };

export function scanNatureReference(manifest, nature, candidate, identity) {
  const project = regionalProjection(manifest, nature);
  const projectedBounds = [...project(manifest.bounds.slice(0, 2)), ...project(manifest.bounds.slice(2))];
  const items = nature.features.map(feature => {
    const polygons = (feature.geometry.type === "Polygon" ? [feature.geometry.coordinates] : feature.geometry.coordinates)
      .map(polygon => polygon.map(ring => ring.map(project)));
    return { feature, polygons, bounds: boundsOf(polygons.flat(2)) };
  });
  const natureTree = spatialTree(items);
  function analyzeNature(candidate) {
    requireData(Number.isFinite(candidate.distance_m) && candidate.distance_m > 0
      && Array.isArray(candidate.geometry) && candidate.geometry.length >= 2 && candidate.geometry.length <= 20_000
      && candidate.geometry.every(validPosition), "invalid_routed_geometry");
    if (candidate.pack_id !== identity.routing_pack_id) return unavailableNature(candidate.distance_m, "nature_routing_pack_mismatch");
    if (nature === null) return unavailableNature(candidate.distance_m, "nature_index_unavailable");
    const points = candidate.geometry.map(project);
    // Match project_geometry_edges: haversine edge lengths normalized to the
    // authoritative routed total; the regional projection is for intersections.
    const lengths = candidate.geometry.slice(1).map((point, index) => geographicDistance(candidate.geometry[index], point));
    const totalLength = lengths.reduce((sum, length) => sum + length, 0);
    if (totalLength <= 0) return unavailableNature(candidate.distance_m, "nature_degenerate_geometry");
    const distances = Object.fromEntries([...PRIMARY_CLASSES, "unknown", "park_or_protected", "near_water"].map((key) => [key, 0]));
    const work = { remaining: MAX_ANALYSIS_OPERATIONS };
    let outside = false;
    try {
      for (let index = 0; index < lengths.length; index += 1) {
        if (lengths[index] === 0) continue;
        const a = points[index]; const b = points[index + 1];
        const edgeBounds = boundsOf([a, b]);
        const nearby = queryTree(natureTree, expandBounds(edgeBounds, 100), [], work);
        const intervals = Object.fromEntries([...PRIMARY_CLASSES, "park_or_protected", "near_water"].map((key) => [key, []]));
        const coverage = rectangleIntervals(a, b, projectedBounds);
        if (intervalLength(coverage) < 1 - 1e-10) outside = true;
        for (const item of nearby) {
          if (overlaps(item.bounds, edgeBounds)) {
            const spans = polygonIntervals(a, b, item.polygons, work);
            if (item.feature.primary_class !== null) intervals[item.feature.primary_class].push(...spans);
            if (item.feature.park_or_protected) intervals.park_or_protected.push(...spans);
          }
          if (item.feature.primary_class === "water") {
            intervals.near_water.push(...polygonIntervals(a, b, item.polygons, work));
            for (const ring of item.polygons.flat()) {
              for (let vertex = 1; vertex < ring.length; vertex += 1) {
                spend(work);
                intervals.near_water.push(...capsuleIntervals(a, b, ring[vertex - 1], ring[vertex], 100));
              }
            }
          }
        }
        const merged = Object.fromEntries(Object.entries(intervals).map(([key, spans]) => [key, unionIntervals(spans)]));
        const cuts = [...new Set([0, 1, ...coverage.flat(), ...Object.values(merged).flat(2)])].sort((left, right) => left - right);
        const normalizedDistance = candidate.distance_m * lengths[index] / totalLength;
        for (let cut = 1; cut < cuts.length; cut += 1) {
          spend(work);
          const middle = (cuts[cut - 1] + cuts[cut]) / 2;
          const covered = inIntervals(middle, coverage);
          const category = covered ? PRIMARY_CLASSES.find((key) => inIntervals(middle, merged[key])) ?? "unknown" : "unknown";
          const distance = normalizedDistance * (cuts[cut] - cuts[cut - 1]);
          distances[category] += distance;
          if (covered && inIntervals(middle, merged.park_or_protected)) distances.park_or_protected += distance;
          if (covered && inIntervals(middle, merged.near_water)) distances.near_water += distance;
        }
      }
    } catch (error) {
      if (!(error instanceof RegionalDataError)) throw error;
      return unavailableNature(candidate.distance_m, error.code, MAX_ANALYSIS_OPERATIONS - work.remaining);
    }
    // Normalize the final rounding residual without attributing uncovered distance.
    distances.unknown = Math.max(0, candidate.distance_m - PRIMARY_CLASSES.reduce((sum, key) => sum + distances[key], 0));
    const metric = (value) => ({ distance_m: value, share: value / candidate.distance_m });
    const breakdown = Object.fromEntries(Object.entries(LOCAL_NATURE_WEIGHTS)
      .map(([key, weight]) => [key, 50 * weight * distances[key] / candidate.distance_m]));
    return freezeData({
      available: true, identity, method: "normalized_routed_edge_polygon_intervals",
      woodland: metric(distances.woodland), open_natural: metric(distances.open_natural),
      agriculture: metric(distances.agriculture), water_crossing: metric(distances.water), urban: metric(distances.urban),
      unknown_landcover: metric(distances.unknown), park_or_protected: metric(distances.park_or_protected), near_water: metric(distances.near_water),
      nature_score: Math.max(0, Math.min(100, 50 + Object.values(breakdown).reduce((sum, points) => sum + points, 0))),
      score_components: breakdown, operation_count: MAX_ANALYSIS_OPERATIONS - work.remaining,
      operation_budget: MAX_ANALYSIS_OPERATIONS,
      warnings: outside ? ["nature_index_route_partly_outside"] : [],
    });
  }
  return analyzeNature(candidate);
}

function unavailableNature(distance, reason, operations = null) {
  const zero = { distance_m: 0, share: 0 };
  return freezeData({ available: false, identity: null, method: null, woodland: zero, open_natural: zero,
    agriculture: zero, water_crossing: zero, urban: zero, unknown_landcover: { distance_m: distance, share: 1 },
    park_or_protected: null, near_water: null, nature_score: null, score_components: null,
    operation_count: operations, operation_budget: MAX_ANALYSIS_OPERATIONS, warnings: [reason] });
}

function regionalProjection(manifest, nature) {
  const reference = nature?.metadata.reference_latitude ?? (manifest.bounds[1] + manifest.bounds[3]) / 2;
  const longitudeScale = EARTH_RADIUS_M * Math.cos(reference * Math.PI / 180) * Math.PI / 180;
  const latitudeScale = EARTH_RADIUS_M * Math.PI / 180;
  return ([lon, lat]) => [(lon - manifest.bounds[0]) * longitudeScale, (lat - manifest.bounds[1]) * latitudeScale];
}

function* projectedNatureItems(nature, project) {
  const work = { remaining: 40_000_000 };
  for (const feature of nature?.features ?? []) {
    const polygons = feature.geometry.type === "Polygon" ? [feature.geometry.coordinates] : feature.geometry.coordinates;
    const projected = polygons.map((polygon) => polygon.map((ring) => ring.map(project)));
    for (const polygon of projected) validateProjectedPolygon(polygon, work);
    yield { feature, polygons: projected, bounds: boundsOf(projected.flat(2)) };
  }
}

function spatialTree(items) {
  if (items.length === 0) return null;
  const bounds = [...items[0].bounds];
  for (const item of items) {
    bounds[0] = Math.min(bounds[0], item.bounds[0]); bounds[1] = Math.min(bounds[1], item.bounds[1]);
    bounds[2] = Math.max(bounds[2], item.bounds[2]); bounds[3] = Math.max(bounds[3], item.bounds[3]);
  }
  if (items.length <= 16) return { bounds, items };
  const axis = bounds[2] - bounds[0] >= bounds[3] - bounds[1] ? 0 : 1;
  const sorted = [...items].sort((a, b) => a.bounds[axis] + a.bounds[axis + 2] - b.bounds[axis] - b.bounds[axis + 2]);
  const middle = Math.floor(sorted.length / 2);
  return { bounds, left: spatialTree(sorted.slice(0, middle)), right: spatialTree(sorted.slice(middle)) };
}

function queryTree(tree, bounds, result = [], work = null) {
  if (work) spend(work);
  if (!tree || !overlaps(tree.bounds, bounds)) return result;
  if (tree.items) {
    for (const item of tree.items) { if (work) spend(work); if (overlaps(item.bounds, bounds)) result.push(item); }
  } else { queryTree(tree.left, bounds, result, work); queryTree(tree.right, bounds, result, work); }
  return result;
}

function polygonIntervals(a, b, polygons, work) {
  const spans = [];
  for (const polygon of polygons) {
    const cuts = [0, 1];
    for (const ring of polygon) {
      for (let i = 1; i < ring.length; i += 1) { spend(work); cuts.push(...segmentCuts(a, b, ring[i - 1], ring[i])); }
    }
    const sorted = [...new Set(cuts)].sort((x, y) => x - y);
    for (let i = 1; i < sorted.length; i += 1) {
      const p = interpolate(a, b, (sorted[i - 1] + sorted[i]) / 2);
      if (inRing(p, polygon[0], work) >= 0 && polygon.slice(1).every((ring) => inRing(p, ring, work) <= 0)) spans.push([sorted[i - 1], sorted[i]]);
    }
  }
  return unionIntervals(spans);
}

function segmentCuts(a, b, c, d) {
  const u = subtract(b, a); const v = subtract(d, c); const w = subtract(c, a);
  const divisor = cross(u, v);
  if (Math.abs(divisor) < 1e-10) {
    if (Math.abs(cross(w, u)) > 1e-7) return [];
    const squared = dot(u, u);
    if (squared === 0) return [];
    return [dot(w, u) / squared, dot(subtract(d, a), u) / squared].filter((t) => t > 0 && t < 1);
  }
  const t = cross(w, v) / divisor; const s = cross(w, u) / divisor;
  return t > 0 && t < 1 && s >= 0 && s <= 1 ? [t] : [];
}

function inRing(p, ring, work) {
  let inside = false;
  for (let i = 1; i < ring.length; i += 1) {
    spend(work);
    const a = ring[i - 1]; const b = ring[i];
    const delta = subtract(b, a); const relative = subtract(p, a);
    if (Math.abs(cross(delta, relative)) <= 1e-7 && dot(relative, subtract(p, b)) <= 1e-7) return 0;
    if ((a[1] > p[1]) !== (b[1] > p[1]) && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
  }
  return inside ? 1 : -1;
}

function capsuleIntervals(a, b, c, d, radius) {
  const spans = [...circleIntervals(a, b, c, radius), ...circleIntervals(a, b, d, radius)];
  const v = subtract(d, c); const length = Math.hypot(...v);
  if (length > 0) {
    const transform = (p) => [dot(subtract(p, c), v) / length, cross(v, subtract(p, c)) / length];
    spans.push(...rectangleIntervals(transform(a), transform(b), [0, -radius, length, radius]));
  }
  return spans;
}

function circleIntervals(a, b, center, radius) {
  const u = subtract(b, a); const offset = subtract(a, center);
  const aa = dot(u, u); const bb = 2 * dot(u, offset); const cc = dot(offset, offset) - radius * radius;
  const discriminant = bb * bb - 4 * aa * cc;
  if (aa === 0 || discriminant < 0) return [];
  const root = Math.sqrt(discriminant);
  const low = Math.max(0, (-bb - root) / (2 * aa)); const high = Math.min(1, (-bb + root) / (2 * aa));
  return low < high ? [[low, high]] : [];
}

function rectangleIntervals(a, b, bounds) {
  let low = 0; let high = 1;
  for (let axis = 0; axis < 2; axis += 1) {
    const delta = b[axis] - a[axis];
    if (delta === 0) { if (a[axis] < bounds[axis] || a[axis] > bounds[axis + 2]) return []; }
    else {
      const first = (bounds[axis] - a[axis]) / delta; const last = (bounds[axis + 2] - a[axis]) / delta;
      low = Math.max(low, Math.min(first, last)); high = Math.min(high, Math.max(first, last));
    }
  }
  return low < high ? [[low, high]] : [];
}

function unionIntervals(spans) {
  const result = [];
  for (const [low, high] of spans.sort((a, b) => a[0] - b[0] || a[1] - b[1])) {
    if (high <= low) continue;
    if (result.length && low <= result.at(-1)[1]) result.at(-1)[1] = Math.max(result.at(-1)[1], high);
    else result.push([low, high]);
  }
  return result;
}

function validPosition(p) { return Array.isArray(p) && p.length === 2 && p.every(Number.isFinite) && Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90; }

function boundsOf(points) {
  const box = [Infinity, Infinity, -Infinity, -Infinity];
  for (const p of points) {
    box[0] = Math.min(box[0], p[0]); box[1] = Math.min(box[1], p[1]);
    box[2] = Math.max(box[2], p[0]); box[3] = Math.max(box[3], p[1]);
  }
  return box;
}

function expandBounds(box, distance) { return [box[0] - distance, box[1] - distance, box[2] + distance, box[3] + distance]; }

function overlaps(a, b) { return a[0] <= b[2] && a[1] <= b[3] && a[2] >= b[0] && a[3] >= b[1]; }

function inIntervals(t, spans) { return spans.some(([low, high]) => low <= t && t <= high); }

function intervalLength(spans) { return spans.reduce((sum, [low, high]) => sum + high - low, 0); }

function subtract(a, b) { return [a[0] - b[0], a[1] - b[1]]; }

function dot(a, b) { return a[0] * b[0] + a[1] * b[1]; }

function cross(a, b) { return a[0] * b[1] - a[1] * b[0]; }

function interpolate(a, b, t) { return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]; }

function metricDistance(a, b) { return Math.hypot(a[0] - b[0], a[1] - b[1]); }

function geographicDistance(a, b) {
  const rad = Math.PI / 180;
  const h = Math.sin((b[1] - a[1]) * rad / 2) ** 2
    + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin((b[0] - a[0]) * rad / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.atan2(Math.sqrt(h), Math.sqrt(Math.max(0, 1 - h)));
}

function spend(work) { requireData(work.remaining > 0, "nature_analysis_budget_exhausted"); work.remaining -= 1; }
