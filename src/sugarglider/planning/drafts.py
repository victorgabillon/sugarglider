"""Shared immutable unfinalized candidate inputs."""

from dataclasses import dataclass
from typing import Literal

from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.planning.models import RouteTopology
from sugarglider.planning.result import (
    ApproximatedPlanStop,
    DroppedPlanStop,
    PlanCompromise,
    ReachedPlanStop,
)
from sugarglider.routing.backend import RoutedPath

type SearchFamily = Literal[
    "auto_tour", "waypoint_control", "waypoint_ordering", "reverse"
]


@dataclass(frozen=True)
class CandidateDraft:
    route: RouteResult
    routing_points: tuple[Coordinate, ...]
    topology: RouteTopology
    construction: str
    search_family: SearchFamily
    routed_path: RoutedPath | None = None
    exact_waypoint_indices: tuple[int, ...] = ()
    reached_stops: tuple[ReachedPlanStop, ...] = ()
    approximated_stops: tuple[ApproximatedPlanStop, ...] = ()
    dropped_stops: tuple[DroppedPlanStop, ...] = ()
    compromises: tuple[PlanCompromise, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()
    quality_inputs: tuple[tuple[str, float], ...] = ()
    maximum_distance_m: float | None = None
    structural_safety_eligible: bool = True
