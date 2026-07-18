"""Local route-corridor POI collection, rewards, and deterministic shortlists."""

from dataclasses import dataclass
from math import hypot

from shapely.geometry import Point

from sugarglider.domain.models import Coordinate, GeoJsonPosition
from sugarglider.pois.index import PoiIndex, PoiRouteMatch
from sugarglider.pois.models import PoiCategory, PoiFeature
from sugarglider.tours.models import (
    AutoTourRequest,
    PoiRejectionReason,
    PoiRewardBreakdown,
    RejectedPoiOpportunity,
    TourPoiVisit,
)
from sugarglider.tours.scoring import marginal_utility, poi_reward

SCENIC_CORRIDOR_RADIUS_M = 600.0
VERIFIED_WATER_CORRIDOR_RADIUS_M = 350.0
MAX_POI_SHORTLIST = 18
MAX_VERIFIED_WATER_SHORTLIST = 6
MAX_REJECTED_POI_OPPORTUNITIES = 12

POI_VISIT_RADII_M: dict[PoiCategory, float] = {
    "viewpoint": 150.0,
    "observation_tower": 120.0,
    "castle": 200.0,
    "ruins": 150.0,
    "archaeological_site": 150.0,
    "tourism_attraction": 120.0,
    "drinking_water": 50.0,
    "fountain": 0.0,
    "water_tap": 0.0,
}


@dataclass(frozen=True)
class TourPoiSettings:
    scenic_corridor_radius_m: float = SCENIC_CORRIDOR_RADIUS_M
    verified_water_corridor_radius_m: float = VERIFIED_WATER_CORRIDOR_RADIUS_M
    include_broad_attractions: bool = False
    shortlist_limit: int = MAX_POI_SHORTLIST
    verified_water_shortlist_limit: int = MAX_VERIFIED_WATER_SHORTLIST

    def __post_init__(self) -> None:
        if not 50 <= self.scenic_corridor_radius_m <= 2_000:
            raise ValueError("scenic POI corridor must be between 50 and 2000 metres")
        if not 25 <= self.verified_water_corridor_radius_m <= 1_000:
            raise ValueError("water POI corridor must be between 25 and 1000 metres")
        if not 1 <= self.shortlist_limit <= MAX_POI_SHORTLIST:
            raise ValueError("POI shortlist limit must be between 1 and 18")
        if not 1 <= self.verified_water_shortlist_limit <= 6:
            raise ValueError("water POI shortlist limit must be between 1 and 6")


@dataclass(frozen=True)
class PoiOpportunity:
    match: PoiRouteMatch
    visit_radius_m: float
    insertion_index: int
    estimated_detour_m: float
    reward: PoiRewardBreakdown
    marginal_utility: float


@dataclass(frozen=True)
class InsertedPoiRecord:
    estimated_detour_m: float
    actual_distance_delta_m: float | None
    marginal_utility: float


@dataclass(frozen=True)
class PoiShortlist:
    matches: tuple[PoiRouteMatch, ...]
    already_collected: tuple[TourPoiVisit, ...]
    opportunities: tuple[PoiOpportunity, ...]
    rejected: tuple[RejectedPoiOpportunity, ...]


def visit_radius(feature: PoiFeature) -> float | None:
    """Return a positive close-enough radius only for preference-eligible POIs."""
    if feature.category == "drinking_water" and feature.potability != "verified":
        return None
    radius = POI_VISIT_RADII_M[feature.category]
    return radius if radius > 0 else None


def shortlist_route_pois(
    *,
    index: PoiIndex | None,
    route_geometry: tuple[GeoJsonPosition, ...],
    routing_points: tuple[Coordinate, ...],
    request: AutoTourRequest,
    settings: TourPoiSettings,
) -> PoiShortlist:
    """Collect zero-cost visits and return at most 18 insertion opportunities."""
    if index is None:
        return PoiShortlist((), (), (), ())
    preferred = frozenset(request.preferred_poi_ids)
    scenic = index.query_near_route(
        route_geometry,
        settings.scenic_corridor_radius_m,
        groups=("scenic",),
        include_broad_attractions=True,
        limit=500,
    )
    water = index.query_near_route(
        route_geometry,
        settings.verified_water_corridor_radius_m,
        groups=("hydration",),
        include_broad_attractions=False,
        limit=200,
    )
    matches = tuple(
        sorted(
            {
                match.feature.id: match
                for match in (*scenic, *water)
                if _preference_enabled(match.feature, request, preferred, settings)
            }.values(),
            key=_match_key,
        )
    )
    already = build_poi_visits(
        matches=matches,
        preferred_poi_ids=preferred,
        base_already_ids=frozenset(match.feature.id for match in matches),
        inserted_records={},
    )
    already = tuple(
        visit for visit in already if visit.visit_distance_m <= visit.visit_radius_m
    )
    already_ids = frozenset(visit.poi.id for visit in already)
    prior_categories = tuple(visit.poi.category for visit in already)
    water_seen = any(
        visit.poi.category == "drinking_water" and visit.poi.potability == "verified"
        for visit in already
    )
    opportunities: list[PoiOpportunity] = []
    rejected: list[RejectedPoiOpportunity] = list(
        _preferred_rejections(index, route_geometry, request, settings)
    )
    for match in matches:
        if match.feature.id in already_ids:
            continue
        # GraphHopper round-trip controls expose routed geometry but no stable
        # intermediate routing-point sequence. They may claim incidental visits,
        # but PR11 must not invent insertion anchors for them.
        if len(routing_points) < 2:
            continue
        radius = visit_radius(match.feature)
        if radius is None:
            continue
        insertion_index, detour = estimate_insertion(
            index=index,
            route_geometry=route_geometry,
            routing_points=routing_points,
            match=match,
        )
        reward = poi_reward(
            match.feature,
            prior_categories=prior_categories,
            verified_water_already_selected=water_seen,
            preferred_poi_ids=preferred,
        )
        utility = marginal_utility(reward.total, detour)
        if utility <= 0:
            rejected.append(
                RejectedPoiOpportunity(
                    poi_id=match.feature.id,
                    display_name=match.feature.display_name,
                    category=match.feature.category,
                    reason_code="reward_too_low",
                    estimated_detour_m=detour,
                    nearest_route_distance_m=match.distance_m,
                )
            )
            continue
        opportunities.append(
            PoiOpportunity(match, radius, insertion_index, detour, reward, utility)
        )
    opportunities.sort(
        key=lambda opportunity: (
            -opportunity.reward.total,
            opportunity.estimated_detour_m,
            opportunity.match.route_progress_share,
            opportunity.match.feature.id,
        )
    )
    retained: list[PoiOpportunity] = []
    water_count = 0
    for opportunity in opportunities:
        is_water = opportunity.match.feature.category == "drinking_water"
        if is_water and water_count >= settings.verified_water_shortlist_limit:
            rejected.append(_rejected(opportunity, "duplicate_category_value"))
            continue
        if len(retained) >= settings.shortlist_limit:
            rejected.append(_rejected(opportunity, "route_budget_exhausted"))
            continue
        retained.append(opportunity)
        if is_water:
            water_count += 1
    rejected.sort(
        key=lambda item: (
            item.nearest_route_distance_m,
            item.estimated_detour_m,
            item.poi_id,
        )
    )
    return PoiShortlist(
        matches,
        already,
        tuple(retained),
        tuple(rejected[:MAX_REJECTED_POI_OPPORTUNITIES]),
    )


def build_poi_visits(
    *,
    matches: tuple[PoiRouteMatch, ...],
    preferred_poi_ids: frozenset[str],
    base_already_ids: frozenset[str],
    inserted_records: dict[str, InsertedPoiRecord],
) -> tuple[TourPoiVisit, ...]:
    """Measure close-enough visits and assign rewards in route-progress order."""
    visits: list[TourPoiVisit] = []
    categories: list[PoiCategory] = []
    water_seen = False
    for match in sorted(matches, key=_match_key):
        radius = visit_radius(match.feature)
        if radius is None or match.distance_m > radius:
            continue
        record = inserted_records.get(match.feature.id)
        breakdown = poi_reward(
            match.feature,
            prior_categories=tuple(categories),
            verified_water_already_selected=water_seen,
            preferred_poi_ids=preferred_poi_ids,
        )
        categories.append(match.feature.category)
        if (
            match.feature.category == "drinking_water"
            and match.feature.potability == "verified"
        ):
            water_seen = True
        already = match.feature.id in base_already_ids
        inserted = record is not None
        visits.append(
            TourPoiVisit(
                poi=match.feature,
                visit_distance_m=match.distance_m,
                visit_radius_m=radius,
                already_on_route=already,
                inserted=inserted,
                estimated_detour_m=(
                    record.estimated_detour_m if record is not None else 0.0
                ),
                actual_distance_delta_m=(
                    record.actual_distance_delta_m if record is not None else 0.0
                ),
                reward=breakdown.total,
                reward_breakdown=breakdown,
                marginal_utility=(
                    record.marginal_utility if record is not None else breakdown.total
                ),
                route_progress_share=match.route_progress_share,
                reason=(
                    "inserted_close_enough"
                    if inserted
                    else "already_on_route"
                    if already
                    else "overlapping_neighborhood"
                ),
            )
        )
    return tuple(visits)


def query_collectible_matches(
    *,
    index: PoiIndex,
    route_geometry: tuple[GeoJsonPosition, ...],
    request: AutoTourRequest,
    settings: TourPoiSettings,
) -> tuple[PoiRouteMatch, ...]:
    """Re-query exact final-route distances for all preference-eligible POIs."""
    preferred = frozenset(request.preferred_poi_ids)
    matches = (
        *index.query_near_route(
            route_geometry,
            settings.scenic_corridor_radius_m,
            groups=("scenic",),
            include_broad_attractions=True,
            limit=500,
        ),
        *index.query_near_route(
            route_geometry,
            settings.verified_water_corridor_radius_m,
            groups=("hydration",),
            limit=200,
        ),
    )
    return tuple(
        sorted(
            {
                match.feature.id: match
                for match in matches
                if _preference_enabled(match.feature, request, preferred, settings)
            }.values(),
            key=_match_key,
        )
    )


def estimate_insertion(
    *,
    index: PoiIndex,
    route_geometry: tuple[GeoJsonPosition, ...],
    routing_points: tuple[Coordinate, ...],
    match: PoiRouteMatch,
) -> tuple[int, float]:
    """Estimate a monotone insertion slot and projected triangle detour."""
    if len(routing_points) < 2:
        raise ValueError("POI insertion requires a routed point sequence")
    projection = index.projection
    line = projection.project_line(route_geometry)
    progress: list[float] = []
    previous = 0.0
    for index_value, point in enumerate(routing_points):
        if index_value == len(routing_points) - 1 and _same_point(
            point, routing_points[0]
        ):
            value = 1.0
        else:
            metric = Point(projection.project_position((point.lon, point.lat)))
            value = float(line.project(metric) / line.length)
        previous = max(previous, value)
        progress.append(previous)
    insertion_index = next(
        (
            index_value
            for index_value in range(1, len(progress))
            if match.route_progress_share <= progress[index_value]
        ),
        len(routing_points) - 1,
    )
    start = routing_points[insertion_index - 1]
    end = routing_points[insertion_index]
    start_xy = projection.project_position((start.lon, start.lat))
    end_xy = projection.project_position((end.lon, end.lat))
    poi_xy = projection.project_position(
        (match.feature.coordinate.lon, match.feature.coordinate.lat)
    )
    detour = max(
        0.0,
        _distance(start_xy, poi_xy)
        + _distance(poi_xy, end_xy)
        - _distance(start_xy, end_xy),
    )
    return insertion_index, detour


def _preference_enabled(
    feature: PoiFeature,
    request: AutoTourRequest,
    preferred: frozenset[str],
    settings: TourPoiSettings,
) -> bool:
    if feature.id in preferred:
        return True
    if feature.group == "hydration":
        return request.drinking_water_preference == "prefer"
    if feature.category == "tourism_attraction":
        return (
            request.scenic_preference == "prefer" and settings.include_broad_attractions
        )
    return request.scenic_preference == "prefer"


def _preferred_rejections(
    index: PoiIndex,
    route_geometry: tuple[GeoJsonPosition, ...],
    request: AutoTourRequest,
    settings: TourPoiSettings,
) -> tuple[RejectedPoiOpportunity, ...]:
    line = index.projection.project_line(route_geometry)
    rejected: list[RejectedPoiOpportunity] = []
    for poi_id in request.preferred_poi_ids:
        feature = index.get_feature(poi_id)
        if feature is None:
            continue
        point = Point(
            index.projection.project_position(
                (feature.coordinate.lon, feature.coordinate.lat)
            )
        )
        distance = float(line.distance(point))
        radius = (
            settings.verified_water_corridor_radius_m
            if feature.group == "hydration"
            else settings.scenic_corridor_radius_m
        )
        reason: PoiRejectionReason | None = None
        if feature.access_status == "private":
            reason = "private_access"
        elif feature.potability == "non_potable":
            reason = "non_potable"
        elif visit_radius(feature) is None:
            reason = "reward_too_low"
        elif distance > radius:
            reason = "outside_corridor"
        if reason is not None:
            rejected.append(
                RejectedPoiOpportunity(
                    poi_id=feature.id,
                    display_name=feature.display_name,
                    category=feature.category,
                    reason_code=reason,
                    estimated_detour_m=max(0.0, 2 * distance),
                    nearest_route_distance_m=distance,
                )
            )
    return tuple(rejected)


def _rejected(
    opportunity: PoiOpportunity, reason: PoiRejectionReason
) -> RejectedPoiOpportunity:
    return RejectedPoiOpportunity(
        poi_id=opportunity.match.feature.id,
        display_name=opportunity.match.feature.display_name,
        category=opportunity.match.feature.category,
        reason_code=reason,
        estimated_detour_m=opportunity.estimated_detour_m,
        nearest_route_distance_m=opportunity.match.distance_m,
    )


def _match_key(match: PoiRouteMatch) -> tuple[float, str, str, str]:
    return (
        match.route_progress_share,
        match.feature.category,
        match.feature.display_name.casefold(),
        match.feature.id,
    )


def _distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return hypot(left[0] - right[0], left[1] - right[1])


def _same_point(left: Coordinate, right: Coordinate) -> bool:
    return (left.lat, left.lon) == (right.lat, right.lon)
