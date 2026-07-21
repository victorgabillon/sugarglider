"""Auto Tour settings and mutable request-scoped algorithm state."""

from dataclasses import dataclass, field

from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.planning.auto_tour.candidate_models import (
    AutoTourCandidate,
)
from sugarglider.planning.auto_tour.diagnostics import (
    AutoTourSearchSummary,
)
from sugarglider.planning.auto_tour.discovered_pois import (
    InsertedPoiRecord,
    PoiOpportunity,
    TourPoiSettings,
)
from sugarglider.planning.auto_tour.models import (
    HardWaypointVisit,
    RejectedPoiOpportunity,
    SkeletonMethod,
    TourConstruction,
    TourDirection,
)
from sugarglider.planning.budget import SearchBudget, SearchPhase
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.diagnostics import PlanSearchDiagnostics
from sugarglider.routing.backend import (
    RoutedPath,
)

ISOCHRONE_REQUEST_BUDGET = 1
ROUND_TRIP_CONTROL_HEADINGS = (0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0)
ROUND_TRIP_CONTROL_REQUEST_BUDGET = 8
SKELETON_ROUTE_REQUEST_BUDGET = 24
RETAINED_SKELETON_LIMIT = 6
MAX_INSERTED_POIS = 4
POI_BEAM_WIDTH = 6
POI_ROUTE_EVALUATION_BUDGET = 24
REQUESTED_PLACE_ROUTE_EVALUATION_BUDGET = 60
POI_EXPANSIONS_PER_STATE = 4
LOCAL_REPAIR_ROUTE_EVALUATION_BUDGET = 12
ALTERNATIVE_LEG_REQUEST_BUDGET = 24
APPROACH_ROUTE_EVALUATION_BUDGET = 32
APPROACH_BEAM_WIDTH = 4
MAX_SNAP_DISPLACEMENT_M = 300.0
ROUTE_CLOSURE_TOLERANCE_M = 25.0
MAX_CANDIDATE_REJECTIONS = 12


class AutoTourNoCandidateError(ValueError):
    """No graph-valid control survived the bounded Auto Tour search."""


class AutoTourMaximumBelowDirectLowerBoundError(ValueError):
    """A user maximum cannot contain the graph-valid endpoint control."""


@dataclass(frozen=True)
class AutoTourSettings:
    """Strict named request budgets and server-controlled POI behavior."""

    round_trip_control_budget: int = ROUND_TRIP_CONTROL_REQUEST_BUDGET
    skeleton_route_budget: int = SKELETON_ROUTE_REQUEST_BUDGET
    retained_skeleton_limit: int = RETAINED_SKELETON_LIMIT
    max_inserted_pois: int = MAX_INSERTED_POIS
    poi_beam_width: int = POI_BEAM_WIDTH
    poi_route_evaluation_budget: int = POI_ROUTE_EVALUATION_BUDGET
    requested_place_route_evaluation_budget: int = (
        REQUESTED_PLACE_ROUTE_EVALUATION_BUDGET
    )
    approach_route_evaluation_budget: int = APPROACH_ROUTE_EVALUATION_BUDGET
    approach_beam_width: int = APPROACH_BEAM_WIDTH
    local_repair_route_evaluation_budget: int = LOCAL_REPAIR_ROUTE_EVALUATION_BUDGET
    alternative_leg_request_budget: int = ALTERNATIVE_LEG_REQUEST_BUDGET
    max_snap_displacement_m: float = MAX_SNAP_DISPLACEMENT_M
    poi: TourPoiSettings = TourPoiSettings()

    def __post_init__(self) -> None:
        if not 1 <= self.round_trip_control_budget <= 8:
            raise ValueError("round-trip control budget must be between 1 and 8")
        if not 1 <= self.skeleton_route_budget <= 24:
            raise ValueError("skeleton route budget must be between 1 and 24")
        if not 1 <= self.retained_skeleton_limit <= 6:
            raise ValueError("retained skeleton limit must be between 1 and 6")
        if not 0 <= self.max_inserted_pois <= 4:
            raise ValueError("maximum inserted POIs must be between 0 and 4")
        if not 1 <= self.poi_beam_width <= 6:
            raise ValueError("POI beam width must be between 1 and 6")
        if not 0 <= self.poi_route_evaluation_budget <= 24:
            raise ValueError("POI route budget must be between 0 and 24")
        if not 0 <= self.requested_place_route_evaluation_budget <= 60:
            raise ValueError("requested-place route budget must be between 0 and 60")
        if not 0 <= self.approach_route_evaluation_budget <= 32:
            raise ValueError("approach route budget must be between 0 and 32")
        if not 1 <= self.approach_beam_width <= 4:
            raise ValueError("approach beam width must be between 1 and 4")
        if not 0 <= self.local_repair_route_evaluation_budget <= 12:
            raise ValueError("local repair route budget must be between 0 and 12")
        if not 0 <= self.alternative_leg_request_budget <= 24:
            raise ValueError("alternative-leg budget must be between 0 and 24")
        if self.max_snap_displacement_m < 0:
            raise ValueError("snap displacement must be non-negative")

    @property
    def total_route_request_budget(self) -> int:
        return (
            self.round_trip_control_budget
            + self.skeleton_route_budget
            + self.poi_route_evaluation_budget
            + self.requested_place_route_evaluation_budget
            + self.local_repair_route_evaluation_budget
            + self.alternative_leg_request_budget
        )


def _search_budget(settings: AutoTourSettings) -> SearchBudget:
    limits = {phase: 0 for phase in SearchPhase}
    limits[SearchPhase.CONTROL] = settings.round_trip_control_budget + 1
    limits[SearchPhase.SKELETON] = settings.skeleton_route_budget
    limits[SearchPhase.REQUESTED_STOP] = (
        settings.requested_place_route_evaluation_budget
    )
    limits[SearchPhase.APPROACH] = settings.approach_route_evaluation_budget
    limits[SearchPhase.DISCOVERED_POI] = settings.poi_route_evaluation_budget
    limits[SearchPhase.REPAIR] = settings.local_repair_route_evaluation_budget
    limits[SearchPhase.ALTERNATIVE_LEG] = settings.alternative_leg_request_budget
    return SearchBudget(
        limits,
        total_limit=settings.total_route_request_budget + 1,
    )


@dataclass
class _SearchState:
    budget: SearchBudget
    context: PlanningSearchContext
    isochrone_proposals_generated: int = 0
    skeleton_candidates: int = 0
    sampled_fallback_skeletons: int = 0
    approach_candidates_considered: int = 0
    considered_approach_ids: set[str] = field(default_factory=set)
    budget_exhausted: bool = False
    requested_place_budget_exhausted: bool = False
    discovered_poi_budget_exhausted: bool = False
    route_call_seconds: float = 0.0
    poi_index_candidate_count: int = 0
    already_collected_count: int = 0
    complete_set_candidate_distance_m: float | None = None
    full_set_route_attempted: bool = False
    full_set_route_succeeded: bool = False
    full_set_distance_m: float | None = None
    full_set_safety_eligible: bool | None = None
    full_set_rejection_reason: str | None = None
    rejected_by_skeleton: dict[str, list[RejectedPoiOpportunity]] = field(
        default_factory=dict
    )


def _public_search_diagnostics(
    state: _SearchState, summary: AutoTourSearchSummary
) -> PlanSearchDiagnostics:
    """Publish the request-scoped manager's accounting without reconstruction."""
    return PlanSearchDiagnostics(
        budget=state.budget.diagnostics(),
        cache=state.context.routes.cache_snapshot(),
        warnings=summary.warnings,
        details={
            "producer_recommended_id": summary.recommended_signature,
            "selected_stop_count": summary.selected_stop_count,
            "dropped_stop_count": summary.dropped_stop_count,
            "requested_place_selected_count": (summary.requested_place_selected_count),
            "requested_place_dropped_count": summary.requested_place_dropped_count,
            "total_seconds": summary.timings.total_seconds,
        },
    )


@dataclass(frozen=True)
class _Draft:
    route: RouteResult
    routed_path: RoutedPath
    routing_points: tuple[Coordinate, ...]
    signature: str
    construction: TourConstruction
    skeleton_id: str
    skeleton_method: SkeletonMethod
    direction: TourDirection
    direction_warnings: tuple[str, ...]
    hard_point_visits: tuple[HardWaypointVisit, ...]
    ellipse_bearing_degrees: float | None = None
    ellipse_aspect_ratio: float | None = None
    ellipse_perimeter_scale: float | None = None
    ellipse_containment_scale: float | None = None


@dataclass(frozen=True)
class _InsertionState:
    draft: _Draft
    family_control: _Draft
    base_already_ids: frozenset[str]
    selected_poi_ids: tuple[str, ...]
    selected_progress: tuple[float, ...]
    inserted_records: dict[str, InsertedPoiRecord]
    deliberately_routed_requested_indices: frozenset[int]
    candidate: AutoTourCandidate


@dataclass(frozen=True)
class _ContinuationOption:
    coordinate: Coordinate
    route_progress_share: float
    poi_opportunity: PoiOpportunity | None = None
    requested_index: int | None = None


@dataclass(frozen=True)
class _RequestedRouteOutcome:
    path: RoutedPath
    points: tuple[Coordinate, ...]
    removed_requested_indices: frozenset[int] = frozenset()
