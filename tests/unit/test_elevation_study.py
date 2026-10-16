"""Discriminating method comparisons, not tests for benchmark timings."""

import pytest

from sugarglider.analysis.elevation import (
    ElevationProfile,
    ElevationSample,
    analyze_elevation,
)
from sugarglider.offline_regions.elevation_study import (
    deadband_totals,
    median_three,
    sensitivity,
)


def test_causal_deadband_can_violate_reversal_and_lose_terminal_change() -> None:
    heights = [0.0, 1.0, 4.0, 2.0, 3.0]
    forward = deadband_totals(heights, 3)
    backward = deadband_totals(list(reversed(heights)), 3)
    assert forward["ascent_m"] == 4
    assert backward["descent_m"] == 3
    assert forward["ascent_m"] != backward["descent_m"]


def test_median_can_erase_a_real_narrow_summit_completely() -> None:
    assert median_three([0.0, 10.0, 0.0]) == [0, 0, 0]
    source = ElevationProfile(
        source_sha256="a" * 64,
        geometry_sha256="b" * 64,
        routing_profile="hike",
        route_distance_m=100,
        height_reference="synthetic narrow summit",
        samples=tuple(
            ElevationSample(index=index, distance_m=index * 50, height_m=height)
            for index, height in enumerate([0.0, 10.0, 0.0])
        ),
    )
    assert analyze_elevation(source).total_ascent_m == 5


def test_comparison_study_refuses_unknown_distance_even_with_all_heights() -> None:
    source = ElevationProfile(
        source_sha256="a" * 64,
        geometry_sha256="b" * 64,
        routing_profile="hike",
        route_distance_m=1_000,
        height_reference="undersampled",
        samples=(
            ElevationSample(index=0, distance_m=0, height_m=0),
            ElevationSample(index=1, distance_m=1_000, height_m=100),
        ),
    )
    with pytest.raises(ValueError, match="complete distance coverage"):
        sensitivity(source)
