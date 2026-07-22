"""Immutable internal models for native canonical Waypoint search."""

from dataclasses import dataclass
from typing import Literal

from sugarglider.domain.models import Coordinate
from sugarglider.planning.models import RouteTopology

type WaypointConstruction = Literal[
    "fixed_control",
    "optimized_order",
    "round_trip_detour",
    "open_alternative_detour",
    "low_overlap_beam",
]


@dataclass(frozen=True)
class WaypointSequenceProposal:
    """One endpoint-fixed exact order, optionally with routed detour anchors."""

    routing_points: tuple[Coordinate, ...]
    exact_points: tuple[Coordinate, ...]
    exact_point_positions: tuple[int, ...]
    original_indices: tuple[int, ...]
    exact_point_ids: tuple[str | None, ...]
    topology: RouteTopology
    construction: WaypointConstruction
    order_provenance: str
    detour_provenance: str | None = None

    def __post_init__(self) -> None:
        if len(self.exact_points) != len(self.exact_point_positions):
            raise ValueError("exact points and positions must have equal length")
        if len(self.exact_points) != len(self.exact_point_ids):
            raise ValueError("exact points and IDs must have equal length")
        if tuple(sorted(self.exact_point_positions)) != self.exact_point_positions:
            raise ValueError("exact point positions must be ordered")
        if any(
            self.routing_points[position] != point
            for position, point in zip(
                self.exact_point_positions, self.exact_points, strict=True
            )
        ):
            raise ValueError("exact point positions must reference exact points")
        if any(
            left == right
            for left, right in zip(
                self.routing_points, self.routing_points[1:], strict=False
            )
        ):
            raise ValueError("adjacent routing coordinates must be distinct")
        if self.topology == "loop":
            if self.routing_points[0] != self.routing_points[-1]:
                raise ValueError("loop proposal must end at its start")
            if self.exact_point_positions[-1] != len(self.routing_points) - 1:
                raise ValueError("loop closing start must be the final exact point")
        elif self.routing_points[0] == self.routing_points[-1]:
            raise ValueError("point-to-point proposal must remain open")


@dataclass(frozen=True)
class OrderingProposalStats:
    generated: int
    deduplicated: int
    rejected_before_routing: int
