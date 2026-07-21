"""Fixed POI rewards, conservative control gates, and lexicographic ranking."""

from collections import Counter
from dataclasses import dataclass

from sugarglider.domain.models import RouteResult
from sugarglider.planning.auto_tour.candidate_models import (
    AutoTourCandidate,
)
from sugarglider.planning.auto_tour.models import (
    CandidateScore,
    DistancePriority,
    PoiRewardBreakdown,
    TourControlComparison,
)
from sugarglider.planning.result import PlanCandidate
from sugarglider.pois.models import PoiCategory, PoiFeature

POI_BASE_REWARDS: dict[PoiCategory, float] = {
    "drinking_water": 6.0,
    "viewpoint": 5.0,
    "observation_tower": 4.5,
    "castle": 4.0,
    "archaeological_site": 3.0,
    "ruins": 3.0,
    "tourism_attraction": 1.5,
    "fountain": 0.0,
    "water_tap": 0.0,
}
CATEGORY_DIVERSITY_BONUS = 1.0
VERIFIED_WATER_ONE_TIME_BONUS = 2.0
PREFERRED_POI_ID_BOOST = 3.0
REPEATED_CATEGORY_DIMINISHING_FACTOR = 0.5
CONTROL_GATE_EPSILON = 1e-12
GLOBAL_AUTO_TOUR_MAXIMUM_DISTANCE_M = 200_000.0
FLEXIBLE_BACKTRACK_REGRESSION_LIMIT = 0.02
BALANCED_BACKTRACK_REGRESSION_LIMIT = 0.01
FLEXIBLE_REPETITION_REGRESSION_LIMIT = 0.08
BALANCED_REPETITION_REGRESSION_LIMIT = 0.02
FLEXIBLE_GEOMETRY_REGRESSION_LIMIT = 0.40
BALANCED_GEOMETRY_REGRESSION_LIMIT = 0.20


@dataclass(frozen=True)
class ScoringWeights:
    distance_error: float = 10.0
    repetition: float = 3.0
    major_road: float = 2.0
    paved: float = 1.0
    unknown_surface: float = 0.25
    trail_like: float = 1.5
    hiking_network: float = 0.75


def score_route(
    route: RouteResult,
    target_distance_m: float,
    weights: ScoringWeights | None = None,
) -> CandidateScore:
    """Return the established fixed route-quality score used by Auto Tour."""
    resolved = weights or ScoringWeights()
    distance_error_ratio = (
        abs(route.summary.distance_m - target_distance_m) / target_distance_m
    )
    repetition_penalty = (
        resolved.repetition * route.analysis.repetition.repeated_distance.share
    )
    major_road_penalty = resolved.major_road * route.analysis.major_road.share
    paved_penalty = resolved.paved * route.analysis.paved.share
    unknown_surface_penalty = (
        resolved.unknown_surface * route.analysis.unknown_surface.share
    )
    trail_like_reward = resolved.trail_like * route.analysis.trail_like.share
    hiking_network_reward = (
        resolved.hiking_network * route.analysis.official_hiking_network.share
    )
    return CandidateScore(
        total=(
            resolved.distance_error * distance_error_ratio
            + repetition_penalty
            + major_road_penalty
            + paved_penalty
            + unknown_surface_penalty
            - trail_like_reward
            - hiking_network_reward
        ),
        distance_error_ratio=distance_error_ratio,
        repetition_penalty=repetition_penalty,
        major_road_penalty=major_road_penalty,
        paved_penalty=paved_penalty,
        unknown_surface_penalty=unknown_surface_penalty,
        trail_like_reward=trail_like_reward,
        hiking_network_reward=hiking_network_reward,
    )


def canonical_auto_tour_key(
    candidate: PlanCandidate, priority: DistancePriority
) -> tuple[object, ...]:
    """Order published Auto Tours without erasing producer POI semantics."""
    selected_requested = tuple(
        stop
        for stop in candidate.selected_stops
        if stop.selection_origin == "requested"
    )
    must_visits = sum(stop.importance == "must_visit" for stop in selected_requested)
    preferred = sum(stop.importance == "prefer" for stop in selected_requested)
    diagnostics = candidate.diagnostics
    route = candidate.route
    repetition = diagnostics.repeated_distance_m
    backtracking = diagnostics.immediate_backtracking_m
    discovered_utility = candidate.score.components.get("poi_reward", 0.0)
    nature_score = (
        route.analysis.nature.nature_score
        if route.analysis.nature is not None
        else -1.0
    )
    coverage = (-must_visits, -preferred, -diagnostics.requested_stop_count)
    distance = (
        0 if diagnostics.within_tolerance else 1,
        diagnostics.target_error_m,
    )
    quality = (
        backtracking,
        repetition,
        -discovered_utility,
        -nature_score,
        candidate.id,
    )
    if priority == "strict":
        return (*distance, *coverage, *quality)
    if priority == "balanced":
        return (*coverage, *distance, *quality)
    return (
        *coverage,
        backtracking,
        repetition,
        -discovered_utility,
        -nature_score,
        *distance,
        candidate.id,
    )


def maximum_auto_tour_distance_m(
    target_distance_m: float,
    tolerance_m: float,
    *,
    priority: DistancePriority = "balanced",
    requested_maximum_distance_m: float | None = None,
) -> float:
    """Return the mode-aware hard route ceiling, capped by server policy."""
    target_derived = target_distance_m + max(
        2.0 * tolerance_m, 0.25 * target_distance_m
    )
    mode_maximum = (
        GLOBAL_AUTO_TOUR_MAXIMUM_DISTANCE_M
        if priority == "flexible"
        else target_derived
    )
    if requested_maximum_distance_m is not None:
        mode_maximum = min(mode_maximum, requested_maximum_distance_m)
    return min(mode_maximum, GLOBAL_AUTO_TOUR_MAXIMUM_DISTANCE_M)


def soft_distance_penalty(
    *,
    distance_m: float,
    target_distance_m: float,
    tolerance_m: float,
    priority: DistancePriority,
) -> float:
    """Return a continuous normalized target-distance penalty."""
    normalized_error = abs(distance_m - target_distance_m) / max(tolerance_m, 1.0)
    weight = 0.10 if priority == "flexible" else 0.50 if priority == "balanced" else 1.0
    return weight * normalized_error**2


def poi_reward(
    feature: PoiFeature,
    *,
    prior_categories: tuple[PoiCategory, ...] = (),
    verified_water_already_selected: bool = False,
    preferred_poi_ids: frozenset[str] = frozenset(),
) -> PoiRewardBreakdown:
    """Return every fixed reward component for one ordered visit."""
    base = POI_BASE_REWARDS[feature.category]
    category_count = Counter(prior_categories)[feature.category]
    diversity = CATEGORY_DIVERSITY_BONUS if category_count == 0 else 0.0
    diminishing = 1.0 / (1.0 + REPEATED_CATEGORY_DIMINISHING_FACTOR * category_count)
    verified_water = (
        feature.potability == "verified" and feature.category == "drinking_water"
    )
    water_bonus = (
        VERIFIED_WATER_ONE_TIME_BONUS
        if verified_water and not verified_water_already_selected
        else 0.0
    )
    preferred_boost = PREFERRED_POI_ID_BOOST if feature.id in preferred_poi_ids else 0.0
    total = (base + diversity) * diminishing + water_bonus + preferred_boost
    return PoiRewardBreakdown(
        base_reward=base,
        category_diversity_bonus=diversity,
        diminishing_return_multiplier=diminishing,
        verified_water_bonus=water_bonus,
        preferred_id_boost=preferred_boost,
        total=total,
    )


def marginal_utility(reward: float, estimated_detour_m: float) -> float:
    """Prefer reward while charging one utility point per estimated kilometre."""
    return reward - estimated_detour_m / 1_000.0


def compare_with_control(
    *,
    route: RouteResult,
    within_tolerance: bool,
    hard_waypoints_selected: bool,
    discovered_poi_reward: float,
    control: RouteResult,
    control_within_tolerance: bool,
    control_signature: str,
    requested_place_gain: int = 0,
    distance_priority: DistancePriority = "strict",
    maximum_distance_m: float | None = None,
    epsilon: float = CONTROL_GATE_EPSILON,
) -> TourControlComparison:
    """Apply route-quality gates before any POI reward can enter ranking."""
    if distance_priority == "strict":
        tolerance_ok = within_tolerance or not control_within_tolerance
        backtracking_limit = epsilon
        repetition_limit = epsilon
        geometry_limit = epsilon
        crossing_limit = 0
    else:
        tolerance_ok = maximum_distance_m is None or (
            route.summary.distance_m <= maximum_distance_m
        )
        backtracking_limit = (
            FLEXIBLE_BACKTRACK_REGRESSION_LIMIT
            if distance_priority == "flexible"
            else BALANCED_BACKTRACK_REGRESSION_LIMIT
        )
        repetition_limit = (
            FLEXIBLE_REPETITION_REGRESSION_LIMIT
            if distance_priority == "flexible"
            else BALANCED_REPETITION_REGRESSION_LIMIT
        )
        geometry_limit = (
            FLEXIBLE_GEOMETRY_REGRESSION_LIMIT
            if distance_priority == "flexible"
            else BALANCED_GEOMETRY_REGRESSION_LIMIT
        )
        crossing_limit = 1 if distance_priority == "flexible" else 0
    backtracking_delta = (
        route.analysis.immediate_backtrack.share
        - control.analysis.immediate_backtrack.share
    )
    repetition_delta = (
        route.analysis.repetition.repeated_distance.share
        - control.analysis.repetition.repeated_distance.share
    )
    route_geometry = route.analysis.loop_geometry
    control_geometry = control.analysis.loop_geometry
    geometry_delta: float | None = None
    crossing_delta: int | None = None
    geometry_ok = True
    if route_geometry is not None and control_geometry is not None:
        geometry_delta = (
            route_geometry.penalty_breakdown.total
            - control_geometry.penalty_breakdown.total
        )
        crossing_delta = (
            route_geometry.self_crossing_count - control_geometry.self_crossing_count
        )
        proximity_delta = (
            route_geometry.outbound_return_proximity.share
            - control_geometry.outbound_return_proximity.share
        )
        proximity_limit = 0.08 if distance_priority == "flexible" else 0.04
        if distance_priority == "strict":
            proximity_limit = epsilon
        geometry_ok = (
            geometry_delta <= geometry_limit
            and crossing_delta <= crossing_limit
            and proximity_delta <= proximity_limit
        )
    elif control_geometry is not None:
        geometry_ok = False
    positive_reward = discovered_poi_reward > epsilon
    positive_requested = requested_place_gain > 0
    reasons: set[str] = set()
    if not hard_waypoints_selected:
        reasons.add("hard_waypoints_unselected")
    if not tolerance_ok:
        reasons.add("distance_tolerance")
    if backtracking_delta > backtracking_limit:
        reasons.add("backtracking_regression")
    if repetition_delta > repetition_limit:
        reasons.add("repetition_regression")
    if not geometry_ok:
        reasons.add("geometry_regression")
    if not positive_reward and not positive_requested:
        reasons.add("no_positive_soft_objective")
    return TourControlComparison(
        control_signature=control_signature,
        target_tolerance_same_or_better=tolerance_ok,
        hard_waypoints_selected=hard_waypoints_selected,
        backtracking_delta_share=backtracking_delta,
        repetition_delta_share=repetition_delta,
        loop_geometry_penalty_delta=geometry_delta,
        self_crossing_delta=crossing_delta,
        positive_discovered_poi_reward=positive_reward,
        positive_requested_place_gain=positive_requested,
        eligible=not reasons,
        rejection_reasons=tuple(sorted(reasons)),
    )


def control_comparison(route: RouteResult, signature: str) -> TourControlComparison:
    """Describe the retained no-POI route relative to itself."""
    return TourControlComparison(
        control_signature=signature,
        target_tolerance_same_or_better=True,
        hard_waypoints_selected=True,
        backtracking_delta_share=0.0,
        repetition_delta_share=0.0,
        loop_geometry_penalty_delta=0.0,
        self_crossing_delta=0,
        positive_discovered_poi_reward=False,
        positive_requested_place_gain=False,
        eligible=True,
        rejection_reasons=(),
    )


def auto_tour_ranking_key(candidate: AutoTourCandidate) -> tuple[object, ...]:
    """Return the documented lexicographic Auto Tour recommendation order."""
    analysis = candidate.route.analysis
    geometry = analysis.loop_geometry
    nature = analysis.nature
    hard_feasible = all(visit.selected for visit in candidate.hard_point_visits)
    if candidate.distance_priority == "strict":
        return (
            0 if hard_feasible else 1,
            0 if candidate.within_tolerance else 1,
            0.0 if candidate.within_tolerance else candidate.target_error_m,
            analysis.immediate_backtrack.share,
            analysis.repetition.repeated_distance.share,
            (0, geometry.penalty_breakdown.total) if geometry is not None else (1, 0.0),
            0 if candidate.control_eligible else 1,
            -candidate.selected_must_visit_count,
            -candidate.selected_preferred_place_count,
            candidate.poi_excursion_penalty_m_equivalent,
            -candidate.total_poi_reward if candidate.control_eligible else 0.0,
            (0, -nature.nature_score) if nature is not None else (1, 0.0),
            candidate.route_score.total,
            candidate.signature,
        )
    closed = geometry is not None and geometry.closed
    highly_mixed = "auto_tour_direction_highly_mixed" in candidate.warnings or (
        geometry is not None and geometry.angular_monotonicity < 0.55
    )
    incoherent_corridor = geometry is not None and (
        geometry.outbound_return_proximity.share > 0.25
        or geometry.maximum_sector_distance_share > 0.85
    )
    non_poi_backtracking_share = (
        candidate.non_poi_backtracking_m / candidate.route.summary.distance_m
        if candidate.route.summary.distance_m > 0
        else 0.0
    )
    severe_backtracking = (
        candidate.non_poi_backtracking_m > 300.0 and non_poi_backtracking_share > 0.02
    )
    net_requested_value = (
        candidate.selected_must_visit_count * 5_000.0
        + candidate.selected_preferred_place_count * 1_500.0
        - candidate.poi_excursion_penalty_m_equivalent
    )
    return (
        0 if hard_feasible else 1,
        0 if closed else 1,
        0 if candidate.route.summary.distance_m <= candidate.maximum_distance_m else 1,
        1 if severe_backtracking else 0,
        -net_requested_value,
        non_poi_backtracking_share,
        1 if highly_mixed or incoherent_corridor else 0,
        (geometry.outbound_return_proximity.share if geometry is not None else 1.0),
        analysis.repetition.repeated_distance.share,
        (0, geometry.penalty_breakdown.total) if geometry is not None else (1, 0.0),
        -candidate.total_poi_reward,
        (0, -nature.nature_score) if nature is not None else (1, 0.0),
        candidate.soft_distance_penalty,
        0 if candidate.control_eligible else 1,
        candidate.route_score.total,
        candidate.signature,
    )
