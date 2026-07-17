"""Immutable public models for deterministic target-distance generation."""

from typing import Annotated, Literal, Self

from pydantic import Field, PrivateAttr, model_validator

from sugarglider.domain.models import Coordinate, ImmutableModel, RouteResult

GenerationStatus = Literal["within_tolerance", "best_effort", "infeasible"]
PointOrderMode = Literal["fixed", "optimize_loop"]
PathSelectionMode = Literal["shortest", "low_overlap"]
CandidateConstruction = Literal[
    "direct_order",
    "round_trip_detour",
    "alternative_leg_beam",
]
NonNegativeFloat = Annotated[float, Field(ge=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Share = Annotated[float, Field(ge=0, le=1)]


class RouteGenerationRequest(ImmutableModel):
    """Ordered mandatory anchors and bounded deterministic search parameters."""

    name: str = "Sugarglider generated route"
    points: Annotated[list[Coordinate], Field(min_length=2, max_length=30)]
    target_distance_m: Annotated[float, Field(ge=1_000, le=200_000)]
    tolerance_m: Annotated[float, Field(ge=100, le=10_000)] = 2_000
    candidate_count: Annotated[int, Field(ge=1, le=5)] = 3
    seed: int = 0
    close_loop: bool = True
    profile: Literal["hike"] = "hike"
    point_order_mode: PointOrderMode = "fixed"
    path_selection_mode: PathSelectionMode = "shortest"
    _required_point_count: int = PrivateAttr()
    _supplied_points: tuple[Coordinate, ...] = PrivateAttr()

    @model_validator(mode="after")
    def validate_and_close_required_points(self) -> Self:
        """Preserve supplied order and append the start exactly once."""
        if not self.close_loop:
            raise ValueError("PR3 route generation requires close_loop=true")
        self._required_point_count = len(self.points)
        self._supplied_points = tuple(self.points)
        for previous, current in zip(self.points, self.points[1:], strict=False):
            if (previous.lat, previous.lon) == (current.lat, current.lon):
                raise ValueError(
                    "adjacent required points must not have equal coordinates"
                )
        first = self.points[0]
        last = self.points[-1]
        if (first.lat, first.lon) != (last.lat, last.lon):
            object.__setattr__(self, "points", [*self.points, first])
        return self

    @property
    def required_point_count(self) -> int:
        """Number of points supplied by the caller before automatic closure."""
        return self._required_point_count

    @property
    def supplied_required_points(self) -> tuple[Coordinate, ...]:
        """Caller-supplied mandatory points without a closing duplicate."""
        points = self._supplied_points
        if len(points) > 1 and (points[0].lat, points[0].lon) == (
            points[-1].lat,
            points[-1].lon,
        ):
            return points[:-1]
        return points


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
    search_budget: Annotated[int, Field(ge=1)]
    search_budget_exhausted: bool
    seed: int
    warnings: tuple[str, ...]


class RouteGenerationResult(ImmutableModel):
    """Baseline, ranked generated candidates, and bounded-search diagnostics."""

    baseline: RouteResult
    candidates: tuple[GeneratedCandidate, ...]
    search: SearchSummary
