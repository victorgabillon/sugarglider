"""Canonical immutable planning results shared by every planning mode."""

from typing import Any, Literal, Self

from pydantic import Field, model_validator

from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.planning.diagnostics import PlanSearchDiagnostics
from sugarglider.planning.models import (
    CanonicalModel,
    PlanKind,
    RequestedStopImportance,
    RouteTopology,
)
from sugarglider.planning.profiles import RoutingProfileId
from sugarglider.pois.models import PoiApproachCandidate

type CandidateRole = Literal[
    "harmonious",
    "maximum_requested_coverage",
    "smooth_low_detour",
    "distance_focused",
]
type StopDecision = Literal["pending", "selected", "dropped"]
type SelectionOrigin = Literal["requested", "discovered", "user_preferred"]
type SelectionMethod = Literal[
    "already_reached",
    "deliberate_insertion",
    "corridor_continuation",
    "short_excursion",
    "shared_excursion",
]


class PlanScore(CanonicalModel):
    total: float
    components: dict[str, float] = Field(default_factory=dict)


class SelectedPlanStop(CanonicalModel):
    id: str
    name: str
    semantic_coordinate: Coordinate
    category: str
    importance: RequestedStopImportance | None = None
    selection_origin: SelectionOrigin
    selection_method: SelectionMethod
    resolved_approach: PoiApproachCandidate
    route_progress: float = Field(ge=0, le=1)
    route_to_approach_m: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_arrival(self) -> Self:
        if self.route_to_approach_m > self.resolved_approach.arrival_tolerance_m:
            raise ValueError("selected stop is outside its strict arrival tolerance")
        return self


class DroppedPlanStop(CanonicalModel):
    id: str
    name: str
    semantic_coordinate: Coordinate
    category: str
    importance: RequestedStopImportance | None = None
    selection_origin: SelectionOrigin
    reason: str
    considered_approaches: tuple[PoiApproachCandidate, ...] = ()


class PlanCandidateDiagnostics(CanonicalModel):
    safety_eligible: bool
    target_error_m: float = Field(ge=0)
    within_tolerance: bool
    requested_stop_count: int = Field(ge=0)
    immediate_backtracking_m: float = Field(ge=0)
    repeated_distance_m: float = Field(ge=0)
    details: dict[str, Any] = Field(default_factory=dict)


class PlanCandidate(CanonicalModel):
    id: str
    routing_profile: RoutingProfileId
    rank: int = Field(ge=1)
    roles: tuple[CandidateRole, ...]
    route: RouteResult
    score: PlanScore
    selected_stops: tuple[SelectedPlanStop, ...] = ()
    dropped_stops: tuple[DroppedPlanStop, ...] = ()
    diagnostics: PlanCandidateDiagnostics

    @model_validator(mode="after")
    def validate_decisions_and_roles(self) -> Self:
        role_order: dict[CandidateRole, int] = {
            "harmonious": 0,
            "maximum_requested_coverage": 1,
            "smooth_low_detour": 2,
            "distance_focused": 3,
        }
        if self.roles != tuple(sorted(set(self.roles), key=role_order.__getitem__)):
            raise ValueError("candidate roles must be unique and canonically ordered")
        selected_ids = {stop.id for stop in self.selected_stops}
        dropped_ids = {stop.id for stop in self.dropped_stops}
        if len(selected_ids) != len(self.selected_stops):
            raise ValueError("selected stop IDs must be unique")
        if len(dropped_ids) != len(self.dropped_stops):
            raise ValueError("dropped stop IDs must be unique")
        if selected_ids.intersection(dropped_ids):
            raise ValueError("a stop cannot be selected and dropped")
        return self


class PlanResult(CanonicalModel):
    schema_version: Literal[1] = 1
    kind: PlanKind
    topology: RouteTopology
    routing_profile: RoutingProfileId
    effective_start: Coordinate
    effective_end: Coordinate
    candidates: tuple[PlanCandidate, ...]
    search_diagnostics: PlanSearchDiagnostics


class PlanGpxRequest(CanonicalModel):
    schema_version: Literal[1]
    candidate: PlanCandidate
