// Compare measured results, never a model's claim of quality. Unknown graph
// attributes and incomplete elevation remain unknown even when diagnostics use
// numeric lower bounds for those fields elsewhere in the application.
import { deepFreeze } from "./local_candidate_evaluator.js";
import { haversineDistance } from "./local_plan_geometry.js";

const natureMetric = { woodland: "woodland", urban: "urban", water: "near_water" };
const weights = { hard: 8, high: 4, medium: 2, low: 1 };
const finite = value => Number.isFinite(value) && value >= 0;

export function assessAdventure({ proposal, grounding, request, result, bindings = {}, exclusions = {}, elevations = {} }) {
  if (result.routing_profile !== request.routing_profile || result.candidates.length > 5
    || grounding.places.length > 20) throw new TypeError("Invalid adventure assessment input.");
  const assessments = result.candidates.map(candidate => {
    const reached = new Map(candidate.reached_stops.map(stop => [stop.id, stop]));
    const dropped = new Map(candidate.dropped_stops.map(stop => [stop.id, stop]));
    const anchors = new Map(candidate.traversal.anchors.map(anchor => [anchor.id, anchor]));
    const hard = request.waypoints.filter(point => point.constraint_strength === "exact");
    const places = grounding.places.map(place => {
      const id = Object.hasOwn(bindings, place.id) ? bindings[place.id] : place.id, stop = reached.get(id), anchor = anchors.get(`exact/${id}`);
      let status = "dropped", reason = dropped.get(id)?.reason ?? (Object.hasOwn(exclusions, place.id) ? exclusions[place.id] : "not_selected_for_this_candidate"), arrival = null;
      if (place.status !== "grounded") { status = place.status; reason = place.status; }
      else if (stop) { status = "reached"; reason = null; arrival = stop.resolved_approach.graph_snap_distance_m; }
      else if (anchor && place.approach) {
        // The publication worker already projected this deliberate exact anchor
        // onto the routed line. Do not scan a long native line again on the UI.
        arrival = haversineDistance([anchor.routed_coordinate.lon, anchor.routed_coordinate.lat],
          [place.approach.coordinate.lon, place.approach.coordinate.lat]);
        const tolerance = Math.min(25, place.approach.arrival_tolerance_m);
        status = finite(arrival) && arrival <= tolerance ? "reached" : "exact_anchor_satisfied_place_arrival_unverified";
        reason = status === "reached" ? null : status;
      }
      return { id: place.id, canonical_id: id, name: place.local_name ?? place.location?.name ?? place.name ?? place.id,
        status, reason, arrival_distance_m: arrival, local_category: place.local_category,
        access_status: place.access_status, story_status: place.story_status };
    });
    const measuredStops = [...new Map(places.filter(place => place.status === "reached").map(place => [place.canonical_id, place])).values()];
    const metrics = {
      historical_places: { value: measuredStops.filter(place => ["castle", "ruins", "archaeological_site"].includes(place.local_category)).length,
        unit: "checked_mapped_places", limitation: "OSM category and checked approach; historical anecdotes are separately sourced AI text." },
      viewpoints: { value: measuredStops.filter(place => ["viewpoint", "observation_tower"].includes(place.local_category)).length,
        unit: "checked_mapped_places", limitation: "Mapped viewpoint category does not guarantee a currently open view or access." },
      interesting_stops: { value: measuredStops.length, unit: "checked_places", limitation: "Interest is proposed by the model; arrival is measured locally." },
    };
    for (const [metric, key] of Object.entries(natureMetric)) {
      const n = candidate.route.analysis.nature, value = n?.available ? n[key]?.share : null;
      metrics[metric] = { value: finite(value) ? value * 100 : null, unit: "percent_of_routed_distance",
        limitation: metric === "water" ? "Near-water overlay; no inference of drinking-water quality or availability." : "Mapped landcover, not current ground conditions." };
    }
    const elevation = elevations[candidate.id], analysis = elevation?.analysis;
    const pinned = candidate.diagnostics.details.local_routing.regional_version;
    const elevationBound = Boolean(pinned) && elevation?.candidate_id === candidate.id && analysis?.routing_profile === candidate.routing_profile
      && analysis.route_distance_m === candidate.route.summary.distance_m
      && elevation.regional_reference?.build_id === pinned?.build_id
      && elevation.regional_reference?.region_id === pinned?.region_id
      && elevation.regional_reference?.pack_id === pinned?.routing_pack_id;
    metrics.elevation_gain = { value: elevationBound && analysis.coverage === "complete" && finite(analysis.total_ascent_m) ? analysis.total_ascent_m : null,
      unit: "metres", limitation: "Measured completed candidates only; no guaranteed elevation-target search." };
    const wishes = proposal.wishes.map(wish => {
      const metric = metrics[wish.metric], value = metric?.value ?? null;
      const available = finite(value), difference = available && wish.value !== null ? value - wish.value : null;
      return { ...wish, status: available ? wish.metric === "elevation_gain" ? "measured_not_directly_optimized" : "measured" : "unavailable",
        measured_value: available ? value : null, unit: metric?.unit ?? null, difference,
        satisfied: available && wish.goal === "avoid" ? value === 0 : null,
        loss: available ? wishLoss(wish, value) : null,
        limitation: metric?.limitation ?? "Authoritative native path details for this preference are unavailable." };
    });
    const mandatoryVisits = proposal.places.filter(place => place.importance === "mandatory")
      .filter(place => hard.some(point => point.id === (Object.hasOwn(bindings, place.id) ? bindings[place.id] : place.id)));
    const hardSatisfied = candidate.diagnostics.safety_eligible
      && hard.every(point => anchors.has(`exact/${point.id}`))
      && mandatoryVisits.every(place => places.find(outcome => outcome.id === place.id)?.status === "reached");
    const measuredLoss = wishes.reduce((sum, wish) => sum + (wish.loss ?? 0) * weights[wish.importance], 0);
    return { candidate_id: candidate.id, hard_route_constraints_satisfied: hardSatisfied,
      within_distance_tolerance: candidate.diagnostics.within_tolerance, distance_m: candidate.route.summary.distance_m,
      target_error_m: candidate.diagnostics.target_error_m,
      nature: candidate.route.analysis.nature ? Object.fromEntries(["woodland", "urban", "open_natural", "unknown_landcover", "near_water", "park_or_protected"]
        .map(key => [key, candidate.route.analysis.nature[key].share])) : null,
      elevation: elevationBound ? { coverage: analysis.coverage, ascent_m: analysis.total_ascent_m, descent_m: analysis.total_descent_m,
        observed_ascent_m: analysis.observed_ascent_m, observed_descent_m: analysis.observed_descent_m } : null,
      loop_geometry: candidate.diagnostics.details.local_routing.loop_geometry ?? null,
      places, wishes, measured_preference_loss: measuredLoss,
      unknown: ["asphalt_percentage", "exact_edge_repetition", "technical_difficulty", "current_access", "surface_suitability",
        ...(!elevationBound || analysis.coverage !== "complete" ? ["complete_elevation"] : [])],
      unsupported_hard_preferences: wishes.filter(wish => wish.importance === "hard" && wish.status === "unavailable").map(wish => wish.metric) };
  });
  return deepFreeze({ region_id: grounding.region_id, build_id: grounding.build_id, assessments });
}

function wishLoss(wish, value) {
  if (wish.goal === "target" && wish.value !== null) return Math.abs(value - wish.value) / Math.max(1, wish.value);
  const normalized = Object.hasOwn(natureMetric, wish.metric) ? value / 100
    : wish.metric === "elevation_gain" ? value / 1000 : value / 20;
  return ["minimize", "avoid"].includes(wish.goal) ? normalized : -normalized;
}

export function compareAdventureAssessments(a, b) {
  return compareMeasured(a, b)
    || (a.candidate_id < b.candidate_id ? -1 : a.candidate_id > b.candidate_id ? 1 : 0);
}
function compareMeasured(a, b) {
  // Unknown is not a zero-cost achievement. Only preferences measured on both
  // candidates can establish a preference improvement; distance stays measured.
  const commonDifference = a.wishes.reduce((sum, wish) => {
    const other = b.wishes.find(item => item.metric === wish.metric && item.goal === wish.goal
      && item.value === wish.value && item.importance === wish.importance);
    return sum + (wish.loss !== null && other?.loss != null ? (wish.loss - other.loss) * weights[wish.importance] : 0);
  }, 0);
  return Number(b.hard_route_constraints_satisfied) - Number(a.hard_route_constraints_satisfied)
    || Number(b.within_distance_tolerance) - Number(a.within_distance_tolerance)
    || commonDifference
    || a.target_error_m - b.target_error_m;
}
export function adventureMeasuredImprovement(previous, revised) {
  return revised.hard_route_constraints_satisfied && compareMeasured(revised, previous) < 0;
}

// Deliberately excludes geometry, coordinates, account details and source prose.
// Place IDs/counts and routed measurements suffice for one strategy revision.
export function compactAdventureAssessment(assessment) {
  return deepFreeze({ region_id: assessment.region_id, build_id: assessment.build_id,
    candidates: assessment.assessments.map(item => ({ id: item.candidate_id,
      hard_route_constraints_satisfied: item.hard_route_constraints_satisfied, distance_m: item.distance_m,
      target_error_m: item.target_error_m, within_distance_tolerance: item.within_distance_tolerance,
      nature: item.nature, elevation: item.elevation, loop_geometry: item.loop_geometry,
      places: item.places.map(place => ({ id: place.id, status: place.status, reason: place.reason, access_status: place.access_status })),
      wishes: item.wishes.map(({ metric, status, measured_value, unit, difference }) => ({ metric, status, measured_value, unit, difference })),
      unknown: item.unknown })) });
}
