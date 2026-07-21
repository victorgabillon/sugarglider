"""Immutable evaluated Auto Tour candidate values."""

from math import isclose
from typing import Annotated, Self

from pydantic import Field, model_validator

from sugarglider.domain.models import (
    Coordinate,
    GeoJsonPosition,
    ImmutableModel,
    RouteResult,
)
from sugarglider.planning.auto_tour.models import (
    CandidateRole,
    CandidateScore,
    DiscoveredPoiVisit,
    DistancePriority,
    DroppedPoiStop,
    HardWaypointVisit,
    NonNegativeFloat,
    NonNegativeInt,
    PoiExcursion,
    RejectedPoiOpportunity,
    RequestedTourPlaceVisit,
    SelectedPoiStop,
    Share,
    SkeletonMethod,
    TourConstruction,
    TourControlComparison,
    TourDirection,
    TourRepairExplanation,
)
from sugarglider.routing.backend import RoutedPath


class AutoTourCandidate(ImmutableModel):
    rank: Annotated[int, Field(ge=1)]
    route: RouteResult
    routed_path: RoutedPath | None = None
    signature: str
    construction: TourConstruction
    direction: TourDirection
    skeleton_id: str
    skeleton_method: SkeletonMethod
    ellipse_bearing_degrees: float | None = None
    ellipse_aspect_ratio: Annotated[float, Field(gt=0, le=1)] | None = None
    ellipse_perimeter_scale: Annotated[float, Field(gt=0)] | None = None
    ellipse_containment_scale: Annotated[float, Field(gt=0, le=1)] | None = None
    routing_points: tuple[Coordinate, ...]
    snapped_routing_points: tuple[GeoJsonPosition, ...] | None
    hard_point_visits: tuple[HardWaypointVisit, ...]
    poi_visits: tuple[DiscoveredPoiVisit, ...]
    requested_place_visits: tuple[RequestedTourPlaceVisit, ...] = ()
    selected_stops: tuple[SelectedPoiStop, ...] = ()
    dropped_stops: tuple[DroppedPoiStop, ...] = ()
    poi_excursions: tuple[PoiExcursion, ...] = ()
    candidate_role: CandidateRole | None = None
    candidate_roles: tuple[CandidateRole, ...] = ()
    poi_excursion_physical_distance_m: NonNegativeFloat = 0.0
    poi_excursion_returning_backtracking_m: NonNegativeFloat = 0.0
    poi_excursion_repeated_distance_m: NonNegativeFloat = 0.0
    poi_excursion_penalty_m_equivalent: NonNegativeFloat = 0.0
    poi_attributed_backtracking_m: NonNegativeFloat = 0.0
    non_poi_backtracking_m: NonNegativeFloat = 0.0
    rejected_poi_opportunities: tuple[RejectedPoiOpportunity, ...] = ()
    target_error_m: NonNegativeFloat
    within_tolerance: bool
    distance_priority: DistancePriority = "flexible"
    soft_distance_penalty: NonNegativeFloat = 0.0
    maximum_distance_m: NonNegativeFloat = 0.0
    control_eligible: bool
    control_comparison: TourControlComparison
    total_poi_reward: NonNegativeFloat
    discovered_poi_reward: NonNegativeFloat
    selected_scenic_count: NonNegativeInt
    selected_verified_water_count: NonNegativeInt
    selected_must_visit_count: NonNegativeInt = 0
    selected_preferred_place_count: NonNegativeInt = 0
    route_score: CandidateScore
    repair: TourRepairExplanation | None = None
    warnings: tuple[str, ...] = ()
    direct_distance_m: NonNegativeFloat | None = None
    detour_ratio: NonNegativeFloat | None = None
    destination_progress_monotonicity: Share | None = None
    reverse_progress_distance_m: NonNegativeFloat | None = None
    reverse_progress_share: Share | None = None
    endpoint_axis_lateral_deviation_m: NonNegativeFloat | None = None
    near_parallel_corridor_share: Share | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_backtracking_partition(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        result = dict(value)
        if "candidate_roles" not in result:
            role = result.get("candidate_role")
            result["candidate_roles"] = (role,) if role is not None else ()
        if "candidate_role" not in result and result.get("candidate_roles"):
            result["candidate_role"] = result["candidate_roles"][0]
        result.setdefault(
            "poi_excursion_physical_distance_m",
            result.get("poi_excursion_repeated_distance_m", 0.0),
        )
        result.setdefault(
            "poi_excursion_returning_backtracking_m",
            result.get("poi_attributed_backtracking_m", 0.0),
        )
        if "non_poi_backtracking_m" not in result:
            route = result.get("route")
            if isinstance(route, RouteResult):
                result["non_poi_backtracking_m"] = (
                    route.analysis.immediate_backtrack.distance_m
                )
            elif isinstance(route, dict):
                analysis = route.get("analysis")
                if isinstance(analysis, dict):
                    backtrack = analysis.get("immediate_backtrack")
                    if isinstance(backtrack, dict):
                        result["non_poi_backtracking_m"] = backtrack.get(
                            "distance_m", 0.0
                        )
        return result

    @model_validator(mode="after")
    def validate_candidate_accounting(self) -> Self:
        role_order: dict[CandidateRole, int] = {
            "harmonious": 0,
            "maximum_requested_coverage": 1,
            "smooth_low_detour": 2,
        }
        if self.candidate_roles != tuple(
            sorted(set(self.candidate_roles), key=role_order.__getitem__)
        ) or self.candidate_role != (
            self.candidate_roles[0] if self.candidate_roles else None
        ):
            raise ValueError("candidate roles must be unique, ordered, and compatible")
        if self.warnings != tuple(sorted(set(self.warnings))):
            raise ValueError("Auto Tour candidate warnings must be sorted and unique")
        if self.target_error_m < 0:
            raise ValueError("target error cannot be negative")
        if self.poi_visits != tuple(
            sorted(
                self.poi_visits,
                key=lambda visit: (visit.route_progress_share, visit.poi.id),
            )
        ):
            raise ValueError("POI visits must be route-progress ordered")
        reward = sum(visit.reward for visit in self.poi_visits)
        inserted_reward = sum(
            visit.reward for visit in self.poi_visits if visit.inserted
        )
        if not isclose(self.total_poi_reward, reward, rel_tol=0, abs_tol=1e-9):
            raise ValueError("total POI reward must match visits")
        if not isclose(
            self.discovered_poi_reward, inserted_reward, rel_tol=0, abs_tol=1e-9
        ):
            raise ValueError("inserted POI reward must match visits")
        must_count = sum(
            visit.selected and visit.requested_place.importance == "must_visit"
            for visit in self.requested_place_visits
        )
        preferred_count = sum(
            visit.selected and visit.requested_place.importance == "prefer"
            for visit in self.requested_place_visits
        )
        if (
            self.selected_must_visit_count != must_count
            or self.selected_preferred_place_count != preferred_count
        ):
            raise ValueError("requested-place counts must match measured visits")
        selected_ids = tuple(stop.semantic_poi.id for stop in self.selected_stops)
        dropped_ids = tuple(stop.semantic_poi.id for stop in self.dropped_stops)
        if len(selected_ids) != len(set(selected_ids)):
            raise ValueError("selected POI IDs must be unique")
        if len(dropped_ids) != len(set(dropped_ids)):
            raise ValueError("dropped POI IDs must be unique")
        if set(selected_ids).intersection(dropped_ids):
            raise ValueError("a POI cannot be both selected and dropped")
        if self.selected_stops != tuple(
            sorted(
                self.selected_stops,
                key=lambda stop: (
                    stop.route_progress_share,
                    stop.semantic_poi.id,
                ),
            )
        ):
            raise ValueError("selected stops must be route-progress ordered")
        repeated = sum(
            excursion.physical_spur_distance_m for excursion in self.poi_excursions
        )
        physical = sum(
            excursion.physical_spur_distance_m for excursion in self.poi_excursions
        )
        returning = sum(
            excursion.returning_backtrack_distance_m
            for excursion in self.poi_excursions
        )
        penalty = sum(
            excursion.penalty_m_equivalent for excursion in self.poi_excursions
        )
        if (
            not isclose(
                self.poi_excursion_repeated_distance_m,
                repeated,
                rel_tol=0,
                abs_tol=1e-9,
            )
            or not isclose(
                self.poi_excursion_physical_distance_m,
                physical,
                rel_tol=0,
                abs_tol=1e-9,
            )
            or not isclose(
                self.poi_excursion_returning_backtracking_m,
                returning,
                rel_tol=0,
                abs_tol=1e-9,
            )
            or not isclose(
                self.poi_excursion_penalty_m_equivalent,
                penalty,
                rel_tol=0,
                abs_tol=1e-9,
            )
        ):
            raise ValueError("candidate POI excursion totals must match excursions")
        if not isclose(
            self.poi_attributed_backtracking_m + self.non_poi_backtracking_m,
            self.route.analysis.immediate_backtrack.distance_m,
            rel_tol=0,
            abs_tol=1e-6,
        ):
            raise ValueError("POI and non-POI backtracking must partition the total")
        return self
