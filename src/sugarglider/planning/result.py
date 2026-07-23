"""Canonical immutable planning results shared by every planning mode."""

from typing import Any, Literal, Self

from pydantic import Field, model_validator

from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.planning.diagnostics import PlanSearchDiagnostics
from sugarglider.planning.models import (
    CanonicalModel,
    ConstraintStrength,
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
type StopDecision = Literal["pending", "reached", "approximated", "dropped"]
type CompromiseSeverity = Literal["info", "warning"]
type CompromiseCode = Literal[
    "target_distance_missed",
    "stop_approximated",
    "stop_dropped",
    "no_profile_compatible_approach",
    "nearest_routeable_point_used",
    "access_unknown",
    "route_budget_exhausted",
    "optional_preference_unmet",
]
type SelectionOrigin = Literal["requested", "discovered", "user_preferred"]
type SelectionMethod = Literal[
    "already_reached",
    "deliberate_insertion",
    "corridor_continuation",
    "short_excursion",
    "shared_excursion",
]
type RouteTraversalDirection = Literal[
    "start_to_end",
    "clockwise",
    "counterclockwise",
    "complex_loop",
]
type TraversalAnchorKind = Literal[
    "start",
    "end",
    "exact_waypoint",
    "requested_stop",
    "approximated_stop",
    "deliberate_discovered_stop",
]
type TraversalOutcome = Literal["reached", "approximated"]


class PlanScore(CanonicalModel):
    total: float
    components: dict[str, float] = Field(default_factory=dict)


class ReachedPlanStop(CanonicalModel):
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
            raise ValueError("reached stop is outside its strict arrival tolerance")
        return self


class ApproximatedPlanStop(CanonicalModel):
    id: str
    name: str
    semantic_coordinate: Coordinate
    category: str
    importance: RequestedStopImportance | None = None
    selection_origin: SelectionOrigin
    resolved_approach: PoiApproachCandidate
    route_progress: float = Field(ge=0, le=1)
    distance_m: float = Field(gt=0)
    normal_tolerance_m: float = Field(gt=0)
    configured_maximum_m: float | None = Field(default=None, gt=0)
    reason: str

    @model_validator(mode="after")
    def validate_approximation(self) -> Self:
        if self.distance_m <= self.normal_tolerance_m:
            raise ValueError("approximated stop must exceed its normal tolerance")
        if (
            self.configured_maximum_m is not None
            and self.distance_m > self.configured_maximum_m
        ):
            raise ValueError("approximated stop exceeds its configured maximum")
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


class PlanCompromise(CanonicalModel):
    code: CompromiseCode
    severity: CompromiseSeverity
    constraint_id: str | None = None
    constraint_name: str | None = None
    semantic_coordinate: Coordinate | None = None
    routed_coordinate: Coordinate | None = None
    distance_m: float | None = Field(default=None, ge=0)
    normal_tolerance_m: float | None = Field(default=None, ge=0)
    configured_maximum_m: float | None = Field(default=None, ge=0)
    reason: str
    profile: RoutingProfileId
    suggestion: str


class PlanTraversalAnchor(CanonicalModel):
    id: str
    name: str
    kind: TraversalAnchorKind
    routed_coordinate: Coordinate
    semantic_coordinate: Coordinate
    route_progress: float = Field(ge=0, le=1)
    constraint_strength: ConstraintStrength | None = None
    outcome: TraversalOutcome


class PlanTraversal(CanonicalModel):
    direction: RouteTraversalDirection
    anchors: tuple[PlanTraversalAnchor, ...]

    @model_validator(mode="after")
    def validate_anchor_order(self) -> Self:
        if not self.anchors or self.anchors[0].kind != "start":
            raise ValueError("traversal must begin with one start anchor")
        ids = tuple(anchor.id for anchor in self.anchors)
        if len(ids) != len(set(ids)):
            raise ValueError("traversal anchor IDs must be unique")
        progress = tuple(anchor.route_progress for anchor in self.anchors)
        if progress != tuple(sorted(progress)):
            raise ValueError("traversal anchors must be sorted by route progress")
        if self.direction == "start_to_end":
            if self.anchors[-1].kind != "end":
                raise ValueError("open traversal must end with one end anchor")
        elif any(anchor.kind == "end" for anchor in self.anchors):
            raise ValueError("loop traversal must not contain an end anchor")
        return self


class PlanCandidateDiagnostics(CanonicalModel):
    safety_eligible: bool
    target_error_m: float = Field(ge=0)
    within_tolerance: bool
    requested_stop_count: int = Field(ge=0)
    approximated_stop_count: int = Field(default=0, ge=0)
    dropped_stop_count: int = Field(default=0, ge=0)
    immediate_backtracking_m: float = Field(ge=0)
    repeated_distance_m: float = Field(ge=0)
    spur_count: int = Field(default=0, ge=0)
    spur_repeated_distance_m: float = Field(default=0, ge=0)
    longest_spur_distance_m: float = Field(default=0, ge=0)
    details: dict[str, Any] = Field(default_factory=dict)


class PlanCandidate(CanonicalModel):
    id: str
    kind: PlanKind
    topology: RouteTopology
    routing_profile: RoutingProfileId
    rank: int = Field(ge=1)
    roles: tuple[CandidateRole, ...]
    route: RouteResult
    score: PlanScore
    traversal: PlanTraversal
    reached_stops: tuple[ReachedPlanStop, ...] = ()
    approximated_stops: tuple[ApproximatedPlanStop, ...] = ()
    dropped_stops: tuple[DroppedPlanStop, ...] = ()
    compromises: tuple[PlanCompromise, ...] = ()
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
        reached_ids = {stop.id for stop in self.reached_stops}
        approximated_ids = {stop.id for stop in self.approximated_stops}
        dropped_ids = {stop.id for stop in self.dropped_stops}
        if len(reached_ids) != len(self.reached_stops):
            raise ValueError("reached stop IDs must be unique")
        if len(approximated_ids) != len(self.approximated_stops):
            raise ValueError("approximated stop IDs must be unique")
        if len(dropped_ids) != len(self.dropped_stops):
            raise ValueError("dropped stop IDs must be unique")
        if (
            reached_ids.intersection(approximated_ids)
            or reached_ids.intersection(dropped_ids)
            or approximated_ids.intersection(dropped_ids)
        ):
            raise ValueError("a stop must have exactly one final outcome")
        if self.topology == "point_to_point":
            if self.traversal.direction != "start_to_end":
                raise ValueError("open candidate traversal must be start-to-end")
        elif self.traversal.direction == "start_to_end":
            raise ValueError("loop candidate traversal must have loop orientation")
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

    @model_validator(mode="after")
    def validate_candidate_identity(self) -> Self:
        if any(
            candidate.kind != self.kind
            or candidate.topology != self.topology
            or candidate.routing_profile != self.routing_profile
            for candidate in self.candidates
        ):
            raise ValueError("result candidates must match kind, topology, and profile")
        return self


class PlanGpxRequest(CanonicalModel):
    schema_version: Literal[1]
    candidate: PlanCandidate
