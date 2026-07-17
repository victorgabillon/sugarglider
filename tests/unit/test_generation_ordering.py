"""Pure deterministic mandatory-point order proposal tests."""

import pytest

from sugarglider.domain.models import Coordinate
from sugarglider.generation.ordering import (
    MAX_ORDER_PROPOSALS,
    cycle_distance_m,
    generate_order_proposals,
    nearest_neighbor_order,
    ordered_closed_points,
    polar_angle_order,
    two_opt_refine,
    validate_point_order,
)


def point(lat: float, lon: float, name: str) -> Coordinate:
    return Coordinate(lat=lat, lon=lon, name=name)


@pytest.fixture
def compass_points() -> tuple[Coordinate, ...]:
    return (
        point(0, 2, "start east"),
        point(1, 0, "north"),
        point(0, -1, "west"),
        point(-1, 0, "south"),
        point(0, 1, "east"),
    )


def test_every_proposal_fixes_start_and_contains_every_point_once(
    compass_points: tuple[Coordinate, ...],
) -> None:
    proposals = generate_order_proposals(compass_points)
    assert proposals
    for proposal in proposals:
        assert proposal[0] == 0
        assert sorted(proposal) == list(range(len(compass_points)))


def test_clockwise_and_counter_clockwise_sweeps(
    compass_points: tuple[Coordinate, ...],
) -> None:
    assert polar_angle_order(compass_points, clockwise=True) == (0, 4, 3, 2, 1)
    assert polar_angle_order(compass_points, clockwise=False) == (0, 4, 1, 2, 3)


def test_nearest_neighbor_order_and_stable_tie_breaking() -> None:
    points = (
        point(0, 0, "start"),
        point(0, 1, "first equal"),
        point(0, -1, "second equal"),
        point(0, 2, "far"),
    )
    assert nearest_neighbor_order(points) == (0, 1, 3, 2)


def test_two_opt_is_deterministic_and_shortens_crossed_cycle() -> None:
    points = (
        point(0, 0, "start"),
        point(1, 1, "north east"),
        point(0, 1, "east"),
        point(1, 0, "north"),
    )
    crossed = (0, 1, 3, 2)
    first = two_opt_refine(points, crossed)
    second = two_opt_refine(points, crossed)
    assert first == second
    assert cycle_distance_m(points, first) < cycle_distance_m(points, crossed)


def test_duplicate_proposals_are_removed_and_count_is_bounded() -> None:
    points = tuple(point(0, index, str(index)) for index in range(20))
    proposals = generate_order_proposals(points)
    assert len(proposals) == len(set(proposals))
    assert len(proposals) <= MAX_ORDER_PROPOSALS


@pytest.mark.parametrize(
    "order",
    [
        (1, 0, 2),
        (0, 1),
        (0, 1, 1),
        (0, 1, 3),
    ],
)
def test_malformed_orders_are_rejected(order: tuple[int, ...]) -> None:
    with pytest.raises(ValueError):
        validate_point_order(order, 3)


def test_ordered_points_adds_one_closing_start(
    compass_points: tuple[Coordinate, ...],
) -> None:
    closed = ordered_closed_points(compass_points, (0, 4, 1, 2, 3))
    assert closed[0] == closed[-1]
    assert len(closed) == len(compass_points) + 1
