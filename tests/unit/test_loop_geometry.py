"""Deterministic projected global-loop geometry and penalty tests."""

import inspect
from collections.abc import Sequence
from math import cos, hypot, pi, sin
from typing import Any

import pytest
from pydantic import ValidationError
from shapely import STRtree
from shapely.geometry import LineString

import sugarglider.analysis.loop_geometry as loop_geometry_module
import sugarglider.nature.projection as nature_projection_module
from sugarglider.analysis.loop_geometry import (
    DEFAULT_LOOP_GEOMETRY_PENALTY_WEIGHTS,
    LOOP_CLOSURE_TOLERANCE_M,
    LoopGeometryRouteAnalyzer,
    _self_crossing_count,
    score_loop_geometry,
)
from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import project_geometry_edges
from sugarglider.domain.analysis import LoopGeometryAnalysis
from sugarglider.domain.models import GeoJsonPosition
from sugarglider.nature.projection import (
    LocalMetricProjection as NatureProjectionImport,
)

type MetricPosition = tuple[float, float]


def _analysis(
    positions: Sequence[MetricPosition], *, route_distance_m: float | None = None
) -> LoopGeometryAnalysis:
    projection = LocalMetricProjection(0.0)
    geometry: tuple[GeoJsonPosition, ...] = tuple(
        projection.unproject_position(position) for position in positions
    )
    geometric_distance = sum(
        hypot(right[0] - left[0], right[1] - left[1])
        for left, right in zip(positions, positions[1:], strict=False)
    )
    distance = geometric_distance if route_distance_m is None else route_distance_m
    edges = project_geometry_edges(
        geometry=geometry,
        route_distance_m=distance,
        path_details={},
    ).edges
    return LoopGeometryRouteAnalyzer().analyze_route(edges, distance)


def _circle(radius_m: float = 1_000.0, count: int = 128) -> tuple[MetricPosition, ...]:
    points = tuple(
        (
            radius_m * cos(2.0 * pi * index / count),
            radius_m * sin(2.0 * pi * index / count),
        )
        for index in range(count)
    )
    return (*points, points[0])


def test_projection_is_shared_deterministic_and_rejects_invalid_coordinates() -> None:
    assert NatureProjectionImport is LocalMetricProjection
    projection = LocalMetricProjection(48.0)
    position: GeoJsonPosition = (2.001, 48.001)
    assert projection.unproject_position(
        projection.project_position(position)
    ) == pytest.approx(position)
    assert projection.project_position(position) == projection.project_position(
        position
    )
    with pytest.raises(ValueError, match="longitude"):
        projection.project_position((181.0, 48.0))
    with pytest.raises(ValueError, match="latitude"):
        projection.project_position((2.0, float("nan")))
    with pytest.raises(ValueError, match="reference latitude"):
        LocalMetricProjection(91.0)
    assert "class LocalMetricProjection" not in inspect.getsource(
        nature_projection_module
    )


def test_circle_and_square_have_explainable_compactness() -> None:
    circle = _analysis(_circle())
    square = _analysis(((0, 0), (1_000, 0), (1_000, 1_000), (0, 1_000), (0, 0)))
    assert circle.closed and square.closed
    assert circle.compactness == pytest.approx(1.0, abs=0.002)
    assert square.enclosed_area_m2 == pytest.approx(1_000_000, rel=1e-9)
    assert square.compactness == pytest.approx(pi / 4.0, rel=1e-9)
    assert square.convex_hull_area_m2 == pytest.approx(1_000_000, rel=1e-9)


def test_lollipop_stem_lowers_compactness_and_repeated_stem_is_near_parallel() -> None:
    square = _analysis(((0, 0), (1_000, 0), (1_000, 1_000), (0, 1_000), (0, 0)))
    lollipop = _analysis(
        (
            (0, 0),
            (3_000, 0),
            (3_000, 1_000),
            (4_000, 1_000),
            (4_000, 0),
            (3_000, 0),
            (0, 0),
        )
    )
    assert lollipop.enclosed_area_m2 == pytest.approx(square.enclosed_area_m2)
    assert lollipop.compactness < square.compactness
    assert lollipop.near_parallel.distance_m > 5_000
    assert lollipop.near_parallel.share > 0.5


def test_elongated_rectangle_has_lower_elongation_than_square() -> None:
    square = _analysis(((0, 0), (1_000, 0), (1_000, 1_000), (0, 1_000), (0, 0)))
    elongated = _analysis(((0, 0), (4_000, 0), (4_000, 250), (0, 250), (0, 0)))
    assert square.elongation == pytest.approx(1.0)
    assert elongated.elongation == pytest.approx(0.0625)
    assert elongated.elongation < square.elongation


def test_open_and_degenerate_routes_warn_without_inventing_area() -> None:
    opened = _analysis(((0, 0), (1_000, 0), (1_000, 1_000)))
    assert not opened.closed
    assert opened.start_end_gap_m > LOOP_CLOSURE_TOLERANCE_M
    assert opened.enclosed_area_m2 == 0
    assert opened.compactness == 0
    assert "loop_geometry_route_not_closed" in opened.warnings

    degenerate = _analysis(((0, 0), (0, 0)), route_distance_m=0)
    assert degenerate.closed
    assert degenerate.enclosed_area_m2 == 0
    assert degenerate.convex_hull_area_m2 == 0
    assert degenerate.elongation == 0
    assert "loop_geometry_degenerate" in degenerate.warnings


@pytest.mark.parametrize("gap_m", [10.0, 24.999])
def test_near_closed_route_uses_synthetic_segment_for_area_only(gap_m: float) -> None:
    positions = (
        (0.0, 0.0),
        (1_000.0, 0.0),
        (1_000.0, 1_000.0),
        (0.0, 1_000.0),
        (0.0, gap_m),
    )
    route_distance_m = sum(
        hypot(right[0] - left[0], right[1] - left[1])
        for left, right in zip(positions, positions[1:], strict=False)
    )
    analysis = _analysis(positions)

    assert analysis.closed
    assert analysis.start_end_gap_m == pytest.approx(gap_m, abs=1e-6)
    assert analysis.enclosed_area_m2 > 0
    assert analysis.compactness > 0
    assert analysis.near_parallel.distance_m <= route_distance_m


def test_route_just_above_closure_tolerance_remains_open() -> None:
    opened = _analysis(
        (
            (0.0, 0.0),
            (1_000.0, 0.0),
            (1_000.0, 1_000.0),
            (0.0, 1_000.0),
            (0.0, 25.001),
        )
    )
    assert not opened.closed
    assert opened.start_end_gap_m > LOOP_CLOSURE_TOLERANCE_M
    assert opened.enclosed_area_m2 == 0
    assert opened.compactness == 0


def test_figure_eight_polygonizes_distinct_faces() -> None:
    figure_eight = _analysis(
        (
            (0, 0),
            (1_000, 1_000),
            (0, 2_000),
            (-1_000, 1_000),
            (0, 0),
            (1_000, -1_000),
            (0, -2_000),
            (-1_000, -1_000),
            (0, 0),
        )
    )
    assert figure_eight.enclosed_area_m2 == pytest.approx(4_000_000, rel=1e-9)
    assert figure_eight.self_crossing_count == 0


def test_one_interior_perpendicular_crossing_is_unique_and_not_near_parallel() -> None:
    crossing = _analysis(
        (
            (0, -1_000),
            (0, 1_000),
            (-1_000, 0),
            (1_000, 0),
            (0, -1_000),
        )
    )
    assert crossing.self_crossing_count == 1
    assert crossing.near_parallel.distance_m == pytest.approx(0, abs=1e-6)


def test_parallel_corridor_exceeds_separated_corridor_and_adjacent_bends() -> None:
    close = _analysis(((0, 0), (1_000, 0), (1_000, 30), (0, 30), (0, 0)))
    separated = _analysis(((0, 0), (1_000, 0), (1_000, 100), (0, 100), (0, 0)))
    square = _analysis(((0, 0), (1_000, 0), (1_000, 1_000), (0, 1_000), (0, 0)))
    assert close.near_parallel.share > separated.near_parallel.share
    assert separated.near_parallel.distance_m == pytest.approx(0, abs=1e-6)
    assert square.near_parallel.distance_m == pytest.approx(0, abs=1e-6)


def test_overlapping_neighbour_buffers_do_not_multiply_edge_distance() -> None:
    route = _analysis(
        (
            (0, 0),
            (1_000, 0),
            (1_000, 20),
            (0, 20),
            (0, 40),
            (1_000, 40),
            (1_000, 60),
            (0, 60),
            (0, 0),
        )
    )
    assert 0 < route.near_parallel.distance_m <= 4_000 + 120
    assert 0 < route.near_parallel.share <= 1


def test_sector_shares_partition_and_balanced_route_has_higher_entropy() -> None:
    balanced = _analysis(
        (
            (0, 0),
            (1_000, 0),
            (700, 700),
            (0, 1_000),
            (-700, 700),
            (-1_000, 0),
            (-700, -700),
            (0, -1_000),
            (700, -700),
            (0, 0),
        )
    )
    one_sided = _analysis(
        ((0, 0), (2_000, 0), (2_000, 200), (1_000, 200), (1_000, 0), (0, 0))
    )
    assert len(balanced.sector_distance_shares) == 8
    assert sum(balanced.sector_distance_shares) == pytest.approx(1.0)
    assert 0 <= balanced.sector_balance <= 1
    assert balanced.sector_balance > one_sided.sector_balance


def test_authoritative_distance_scales_public_distances_not_shares() -> None:
    positions = ((0, 0), (1_000, 0), (1_000, 30), (0, 30), (0, 0))
    normal = _analysis(positions)
    doubled = _analysis(
        positions,
        route_distance_m=2
        * sum(
            hypot(right[0] - left[0], right[1] - left[1])
            for left, right in zip(positions, positions[1:], strict=False)
        ),
    )
    assert doubled.near_parallel.distance_m == pytest.approx(
        2 * normal.near_parallel.distance_m
    )
    assert doubled.near_parallel.share == pytest.approx(normal.near_parallel.share)
    assert doubled.sector_distance_shares == pytest.approx(
        normal.sector_distance_shares
    )
    assert doubled.mean_radius_m == pytest.approx(normal.mean_radius_m)
    assert doubled.compactness < normal.compactness


def test_penalty_exposes_exact_weights_components_clipping_and_total() -> None:
    weights = DEFAULT_LOOP_GEOMETRY_PENALTY_WEIGHTS
    penalty = score_loop_geometry(
        self_crossing_count=12,
        near_parallel_share=0.2,
        compactness=0.4,
        sector_balance=0.6,
        elongation=0.8,
    )
    assert penalty.crossing_count_input == 8
    assert penalty.crossing_penalty == pytest.approx(
        weights.crossing_penalty_per_crossing * 8
    )
    assert penalty.near_parallel_penalty == pytest.approx(
        weights.near_parallel_penalty_weight * 0.2
    )
    assert penalty.compactness_penalty == pytest.approx(
        weights.compactness_penalty_weight * 0.6
    )
    assert penalty.sector_imbalance_penalty == pytest.approx(
        weights.sector_imbalance_penalty_weight * 0.4
    )
    assert penalty.elongation_penalty == pytest.approx(
        weights.elongation_penalty_weight * 0.2
    )
    assert penalty.total == pytest.approx(
        penalty.crossing_penalty
        + penalty.near_parallel_penalty
        + penalty.compactness_penalty
        + penalty.sector_imbalance_penalty
        + penalty.elongation_penalty
    )
    worse = score_loop_geometry(
        self_crossing_count=0,
        near_parallel_share=0.3,
        compactness=1,
        sector_balance=1,
        elongation=1,
    )
    better = score_loop_geometry(
        self_crossing_count=0,
        near_parallel_share=0.1,
        compactness=1,
        sector_balance=1,
        elongation=1,
    )
    assert worse.total > better.total
    clipped = score_loop_geometry(
        self_crossing_count=999,
        near_parallel_share=2,
        compactness=-1,
        sector_balance=2,
        elongation=-1,
    )
    assert clipped.crossing_count_input == 8
    assert clipped.near_parallel_share_input == 1
    assert clipped.compactness_input == 0
    assert clipped.sector_balance_input == 1
    assert clipped.elongation_input == 0


def test_public_model_rejects_crossing_input_inconsistent_with_analysis() -> None:
    payload = _analysis(
        ((0, 0), (1_000, 0), (1_000, 1_000), (0, 1_000), (0, 0))
    ).model_dump()
    payload["penalty_breakdown"]["crossing_count_input"] = 1
    with pytest.raises(ValidationError, match="penalty inputs"):
        LoopGeometryAnalysis.model_validate(payload)


@pytest.mark.parametrize(
    "component",
    [
        "crossing_penalty",
        "near_parallel_penalty",
        "compactness_penalty",
        "sector_imbalance_penalty",
        "elongation_penalty",
    ],
)
def test_public_model_rejects_component_inconsistent_with_weight_and_input(
    component: str,
) -> None:
    payload = _analysis(_circle()).model_dump()
    payload["penalty_breakdown"][component] += 0.01
    payload["penalty_breakdown"]["total"] += 0.01
    with pytest.raises(ValidationError, match="weights and inputs"):
        LoopGeometryAnalysis.model_validate(payload)


def test_crossing_deduplication_and_tree_query_order_are_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lines = (
        LineString(((-1_000, 0), (1_000, 0))),
        LineString(((2_000, 2_000), (3_000, 2_000))),
        LineString(((0, -1_000), (0, 1_000))),
        LineString(((2_000, 3_000), (3_000, 3_000))),
        LineString(((-1_000, -1_000), (1_000, 1_000))),
    )
    assert _self_crossing_count(lines, STRtree(lines), False) == 1

    original_tree = vars(loop_geometry_module)["STRtree"]

    class ReversedQueryTree:
        def __init__(self, geometries: Any) -> None:
            self._delegate = original_tree(geometries)

        def query(self, *args: Any, **kwargs: Any) -> tuple[int, ...]:
            raw = self._delegate.query(*args, **kwargs)
            return tuple(reversed(tuple(int(index) for index in raw)))

    positions = (
        (0, -1_000),
        (0, 1_000),
        (-1_000, 0),
        (1_000, 0),
        (0, -1_000),
    )
    expected = _analysis(positions)
    monkeypatch.setattr(loop_geometry_module, "STRtree", ReversedQueryTree)
    actual = _analysis(positions)
    assert actual == expected
