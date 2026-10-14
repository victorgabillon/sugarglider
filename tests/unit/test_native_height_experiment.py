"""Synthetic route/DEM inputs only; no JNI, external terrain or network."""

import struct
from dataclasses import replace

import pytest
from pydantic import ValidationError

from sugarglider.offline_regions.elevation_feasibility import (
    HGT_SAMPLES_PER_SIDE,
    SkadiTile,
)
from sugarglider.offline_regions.elevation_hgt_probe import HgtProbe
from sugarglider.offline_regions.native_height_experiment import (
    HeightPlan,
    ResearchRoute,
    compare_heights,
    height_plan,
    sample_routed_geometry,
)


@pytest.fixture(scope="module")
def zero_probe() -> HgtProbe:
    count = HGT_SAMPLES_PER_SIDE**2
    return HgtProbe(
        tile=SkadiTile(48, 2),
        source_sha256="a" * 64,
        compressed_bytes=1,
        pixels_valid=count,
        pixels_void=0,
        pixels_invalid=0,
        min_height_m=0,
        max_height_m=0,
        data=struct.pack(">h", 0) * count,
    )


def test_samples_follow_routed_bend_and_normalized_backend_distance() -> None:
    route = ResearchRoute(
        routing_profile="hike",
        distance_m=200,
        geometry=((2.1, 48.1), (2.11, 48.1), (2.11, 48.11)),
    )
    original = route.model_dump_json()
    samples = sample_routed_geometry(route, spacing_m=50)
    assert [point.distance_m for point in samples] == [0, 50, 100, 150, 200]
    assert samples[1].lat == 48.1
    assert samples[1].edge_index == 0
    assert samples[2].lon == 2.11
    assert samples[2].edge_index == 1
    assert samples[-1].lat == 48.11
    assert route.model_dump_json() == original
    assert samples == sample_routed_geometry(route, spacing_m=50)


def test_duplicate_vertices_and_short_final_interval_retain_both_endpoints() -> None:
    route = ResearchRoute(
        routing_profile="city_bike",
        distance_m=101,
        geometry=((2.1, 48.1), (2.1, 48.1), (2.11, 48.1), (2.11, 48.1)),
    )
    points = sample_routed_geometry(route, spacing_m=50)
    assert [point.distance_m for point in points] == [0, 50, 100, 101]
    assert (points[0].lon, points[0].lat) == route.geometry[0]
    assert (points[-1].lon, points[-1].lat) == route.geometry[-1]


@pytest.mark.parametrize("spacing", [0, -1, float("nan"), float("inf"), 1_001])
def test_invalid_spacing_is_rejected(spacing: float) -> None:
    route = ResearchRoute(
        routing_profile="hike", distance_m=100, geometry=((2, 48), (2.1, 48))
    )
    with pytest.raises(ValueError, match="spacing"):
        sample_routed_geometry(route, spacing_m=spacing)


def test_budget_rejection_never_coarsens_spacing_or_returns_partial_plan() -> None:
    route = ResearchRoute(
        routing_profile="hike", distance_m=100, geometry=((2, 48), (2.1, 48))
    )
    with pytest.raises(ValueError, match="sample budget exceeded"):
        sample_routed_geometry(route, spacing_m=1, maximum_samples=100)
    assert len(sample_routed_geometry(route, spacing_m=1, maximum_samples=101)) == 101
    with pytest.raises(ValueError, match="invalid sample budget"):
        sample_routed_geometry(route, maximum_samples=2_049)


def test_invalid_geometry_and_profile_cannot_be_research_routes() -> None:
    with pytest.raises(ValidationError):
        ResearchRoute.model_validate(
            {
                "routing_profile": "bike",
                "distance_m": 1,
                "geometry": [[2, 48], [2.1, 48]],
            }
        )
    with pytest.raises(ValidationError):
        ResearchRoute(
            routing_profile="hike",
            distance_m=100,
            geometry=((2, float("nan")), (2.1, 48)),
        )
    with pytest.raises(ValueError, match="degenerate"):
        sample_routed_geometry(
            ResearchRoute(
                routing_profile="hike", distance_m=100, geometry=((2, 48), (2, 48))
            )
        )


def availability_plan(probe: HgtProbe) -> HeightPlan:
    route = ResearchRoute(
        routing_profile="trail_run", distance_m=10, geometry=((2.1, 48.1), (2.1, 47.9))
    )
    return height_plan(route, probe)


def test_missing_height_stays_null_and_valid_sea_level_stays_zero(
    zero_probe: HgtProbe,
) -> None:
    plan = availability_plan(zero_probe)
    result = compare_heights(plan, (0.0, None), zero_probe)
    assert result["available_count"] == 1
    assert result["unavailable_count"] == 1
    assert result["publication_allowed"] is False
    assert result["routing_profile"] == "trail_run"
    samples = result["samples"]
    assert isinstance(samples, list)
    assert samples[0]["height_m"] == 0
    assert samples[1]["height_m"] is None


def test_native_identity_count_and_availability_mismatches_fail(
    zero_probe: HgtProbe,
) -> None:
    plan = availability_plan(zero_probe)
    for heights, message in [
        ((0.0,), "count"),
        ((None, None), "availability"),
        ((0.0, 0.0), "availability"),
    ]:
        with pytest.raises(ValueError, match=message):
            compare_heights(plan, heights, zero_probe)
    with pytest.raises(ValueError, match="source identity"):
        compare_heights(plan, (0.0, None), replace(zero_probe, source_sha256="b" * 64))


def test_nonfinite_height_and_excessive_independent_error_are_rejected(
    zero_probe: HgtProbe,
) -> None:
    plan = availability_plan(zero_probe)
    with pytest.raises(ValueError, match="invalid native height"):
        compare_heights(plan, (float("nan"), None), zero_probe)
    with pytest.raises(ValueError, match="height error exceeds"):
        compare_heights(plan, (0.1, None), zero_probe)
    assert (
        compare_heights(plan, (0.0005, None), zero_probe)["maximum_absolute_error_m"]
        == 0.0005
    )


def test_plan_serialization_remains_unpublished_and_preserves_profile(
    zero_probe: HgtProbe,
) -> None:
    plan = availability_plan(zero_probe)
    assert HeightPlan.model_validate_json(plan.model_dump_json()) == plan
    with pytest.raises(ValidationError):
        HeightPlan.model_validate({**plan.model_dump(), "publication_allowed": True})


def test_native_decimal_truncation_allows_under_one_centimetre(
    zero_probe: HgtProbe,
) -> None:
    data = bytearray(zero_probe.data)
    for row in (3239, 3240):
        for column, value in ((360, 92), (361, 93)):
            struct.pack_into(
                ">h", data, (row * HGT_SAMPLES_PER_SIDE + column) * 2, value
            )
    probe = replace(zero_probe, data=bytes(data), max_height_m=93)
    route = ResearchRoute(
        routing_profile="hike",
        distance_m=10,
        geometry=((2.100002, 48.1), (2.100002, 47.9)),
    )
    plan = height_plan(route, probe)
    result = compare_heights(plan, (92.0, None), probe)
    assert result["maximum_absolute_error_m"] == pytest.approx(0.0072)
    with pytest.raises(ValueError, match="height error exceeds"):
        compare_heights(plan, (92.0, None), probe, tolerance_m=0.006)
