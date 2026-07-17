"""Pure tests for deterministic backend-classified map sections."""

import pytest

from sugarglider.analysis.route import RouteAnalyzer
from sugarglider.analysis.visualization import build_route_visualization
from sugarglider.domain.models import (
    GeoJsonPosition,
    PathDetailSegment,
    RouteResult,
    RouteSummary,
)


def route(
    geometry: tuple[GeoJsonPosition, ...],
    edge_ids: tuple[int | None, ...] | None,
    *,
    distance_m: float | None = None,
    surface: str | None = "GRAVEL",
) -> RouteResult:
    """Build a valid analyzed result with one detail segment per geometry edge."""
    path_details: dict[str, tuple[PathDetailSegment, ...]] = {}
    if edge_ids is not None:
        path_details["edge_id"] = tuple(
            PathDetailSegment(from_index=index, to_index=index + 1, value=value)
            for index, value in enumerate(edge_ids)
            if value is not None
        )
    if surface is not None:
        path_details["surface"] = (
            PathDetailSegment(
                from_index=0,
                to_index=len(geometry) - 1,
                value=surface,
            ),
        )
    total = distance_m if distance_m is not None else float(len(geometry) - 1) * 100
    return RouteResult(
        name="Visualization route",
        summary=RouteSummary(
            distance_m=total,
            duration_ms=1,
            input_point_count=2,
            routed_point_count=len(geometry),
        ),
        geometry=geometry,
        path_details=path_details,
        analysis=RouteAnalyzer().analyze(geometry, total, path_details),
    )


def line(edge_count: int) -> tuple[GeoJsonPosition, ...]:
    return tuple((2.0 + index * 0.001, 48.0) for index in range(edge_count + 1))


def kinds(result: RouteResult) -> list[str]:
    return [
        feature.properties.kind
        for feature in build_route_visualization(result).features
    ]


def test_no_repetition_groups_compatible_adjacent_geometry_edges() -> None:
    visualization = build_route_visualization(route(line(3), (7, 7, 7)))
    assert len(visualization.features) == 1
    assert visualization.features[0].properties.kind == "normal"
    assert visualization.features[0].geometry.coordinates == line(3)


def test_repeated_edge_used_later_marks_only_later_run() -> None:
    visualization = build_route_visualization(route(line(3), (1, 2, 1)))
    assert [feature.properties.kind for feature in visualization.features] == [
        "normal",
        "normal",
        "repeated",
    ]
    assert visualization.features[-1].properties.distance_m == pytest.approx(100)


def test_one_edge_immediate_reversal_has_priority_over_repetition() -> None:
    result = route(((0.0, 0.0), (0.001, 0.0), (0.0, 0.0)), (9, 9))
    assert kinds(result) == ["normal", "immediate_backtrack"]


def test_multi_edge_out_and_back_marks_returning_half() -> None:
    geometry = (
        (0.0, 0.0),
        (0.001, 0.0),
        (0.002, 0.0),
        (0.001, 0.0),
        (0.0, 0.0),
    )
    visualization = build_route_visualization(route(geometry, (1, 2, 2, 1)))
    assert [feature.properties.kind for feature in visualization.features] == [
        "normal",
        "normal",
        "immediate_backtrack",
        "immediate_backtrack",
    ]


def test_unknown_edge_ids_remain_visibly_unknown_and_break_continuity() -> None:
    visualization = build_route_visualization(route(line(3), (1, None, 1)))
    assert visualization.features[1].properties.edge_id is None
    assert visualization.features[1].properties.kind == "normal"
    assert visualization.features[2].properties.kind == "repeated"


def test_feature_distances_conserve_authoritative_route_distance() -> None:
    visualization = build_route_visualization(
        route(line(3), (1, 2, 1), distance_m=987.65)
    )
    assert sum(
        feature.properties.distance_m for feature in visualization.features
    ) == pytest.approx(987.65)


def test_geojson_coordinate_order_and_serialization_are_deterministic() -> None:
    geometry = ((2.1, 48.7), (2.2, 48.8), (2.3, 48.9))
    result = route(geometry, (3, 4))
    first = build_route_visualization(result)
    second = build_route_visualization(result)
    assert first.features[0].geometry.coordinates == (geometry[0], geometry[1])
    assert first.model_dump_json() == second.model_dump_json()
