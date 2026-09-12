import { LOCAL_NATURE_WEIGHTS } from "./local_region_data.js";
import { canonicalCoordinate, haversineDistance, locateOnRoutedGeometry } from "./local_plan_geometry.js";

// Publication consumes the final regional analysis; it never intersects polygons
// again or turns missing graph attributes into observed facts.
export function publishLocalNature(draft) {
  const source = draft.nature_analysis;
  if (!source?.available) return null;
  requireEvidence(source.identity?.routing_pack_id === draft.pack_id
    && Number.isSafeInteger(source.identity.nature_count) && source.identity.nature_count >= 0);
  const keys = ["woodland", "open_natural", "agriculture", "water_crossing", "urban", "unknown_landcover",
    "park_or_protected", "near_water"];
  for (const key of keys) {
    const metric = source[key];
    requireEvidence(metric && Number.isFinite(metric.distance_m) && metric.distance_m >= 0
      && metric.distance_m <= draft.distance_m + 1e-6 && Number.isFinite(metric.share)
      && metric.share >= 0 && metric.share <= 1 + 1e-12
      && Math.abs(metric.share * draft.distance_m - metric.distance_m) < 1e-6);
  }
  const partition = keys.slice(0, 6).reduce((sum, key) => sum + source[key].distance_m, 0);
  requireEvidence(Math.abs(partition - draft.distance_m) < 1e-6);
  const names = { woodland: "woodland_reward", open_natural: "open_natural_reward", agriculture: "agriculture_reward",
    park_or_protected: "park_or_protected_reward", near_water: "near_water_reward", urban: "urban_penalty", unknown: "unknown_penalty" };
  const breakdown = { base_score: 50 };
  let rawScore = 50;
  for (const [key, weight] of Object.entries(LOCAL_NATURE_WEIGHTS)) {
    const share = source[key === "unknown" ? "unknown_landcover" : key].share;
    const points = source.score_components?.[key];
    requireEvidence(Number.isFinite(points) && Math.abs(points - 50 * weight * share) < 1e-9);
    breakdown[names[key]] = { weight, share, points };
    rawScore += points;
  }
  requireEvidence(Number.isFinite(source.nature_score)
    && Math.abs(source.nature_score - Math.max(0, Math.min(100, rawScore))) < 1e-9);
  breakdown.raw_score = rawScore;
  breakdown.final_score = source.nature_score;
  return { available: true, index_format_version: 1, index_feature_count: source.identity.nature_count,
    ...Object.fromEntries(keys.map((key) => [key, source[key]])), nature_score: source.nature_score,
    score_breakdown: breakdown, warnings: source.warnings };
}

export function publishLocalStops(request, draft) {
  const selected = draft.selected_pois ?? [];
  const outcomes = draft.poi_outcomes ?? [];
  requireEvidence(selected.length <= 8 && outcomes.length <= 72);
  // Full indexed metadata belongs to the draft. A semantic centroid or a bare
  // OSM ID cannot substitute for an approach that the routed geometry reaches.
  const reached = selected.map((poi) => {
    const approach = poi.approach;
    requireEvidence(approach && !["private", "restricted"].includes(approach.access)
      && poi.potability !== "non_potable"
      && (!["drinking_water", "fountain", "water_tap"].includes(poi.category) || poi.potability === "verified")
      && poi.approach_id === approach.id);
    const tolerance = Math.min(approach.arrival_tolerance_m,
      ["drinking_water", "fountain", "water_tap"].includes(poi.category) ? 15 : 25);
    requireEvidence(Number.isFinite(tolerance) && tolerance > 0);
    const sourceArrival = haversineDistance(position(approach.coordinate), position(poi.routed_coordinate));
    const located = locateOnRoutedGeometry(draft.geometry, poi.routed_coordinate);
    const sourceLocated = locateOnRoutedGeometry(draft.geometry, approach.coordinate);
    requireEvidence(sourceArrival <= tolerance && sourceLocated.distance_m <= tolerance
      && located.distance_m <= 1 && selected.filter((other) => other.poi_id === poi.poi_id).length === 1);
    return { id: poi.poi_id, name: poi.name, semantic_coordinate: canonicalCoordinate(poi.semantic_coordinate),
      category: poi.category, importance: null,
      selection_origin: request.preferred_discovered_poi_ids.includes(poi.poi_id) ? "user_preferred" : "discovered",
      selection_method: "deliberate_insertion",
      resolved_approach: { ...approach, coordinate: { ...canonicalCoordinate(poi.routed_coordinate), name: null },
        graph_snap_distance_m: sourceArrival, arrival_tolerance_m: tolerance,
        semantic_distance_m: haversineDistance(position(poi.semantic_coordinate), position(poi.routed_coordinate)) },
      route_progress: located.route_progress, route_to_approach_m: located.distance_m };
  });
  reached.sort((left, right) => left.route_progress - right.route_progress || compareText(left.id, right.id));
  const reachedIds = new Set(reached.map((stop) => stop.id));
  const dropped = outcomes.filter((outcome) => outcome.semantic_coordinate && !reachedIds.has(outcome.poi_id)).map((outcome) => {
    requireEvidence(outcome.status === "dropped" && typeof outcome.reason === "string" && outcome.reason.length > 0);
    return { id: outcome.poi_id, name: outcome.name, semantic_coordinate: canonicalCoordinate(outcome.semantic_coordinate),
      category: outcome.category, importance: null, selection_origin: outcome.selection_origin,
      reason: outcome.reason, considered_approaches: [] };
  });
  requireEvidence(new Set(dropped.map((stop) => stop.id)).size === dropped.length);
  return { reached, approximated: [], dropped };
}

function position(point) { return [point.lon, point.lat]; }
function compareText(left, right) { return left < right ? -1 : left > right ? 1 : 0; }
function requireEvidence(condition) {
  if (!condition) { const error = new Error("Invalid local candidate enrichment."); error.code = "invalid_local_candidate_enrichment"; throw error; }
}
