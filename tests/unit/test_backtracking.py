"""Immediate and near-immediate directed-edge retracing tests."""

import pytest

from sugarglider.analysis.backtracking import (
    MAX_BACKTRACK_SPUR_EDGES,
    DirectedEdgeTraversal,
    measure_immediate_backtracking,
    reversed_traversal,
)
from sugarglider.analysis.route import RouteAnalyzer
from sugarglider.domain.models import PathDetailSegment


def traversal(
    edge_id: int | None,
    start: tuple[float, float],
    end: tuple[float, float],
    distance_m: float = 100.0,
) -> DirectedEdgeTraversal:
    return DirectedEdgeTraversal(edge_id, start, end, distance_m)


def complete_spur(depth: int) -> tuple[DirectedEdgeTraversal, ...]:
    outward = tuple(
        traversal(index, (float(index), 0), (float(index + 1), 0), 1.0)
        for index in range(depth)
    )
    returning = tuple(
        traversal(index, (float(index + 1), 0), (float(index), 0), 1.0)
        for index in reversed(range(depth))
    )
    return (*outward, *returning)


def test_no_repetition_has_no_immediate_backtrack() -> None:
    measured = measure_immediate_backtracking(
        (
            traversal(1, (0, 0), (1, 0)),
            traversal(2, (1, 0), (2, 0)),
        )
    )
    assert measured.immediate_backtrack_distance_m == 0
    assert measured.known_edge_distance_m == 200


def test_one_edge_immediate_reversal_counts_only_return() -> None:
    measured = measure_immediate_backtracking(
        (
            traversal(1, (0, 0), (1, 0)),
            traversal(1, (1, 0), (0, 0)),
        )
    )
    assert measured.immediate_backtrack_distance_m == 100


def test_multi_edge_spur_complete_return_counts_returning_half() -> None:
    measured = measure_immediate_backtracking(
        (
            traversal(1, (0, 0), (1, 0)),
            traversal(2, (1, 0), (2, 0)),
            traversal(2, (2, 0), (1, 0)),
            traversal(1, (1, 0), (0, 0)),
        )
    )
    assert measured.immediate_backtrack_distance_m == 200


@pytest.mark.parametrize("depth", [40, MAX_BACKTRACK_SPUR_EDGES])
def test_complete_spur_within_stack_depth_counts_every_return(depth: int) -> None:
    measured = measure_immediate_backtracking(complete_spur(depth))
    assert measured.immediate_backtrack_distance_m == depth


def test_spur_beyond_stack_depth_counts_only_innermost_bounded_return() -> None:
    measured = measure_immediate_backtracking(
        complete_spur(MAX_BACKTRACK_SPUR_EDGES + 1)
    )
    assert measured.immediate_backtrack_distance_m == MAX_BACKTRACK_SPUR_EDGES


def test_edge_repeated_after_unreturned_path_is_not_immediate_backtrack() -> None:
    measured = measure_immediate_backtracking(
        (
            traversal(1, (0, 0), (1, 0)),
            traversal(2, (1, 0), (2, 0)),
            traversal(3, (2, 0), (3, 0)),
            traversal(1, (1, 0), (0, 0)),
        )
    )
    assert measured.immediate_backtrack_distance_m == 0


def test_unknown_edge_breaks_backtrack_continuity_and_reduces_coverage() -> None:
    measured = measure_immediate_backtracking(
        (
            traversal(1, (0, 0), (1, 0)),
            traversal(None, (1, 0), (2, 0)),
            traversal(1, (1, 0), (0, 0)),
        )
    )
    assert measured.immediate_backtrack_distance_m == 0
    assert measured.known_edge_distance_m == 200


def test_unavailable_edge_ids_report_zero_known_distance() -> None:
    measured = measure_immediate_backtracking((traversal(None, (0, 0), (1, 0)),))
    assert measured == measured.__class__(0.0, 0.0)


def test_reversal_requires_opposite_geometry_direction() -> None:
    forward = traversal(1, (0, 0), (1, 0))
    assert reversed_traversal(forward, traversal(1, (1, 0), (0, 0)))
    assert not reversed_traversal(forward, traversal(1, (0, 0), (1, 0)))
    assert not reversed_traversal(forward, traversal(2, (1, 0), (0, 0)))


def test_analyzer_normalizes_backtrack_distance_and_share() -> None:
    analysis = RouteAnalyzer().analyze(
        ((0, 0), (0.001, 0), (0, 0)),
        300.0,
        {
            "edge_id": (
                PathDetailSegment(from_index=0, to_index=1, value=7),
                PathDetailSegment(from_index=1, to_index=2, value=7),
            )
        },
    )
    assert analysis.immediate_backtrack.distance_m == pytest.approx(150.0)
    assert analysis.immediate_backtrack.share == pytest.approx(0.5)
    assert analysis.backtrack_edge_id_coverage.distance_m == pytest.approx(300.0)
    assert analysis.backtrack_edge_id_coverage.share == 1.0


def test_analyzer_warns_when_backtrack_edge_coverage_is_insufficient() -> None:
    analysis = RouteAnalyzer().analyze(
        ((0, 0), (0.001, 0), (0.002, 0)),
        200.0,
        {"edge_id": (PathDetailSegment(from_index=0, to_index=1, value=7),)},
    )
    assert analysis.backtrack_edge_id_coverage.share == pytest.approx(0.5)
    assert "backtrack_edge_id_coverage_insufficient" in analysis.warnings
