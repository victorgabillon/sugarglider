export const formatDistance = (metres) => `${(Number(metres) / 1000).toFixed(2)} km`;
export const formatPercent = (share) => `${(Number(share) * 100).toFixed(1)}%`;
export const formatCount = (value) => new Intl.NumberFormat().format(Number(value));

const labels = {
  direct_order: "Direct mandatory order",
  round_trip_detour: "Round-trip detour",
  sector_balanced_detour: "Sector-balanced detour",
  alternative_leg_beam: "Alternative-leg beam",
  within_tolerance: "Within tolerance",
  best_effort: "Best effort",
  infeasible: "Mandatory route infeasible",
  edge_id_coverage_incomplete: "Some route edges have no graph edge ID.",
  backtrack_edge_id_coverage_insufficient: "Backtracking coverage is incomplete.",
  low_overlap_edge_id_coverage_insufficient: "Low-overlap comparison has incomplete edge coverage.",
  low_overlap_leg_budget_exhausted: "The alternative-leg request budget was exhausted.",
  low_overlap_no_complete_candidate: "No complete low-overlap assembly was available.",
  candidate_diversity_relaxed: "Candidate diversity was relaxed to fill the requested count.",
  nature_index_unavailable: "Mapped nature was requested, but the local nature index is unavailable.",
  nature_analysis_incomplete: "Mapped nature could not be evaluated for every candidate.",
  nature_index_route_partly_outside: "Part of the route is outside the local nature index and remains unknown.",
  nature_no_candidate_improvement: "No eligible candidate improved the mapped nature score; the original recommendation was preserved.",
  loop_geometry_analysis_incomplete: "Loop geometry could not be evaluated for every candidate.",
  loop_geometry_no_candidate_improvement: "No eligible candidate strictly improved the loop-geometry penalty; the previous recommendation was preserved.",
  loop_geometry_route_not_closed: "The routed geometry is not closed within the 25 m analysis tolerance.",
  loop_geometry_degenerate: "The routed geometry is too degenerate for every loop-shape metric.",
  loop_geometry_area_unavailable: "No positive enclosed polygon face could be measured.",
  auto_tour_poi_index_unavailable: "The local POI index is unavailable; the tour contains no POI claims.",
  auto_tour_nature_index_unavailable: "The local nature index is unavailable; nature remains not evaluated.",
  auto_tour_isochrone_unavailable: "The isochrone was unavailable; headed GraphHopper round-trip controls were used.",
  graphhopper_round_trip_sampled: "Sampled GraphHopper round trip",
  corridor_continuation: "Corridor continuation repair",
  flexible: "Flexible",
  balanced: "Balanced",
  strict: "Strict",
  must_visit: "Must visit",
  prefer: "Prefer",
  already_on_route: "Already on route",
  deliberately_routed_close_enough: "Deliberately routed close enough",
  not_reached: "Not reached",
  snapped_outside_visit_radius: "Snapped route remained outside radius",
  auto_tour_isochrone_geometry_repaired: "GraphHopper's isochrone needed a topology repair before skeleton construction.",
  auto_tour_no_safe_poi_improvement: "No POI insertion passed every conservative control gate.",
  auto_tour_no_safe_water_insertion: "No verified-water insertion passed every conservative control gate.",
  auto_tour_route_budget_exhausted: "A strict Auto Tour route-request budget was exhausted.",
  low_overlap_not_natural_improvement: "This alternative is retained only as a trade-off and is not recommendable.",
};

export const friendlyLabel = (value) => labels[value] ?? value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
export const constructionLabel = (value) => labels[value] ?? friendlyLabel(value);

export function metricRows(rows) {
  return `<dl class="metric-grid">${rows.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd>`).join("")}</dl>`;
}

export function escapeHtml(value) {
  const element = document.createElement("span");
  element.textContent = String(value);
  return element.innerHTML;
}

export function lowOverlapLabel(candidate) {
  if (candidate.construction !== "alternative_leg_beam") return "Natural standard control";
  if (candidate.rank === 1) return "Refined natural recommendation";
  return "Refined comparison";
}
