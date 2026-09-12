import {
  REGIONAL_INDEX_MAX_EXPANDED_BYTES, RegionalDataError, boundedText,
  containsPosition, freezeData, requireData, requireFields, verifyRegionalBytes,
} from "./regional_manifest.js";

const EARTH_RADIUS_M = 6_371_008.8;
const MAX_FEATURES = 250_000;
const MAX_POSITIONS = 2_000_000;
const MAX_ANALYSIS_OPERATIONS = 4_000_000;
const PRIMARY_CLASSES = Object.freeze(["urban", "water", "woodland", "open_natural", "agriculture"]);
const CATEGORIES = Object.freeze(["viewpoint", "castle", "ruins", "archaeological_site", "observation_tower", "tourism_attraction", "drinking_water", "fountain", "water_tap"]);
const ACCESS = Object.freeze(["public", "unknown", "private", "restricted"]);
const POTABILITY = Object.freeze(["verified", "unknown", "non_potable", "not_applicable"]);
const APPROACH_KINDS = Object.freeze(["exact_feature", "drinking_water_source", "viewpoint_location", "mapped_entrance", "mapped_gate", "public_path_boundary", "nearby_public_path", "user_override", "strict_graph_snap"]);
const APPROACH_SOURCES = Object.freeze(["osm_feature", "osm_entrance", "osm_gate", "osm_path_intersection", "osm_spatial_boundary_inference", "imported_coordinate", "user_override"]);
const PROVENANCE = Object.freeze(["feature_geometry", "way_boundary_node", "relation_boundary_node", "shared_path_boundary_node", "spatial_boundary_inferred", "imported_coordinate", "user_override"]);

export async function decodeRegionalIndex(bytes, descriptor) {
  await verifyRegionalBytes(bytes, descriptor);
  let reader;
  try {
    reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip")).getReader();
    const decoder = new TextDecoder("utf-8", { fatal: true });
    let size = 0;
    let text = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      requireData(size <= REGIONAL_INDEX_MAX_EXPANDED_BYTES, "regional_index_too_large");
      text += decoder.decode(value, { stream: true });
    }
    return JSON.parse(text + decoder.decode());
  } catch (error) {
    await reader?.cancel().catch(() => {});
    if (error instanceof RegionalDataError) throw error;
    throw new RegionalDataError("invalid_regional_index");
  } finally { reader?.releaseLock(); }
}

export function createLocalRegionData(manifest, { pois = null, nature = null } = {}) {
  if (pois !== null) validatePoiDocument(pois, manifest);
  if (nature !== null) validateNatureDocument(nature, manifest);
  freezeData(nature);
  const reference = nature?.metadata.reference_latitude ?? (manifest.bounds[1] + manifest.bounds[3]) / 2;
  const longitudeScale = EARTH_RADIUS_M * Math.cos(reference * Math.PI / 180) * Math.PI / 180;
  const latitudeScale = EARTH_RADIUS_M * Math.PI / 180;
  const project = ([lon, lat]) => [(lon - manifest.bounds[0]) * longitudeScale, (lat - manifest.bounds[1]) * latitudeScale];
  const projectedBounds = [...project(manifest.bounds.slice(0, 2)), ...project(manifest.bounds.slice(2))];
  const validationWork = { remaining: 40_000_000 };
  const natureItems = (nature?.features ?? []).map((feature) => {
    const polygons = feature.geometry.type === "Polygon" ? [feature.geometry.coordinates] : feature.geometry.coordinates;
    const projected = polygons.map((polygon) => polygon.map((ring) => ring.map(project)));
    for (const polygon of projected) validateProjectedPolygon(polygon, validationWork);
    return { feature, polygons: projected, bounds: boundsOf(projected.flat(2)) };
  });
  const natureTree = spatialTree(natureItems);
  const poiFeatures = freezeData(pois?.features ?? []);
  const poiTree = spatialTree(poiFeatures.map((feature) => {
    const point = project([feature.coordinate.lon, feature.coordinate.lat]);
    return { feature, bounds: [...point, ...point] };
  }));
  const byId = new Map(poiFeatures.map((feature) => [feature.id, feature]));
  const identity = freezeData({
    region_id: manifest.region_id,
    build_id: manifest.build_id,
    routing_pack_id: manifest.components.routing.component_id,
    routing_sha256: manifest.components.routing.files[1].sha256,
    bounds: [...manifest.bounds],
    poi_component_id: pois === null ? null : manifest.components.pois.component_id,
    nature_component_id: nature === null ? null : manifest.components.nature.component_id,
    poi_count: poiFeatures.length,
    nature_count: natureItems.length,
  });

  function queryPois({ center, radius_m, limit = 64, requested_ids = [] }) {
    requireData(validCoordinate(center) && Number.isFinite(radius_m) && radius_m > 0 && radius_m <= 60_000
      && Number.isSafeInteger(limit) && limit >= 1 && limit <= 64
      && Array.isArray(requested_ids) && requested_ids.length <= 8
      && requested_ids.every((id) => typeof id === "string" && id.length <= 100), "invalid_local_poi_query");
    const p = project([center.lon, center.lat]);
    const bounds = [p[0] - radius_m, p[1] - radius_m, p[0] + radius_m, p[1] + radius_m];
    const matches = queryTree(poiTree, bounds).map(({ feature }) => feature)
      .filter((feature) => containsPosition(manifest.bounds, [feature.coordinate.lon, feature.coordinate.lat])
        && metricDistance(p, project([feature.coordinate.lon, feature.coordinate.lat])) <= radius_m)
      .sort((left, right) => metricDistance(p, project([left.coordinate.lon, left.coordinate.lat]))
        - metricDistance(p, project([right.coordinate.lon, right.coordinate.lat])) || compareText(left.id, right.id));
    const requested = requested_ids.map((id) => ({ id, feature: byId.get(id) ?? null }));
    return freezeData({ available: pois !== null, requested, features: matches.slice(0, limit), truncated: matches.length > limit, identity });
  }

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
    const breakdown = Object.fromEntries(Object.entries({ woodland: 1, open_natural: 0.85, agriculture: 0.3,
      park_or_protected: 0.2, near_water: 0.15, urban: -1, unknown: -0.1 })
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

  return Object.freeze({ identity, queryPois, analyzeNature });
}

export function unavailableNature(distance, reason, operations = null) {
  const zero = { distance_m: 0, share: 0 };
  return freezeData({ available: false, identity: null, method: null, woodland: zero, open_natural: zero,
    agriculture: zero, water_crossing: zero, urban: zero, unknown_landcover: { distance_m: distance, share: 1 },
    park_or_protected: null, near_water: null, nature_score: null, score_components: null,
    operation_count: operations, operation_budget: MAX_ANALYSIS_OPERATIONS, warnings: [reason] });
}

export function eligibleLocalPoi(feature, bounds) {
  if (!feature) return "poi_not_found";
  if (["private", "restricted"].includes(feature.access_status)) return "poi_access_restricted";
  if (feature.potability === "non_potable") return "poi_non_potable";
  if (feature.group === "hydration" && feature.potability !== "verified") return "poi_potability_unverified";
  if (!containsPosition(bounds, [feature.coordinate.lon, feature.coordinate.lat])) return "poi_outside_region";
  if (!feature.approach_candidates.some((approach) => containsPosition(bounds, [approach.coordinate.lon, approach.coordinate.lat]))) return "poi_no_covered_meaningful_approach";
  return null;
}

function validateDocument(document, manifest, version, metadataFields) {
  requireFields(document, ["metadata", "features"]);
  requireFields(document.metadata, metadataFields);
  const metadata = document.metadata;
  requireData(metadata.format_version === version && metadata.source_basename === manifest.source.basename
    && metadata.source_size_bytes === manifest.source.byte_size
    && JSON.stringify(metadata.bounding_box) === JSON.stringify(manifest.bounds)
    && Array.isArray(document.features) && document.features.length <= MAX_FEATURES
    && metadata.feature_count === document.features.length);
}

function validatePoiDocument(document, manifest) {
  validateDocument(document, manifest, 2, ["format_version", "source_basename", "source_size_bytes", "feature_count", "category_counts", "potability_counts", "access_counts", "approach_counts", "bounding_box", "skipped_invalid_count", "build_configuration", "classifier_version"]);
  requireFields(document.metadata.build_configuration, ["classifier_version", "geometry_policy", "identity_policy", "include_non_potable"]);
  const config = document.metadata.build_configuration;
  requireData(document.metadata.classifier_version === "1" && config.classifier_version === "1"
    && config.geometry_policy === "semantic-point_with-bounded-public-approaches" && config.identity_policy === "osm-type-and-id"
    && typeof config.include_non_potable === "boolean" && nonnegative(document.metadata.skipped_invalid_count, true));
  let previous = "";
  const counts = { category_counts: {}, potability_counts: {}, access_counts: {}, approach_counts: {} };
  for (const feature of document.features) {
    requireFields(feature, ["id", "osm_type", "osm_id", "coordinate", "category", "secondary_categories", "group", "display_name", "name_source", "scenic_confidence", "potability", "access_status", "ruins", "tags", "source_updated_at", "warnings", "approach_candidates"]);
    requireData(osmIdentity(feature.osm_type, feature.osm_id) === feature.id && feature.id > previous
      && validCoordinate(feature.coordinate) && CATEGORIES.includes(feature.category)
      && boundedText(feature.display_name, 1000) && ["name", "category_fallback"].includes(feature.name_source)
      && ["primary", "broad", "none"].includes(feature.scenic_confidence) && POTABILITY.includes(feature.potability)
      && ACCESS.includes(feature.access_status) && typeof feature.ruins === "boolean"
      && (feature.source_updated_at === null || boundedText(feature.source_updated_at, 100))
      && sortedStrings(feature.warnings) && Array.isArray(feature.secondary_categories)
      && feature.secondary_categories.every((category) => CATEGORIES.includes(category) && category !== feature.category)
      && new Set(feature.secondary_categories).size === feature.secondary_categories.length
      && feature.group === (CATEGORIES.indexOf(feature.category) >= 6 ? "hydration" : "scenic")
      && Array.isArray(feature.tags) && feature.tags.length <= 100
      && Array.isArray(feature.approach_candidates) && feature.approach_candidates.length <= 8);
    previous = feature.id;
    let previousTag = "";
    for (const tag of feature.tags) {
      requireData(Array.isArray(tag) && tag.length === 2 && boundedText(tag[0], 200) && tag[0] > previousTag && typeof tag[1] === "string" && tag[1].length <= 10_000);
      previousTag = tag[0];
    }
    let previousApproach = "";
    for (const approach of feature.approach_candidates) {
      requireFields(approach, ["id", "coordinate", "kind", "source", "access", "semantic_distance_m", "graph_snap_distance_m", "arrival_tolerance_m", "name", "osm_type", "osm_id", "provenance", "warnings"]);
      requireData(boundedText(approach.id, 320) && approach.id > previousApproach && validCoordinate(approach.coordinate)
        && APPROACH_KINDS.includes(approach.kind) && APPROACH_SOURCES.includes(approach.source) && PROVENANCE.includes(approach.provenance)
        && ["public", "unknown"].includes(approach.access) && !["private", "restricted"].includes(feature.access_status)
        && nonnegative(approach.semantic_distance_m) && (approach.graph_snap_distance_m === null || nonnegative(approach.graph_snap_distance_m))
        && Number.isFinite(approach.arrival_tolerance_m) && approach.arrival_tolerance_m > 0 && approach.arrival_tolerance_m <= 100
        && (approach.name === null || boundedText(approach.name, 200))
        && (approach.osm_type === null && approach.osm_id === null || osmIdentity(approach.osm_type, approach.osm_id) !== null)
        && sortedStrings(approach.warnings));
      previousApproach = approach.id;
      increment(counts.approach_counts, approach.kind);
    }
    increment(counts.category_counts, feature.category);
    increment(counts.potability_counts, feature.potability);
    increment(counts.access_counts, feature.access_status);
  }
  for (const [key, expected] of Object.entries(counts)) requireCounts(document.metadata[key], expected);
}

function validateNatureDocument(document, manifest) {
  validateDocument(document, manifest, 1, ["format_version", "source_basename", "source_size_bytes", "source_mtime_ns", "reference_latitude", "bounding_box", "category_counts", "feature_count"]);
  requireData(manifest.bounds[3] - manifest.bounds[1] <= 10 && document.metadata.source_mtime_ns === null && Number.isFinite(document.metadata.reference_latitude)
    && document.metadata.reference_latitude >= manifest.bounds[1] && document.metadata.reference_latitude <= manifest.bounds[3]);
  let previous = "";
  let positions = 0;
  const counts = {};
  for (const feature of document.features) {
    requireFields(feature, ["feature_id", "osm_id", "osm_source", "primary_class", "park_or_protected", "tags", "geometry"]);
    requireData(["way", "relation"].includes(feature.osm_source) && osmIdentity(feature.osm_source, feature.osm_id) === feature.feature_id
      && feature.feature_id > previous && (feature.primary_class === null || PRIMARY_CLASSES.includes(feature.primary_class))
      && typeof feature.park_or_protected === "boolean" && (feature.primary_class !== null || feature.park_or_protected)
      && feature.tags !== null && typeof feature.tags === "object" && !Array.isArray(feature.tags)
      && Object.entries(feature.tags).every(([key, value]) => boundedText(key, 200) && boundedText(value, 1000)));
    previous = feature.feature_id;
    if (feature.primary_class !== null) increment(counts, feature.primary_class);
    if (feature.park_or_protected) increment(counts, "park_or_protected");
    requireFields(feature.geometry, ["type", "coordinates"]);
    requireData(["Polygon", "MultiPolygon"].includes(feature.geometry.type));
    const polygons = feature.geometry.type === "Polygon" ? [feature.geometry.coordinates] : feature.geometry.coordinates;
    requireData(Array.isArray(polygons) && polygons.length > 0 && polygons.length <= MAX_POSITIONS);
    for (const polygon of polygons) {
      requireData(Array.isArray(polygon) && polygon.length > 0 && polygon.length <= MAX_POSITIONS);
      for (const ring of polygon) {
        requireData(Array.isArray(ring) && ring.length >= 4 && ring.length <= MAX_POSITIONS && ring.every(validPosition)
          && ring[0][0] === ring.at(-1)[0] && ring[0][1] === ring.at(-1)[1]);
        positions += ring.length;
        requireData(positions <= MAX_POSITIONS, "regional_index_too_large");
      }
    }
  }
  requireCounts(document.metadata.category_counts, counts);
}

function spatialTree(items) {
  if (items.length === 0) return null;
  const bounds = items.reduce((box, item) => [Math.min(box[0], item.bounds[0]), Math.min(box[1], item.bounds[1]), Math.max(box[2], item.bounds[2]), Math.max(box[3], item.bounds[3])], [...items[0].bounds]);
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

function validateProjectedPolygon(polygon, work) {
  const segments = [];
  for (let ringIndex = 0; ringIndex < polygon.length; ringIndex += 1) {
    const ring = polygon[ringIndex];
    let area = 0;
    for (let vertex = 1; vertex < ring.length; vertex += 1) {
      spend(work);
      const a = ring[vertex - 1]; const b = ring[vertex];
      // Zero-length consecutive vertices do not create a new polygon boundary.
      if (metricDistance(a, b) === 0) continue;
      area += cross(subtract(a, ring[0]), subtract(b, ring[0]));
      segments.push({ a, b, ringIndex, vertex, lastVertex: ring.length - 1, bounds: boundsOf([a, b]) });
    }
    requireData(Math.abs(area) > 1e-8, "invalid_nature_polygon");
    if (ringIndex > 0) requireData(inRing(ring[0], polygon[0], work) >= 0, "invalid_nature_polygon");
  }
  const tree = spatialTree(segments);
  for (const segment of segments) {
    for (const other of queryTree(tree, segment.bounds, [], work)) {
      if (other.ringIndex < segment.ringIndex || other.ringIndex === segment.ringIndex && other.vertex <= segment.vertex) continue;
      const { a, b } = segment; const { a: c, b: d } = other;
      const u = subtract(b, a); const v = subtract(d, c); const w = subtract(c, a);
      const divisor = cross(u, v);
      if (Math.abs(divisor) > 1e-10) {
        const t = cross(w, v) / divisor; const s = cross(w, u) / divisor;
        // Point touches are allowed; crossing interiors are not. Adjacent edges
        // meet only at endpoints and therefore never satisfy this condition.
        requireData(!(t > 1e-10 && t < 1 - 1e-10 && s > 1e-10 && s < 1 - 1e-10), "invalid_nature_polygon");
      } else if (Math.abs(cross(w, u)) < 1e-7) {
        const length = dot(u, u);
        const first = dot(w, u) / length; const second = dot(subtract(d, a), u) / length;
        requireData(Math.min(1, Math.max(first, second)) - Math.max(0, Math.min(first, second)) <= 1e-10, "invalid_nature_polygon");
      }
    }
  }
  for (let hole = 1; hole < polygon.length; hole += 1) {
    for (let other = hole + 1; other < polygon.length; other += 1) {
      requireData(inRing(polygon[hole][0], polygon[other], work) <= 0
        && inRing(polygon[other][0], polygon[hole], work) <= 0, "invalid_nature_polygon");
    }
  }
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

function requireCounts(actual, expected) {
  requireFields(actual, Object.keys(expected));
  requireData(Object.entries(expected).every(([key, count]) => actual[key] === count));
}
function increment(counts, key) { counts[key] = (counts[key] ?? 0) + 1; }
function osmIdentity(type, id) { return ["node", "way", "relation"].includes(type) && nonnegative(id, true) ? `${type}/${id}` : null; }
function nonnegative(value, integer = false) { return Number.isFinite(value) && value >= 0 && (!integer || Number.isSafeInteger(value)); }
function sortedStrings(value) { return Array.isArray(value) && value.length <= 100 && value.every((text, i) => boundedText(text, 500) && (i === 0 || value[i - 1] < text)); }
function validPosition(p) { return Array.isArray(p) && p.length === 2 && p.every(Number.isFinite) && Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90; }
function validCoordinate(p) { return p !== null && typeof p === "object" && (p.name === undefined || p.name === null) && validPosition([p.lon, p.lat]); }
function boundsOf(points) { return points.reduce((box, p) => [Math.min(box[0], p[0]), Math.min(box[1], p[1]), Math.max(box[2], p[0]), Math.max(box[3], p[1])], [Infinity, Infinity, -Infinity, -Infinity]); }
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
function compareText(a, b) { return a < b ? -1 : a > b ? 1 : 0; }
function spend(work) { requireData(work.remaining > 0, "nature_analysis_budget_exhausted"); work.remaining -= 1; }
