"""Immutable public models for explainable skeleton-first Auto Tours."""

from math import isclose
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from sugarglider.domain.generation import (
    CandidateScore,
    LoopGeometryPreference,
    NaturePreference,
    PathSelectionMode,
)
from sugarglider.domain.models import (
    Coordinate,
    GeoJsonPosition,
    ImmutableModel,
    RouteResult,
)
from sugarglider.pois.models import PoiCategory, PoiFeature

type TourDirection = Literal["clockwise", "counterclockwise", "mixed"]
type DirectionPreference = Literal["any", "clockwise", "counterclockwise"]
type DistancePriority = Literal["flexible", "balanced", "strict"]
type RequestedPlaceImportance = Literal["must_visit", "prefer"]
type TourConstruction = Literal[
    "isochrone_ellipse",
    "graphhopper_round_trip",
    "graphhopper_round_trip_sampled",
    "poi_insertion",
    "local_repair",
    "corridor_continuation",
    "alternative_leg_repair",
]
type SkeletonMethod = Literal[
    "isochrone_ellipse",
    "graphhopper_round_trip",
    "graphhopper_round_trip_sampled",
]
type PoiRejectionReason = Literal[
    "private_access",
    "non_potable",
    "outside_corridor",
    "reward_too_low",
    "route_budget_exhausted",
    "snap_too_far",
    "distance_tolerance",
    "backtracking_regression",
    "repetition_regression",
    "geometry_regression",
    "duplicate_category_value",
]

NonNegativeFloat = Annotated[float, Field(ge=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Share = Annotated[float, Field(ge=0, le=1)]


class RequestedTourPlace(ImmutableModel):
    """A user-requested place satisfied by a measured close-enough route pass."""

    name: Annotated[str, Field(min_length=1, max_length=200)]
    coordinate: Coordinate
    visit_radius_m: Annotated[float, Field(ge=25, le=500)] = 100.0
    importance: RequestedPlaceImportance = "prefer"
    original_index: NonNegativeInt | None = None


class RequestedTourPlaceVisit(ImmutableModel):
    requested_place: RequestedTourPlace
    measured_distance_m: NonNegativeFloat
    route_progress_share: Share
    satisfied: bool
    deliberately_routed: bool
    reason: Literal[
        "already_on_route",
        "deliberately_routed_close_enough",
        "not_reached",
        "snapped_outside_visit_radius",
    ]

    @model_validator(mode="after")
    def validate_satisfaction(self) -> Self:
        expected = self.measured_distance_m <= self.requested_place.visit_radius_m
        if self.satisfied != expected:
            raise ValueError(
                "requested-place satisfaction must match measured distance"
            )
        if self.reason.endswith("close_enough") and not self.satisfied:
            raise ValueError("close-enough reason requires a satisfied requested place")
        return self


class AutoTourRequest(ImmutableModel):
    """A fixed start, optional hard anchors, and soft touring preferences."""

    name: str = "Sugarglider Auto Tour"
    start: Coordinate
    target_distance_m: Annotated[float, Field(ge=1_000, le=200_000)]
    tolerance_m: Annotated[float, Field(ge=100, le=10_000)] = 2_000
    candidate_count: Annotated[int, Field(ge=1, le=5)] = 3
    seed: int = 0
    profile: Literal["hike"] = "hike"
    direction_preference: DirectionPreference = "any"
    hard_points: Annotated[tuple[Coordinate, ...], Field(max_length=6)] = ()
    requested_places: Annotated[
        tuple[RequestedTourPlace, ...], Field(max_length=30)
    ] = ()
    preferred_poi_ids: Annotated[tuple[str, ...], Field(max_length=8)] = ()
    distance_priority: DistancePriority = "flexible"
    scenic_preference: Literal["off", "prefer"] = "prefer"
    drinking_water_preference: Literal["off", "prefer"] = "prefer"
    nature_preference: NaturePreference = "prefer"
    loop_geometry_preference: LoopGeometryPreference = "prefer"
    path_selection_mode: PathSelectionMode = "low_overlap"

    @model_validator(mode="after")
    def validate_stable_points_and_ids(self) -> Self:
        point_keys = tuple((point.lat, point.lon) for point in self.hard_points)
        if len(point_keys) != len(set(point_keys)):
            raise ValueError("Auto Tour hard points must be unique")
        if (self.start.lat, self.start.lon) in point_keys:
            raise ValueError("Auto Tour hard points must not duplicate the start")
        if any(not value.strip() for value in self.preferred_poi_ids):
            raise ValueError("preferred POI IDs must not be empty")
        if len(self.preferred_poi_ids) != len(set(self.preferred_poi_ids)):
            raise ValueError("preferred POI IDs must be unique")
        requested_keys = tuple(
            (
                place.name,
                place.coordinate.lat,
                place.coordinate.lon,
                place.original_index,
            )
            for place in self.requested_places
        )
        if len(requested_keys) != len(set(requested_keys)):
            raise ValueError("requested Auto Tour places must be unique")
        return self


class TourHardPointVisit(ImmutableModel):
    original_index: NonNegativeInt
    coordinate: Coordinate
    snapped_coordinate: GeoJsonPosition | None
    snap_distance_m: NonNegativeFloat | None
    satisfied: bool


class PoiRewardBreakdown(ImmutableModel):
    base_reward: NonNegativeFloat
    category_diversity_bonus: NonNegativeFloat
    diminishing_return_multiplier: Annotated[float, Field(gt=0, le=1)]
    verified_water_bonus: NonNegativeFloat
    preferred_id_boost: NonNegativeFloat
    total: NonNegativeFloat

    @model_validator(mode="after")
    def validate_total(self) -> Self:
        expected = (
            (self.base_reward + self.category_diversity_bonus)
            * self.diminishing_return_multiplier
            + self.verified_water_bonus
            + self.preferred_id_boost
        )
        if not isclose(self.total, expected, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("POI reward total must match its public components")
        return self


class TourPoiVisit(ImmutableModel):
    poi: PoiFeature
    visit_distance_m: NonNegativeFloat
    visit_radius_m: Annotated[float, Field(gt=0)]
    already_on_route: bool
    inserted: bool
    estimated_detour_m: NonNegativeFloat
    actual_distance_delta_m: float | None
    reward: NonNegativeFloat
    reward_breakdown: PoiRewardBreakdown
    marginal_utility: float
    route_progress_share: Share
    reason: str

    @model_validator(mode="after")
    def validate_visit_flags(self) -> Self:
        if self.already_on_route and self.inserted:
            raise ValueError("a POI visit cannot be both incidental and inserted")
        if not isclose(
            self.reward, self.reward_breakdown.total, rel_tol=0, abs_tol=1e-12
        ):
            raise ValueError("POI visit reward must match its breakdown")
        return self


class RejectedPoiOpportunity(ImmutableModel):
    poi_id: str
    display_name: str
    category: PoiCategory
    reason_code: PoiRejectionReason
    estimated_detour_m: NonNegativeFloat
    nearest_route_distance_m: NonNegativeFloat


class TourControlComparison(ImmutableModel):
    control_signature: str
    target_tolerance_same_or_better: bool
    hard_points_satisfied: bool
    backtracking_delta_share: float
    repetition_delta_share: float
    loop_geometry_penalty_delta: float | None
    self_crossing_delta: int | None
    positive_inserted_poi_reward: bool
    positive_requested_place_gain: bool = False
    eligible: bool
    rejection_reasons: tuple[str, ...]

    @model_validator(mode="after")
    def validate_reasons(self) -> Self:
        if self.rejection_reasons != tuple(sorted(set(self.rejection_reasons))):
            raise ValueError("control-comparison reasons must be sorted and unique")
        return self


class TourRepairExplanation(ImmutableModel):
    reason: Literal["corridor_continuation"]
    repeated_distance_removed_m: NonNegativeFloat
    immediate_backtracking_removed_m: NonNegativeFloat
    additional_route_distance_m: float
    requested_places_satisfied: NonNegativeInt
    added_scenic_pois: NonNegativeInt
    added_verified_water_pois: NonNegativeInt
    geometry_changed: bool


class AutoTourCandidate(ImmutableModel):
    rank: Annotated[int, Field(ge=1)]
    route: RouteResult
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
    hard_point_visits: tuple[TourHardPointVisit, ...]
    poi_visits: tuple[TourPoiVisit, ...]
    requested_place_visits: tuple[RequestedTourPlaceVisit, ...] = ()
    rejected_poi_opportunities: tuple[RejectedPoiOpportunity, ...] = ()
    target_error_m: NonNegativeFloat
    within_tolerance: bool
    distance_priority: DistancePriority = "flexible"
    soft_distance_penalty: NonNegativeFloat = 0.0
    maximum_distance_m: NonNegativeFloat = 0.0
    control_eligible: bool
    control_comparison: TourControlComparison
    total_poi_reward: NonNegativeFloat
    inserted_poi_reward: NonNegativeFloat
    selected_scenic_count: NonNegativeInt
    selected_verified_water_count: NonNegativeInt
    satisfied_must_visit_count: NonNegativeInt = 0
    satisfied_preferred_place_count: NonNegativeInt = 0
    route_score: CandidateScore
    repair: TourRepairExplanation | None = None
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_candidate_accounting(self) -> Self:
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
            self.inserted_poi_reward, inserted_reward, rel_tol=0, abs_tol=1e-9
        ):
            raise ValueError("inserted POI reward must match visits")
        must_count = sum(
            visit.satisfied and visit.requested_place.importance == "must_visit"
            for visit in self.requested_place_visits
        )
        preferred_count = sum(
            visit.satisfied and visit.requested_place.importance == "prefer"
            for visit in self.requested_place_visits
        )
        if (
            self.satisfied_must_visit_count != must_count
            or self.satisfied_preferred_place_count != preferred_count
        ):
            raise ValueError("requested-place counts must match measured visits")
        return self


class AutoTourTimings(ImmutableModel):
    isochrone_seconds: NonNegativeFloat
    skeleton_construction_seconds: NonNegativeFloat
    route_call_seconds: NonNegativeFloat
    poi_corridor_query_seconds: NonNegativeFloat
    poi_insertion_search_seconds: NonNegativeFloat
    local_repair_seconds: NonNegativeFloat
    total_seconds: NonNegativeFloat


class AutoTourSearchSummary(ImmutableModel):
    isochrone_request_count: Annotated[int, Field(ge=0, le=1)]
    round_trip_control_request_count: Annotated[int, Field(ge=0, le=8)]
    sampled_fallback_skeleton_count: NonNegativeInt = 0
    skeleton_route_request_count: Annotated[int, Field(ge=0, le=24)]
    skeleton_candidate_count: NonNegativeInt
    retained_skeleton_count: Annotated[int, Field(ge=0, le=6)]
    poi_index_candidate_count: NonNegativeInt
    already_collected_poi_count: NonNegativeInt
    poi_route_evaluation_count: Annotated[int, Field(ge=0, le=24)]
    local_repair_evaluation_count: Annotated[int, Field(ge=0, le=12)]
    corridor_repair_evaluation_count: Annotated[int, Field(ge=0, le=12)] = 0
    alternative_leg_request_count: Annotated[int, Field(ge=0, le=24)]
    total_route_request_budget: Annotated[int, Field(ge=1)]
    total_route_request_count: NonNegativeInt
    budget_exhausted: bool
    control_signature: str
    recommended_signature: str
    control_retained: bool
    selected_scenic_count: NonNegativeInt
    selected_verified_water_count: NonNegativeInt
    requested_place_satisfied_count: NonNegativeInt = 0
    requested_place_missed_count: NonNegativeInt = 0
    maximum_distance_m: NonNegativeFloat = 0.0
    route_cache_hit_count: NonNegativeInt = 0
    timings: AutoTourTimings
    warnings: tuple[str, ...]

    @model_validator(mode="after")
    def validate_accounting(self) -> Self:
        expected = (
            self.round_trip_control_request_count
            + self.skeleton_route_request_count
            + self.poi_route_evaluation_count
            + self.local_repair_evaluation_count
            + self.alternative_leg_request_count
        )
        if self.total_route_request_count != expected:
            raise ValueError("Auto Tour route-request total does not match phases")
        if self.total_route_request_count > self.total_route_request_budget:
            raise ValueError("Auto Tour exceeded its route-request budget")
        if self.corridor_repair_evaluation_count > self.local_repair_evaluation_count:
            raise ValueError("corridor repairs must be part of the local repair budget")
        if self.warnings != tuple(sorted(set(self.warnings))):
            raise ValueError("Auto Tour warnings must be sorted and unique")
        return self


class AutoTourResult(ImmutableModel):
    """Recommended candidates plus the separately retained no-POI control."""

    control: AutoTourCandidate
    candidates: tuple[AutoTourCandidate, ...]
    search: AutoTourSearchSummary

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if not self.candidates:
            raise ValueError("Auto Tour must return at least one candidate")
        if self.control.poi_visits and any(
            visit.inserted for visit in self.control.poi_visits
        ):
            raise ValueError("the retained control cannot contain inserted POIs")
        if self.search.control_signature != self.control.signature:
            raise ValueError("search control signature must match retained control")
        if self.search.recommended_signature != self.candidates[0].signature:
            raise ValueError("search recommendation must match rank one")
        if tuple(candidate.rank for candidate in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("Auto Tour candidate ranks must be contiguous")
        if len({candidate.signature for candidate in self.candidates}) != len(
            self.candidates
        ):
            raise ValueError("Auto Tour candidates must have unique signatures")
        return self
