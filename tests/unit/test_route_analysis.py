"""Focused tests for deterministic normalized route analysis."""

from math import isclose

import pytest

from sugarglider.analysis.route import (
    MAJOR_ROAD_CLASSES,
    OFFICIAL_HIKING_NETWORKS,
    PAVED_SURFACES,
    TRAIL_LIKE_ROAD_CLASSES,
    UNPAVED_SURFACES,
    RouteAnalysisError,
    RouteAnalyzer,
    haversine_distance_m,
)
from sugarglider.domain.analysis import DetailValue, RouteAnalysis
from sugarglider.domain.models import GeoJsonPosition, PathDetailSegment


def geometry(edge_count: int) -> tuple[GeoJsonPosition, ...]:
    """Create equal-length eastbound equatorial edges."""
    return tuple((index * 0.001, 0.0) for index in range(edge_count + 1))


def segments(values: list[DetailValue]) -> tuple[PathDetailSegment, ...]:
    return tuple(
        PathDetailSegment(from_index=index, to_index=index + 1, value=value)
        for index, value in enumerate(values)
    )


def analyze_values(
    detail: str, values: list[DetailValue], route_distance_m: float | None = None
) -> RouteAnalysis:
    distance = float(len(values)) if route_distance_m is None else route_distance_m
    return RouteAnalyzer().analyze(
        geometry(len(values)), distance, {detail: segments(values)}
    )


def test_haversine_distance_uses_geojson_order() -> None:
    distance = haversine_distance_m((0.0, 0.0), (1.0, 0.0))
    assert distance == pytest.approx(111_195, rel=1e-4)


def test_distance_normalization_scales_edges_to_authoritative_total() -> None:
    analysis = RouteAnalyzer().analyze(geometry(3), 900.0, {})
    assert analysis.geometry_distance_m > 300
    assert analysis.distance_scale_factor == pytest.approx(
        900.0 / analysis.geometry_distance_m
    )
    assert analysis.unknown_surface.distance_m == pytest.approx(900.0)
    assert analysis.unknown_surface.share == 1.0


def test_zero_route_distance_is_intentional() -> None:
    analysis = RouteAnalyzer().analyze(geometry(2), 0.0, {})
    assert analysis.distance_scale_factor == 0.0
    assert analysis.unknown_surface.distance_m == 0.0
    assert analysis.unknown_surface.share == 0.0


def test_zero_length_geometry_and_zero_route_is_supported() -> None:
    analysis = RouteAnalyzer().analyze(((2.0, 48.0), (2.0, 48.0)), 0.0, {})
    assert analysis.geometry_distance_m == 0.0
    assert analysis.distance_scale_factor == 0.0


@pytest.mark.parametrize(
    ("route_geometry", "route_distance"),
    [
        (((2.0, 48.0),), 0.0),
        (((2.0, 48.0), (2.0, 48.0)), 10.0),
        (((2.0, 48.0), (2.1, 48.0)), -1.0),
    ],
)
def test_impossible_distance_inputs_are_rejected(
    route_geometry: tuple[GeoJsonPosition, ...], route_distance: float
) -> None:
    with pytest.raises(RouteAnalysisError):
        RouteAnalyzer().analyze(route_geometry, route_distance, {})


def test_one_interval_projects_over_one_edge() -> None:
    analysis = RouteAnalyzer().analyze(
        geometry(2),
        200.0,
        {"surface": (PathDetailSegment(from_index=0, to_index=1, value="PAVED"),)},
    )
    breakdown = analysis.detail_breakdowns["surface"]
    assert breakdown.covered_distance_m == pytest.approx(100.0)
    assert breakdown.coverage_share == pytest.approx(0.5)


def test_one_interval_projects_over_several_edges() -> None:
    analysis = RouteAnalyzer().analyze(
        geometry(4),
        400.0,
        {"surface": (PathDetailSegment(from_index=1, to_index=4, value="GRAVEL"),)},
    )
    assert analysis.detail_breakdowns["surface"].covered_distance_m == pytest.approx(
        300.0
    )


def test_adjacent_intervals_and_gaps_are_allowed() -> None:
    analysis = RouteAnalyzer().analyze(
        geometry(4),
        400.0,
        {
            "surface": (
                PathDetailSegment(from_index=0, to_index=1, value="PAVED"),
                PathDetailSegment(from_index=1, to_index=2, value="GRAVEL"),
                PathDetailSegment(from_index=3, to_index=4, value=None),
            )
        },
    )
    breakdown = analysis.detail_breakdowns["surface"]
    assert breakdown.covered_distance_m == pytest.approx(300.0)
    assert [bucket.value for bucket in breakdown.buckets] == [None, "GRAVEL", "PAVED"]
    assert analysis.unknown_surface.distance_m == pytest.approx(200.0)


@pytest.mark.parametrize(
    "detail_segments",
    [
        (
            PathDetailSegment(from_index=0, to_index=2, value="A"),
            PathDetailSegment(from_index=1, to_index=3, value="B"),
        ),
        (PathDetailSegment(from_index=1, to_index=1, value="A"),),
        (PathDetailSegment(from_index=2, to_index=1, value="A"),),
        (PathDetailSegment(from_index=0, to_index=3, value="A"),),
        (PathDetailSegment.model_construct(from_index=-1, to_index=1, value="A"),),
    ],
)
def test_invalid_detail_intervals_are_rejected(
    detail_segments: tuple[PathDetailSegment, ...],
) -> None:
    with pytest.raises(RouteAnalysisError):
        RouteAnalyzer().analyze(geometry(2), 200.0, {"surface": detail_segments})


@pytest.mark.parametrize("surface", sorted(PAVED_SURFACES))
def test_all_paved_surfaces(surface: str) -> None:
    analysis = analyze_values("surface", [surface])
    assert analysis.paved.distance_m == pytest.approx(1.0)


@pytest.mark.parametrize("surface", sorted(UNPAVED_SURFACES))
def test_all_unpaved_surfaces(surface: str) -> None:
    analysis = analyze_values("surface", [surface.lower()])
    assert analysis.unpaved.distance_m == pytest.approx(1.0)


@pytest.mark.parametrize("surface", [None, "MISSING", "OTHER", "FUTURE_SURFACE"])
def test_unknown_surface_values(surface: DetailValue) -> None:
    analysis = analyze_values("surface", [surface])
    assert analysis.unknown_surface.distance_m == pytest.approx(1.0)


def test_surface_partition_always_sums_to_route() -> None:
    analysis = RouteAnalyzer().analyze(
        geometry(5),
        500.0,
        {"surface": segments(["ASPHALT", "GRAVEL", None, "OTHER"])},
    )
    classified = (
        analysis.paved.distance_m
        + analysis.unpaved.distance_m
        + analysis.unknown_surface.distance_m
    )
    assert classified == pytest.approx(analysis.route_distance_m)


@pytest.mark.parametrize("road_class", sorted(TRAIL_LIKE_ROAD_CLASSES))
def test_trail_like_road_classes(road_class: str) -> None:
    analysis = analyze_values("road_class", [road_class])
    assert analysis.trail_like.share == 1.0


@pytest.mark.parametrize(
    "road_class", ["RESIDENTIAL", "SERVICE", "UNCLASSIFIED", "CYCLEWAY", "ROAD"]
)
def test_non_trail_road_classes(road_class: str) -> None:
    analysis = analyze_values("road_class", [road_class])
    assert analysis.trail_like.share == 0.0


@pytest.mark.parametrize("network", sorted(OFFICIAL_HIKING_NETWORKS))
def test_official_hiking_networks(network: str) -> None:
    analysis = analyze_values("foot_network", [network.lower()])
    assert analysis.official_hiking_network.share == 1.0


@pytest.mark.parametrize("road_class", sorted(MAJOR_ROAD_CLASSES))
def test_major_road_classes(road_class: str) -> None:
    analysis = analyze_values("road_class", [road_class])
    assert analysis.major_road.share == 1.0


def test_car_access_requires_explicit_true() -> None:
    analysis = RouteAnalyzer().analyze(
        geometry(3),
        300.0,
        {"car_access": segments([True, False])},
    )
    assert analysis.car_accessible.distance_m == pytest.approx(100.0)
    assert analysis.car_accessible.share == pytest.approx(1 / 3)


def test_unique_edge_ids_have_no_repetition() -> None:
    analysis = analyze_values("edge_id", [1, 2, 3])
    repetition = analysis.repetition
    assert repetition.available
    assert repetition.unique_edge_count == 3
    assert repetition.traversed_edge_run_count == 3
    assert repetition.repeated_edge_count == 0
    assert repetition.repeated_distance.distance_m == 0


def test_adjacent_pieces_of_same_edge_form_one_run() -> None:
    repetition = analyze_values("edge_id", [1, 1, 2]).repetition
    assert repetition.unique_edge_count == 2
    assert repetition.traversed_edge_run_count == 2
    assert repetition.repeated_edge_count == 0


def test_later_non_contiguous_run_counts_only_subsequent_distance() -> None:
    repetition = analyze_values("edge_id", [1, 1, 2, 1], 400.0).repetition
    assert repetition.unique_edge_count == 2
    assert repetition.traversed_edge_run_count == 3
    assert repetition.repeated_edge_count == 1
    assert repetition.repeated_distance.distance_m == pytest.approx(100.0)
    assert repetition.repeated_distance.share == pytest.approx(0.25)


def test_three_runs_and_opposite_direction_reuse_count_as_repetition() -> None:
    repetition = analyze_values("edge_id", [7, 2, 7, 3, 7], 500.0).repetition
    assert repetition.repeated_edge_count == 1
    assert repetition.traversed_edge_run_count == 5
    assert repetition.repeated_distance.distance_m == pytest.approx(200.0)


def test_immediate_opposite_direction_traversal_starts_a_new_run() -> None:
    route_geometry = ((0.0, 0.0), (0.001, 0.0), (0.0, 0.0))
    detail = (PathDetailSegment(from_index=0, to_index=2, value=7),)
    repetition = (
        RouteAnalyzer().analyze(route_geometry, 200.0, {"edge_id": detail}).repetition
    )
    assert repetition.unique_edge_count == 1
    assert repetition.traversed_edge_run_count == 2
    assert repetition.repeated_edge_count == 1
    assert repetition.repeated_distance.distance_m == pytest.approx(100.0)


def test_incomplete_edge_id_coverage_is_visible() -> None:
    analysis = RouteAnalyzer().analyze(
        geometry(3),
        300.0,
        {"edge_id": (PathDetailSegment(from_index=0, to_index=2, value=1),)},
    )
    assert analysis.repetition.edge_id_coverage.share == pytest.approx(2 / 3)
    assert "edge_id_coverage_incomplete" in analysis.warnings


def test_absent_edge_ids_disable_repetition() -> None:
    analysis = RouteAnalyzer().analyze(geometry(2), 200.0, {})
    repetition = analysis.repetition
    assert not repetition.available
    assert repetition.unique_edge_count == 0
    assert repetition.repeated_distance.distance_m == 0
    assert "edge_id_coverage_incomplete" in analysis.warnings


def test_analysis_is_deterministic_across_detail_dictionary_order() -> None:
    details_a = {
        "surface": segments(["PAVED", "GRAVEL"]),
        "mixed": segments([None, True]),
    }
    details_b = {"mixed": details_a["mixed"], "surface": details_a["surface"]}
    analyzer = RouteAnalyzer()
    first = analyzer.analyze(geometry(2), 200.0, details_a)
    second = analyzer.analyze(geometry(2), 200.0, details_b)
    assert first.model_dump_json() == second.model_dump_json()


def test_mixed_bucket_values_have_stable_type_aware_order() -> None:
    values: list[DetailValue] = ["text", 2.5, 2, True, None]
    analysis = analyze_values("mixed", values)
    buckets = analysis.detail_breakdowns["mixed"].buckets
    assert [bucket.value for bucket in buckets] == [None, True, 2, 2.5, "text"]
    assert isclose(
        sum(bucket.distance_m for bucket in buckets),
        analysis.detail_breakdowns["mixed"].covered_distance_m,
    )
