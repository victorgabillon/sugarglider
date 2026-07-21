"""Private immutable Auto Tour search and diagnostic models."""

from math import isclose
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, PrivateAttr, model_validator
from pydantic.json_schema import SkipJsonSchema

from sugarglider.domain.endpoints import (
    EndpointSelection,
    ResolvedEndpoints,
    RouteTopology,
    resolve_auto_tour_endpoints,
)
from sugarglider.domain.models import (
    Coordinate,
    GeoJsonPosition,
    ImmutableModel,
)
from sugarglider.pois.models import PoiApproachCandidate, PoiCategory, PoiFeature

type TourDirection = Literal["clockwise", "counterclockwise", "mixed"]
type DirectionPreference = Literal["any", "clockwise", "counterclockwise"]
type DistancePriority = Literal["flexible", "balanced", "strict"]
type PathSelectionMode = Literal["shortest", "low_overlap"]
type NaturePreference = Literal["off", "prefer"]
type LoopGeometryPreference = Literal["off", "prefer"]
type RequestedPlaceImportance = Literal["must_visit", "prefer"]
type PoiDecision = Literal["selected", "dropped"]
type PoiOrigin = Literal["requested", "discovered_scenic", "discovered_water"]
type PoiSelectionReason = Literal[
    "requested_must_visit",
    "requested_preferred",
    "preferred_by_user",
    "already_on_route",
    "low_cost_insertion",
    "corridor_continuation",
    "shared_excursion",
]
type PoiDropReason = Literal[
    "user_deselected",
    "no_meaningful_approach",
    "private_or_restricted",
    "graph_unreachable",
    "approach_snap_too_far",
    "arrival_tolerance_not_met",
    "spur_cost_too_high",
    "route_safety_rejected",
    "maximum_distance_rejected",
    "search_budget_exhausted",
    "lower_utility_candidate",
]
type CandidateRole = Literal[
    "harmonious", "maximum_requested_coverage", "smooth_low_detour"
]
type RequestedPlaceFailureReason = Literal[
    "requested_place_snap_too_far",
    "requested_place_graph_unreachable",
    "requested_place_private_or_restricted",
    "requested_place_route_budget_exhausted",
    "requested_place_safety_rejected",
    "requested_place_distance_ceiling_rejected",
    "requested_place_user_maximum_rejected",
    "requested_place_server_maximum_rejected",
    "requested_place_search_budget_exhausted",
    "requested_place_lower_utility_subset",
]
type TourConstruction = Literal[
    "isochrone_ellipse",
    "graphhopper_round_trip",
    "graphhopper_round_trip_sampled",
    "poi_insertion",
    "local_repair",
    "corridor_continuation",
    "alternative_leg_repair",
    "point_to_point_direct",
    "point_to_point_hard_waypoints",
    "point_to_point_alternative",
    "requested_place_family",
]
type SkeletonMethod = Literal[
    "isochrone_ellipse",
    "graphhopper_round_trip",
    "graphhopper_round_trip_sampled",
    "point_to_point_direct",
    "point_to_point_hard_waypoints",
    "point_to_point_alternative",
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


class CandidateScore(ImmutableModel):
    total: float
    distance_error_ratio: NonNegativeFloat
    repetition_penalty: NonNegativeFloat
    major_road_penalty: NonNegativeFloat
    paved_penalty: NonNegativeFloat
    unknown_surface_penalty: NonNegativeFloat
    trail_like_reward: NonNegativeFloat
    hiking_network_reward: NonNegativeFloat


class RequestedTourPlace(ImmutableModel):
    """One semantic requested place, independently of its route approach."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Annotated[str, Field(min_length=1, max_length=240)] | None = None
    name: Annotated[str, Field(min_length=1, max_length=200)]
    coordinate: Coordinate
    access_search_radius_m: Annotated[float, Field(ge=25, le=2_000)] = 500.0
    arrival_tolerance_m: Annotated[float, Field(gt=0, le=25)] = 25.0
    importance: RequestedPlaceImportance = "prefer"
    osm_reference: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    approach_override: Coordinate | None = None
    original_index: NonNegativeInt | None = None
    approach_candidates: SkipJsonSchema[tuple[PoiApproachCandidate, ...]] = Field(
        default=(), exclude=True
    )
    chosen_approach: SkipJsonSchema[PoiApproachCandidate | None] = Field(
        default=None, exclude=True
    )
    import_warnings: SkipJsonSchema[tuple[str, ...]] = Field(default=(), exclude=True)
    approach_resolution_drop_reason: SkipJsonSchema[PoiDropReason | None] = Field(
        default=None, exclude=True
    )

    @model_validator(mode="after")
    def validate_override_and_approaches(self) -> Self:
        if self.approach_override is not None:
            from sugarglider.analysis.route import haversine_distance_m

            distance = haversine_distance_m(
                (self.coordinate.lon, self.coordinate.lat),
                (self.approach_override.lon, self.approach_override.lat),
            )
            if distance > 1_000.0:
                raise ValueError(
                    "requested-place approach override must be within 1000 metres"
                )
        if self.import_warnings != tuple(sorted(set(self.import_warnings))):
            raise ValueError(
                "requested-place import warnings must be sorted and unique"
            )
        if self.chosen_approach is not None and self.chosen_approach not in (
            self.approach_candidates
        ):
            raise ValueError("chosen approach must belong to the bounded candidates")
        return self

    @property
    def routing_coordinate(self) -> Coordinate:
        return (
            self.chosen_approach.coordinate
            if self.chosen_approach is not None
            else self.coordinate
        )


class RequestedTourPlaceVisit(ImmutableModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    requested_place: RequestedTourPlace
    measured_distance_m: NonNegativeFloat
    closest_route_distance_m: NonNegativeFloat = 0.0
    chosen_approach: PoiApproachCandidate | None = None
    arrival_tolerance_m: Annotated[float, Field(gt=0, le=100)] = 25.0
    route_progress_share: Share
    decision: PoiDecision
    deliberately_routed: bool
    deliberately_routed_in_another_retained_candidate: bool = False
    deliberately_considered: bool = True
    graph_snap_distance_m: NonNegativeFloat | None = None
    selection_reason: PoiSelectionReason | None = None
    drop_reason: PoiDropReason | None = None

    @model_validator(mode="after")
    def validate_satisfaction(self) -> Self:
        if not isclose(
            self.measured_distance_m,
            self.closest_route_distance_m,
            rel_tol=0,
            abs_tol=1e-9,
        ):
            raise ValueError("closest route distance must match measured distance")
        arrived = (
            self.chosen_approach is not None
            and self.measured_distance_m <= self.arrival_tolerance_m
        )
        if (
            arrived
            and self.chosen_approach is not None
            and self.chosen_approach.kind == "strict_graph_snap"
            and self.deliberately_routed
        ):
            arrived = (
                self.graph_snap_distance_m is not None
                and self.graph_snap_distance_m <= 25.0
            )
        if (self.decision == "selected") != arrived:
            raise ValueError("selected requested places must pass strict arrival")
        if self.decision == "selected":
            if self.selection_reason is None or self.drop_reason is not None:
                raise ValueError(
                    "selected requested places require one selection reason"
                )
        elif self.drop_reason is None or self.selection_reason is not None:
            raise ValueError("dropped requested places require one drop reason")
        return self

    @property
    def selected(self) -> bool:
        """Return whether strict arrival selected this requested place."""
        return self.decision == "selected"


class SemanticPoi(ImmutableModel):
    id: Annotated[str, Field(min_length=1, max_length=320)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    coordinate: Coordinate
    category: str
    origin: PoiOrigin
    importance: RequestedPlaceImportance | None = None
    osm_reference: str | None = None


class SelectedPoiStop(ImmutableModel):
    semantic_poi: SemanticPoi
    chosen_approach: PoiApproachCandidate
    route_progress_share: Share
    measured_route_to_approach_m: NonNegativeFloat
    selection_reason: PoiSelectionReason
    deliberately_inserted: bool
    excursion_id: str | None = None

    @model_validator(mode="after")
    def validate_arrival(self) -> Self:
        if self.measured_route_to_approach_m > self.chosen_approach.arrival_tolerance_m:
            raise ValueError("selected POI stop is outside its arrival tolerance")
        return self


class DroppedPoiStop(ImmutableModel):
    semantic_poi: SemanticPoi
    approach_candidates_considered: tuple[PoiApproachCandidate, ...]
    best_graph_snap_distance_m: NonNegativeFloat | None = None
    drop_reason: PoiDropReason
    estimated_marginal_route_cost_m: NonNegativeFloat | None = None
    selected_in_another_retained_candidate: bool = False


class PoiExcursion(ImmutableModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Annotated[str, Field(min_length=1, max_length=320)]
    entry_anchor: Coordinate
    exit_anchor: Coordinate
    selected_poi_ids: Annotated[tuple[str, ...], Field(min_length=1)]
    outward_distance_m: NonNegativeFloat = 0.0
    returning_backtrack_distance_m: NonNegativeFloat = 0.0
    physical_spur_distance_m: NonNegativeFloat = 0.0
    free_physical_spur_allowance_m: Annotated[float, Field(ge=0, le=1_000)] = 200.0
    penalized_physical_spur_distance_m: NonNegativeFloat = 0.0
    verified: bool = True
    penalty_m_equivalent: NonNegativeFloat
    through_route: bool
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_excursion_accounting(self) -> Self:
        if not isclose(
            self.physical_spur_distance_m,
            self.outward_distance_m + self.returning_backtrack_distance_m,
            rel_tol=0,
            abs_tol=1e-6,
        ):
            raise ValueError("physical POI spur must equal outward plus returning")
        excess = max(
            0.0,
            self.physical_spur_distance_m - self.free_physical_spur_allowance_m,
        )
        expected_penalty = excess + excess * excess / 400.0
        if not isclose(
            self.penalized_physical_spur_distance_m,
            excess,
            rel_tol=0,
            abs_tol=1e-9,
        ):
            raise ValueError("penalized POI distance must match repeated excess")
        if not isclose(
            self.penalty_m_equivalent, expected_penalty, rel_tol=0, abs_tol=1e-9
        ):
            raise ValueError("POI excursion penalty must use the convex formula")
        expected_warnings = tuple(
            sorted(
                {
                    warning
                    for threshold, warning in (
                        (800.0, "long_poi_excursion"),
                        (2_000.0, "severe_poi_excursion"),
                    )
                    if self.physical_spur_distance_m > threshold
                }
                | ({"poi_excursion_unverified"} if not self.verified else set())
            )
        )
        if self.warnings != expected_warnings:
            raise ValueError("POI excursion warnings must match repeated distance")
        if self.selected_poi_ids != tuple(sorted(set(self.selected_poi_ids))):
            raise ValueError("excursion POI IDs must be unique and sorted")
        return self


def poi_excursion_penalty_m(
    repeated_distance_m: float, free_allowance_m: float = 200.0
) -> float:
    if repeated_distance_m < 0:
        raise ValueError("repeated POI excursion distance must be non-negative")
    if not 0 <= free_allowance_m <= 1_000:
        raise ValueError("free POI excursion allowance must be between 0 and 1000")
    excess = max(0.0, repeated_distance_m - free_allowance_m)
    return excess + excess * excess / 400.0


class AutoTourSearchRequest(ImmutableModel):
    """A fixed start, optional hard anchors, and soft touring preferences."""

    name: str = "Sugarglider Auto Tour"
    start: Coordinate | None = None
    end: Coordinate | None = None
    topology: RouteTopology = "auto"
    target_distance_m: Annotated[float, Field(ge=1_000, le=200_000)]
    tolerance_m: Annotated[float, Field(ge=100, le=10_000)] = 2_000
    maximum_distance_m: Annotated[float, Field(gt=0, le=200_000)] | None = None
    candidate_count: Annotated[int, Field(ge=1, le=5)] = 3
    seed: int = 0
    profile: Literal["hike"] = "hike"
    direction_preference: DirectionPreference = "any"
    hard_waypoints: Annotated[tuple[Coordinate, ...], Field(max_length=6)] = ()
    requested_stops: Annotated[
        tuple[RequestedTourPlace, ...], Field(max_length=30)
    ] = ()
    preferred_poi_ids: Annotated[tuple[str, ...], Field(max_length=8)] = ()
    distance_priority: DistancePriority = "flexible"
    scenic_preference: Literal["off", "prefer"] = "prefer"
    drinking_water_preference: Literal["off", "prefer"] = "prefer"
    nature_preference: NaturePreference = "prefer"
    loop_geometry_preference: LoopGeometryPreference = "prefer"
    path_selection_mode: PathSelectionMode = "low_overlap"
    free_poi_spur_physical_m: Annotated[float, Field(ge=0, le=1_000)] = 200.0
    _endpoint_selection: EndpointSelection = PrivateAttr()

    @model_validator(mode="after")
    def validate_stable_points_and_ids(self) -> Self:
        point_keys = tuple((point.lat, point.lon) for point in self.hard_waypoints)
        if len(point_keys) != len(set(point_keys)):
            raise ValueError("Auto Tour hard points must be unique")
        if self.start is not None and (self.start.lat, self.start.lon) in point_keys:
            raise ValueError("Auto Tour hard points must not duplicate the start")
        if any(not value.strip() for value in self.preferred_poi_ids):
            raise ValueError("preferred POI IDs must not be empty")
        if len(self.preferred_poi_ids) != len(set(self.preferred_poi_ids)):
            raise ValueError("preferred POI IDs must be unique")
        requested_keys = tuple(
            (
                place.id,
                place.name,
                place.coordinate.lat,
                place.coordinate.lon,
                place.original_index,
            )
            for place in self.requested_stops
        )
        if len(requested_keys) != len(set(requested_keys)):
            raise ValueError("requested Auto Tour places must be unique")
        requested_ids = tuple(
            place.id for place in self.requested_stops if place.id is not None
        )
        if len(requested_ids) != len(set(requested_ids)):
            raise ValueError("requested Auto Tour place IDs must be unique")
        original_indices = tuple(
            place.original_index
            for place in self.requested_stops
            if place.original_index is not None
        )
        if len(original_indices) != len(set(original_indices)):
            raise ValueError("requested Auto Tour original indices must be unique")
        self._endpoint_selection = resolve_auto_tour_endpoints(
            start=self.start,
            end=self.end,
            requested_stops=tuple(
                (place.coordinate, place.original_index)
                for place in self.requested_stops
            ),
            hard_waypoints=self.hard_waypoints,
            topology=self.topology,
        )
        return self

    @property
    def resolved_endpoints(self) -> ResolvedEndpoints:
        return self._endpoint_selection.resolved

    @property
    def effective_start(self) -> Coordinate:
        return self.resolved_endpoints.start

    @property
    def effective_end(self) -> Coordinate:
        return self.resolved_endpoints.end

    @property
    def interior_hard_waypoints(self) -> tuple[Coordinate, ...]:
        consumed = self._endpoint_selection.consumed_hard_point_indices
        return tuple(
            point
            for index, point in enumerate(self.hard_waypoints)
            if index not in consumed
        )

    @property
    def interior_requested_stops(self) -> tuple[RequestedTourPlace, ...]:
        consumed = self._endpoint_selection.consumed_requested_indices
        return tuple(
            place
            for index, place in enumerate(self.requested_stops)
            if index not in consumed
        )

    @property
    def interior_requested_place_indices(self) -> tuple[int, ...]:
        consumed = self._endpoint_selection.consumed_requested_indices
        return tuple(
            index for index in range(len(self.requested_stops)) if index not in consumed
        )


class HardWaypointVisit(ImmutableModel):
    original_index: NonNegativeInt
    coordinate: Coordinate
    snapped_coordinate: GeoJsonPosition | None
    snap_distance_m: NonNegativeFloat | None
    selected: bool


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


class DiscoveredPoiVisit(ImmutableModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    poi: PoiFeature
    visit_distance_m: NonNegativeFloat
    chosen_approach: PoiApproachCandidate
    arrival_tolerance_m: Annotated[float, Field(gt=0, le=100)]
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
        if self.visit_distance_m > self.arrival_tolerance_m:
            raise ValueError("a selected discovered POI must pass strict arrival")
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
    hard_waypoints_selected: bool
    backtracking_delta_share: float
    repetition_delta_share: float
    loop_geometry_penalty_delta: float | None
    self_crossing_delta: int | None
    positive_discovered_poi_reward: bool
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
    requested_stops_selected: NonNegativeInt
    added_scenic_pois: NonNegativeInt
    added_verified_water_pois: NonNegativeInt
    geometry_changed: bool
