"""Cumulative proposal sampling and required-point preservation tests."""

import pytest
from shapely.geometry import LineString, Point

from sugarglider.domain.models import Coordinate
from sugarglider.generation.geometry import (
    insert_optional_points,
    proposal_point_sequences,
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


def test_off_proposal_sequence_is_the_unchanged_legacy_sample() -> None:
    proposal = ((0.0, 0.0), (0.02, 0.0), (0.02, 0.02), (0.0, 0.0))
    start = Coordinate(lat=0, lon=0)
    sequences = proposal_point_sequences(proposal, start, start, prefer_balanced=False)
    assert len(sequences) == 1
    assert sequences[0].variant == "legacy"
    assert sequences[0].construction == "round_trip_detour"
    assert sequences[0].optional_points == sample_optional_points(proposal, start)


def test_balanced_forward_reverse_and_control_are_derived_from_proposal() -> None:
    proposal = (
        (0.0, 0.0),
        (0.03, 0.0),
        (0.03, 0.03),
        (-0.03, 0.03),
        (-0.03, -0.03),
        (0.03, -0.03),
        (0.0, 0.0),
    )
    start = Coordinate(lat=0, lon=0)
    first = proposal_point_sequences(proposal, start, start, prefer_balanced=True)
    second = proposal_point_sequences(proposal, start, start, prefer_balanced=True)
    assert first == second
    assert [sequence.variant for sequence in first] == [
        "balanced_forward",
        "balanced_reverse",
        "legacy",
    ]
    assert first[1].optional_points == tuple(
        point.model_copy(update={"name": f"Generated detour {index}"})
        for index, point in enumerate(
            reversed(first[0].optional_points),
            start=1,
        )
    )
    proposal_line = LineString(proposal)
    for sequence in first:
        assert 1 <= len(sequence.optional_points) <= 3
        assert all(
            proposal_line.distance(Point(point.lon, point.lat)) < 1e-12
            for point in sequence.optional_points
        )


def test_duplicate_balanced_orientation_is_removed() -> None:
    proposal = ((0.0, 0.0), (0.012, 0.0), (0.0, 0.0))
    start = Coordinate(lat=0, lon=0)
    sequences = proposal_point_sequences(
        proposal,
        start,
        start,
        prefer_balanced=True,
        minimum_separation_m=900,
    )
    assert [sequence.variant for sequence in sequences] == [
        "balanced_forward",
        "legacy",
    ]


def test_refinement_derives_only_the_retained_variant_and_orientation() -> None:
    proposal = (
        (0.0, 0.0),
        (0.03, 0.0),
        (0.03, 0.03),
        (-0.03, 0.03),
        (-0.03, -0.03),
        (0.03, -0.03),
        (0.0, 0.0),
    )
    start = Coordinate(lat=0, lon=0)
    initial = proposal_point_sequences(proposal, start, start, prefer_balanced=True)
    for sequence in initial:
        refined = proposal_point_sequences(
            proposal,
            start,
            start,
            prefer_balanced=True,
            variant=sequence.variant,
        )
        assert refined == (sequence,)
