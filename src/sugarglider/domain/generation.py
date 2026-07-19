"""Immutable public models for deterministic target-distance generation."""

from typing import Annotated, Literal, Self

from pydantic import Field, PrivateAttr, model_validator

from sugarglider.domain.endpoints import (
    EndpointSelection,
    EndpointVisit,
    ResolvedEndpoints,
    ResolvedRouteTopology,
    RouteTopology,
    resolve_waypoint_endpoints,
    routing_sequence,
)
from sugarglider.domain.models import Coordinate, ImmutableModel, RouteResult

GenerationStatus = Literal["within_tolerance", "best_effort", "infeasible"]
PointOrderMode = Literal["fixed", "optimize_loop", "optimize_path"]
PathSelectionMode = Literal["shortest", "low_overlap"]
NaturePreference = Literal["off", "prefer"]
LoopGeometryPreference = Literal["off", "prefer"]
CandidateConstruction = Literal[
    "direct_order",
    "open_path_direct",
    "open_path_optimized",
    "open_path_alternative_leg_beam",
    "round_trip_detour",
    "sector_balanced_detour",
    "alternative_leg_beam",
]
NonNegativeFloat = Annotated[float, Field(ge=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Share = Annotated[float, Field(ge=0, le=1)]


class RouteGenerationRequest(ImmutableModel):
    """Ordered mandatory anchors and bounded deterministic search parameters."""

    name: str = "Sugarglider generated route"
    start: Coordinate | None = None
    end: Coordinate | None = None
    points: Annotated[list[Coordinate], Field(max_length=30)] = Field(
        default_factory=list
    )
    route_topology: RouteTopology = "auto"
    target_distance_m: Annotated[float, Field(ge=1_000, le=200_000)]
    tolerance_m: Annotated[float, Field(ge=100, le=10_000)] = 2_000
    candidate_count: Annotated[int, Field(ge=1, le=5)] = 3
    seed: int = 0
    close_loop: bool | None = True
    profile: Literal["hike"] = "hike"
    point_order_mode: PointOrderMode = "fixed"
    path_selection_mode: PathSelectionMode = "shortest"
    nature_preference: NaturePreference = "off"
    loop_geometry_preference: LoopGeometryPreference = "off"
    _required_point_count: int = PrivateAttr()
    _supplied_points: tuple[Coordinate, ...] = PrivateAttr()
    _endpoint_selection: EndpointSelection = PrivateAttr()
    _routing_points: tuple[Coordinate, ...] = PrivateAttr()
    _interior_points: tuple[Coordinate, ...] = PrivateAttr()

    @model_validator(mode="after")
    def validate_and_close_required_points(self) -> Self:
        """Resolve topology while retaining the exact legacy loop representation."""
        supplied = tuple(self.points)
        requested_topology = self.route_topology
        topology_was_supplied = "route_topology" in self.model_fields_set
        close_loop_was_supplied = "close_loop" in self.model_fields_set
        if not topology_was_supplied and self.close_loop is False:
            requested_topology = "point_to_point"
        if topology_was_supplied and close_loop_was_supplied:
            conflicts = (
                self.close_loop is True and requested_topology == "point_to_point"
            ) or (self.close_loop is False and requested_topology == "loop")
            if conflicts:
                from sugarglider.domain.endpoints import endpoint_error

                raise endpoint_error(
                    "route_topology_conflicts_with_close_loop",
                    "route_topology conflicts with the legacy close_loop value.",
                )
        for previous, current in zip(supplied, supplied[1:], strict=False):
            if (previous.lat, previous.lon) == (current.lat, current.lon):
                raise ValueError(
                    "adjacent required points must not have equal coordinates"
                )
        endpoint_points = supplied
        if (
            self.start is None
            and self.end is None
            and len(supplied) > 1
            and (supplied[0].lat, supplied[0].lon)
            == (supplied[-1].lat, supplied[-1].lon)
            and requested_topology != "point_to_point"
        ):
            endpoint_points = supplied[:-1]
        selection = resolve_waypoint_endpoints(
            start=self.start,
            end=self.end,
            points=endpoint_points,
            route_topology=requested_topology,
        )
        interior = tuple(
            point
            for index, point in enumerate(endpoint_points)
            if index not in selection.consumed_point_indices
        )
        if (
            selection.resolved.topology == "loop"
            and not interior
            and not (
                self.start is not None
                and self.end is not None
                and (self.start.lat, self.start.lon) == (self.end.lat, self.end.lon)
            )
        ):
            raise ValueError("a Waypoint loop requires at least one interior point")
        route_points = routing_sequence(selection.resolved, interior)
        if (
            self.point_order_mode == "optimize_loop"
            and selection.resolved.topology != "loop"
        ):
            raise ValueError("optimize_loop is only valid for loop topology")
        if (
            self.point_order_mode == "optimize_path"
            and selection.resolved.topology != "point_to_point"
        ):
            raise ValueError("optimize_path is only valid for point-to-point topology")
        self._required_point_count = (
            len(supplied) + int(self.start is not None) + int(self.end is not None)
        )
        self._supplied_points = supplied
        self._endpoint_selection = selection
        self._routing_points = route_points
        self._interior_points = interior
        # Preserve the historical public points-only closed-loop model shape.
        if (
            self.start is None
            and self.end is None
            and selection.resolved.topology == "loop"
        ):
            object.__setattr__(self, "points", list(route_points))
        return self

    @property
    def required_point_count(self) -> int:
        """Number of points supplied by the caller before automatic closure."""
        return self._required_point_count

    @property
    def supplied_required_points(self) -> tuple[Coordinate, ...]:
        """All effective mandatory points without a closing duplicate."""
        return (self.resolved_endpoints.start, *self._interior_points)

    @property
    def resolved_endpoints(self) -> ResolvedEndpoints:
        return self._endpoint_selection.resolved

    @property
    def routing_points(self) -> tuple[Coordinate, ...]:
        return self._routing_points

    @property
    def interior_points(self) -> tuple[Coordinate, ...]:
        return self._interior_points

    @property
    def caller_supplied_points(self) -> tuple[Coordinate, ...]:
        return self._supplied_points


class RequiredPointVisit(ImmutableModel):
    """One mandatory visit with its stable index in the original request."""

    original_index: NonNegativeInt
    coordinate: Coordinate


class CandidateScore(ImmutableModel):
    """Fixed PR3 score with positive penalty and reward magnitudes."""

    total: float
    distance_error_ratio: NonNegativeFloat
    repetition_penalty: NonNegativeFloat
    major_road_penalty: NonNegativeFloat
    paved_penalty: NonNegativeFloat
    unknown_surface_penalty: NonNegativeFloat
    trail_like_reward: NonNegativeFloat
    hiking_network_reward: NonNegativeFloat


class GeneratedCandidate(ImmutableModel):
    """One distinct analyzed graph-valid candidate in ranked order."""

    rank: Annotated[int, Field(ge=1)]
    route: RouteResult
    optional_points: tuple[Coordinate, ...]
    required_point_order: tuple[RequiredPointVisit, ...]
    routing_points: tuple[Coordinate, ...]
    construction: CandidateConstruction
    target_error_m: NonNegativeFloat
    within_tolerance: bool
    score: CandidateScore
    signature: str


class SearchSummary(ImmutableModel):
    """Deterministic accounting for one bounded generation search."""

    status: GenerationStatus
    target_distance_m: NonNegativeFloat
    tolerance_m: NonNegativeFloat
    baseline_distance_m: NonNegativeFloat
    best_order_distance_m: NonNegativeFloat
    evaluated_candidate_count: NonNegativeInt
    successful_candidate_count: NonNegativeInt
    rejected_candidate_count: NonNegativeInt
    round_trip_proposal_count: NonNegativeInt
    evaluated_order_count: NonNegativeInt
    successful_order_count: NonNegativeInt
    rejected_order_count: NonNegativeInt
    fixed_order_repeated_share: Share
    best_order_repeated_share: Share
    fixed_order_backtrack_share: Share
    best_order_backtrack_share: Share
    alternative_leg_request_count: NonNegativeInt = 0
    alternative_path_count: NonNegativeInt = 0
    low_overlap_refined_source_count: NonNegativeInt = 0
    low_overlap_candidate_count: NonNegativeInt = 0
    low_overlap_request_budget: NonNegativeInt = 0
    low_overlap_budget_exhausted: bool = False
    low_overlap_requested: bool
    pre_low_overlap_repeated_share: Share | None
    best_low_overlap_repeated_share: Share | None
    pre_low_overlap_backtrack_share: Share | None
    best_low_overlap_backtrack_share: Share | None
    nature_requested: bool
    nature_index_available: bool
    nature_index_feature_count: NonNegativeInt | None
    recommended_nature_score: Annotated[float, Field(ge=0, le=100)] | None
    best_available_nature_score: Annotated[float, Field(ge=0, le=100)] | None
    loop_geometry_requested: bool = False
    recommended_loop_geometry_penalty: NonNegativeFloat | None = None
    best_available_loop_geometry_penalty: NonNegativeFloat | None = None
    derived_proposal_sequence_count: NonNegativeInt = 0
    base_search_budget: NonNegativeInt = 0
    loop_geometry_extra_evaluation_budget: NonNegativeInt = 0
    loop_geometry_extra_evaluated_count: NonNegativeInt = 0
    loop_geometry_extra_successful_count: NonNegativeInt = 0
    loop_geometry_extra_rejected_count: NonNegativeInt = 0
    search_budget: Annotated[int, Field(ge=1)]
    search_budget_exhausted: bool
    seed: int
    warnings: tuple[str, ...]


class RouteGenerationResult(ImmutableModel):
    """Baseline, ranked generated candidates, and bounded-search diagnostics."""

    baseline: RouteResult
    candidates: tuple[GeneratedCandidate, ...]
    search: SearchSummary
    topology: ResolvedRouteTopology = "loop"
    effective_start: Coordinate | None = None
    effective_end: Coordinate | None = None
    endpoint_visits: tuple[EndpointVisit, EndpointVisit] | tuple[()] = ()
    endpoint_warnings: tuple[str, ...] = ()
