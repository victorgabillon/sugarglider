"""Mode-neutral semantic-anchor source models for global optimization."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.planning.models import (
    ConstraintStrength,
    DistancePriority,
    RouteTopology,
)
from sugarglider.planning.profiles import RoutingProfileId
from sugarglider.pois.models import PoiApproachCandidate
from sugarglider.routing.backend import RoutedPath

type SemanticAnchorKind = Literal["exact", "soft", "fixed"]
type SemanticStopOutcome = Literal["reached", "approximated"]


@dataclass(frozen=True)
class SemanticRoutingAnchor:
    """One semantic routing anchor translated into the global optimizer."""

    id: str
    name: str
    coordinate: Coordinate
    semantic_coordinate: Coordinate
    kind: SemanticAnchorKind
    route_progress: float
    constraint_strength: ConstraintStrength | None = None
    outcome: SemanticStopOutcome | None = None
    current_approach: PoiApproachCandidate | None = None
    approach_candidates: tuple[PoiApproachCandidate, ...] = ()
    maximum_semantic_distance_m: float | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.name:
            raise ValueError("optimization anchors require identity and name")
        if not isfinite(self.route_progress) or not 0 <= self.route_progress <= 1:
            raise ValueError("optimization anchor progress must be normalized")
        if self.kind == "soft":
            if (
                self.constraint_strength not in {"approach", "best_effort"}
                or self.outcome is None
                or self.current_approach is None
                or self.maximum_semantic_distance_m is None
            ):
                raise ValueError("soft anchors require complete routing semantics")
        elif (
            self.outcome is not None
            or self.current_approach is not None
            or self.approach_candidates
            or self.maximum_semantic_distance_m is not None
        ):
            raise ValueError("fixed and exact anchors cannot carry approaches")

    @property
    def reorderable(self) -> bool:
        return self.kind == "soft"


@dataclass(frozen=True)
class SemanticOptimizationSource:
    """One graph-valid source and its semantic routing-anchor order."""

    source_candidate_id: str
    route: RouteResult
    routed_path: RoutedPath
    source_anchor_order: tuple[SemanticRoutingAnchor, ...]
    exact_boundary_indices: tuple[int, ...]
    topology: RouteTopology
    profile: RoutingProfileId
    target_distance_m: float
    tolerance_m: float
    distance_priority: DistancePriority
    maximum_distance_m: float | None = None

    def __post_init__(self) -> None:
        if not self.source_anchor_order:
            raise ValueError("optimization requires at least one route anchor")
        if (
            tuple(sorted(set(self.exact_boundary_indices)))
            != self.exact_boundary_indices
        ):
            raise ValueError("exact boundary indices must be unique and ordered")
        if (
            not self.exact_boundary_indices
            or self.exact_boundary_indices[0] != 0
            or self.exact_boundary_indices[-1] != len(self.source_anchor_order) - 1
        ):
            raise ValueError("optimization must retain exact endpoint boundaries")
        if any(
            self.source_anchor_order[index].kind != "exact"
            for index in self.exact_boundary_indices
        ):
            raise ValueError("exact boundary indices must reference exact anchors")
