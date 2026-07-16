"""Cumulative proposal sampling and required-point preservation tests."""

import pytest

from sugarglider.domain.models import Coordinate
from sugarglider.generation.geometry import (
    insert_optional_points,
    sample_optional_points,
)


def test_sampling_uses_cumulative_distance_on_uneven_segments() -> None:
    proposal = (
        (0.0, 0.0),
        (0.001, 0.0),
        (0.010, 0.0),
        (0.010, 0.010),
        (0.0, 0.0),
    )
    sampled = sample_optional_points(
        proposal,
        Coordinate(lat=0.0, lon=0.0),
        minimum_separation_m=1.0,
    )
    assert len(sampled) == 3
    assert sampled[0].lon > 0.007
    assert sampled[1].lon == pytest.approx(0.010, abs=0.001)
    assert sampled[2].lat > 0.004
    assert [point.name for point in sampled] == [
        "Generated detour 1",
        "Generated detour 2",
        "Generated detour 3",
    ]


def test_duplicate_terminal_point_is_not_sampled() -> None:
    proposal = ((0.0, 0.0), (0.01, 0.0), (0.01, 0.01), (0.0, 0.0))
    sampled = sample_optional_points(
        proposal, Coordinate(lat=0.0, lon=0.0), minimum_separation_m=10
    )
    assert all((point.lon, point.lat) != proposal[-1] for point in sampled)


def test_close_and_duplicate_samples_are_rejected() -> None:
    tiny = ((0.0, 0.0), (0.00001, 0.0), (0.0, 0.0))
    assert sample_optional_points(tiny, Coordinate(lat=0, lon=0)) == ()


def test_optional_points_are_inserted_without_reordering_required_points() -> None:
    first = Coordinate(lat=48.0, lon=2.0, name="first")
    second = Coordinate(lat=48.1, lon=2.1, name="second")
    third = Coordinate(lat=48.2, lon=2.2, name="third")
    optional = (
        Coordinate(lat=48.05, lon=2.05, name="optional 1"),
        Coordinate(lat=48.06, lon=2.06, name="optional 2"),
    )
    required = (first, second, third, first)
    combined = insert_optional_points(required, 1, optional)
    assert combined == (first, second, *optional, third, first)
    assert tuple(point for point in combined if point in required) == required


def test_insertion_cannot_follow_the_closing_point() -> None:
    required = (
        Coordinate(lat=48, lon=2),
        Coordinate(lat=49, lon=3),
        Coordinate(lat=48, lon=2),
    )
    with pytest.raises(ValueError):
        insert_optional_points(required, 2, ())
