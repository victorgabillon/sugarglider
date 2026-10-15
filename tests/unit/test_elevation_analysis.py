"""Physical invariants using synthetic signals only; metres throughout."""

import json
import math
import random
from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from sugarglider.analysis.elevation import (
    MAX_ELEVATION_SAMPLES,
    NUMERICAL_TOLERANCE_M,
    ElevationAnalysis,
    ElevationParameters,
    ElevationProfile,
    ElevationSample,
    analyze_elevation,
    profile_digest,
)


def profile(
    heights: Sequence[float | None], distances: list[float] | None = None
) -> ElevationProfile:
    distances = distances or [index * 50.0 for index in range(len(heights))]
    return ElevationProfile(
        source_sha256="a" * 64,
        geometry_sha256="b" * 64,
        routing_profile="trail_run",
        route_distance_m=distances[-1],
        height_reference="synthetic, known terrain",
        samples=tuple(
            ElevationSample(index=index, distance_m=distance, height_m=height)
            for index, (height, distance) in enumerate(
                zip(heights, distances, strict=True)
            )
        ),
    )


def reverse(source: ElevationProfile) -> ElevationProfile:
    return profile(
        [point.height_m for point in reversed(source.samples)],
        [
            source.route_distance_m - point.distance_m
            for point in reversed(source.samples)
        ],
    )


@pytest.mark.parametrize("height", [-100.0, 0.0, 100.0, 8_000.0])
def test_constant_altitude_is_exactly_zero(height: float) -> None:
    result = analyze_elevation(profile([height] * 20))
    assert result.total_ascent_m == result.total_descent_m == 0
    assert result.minimum_height_m == result.maximum_height_m == height
    assert all(point.filtered_height_m == height for point in result.samples)


@pytest.mark.parametrize("direction", [-1, 1])
def test_monotone_slopes_preserve_full_change(direction: int) -> None:
    result = analyze_elevation(profile([direction * float(i) for i in range(21)]))
    assert result.total_ascent_m == (20 if direction > 0 else 0)
    assert result.total_descent_m == (20 if direction < 0 else 0)


def test_one_summit_has_exact_predictable_smoothing_loss() -> None:
    source = profile([0.0, 10.0, 20.0, 30.0, 20.0, 10.0, 0.0])
    result = analyze_elevation(source)
    # Exact integral of the two slopes in a ±50m window: summit 25m.
    assert result.total_ascent_m == result.total_descent_m == 25
    assert result.raw_observed_ascent_m == result.raw_observed_descent_m == 30
    assert result.minimum_height_m == 0
    assert result.maximum_height_m == 30  # Available raw extrema, not filtered.


def test_multiple_broad_genuine_climbs_survive() -> None:
    heights = [0.0] * 3
    for _ in range(3):
        heights += [float(i) for i in range(1, 31)]
        heights += [30.0] * 3
        heights += [float(i) for i in range(29, -1, -1)]
        heights += [0.0] * 3
    result = analyze_elevation(profile(heights))
    assert result.total_ascent_m == result.total_descent_m == 90


def test_small_alternating_noise_is_removed_without_inventing_climbs() -> None:
    result = analyze_elevation(profile([0.0, *[(-1.0) ** i for i in range(101)], 0.0]))
    assert result.raw_observed_ascent_m == 101
    assert result.total_ascent_m is not None and result.total_ascent_m <= 1
    assert result.total_descent_m == result.total_ascent_m


@pytest.mark.parametrize("direction", [-1, 1])
def test_noisy_slopes_recover_net_change_with_bounded_endpoint_noise(
    direction: int,
) -> None:
    heights = [direction * i * 0.5 + (-1.0) ** i for i in range(101)]
    result = analyze_elevation(profile(heights))
    # Retained noisy endpoints leave 0.5m residual reversal; interior noise
    # cancels. Do not pretend smoothing can identify the true endpoint height.
    assert result.total_ascent_m == pytest.approx(50.5 if direction > 0 else 0.5)
    assert result.total_descent_m == pytest.approx(50.5 if direction < 0 else 0.5)
    assert result.raw_observed_ascent_m is not None
    assert result.raw_observed_descent_m is not None
    assert result.raw_observed_ascent_m + result.raw_observed_descent_m > 100


def test_irregular_spacing_uses_distance_not_sample_count() -> None:
    dense = profile([0.0, 50.0, 51.0, 52.0, 100.0], [0.0, 50.0, 51.0, 52.0, 100.0])
    result = analyze_elevation(dense)
    # A linear ramp is unchanged at interior positions whose windows fit.
    assert result.samples[1].filtered_height_m == 50
    assert result.total_ascent_m == 100
    assert result.total_descent_m == 0
    # Inserting points on a linear edge must not change the original outputs.
    sparse = profile([0.0, 20.0, 0.0], [0.0, 50.0, 100.0])
    refined = profile([0.0, 8.0, 20.0, 16.0, 0.0], [0.0, 20.0, 50.0, 60.0, 100.0])
    assert analyze_elevation(sparse).samples[1].filtered_height_m == pytest.approx(
        analyze_elevation(refined).samples[2].filtered_height_m
    )


def test_missing_intervals_are_never_zero_filled_or_connected() -> None:
    result = analyze_elevation(profile([100.0, 110.0, None, None, 0.0, -10.0]))
    assert result.coverage == "partial"
    assert result.analyzed_distance_m == 100
    assert result.unknown_distance_m == 150
    assert result.total_ascent_m is result.total_descent_m is None
    assert result.observed_ascent_m == result.observed_descent_m == 10
    assert [point.filtered_height_m for point in result.samples] == [
        100,
        110,
        None,
        None,
        0,
        -10,
    ]
    assert [point.segment_index for point in result.samples] == [0, 0, None, None, 1, 1]


def test_even_one_missing_sample_breaks_the_filter_window() -> None:
    result = analyze_elevation(
        profile([0.0, 10.0, None, 200.0, 210.0]),
        ElevationParameters(smoothing_radius_m=500),
    )
    assert result.observed_ascent_m == 20
    assert result.observed_descent_m == 0
    assert result.samples[2].filtered_height_m is None


def test_large_nonnull_gap_is_unknown_distance_not_interpolated() -> None:
    result = analyze_elevation(
        profile([0.0, 10.0, 1_000.0, 990.0], [0.0, 50.0, 1_000.0, 1_050.0])
    )
    assert result.coverage == "partial"
    assert result.analyzed_distance_m == 100
    assert result.unknown_distance_m == 950
    assert result.observed_ascent_m == result.observed_descent_m == 10
    assert result.total_ascent_m is None


@pytest.mark.parametrize("heights", [[None, None, None], [None, 100.0, None]])
def test_no_supported_interval_never_reports_zero_gain(
    heights: list[float | None],
) -> None:
    result = analyze_elevation(profile(heights))
    assert result.coverage == ("partial" if 100 in heights else "unavailable")
    assert result.observed_ascent_m is result.observed_descent_m is None
    assert result.total_ascent_m is result.total_descent_m is None
    assert result.analyzed_distance_m == 0
    assert result.unknown_distance_m == 100
    assert result.minimum_height_m == (100 if 100 in heights else None)


def test_leading_and_trailing_unknown_samples_are_not_extrapolated() -> None:
    result = analyze_elevation(profile([None, 0.0, 10.0, None]))
    assert result.coverage == "partial"
    assert result.observed_ascent_m == 10
    assert result.analyzed_distance_m == 50
    assert result.unknown_distance_m == 100


@pytest.mark.parametrize("radius", [0.0, 1.0, 25.0, 50.0, 100.0, 500.0])
@pytest.mark.parametrize("maximum_gap", [100.0, 1_000.0])
def test_random_irregular_profiles_reverse_and_never_gain_variation(
    radius: float,
    maximum_gap: float,
) -> None:
    rng = random.Random(89)
    parameters = ElevationParameters(
        smoothing_radius_m=radius, maximum_gap_m=maximum_gap
    )
    for _ in range(40):
        count = rng.randint(3, 100)
        heights: list[float | None] = [rng.uniform(-100, 500) for _ in range(count)]
        distances = [0.0]
        for _ in range(count - 1):
            distances.append(distances[-1] + rng.uniform(0.1, 150))
        source = profile(heights, distances)
        forward = analyze_elevation(source, parameters)
        backward = analyze_elevation(reverse(source), parameters)
        if maximum_gap == 1_000:
            assert forward.coverage == "complete"
            assert forward.total_ascent_m is not None
            assert forward.total_descent_m is not None
            assert heights[0] is not None and heights[-1] is not None
            assert forward.total_ascent_m - forward.total_descent_m == pytest.approx(
                heights[-1] - heights[0], abs=NUMERICAL_TOLERANCE_M, rel=0
            )
        assert forward.coverage == backward.coverage
        assert forward.observed_ascent_m == pytest.approx(
            backward.observed_descent_m, abs=NUMERICAL_TOLERANCE_M, rel=0
        )
        assert forward.observed_descent_m == pytest.approx(
            backward.observed_ascent_m, abs=NUMERICAL_TOLERANCE_M, rel=0
        )
        assert forward.observed_ascent_m is not None
        assert forward.raw_observed_ascent_m is not None
        assert forward.observed_ascent_m <= (
            forward.raw_observed_ascent_m + NUMERICAL_TOLERANCE_M
        )
        for left, right in zip(
            forward.samples, reversed(backward.samples), strict=True
        ):
            assert left.filtered_height_m == pytest.approx(
                right.filtered_height_m, abs=NUMERICAL_TOLERANCE_M, rel=0
            )


def test_full_budget_is_deterministic_immutable_and_json_roundtrips() -> None:
    source = profile([math.sin(i / 10) * 100 for i in range(MAX_ELEVATION_SAMPLES)])
    original = source.model_dump_json()
    result = analyze_elevation(source)
    assert result == analyze_elevation(source)
    assert len(result.samples) == MAX_ELEVATION_SAMPLES
    assert source.model_dump_json() == original
    assert ElevationAnalysis.model_validate_json(result.model_dump_json()) == result
    assert result.source_sha256 == source.source_sha256
    assert result.geometry_sha256 == source.geometry_sha256
    assert result.routing_profile == source.routing_profile
    assert result.route_distance_m == source.route_distance_m
    assert [s.distance_m for s in result.samples] == [
        s.distance_m for s in source.samples
    ]
    with pytest.raises(ValidationError):
        result.coverage = "partial"


@pytest.mark.parametrize("radius", [1.0, 50.0, 500.0])
def test_full_budget_extreme_heights_reverse_with_documented_numeric_tolerance(
    radius: float,
) -> None:
    rng = random.Random(89)
    distances = [0.0]
    for _ in range(MAX_ELEVATION_SAMPLES - 1):
        distances.append(distances[-1] + rng.uniform(0.01, 95))
    source = profile([rng.uniform(-16_000, 16_000) for _ in distances], distances)
    parameters = ElevationParameters(smoothing_radius_m=radius)
    forward = analyze_elevation(source, parameters)
    backward = analyze_elevation(reverse(source), parameters)
    assert forward.coverage == backward.coverage == "complete"
    assert forward.total_ascent_m == pytest.approx(
        backward.total_descent_m, abs=NUMERICAL_TOLERANCE_M, rel=0
    )
    for left, right in zip(forward.samples, reversed(backward.samples), strict=True):
        assert left.filtered_height_m == pytest.approx(
            right.filtered_height_m, abs=NUMERICAL_TOLERANCE_M, rel=0
        )


@pytest.mark.parametrize("radius", [25.0, 80.0, 500.0])
def test_distance_integral_matches_independent_direct_trapezoid_reference(
    radius: float,
) -> None:
    distances = [0.0, 10.0, 30.0, 50.0, 100.0, 120.0]
    heights = [10.0, -3.0, 50.0, 20.0, 40.0, 5.0]
    source = profile(heights, distances)
    result = analyze_elevation(source, ElevationParameters(smoothing_radius_m=radius))
    for index in range(1, len(distances) - 1):
        left, right = distances[index] - radius, distances[index] + radius
        area = heights[0] * max(0, -left)
        area += heights[-1] * max(0, right - distances[-1])
        for edge in range(len(distances) - 1):
            start = max(left, distances[edge])
            end = min(right, distances[edge + 1])
            if end <= start:
                continue
            slope = (heights[edge + 1] - heights[edge]) / (
                distances[edge + 1] - distances[edge]
            )
            a = heights[edge] + slope * (start - distances[edge])
            b = heights[edge] + slope * (end - distances[edge])
            area += (a + b) * (end - start) / 2
        assert result.samples[index].filtered_height_m == pytest.approx(
            area / (radius * 2), abs=NUMERICAL_TOLERANCE_M, rel=0
        )


@pytest.mark.parametrize(
    "distances", [[0.0, 50.0, 50.0], [0.0, 100.0, 50.0], [1.0, 50.0, 100.0]]
)
def test_bad_progress_is_rejected(distances: list[float]) -> None:
    with pytest.raises(ValueError):
        profile([0.0, 1.0, 2.0], distances)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -16_385.0, 16_385.0])
def test_invalid_heights_are_rejected(value: float) -> None:
    with pytest.raises(ValidationError):
        profile([0.0, value])


@pytest.mark.parametrize(
    "updates",
    [
        {"route_distance_m": 49},
        {"routing_profile": "foot"},
        {"source_sha256": "bad"},
        {"unexpected": 0},
        {"route_distance_m": "50"},
        {"route_distance_m": True},
        {
            "samples": [
                {"index": 1, "distance_m": 0, "height_m": 0},
                {"index": 2, "distance_m": 50, "height_m": 1},
            ]
        },
    ],
)
def test_malformed_profiles_are_rejected(updates: dict[str, object]) -> None:
    data = profile([0.0, 1.0]).model_dump(mode="json")
    data.update(updates)
    with pytest.raises(ValidationError):
        ElevationProfile.model_validate_json(json.dumps(data))


def test_oversized_profile_is_rejected_without_coarsening() -> None:
    with pytest.raises(ValidationError):
        profile([0.0] * (MAX_ELEVATION_SAMPLES + 1))


def test_profile_identity_binds_heights_and_is_independent_of_filter_parameters() -> (
    None
):
    source = profile([0.0, 1.0, 0.0])
    identity = profile_digest(source)
    assert identity != profile_digest(profile([0.0, 2.0, 0.0]))
    assert identity != profile_digest(profile([0.0, None, 0.0]))
    assert analyze_elevation(source).profile_sha256 == (
        analyze_elevation(
            source, ElevationParameters(smoothing_radius_m=0)
        ).profile_sha256
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"smoothing_radius_m": -1},
        {"smoothing_radius_m": 0.5},
        {"smoothing_radius_m": float("nan")},
        {"smoothing_radius_m": 501},
        {"maximum_gap_m": 0},
        {"maximum_gap_m": 1_001},
    ],
)
def test_invalid_policy_is_rejected(updates: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        ElevationParameters.model_validate(updates)
