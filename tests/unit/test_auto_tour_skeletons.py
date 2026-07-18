"""Deterministic Auto Tour ellipse and direction tests."""

import pytest
from shapely.geometry import Point, Polygon, box

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.domain.models import Coordinate
from sugarglider.tours.skeletons import (
    ELLIPSE_VERTEX_COUNT,
    classify_route_direction,
    ellipse_vertices,
    generate_isochrone_skeletons,
    ramanujan_perimeter,
    routing_points_with_hard_anchors,
    sample_round_trip_routing_points,
    solve_ellipse_axes,
)

START = Coordinate(lat=48.87, lon=2.09, name="Start")


def _wgs84_box(radius_m: float) -> Polygon:
    projection = LocalMetricProjection(START.lat)
    center = projection.project_position((START.lon, START.lat))
    metric = box(
        center[0] - radius_m,
        center[1] - radius_m,
        center[0] + radius_m,
        center[1] + radius_m,
    )
    corners = tuple(
        projection.unproject_position((float(position[0]), float(position[1])))
        for position in metric.exterior.coords
    )
    return Polygon(corners)


@pytest.mark.parametrize("aspect_ratio", [1.0, 0.75, 0.55])
def test_axis_solve_matches_target_perimeter(aspect_ratio: float) -> None:
    major, minor = solve_ellipse_axes(41_000, aspect_ratio)
    assert minor == pytest.approx(major * aspect_ratio)
    assert ramanujan_perimeter(major, minor) == pytest.approx(41_000, abs=1e-8)


@pytest.mark.parametrize("direction", ["clockwise", "counterclockwise"])
def test_start_is_exactly_vertex_zero_on_six_vertex_perimeter(direction: str) -> None:
    vertices, center = ellipse_vertices(
        start=START,
        bearing_degrees=45,
        major_radius_m=5_000,
        minor_radius_m=3_000,
        direction=direction,  # type: ignore[arg-type]
    )
    projection = LocalMetricProjection(START.lat)
    assert len(vertices) == ELLIPSE_VERTEX_COUNT
    assert vertices[0] is START
    start_metric = projection.project_position((START.lon, START.lat))
    assert Point(start_metric).distance(Point(center)) == pytest.approx(5_000)
    assert len({(vertex.lat, vertex.lon) for vertex in vertices}) == 6


def test_clockwise_and_counterclockwise_sequences_are_opposite() -> None:
    clockwise, _ = ellipse_vertices(
        start=START,
        bearing_degrees=90,
        major_radius_m=4_000,
        minor_radius_m=3_000,
        direction="clockwise",
    )
    counterclockwise, _ = ellipse_vertices(
        start=START,
        bearing_degrees=90,
        major_radius_m=4_000,
        minor_radius_m=3_000,
        direction="counterclockwise",
    )
    assert tuple((point.lat, point.lon) for point in clockwise[1:]) == tuple(
        (point.lat, point.lon) for point in reversed(counterclockwise[1:])
    )


def test_direction_filtering_and_deterministic_containment_shrink() -> None:
    envelope = _wgs84_box(8_000)
    first = generate_isochrone_skeletons(
        start=START,
        target_distance_m=41_000,
        envelope=envelope,
        direction_preference="clockwise",
    )
    second = generate_isochrone_skeletons(
        start=START,
        target_distance_m=41_000,
        envelope=envelope,
        direction_preference="clockwise",
    )
    assert first == second
    assert first
    assert all(skeleton.direction == "clockwise" for skeleton in first)
    assert any(skeleton.containment_scale < 1 for skeleton in first)
    projection = LocalMetricProjection(START.lat)
    metric_envelope = projection.project_polygon(envelope)
    for skeleton in first:
        assert all(
            metric_envelope.covers(
                Point(projection.project_position((vertex.lon, vertex.lat)))
            )
            for vertex in skeleton.vertices[1:]
        )


def test_skeleton_is_rejected_below_minimum_without_boundary_projection() -> None:
    envelope = _wgs84_box(100)
    assert (
        generate_isochrone_skeletons(
            start=START,
            target_distance_m=41_000,
            envelope=envelope,
        )
        == ()
    )


def test_hard_points_are_inserted_monotonically_and_start_remains_fixed() -> None:
    skeleton = generate_isochrone_skeletons(
        start=START,
        target_distance_m=20_000,
        envelope=_wgs84_box(20_000),
        direction_preference="counterclockwise",
    )[0]
    hard = (
        Coordinate(lat=48.89, lon=2.10, name="A"),
        Coordinate(lat=48.86, lon=2.05, name="B"),
    )
    points = routing_points_with_hard_anchors(skeleton, hard)
    assert points[0] is points[-1] is START
    assert all(point in points for point in hard)
    assert len(points) == ELLIPSE_VERTEX_COUNT + len(hard) + 1


def test_complete_route_direction_uses_geometry_not_requested_order() -> None:
    clockwise = (
        (2.0, 48.0),
        (2.0, 48.1),
        (2.1, 48.1),
        (2.1, 48.0),
        (2.0, 48.0),
    )
    counterclockwise = tuple(reversed(clockwise))
    assert classify_route_direction(clockwise).direction == "clockwise"
    assert classify_route_direction(counterclockwise).direction == "counterclockwise"


def test_highly_mixed_route_has_explicit_warning() -> None:
    bow = (
        (2.0, 48.0),
        (2.1, 48.1),
        (2.0, 48.1),
        (2.1, 48.0),
        (2.0, 48.0),
    )
    analysis = classify_route_direction(bow)
    assert analysis.direction == "mixed"
    assert "auto_tour_direction_highly_mixed" in analysis.warnings


def test_round_trip_sampling_is_ordered_bounded_and_deterministic() -> None:
    geometry = (
        (START.lon, START.lat),
        (2.16, 48.87),
        (2.16, 48.92),
        (2.09, 48.92),
        (START.lon, START.lat),
    )
    first = sample_round_trip_routing_points(
        start=START,
        geometry=geometry,
        route_distance_m=30_000,
    )
    second = sample_round_trip_routing_points(
        start=START,
        geometry=geometry,
        route_distance_m=30_000,
    )
    assert first == second
    assert first is not None
    assert first[0] is first[-1] is START
    assert 5 <= len(first) - 2 <= 8
    projection = LocalMetricProjection(START.lat)
    anchors = tuple(
        projection.project_position((point.lon, point.lat)) for point in first[:-1]
    )
    for left, right in zip(anchors, anchors[1:], strict=False):
        assert Point(left).distance(Point(right)) >= 250
