"""Pure immediate-retracing detection over directed GraphHopper edge traversals."""

from dataclasses import dataclass

from sugarglider.domain.models import GeoJsonPosition

MAX_BACKTRACK_SPUR_EDGES = 64
MIN_BACKTRACK_EDGE_ID_COVERAGE = 0.90


@dataclass(frozen=True)
class DirectedEdgeTraversal:
    """One geometry edge with its known graph identity and travel direction."""

    edge_id: int | None
    start: GeoJsonPosition
    end: GeoJsonPosition
    distance_m: float


@dataclass(frozen=True)
class BacktrackMeasurement:
    """Raw distances used to construct normalized public metrics."""

    immediate_backtrack_distance_m: float
    known_edge_distance_m: float


def reversed_traversal(
    earlier: DirectedEdgeTraversal, later: DirectedEdgeTraversal
) -> bool:
    """Return whether two known traversals use one edge in opposite directions."""
    return (
        earlier.edge_id is not None
        and earlier.edge_id == later.edge_id
        and earlier.start == later.end
        and earlier.end == later.start
    )


def measure_immediate_backtracking(
    traversals: tuple[DirectedEdgeTraversal, ...],
    *,
    maximum_spur_edges: int = MAX_BACKTRACK_SPUR_EDGES,
) -> BacktrackMeasurement:
    """Count returns along a bounded stack-shaped out-and-back spur.

    Unknown edge IDs break continuity. Only the returning traversal is counted.
    At most the most recent ``maximum_spur_edges`` outward traversals are retained,
    so longer spurs deterministically count only that innermost returning depth.
    """
    returning = classify_immediate_backtracking(
        traversals, maximum_spur_edges=maximum_spur_edges
    )
    known_distance = sum(
        traversal.distance_m
        for traversal in traversals
        if traversal.edge_id is not None
    )
    backtrack_distance = sum(
        traversal.distance_m
        for traversal, is_returning in zip(traversals, returning, strict=True)
        if is_returning
    )

    return BacktrackMeasurement(backtrack_distance, known_distance)


def classify_immediate_backtracking(
    traversals: tuple[DirectedEdgeTraversal, ...],
    *,
    maximum_spur_edges: int = MAX_BACKTRACK_SPUR_EDGES,
) -> tuple[bool, ...]:
    """Mark returning traversals using the public metric's bounded stack rules."""
    if maximum_spur_edges < 1:
        raise ValueError("maximum backtrack spur depth must be positive")

    stack: list[DirectedEdgeTraversal] = []
    returning = [False] * len(traversals)
    for index, traversal in enumerate(traversals):
        if traversal.edge_id is None:
            stack.clear()
            continue
        if stack and reversed_traversal(stack[-1], traversal):
            returning[index] = True
            stack.pop()
            continue
        stack.append(traversal)
        if len(stack) > maximum_spur_edges:
            del stack[0]
    return tuple(returning)
