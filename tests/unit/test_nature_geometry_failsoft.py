"""Robust nature overlay repair and candidate fail-soft regression tests."""

from collections.abc import Sequence
from logging import WARNING

import pytest
from shapely.errors import GEOSException
from shapely.geometry import GeometryCollection, LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

import sugarglider.nature.analysis as nature_analysis_module
from sugarglider.analysis.route import ProjectedGeometryEdge, RouteAnalyzer
from sugarglider.domain.models import RouteResult
from sugarglider.nature.analysis import (
    NATURE_GEOMETRY_OVERLAY_WARNING,
    NatureRouteAnalyzer,
)
from sugarglider.nature.classification import PrimaryNatureClass
from sugarglider.nature.index import NatureIndex
from sugarglider.nature.models import (
    NatureIndexDocument,
    NatureIndexFeature,
    NatureIndexMetadata,
    PolygonGeometry,
)
from sugarglider.nature.scoring import available_nature_score
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.models import PLAN_REQUEST_ADAPTER, WaypointPlanRequest
from sugarglider.planning.result import PlanScore
from sugarglider.planning.waypoint.scoring import (
    WaypointCandidateScorer,
    waypoint_comparison_total,
)


def _polygon(
    feature_id: str,
    primary_class: PrimaryNatureClass | None,
    coordinates: Sequence[tuple[float, float]],
    *,
    park: bool = False,
) -> NatureIndexFeature:
    return NatureIndexFeature(
        feature_id=feature_id,
        osm_id=int(feature_id.split("/")[1]),
        osm_source="way",
        primary_class=primary_class,
        park_or_protected=park,
        tags={},
        geometry=PolygonGeometry(coordinates=(tuple(coordinates),)),
    )


def _rectangle(
    west: float,
    east: float,
    south: float = -0.001,
    north: float = 0.001,
) -> tuple[tuple[float, float], ...]:
    return (
        (west, south),
        (east, south),
        (east, north),
        (west, north),
        (west, south),
    )


def _index(*features: NatureIndexFeature) -> NatureIndex:
    counts: dict[str, int] = {}
    for feature in features:
        if feature.primary_class is not None:
            counts[feature.primary_class] = counts.get(feature.primary_class, 0) + 1
        if feature.park_or_protected:
            counts["park_or_protected"] = counts.get("park_or_protected", 0) + 1
    return NatureIndex(
        NatureIndexDocument(
            metadata=NatureIndexMetadata(
                source_basename="overlay-regression.osm",
                reference_latitude=0,
                bounding_box=(-0.01, -0.01, 0.02, 0.01),
                category_counts={key: counts[key] for key in sorted(counts)},
                feature_count=len(features),
            ),
            features=tuple(sorted(features, key=lambda feature: feature.feature_id)),
        )
    )


def _edge(
    start: tuple[float, float] = (0, 0),
    end: tuple[float, float] = (0.004, 0),
    distance_m: float = 400,
) -> ProjectedGeometryEdge:
    return ProjectedGeometryEdge(0, 1, start, end, distance_m, ())


def _failed_analysis(
    monkeypatch: pytest.MonkeyPatch,
    *,
    distance_m: float,
) -> NatureRouteAnalyzer:
    analyzer = NatureRouteAnalyzer(
        _index(_polygon("way/1", "woodland", _rectangle(-0.002, 0.006)))
    )

    def fail_intersection(*_args: object, **_kwargs: object) -> object:
        raise GEOSException("forced intersection failure")

    monkeypatch.setattr(nature_analysis_module, "intersection", fail_intersection)
    evaluation = analyzer.analyze((_edge(distance_m=distance_m),), distance_m)
    assert not evaluation.analysis.available
    return analyzer


def test_overlapping_valid_polygons_preserve_priority_without_double_counting() -> None:
    analyzer = NatureRouteAnalyzer(
        _index(
            _polygon("way/1", "woodland", _rectangle(0, 0.0025)),
            _polygon("way/2", "woodland", _rectangle(0.0015, 0.003)),
            _polygon("way/3", "urban", _rectangle(0.002, 0.004)),
        )
    )
    first = analyzer.analyze((_edge(),), 400).analysis
    second = analyzer.analyze((_edge(),), 400).analysis

    assert first == second
    assert first.available
    assert first.woodland.distance_m == pytest.approx(200, abs=1e-5)
    assert first.urban.distance_m == pytest.approx(200, abs=1e-5)
    assert first.unknown_landcover.distance_m == pytest.approx(0, abs=1e-5)
    assert sum(
        metric.distance_m
        for metric in (
            first.woodland,
            first.open_natural,
            first.agriculture,
            first.water_crossing,
            first.urban,
            first.unknown_landcover,
        )
    ) == pytest.approx(400)


def test_polygonal_normalization_repairs_and_discards_non_area_artifacts() -> None:
    invalid = Polygon(((0, 0), (2, 2), (2, 0), (0, 2), (0, 0)))
    mixed = GeometryCollection(
        (
            invalid,
            LineString(((0, 0), (3, 0))),
            Point(9, 9),
            Polygon(),
        )
    )

    normalized = nature_analysis_module._normalize_polygonal(
        mixed,
        operation="test_normalization",
    )

    assert normalized.geom_type == "MultiPolygon"
    assert normalized.is_valid
    assert normalized.area == pytest.approx(2)
    assert all(part.geom_type == "Polygon" for part in normalized.geoms)


def test_valid_geometry_does_not_use_buffer_zero_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_buffer_zero(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("ordinary valid geometry must not use buffer(0)")

    monkeypatch.setattr(
        nature_analysis_module,
        "_buffer_zero_polygonal",
        fail_buffer_zero,
    )
    result = NatureRouteAnalyzer(
        _index(
            _polygon("way/1", "woodland", _rectangle(0, 0.003), park=True),
            _polygon("way/2", "urban", _rectangle(0.001, 0.004)),
        )
    ).analyze((_edge(),), 400)

    assert result.analysis.available
    assert result.analysis.woodland.distance_m == pytest.approx(100, abs=1e-5)
    assert result.analysis.urban.distance_m == pytest.approx(300, abs=1e-5)
    assert result.analysis.park_or_protected.distance_m == pytest.approx(
        300,
        abs=1e-5,
    )


def test_both_priority_union_strategies_fail_soft(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_union(*_args: object, **_kwargs: object) -> object:
        raise GEOSException("forced union failure")

    monkeypatch.setattr(nature_analysis_module, "coverage_union_all", fail_union)
    monkeypatch.setattr(nature_analysis_module, "unary_union", fail_union)
    analyzer = NatureRouteAnalyzer(
        _index(
            _polygon("way/1", "woodland", _rectangle(0, 0.003)),
            _polygon("way/2", "urban", _rectangle(0.001, 0.002)),
        )
    )

    with caplog.at_level(WARNING, logger=nature_analysis_module.__name__):
        analysis = analyzer.analyze((_edge(end=(0.003, 0), distance_m=300),), 300)

    assert not analysis.analysis.available
    assert analysis.analysis.warnings == (NATURE_GEOMETRY_OVERLAY_WARNING,)
    assert analysis.analysis.woodland.distance_m == 0
    assert analysis.analysis.urban.distance_m == 0
    assert analysis.analysis.unknown_landcover.distance_m == 300
    assert len(caplog.records) == 1
    assert "priority_coverage_general_union" in caplog.text
    assert "POLYGON" not in caplog.text


def test_priority_difference_failure_does_not_count_lower_priority_area(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_difference(*_args: object, **_kwargs: object) -> object:
        raise GEOSException("forced difference failure")

    monkeypatch.setattr(nature_analysis_module, "difference", fail_difference)
    analysis = NatureRouteAnalyzer(
        _index(
            _polygon("way/1", "woodland", _rectangle(0, 0.003)),
            _polygon("way/2", "urban", _rectangle(0.002, 0.004)),
        )
    ).analyze((_edge(),), 400)

    assert not analysis.analysis.available
    assert analysis.analysis.woodland.distance_m == 0
    assert analysis.analysis.urban.distance_m == 0
    assert analysis.analysis.unknown_landcover.distance_m == 400


def test_intersection_failure_preserves_complete_non_nature_route_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyzer = _failed_analysis(monkeypatch, distance_m=400)
    route = RouteAnalyzer(nature_analyzer=analyzer).analyze(
        ((0, 0), (0.004, 0)),
        400,
        {},
    )

    assert route.route_distance_m == 400
    assert route.unknown_surface.distance_m == 400
    assert route.nature is not None
    assert not route.nature.available
    assert route.nature.warnings == (NATURE_GEOMETRY_OVERLAY_WARNING,)
    assert route.nature.unknown_landcover.distance_m == 400
    assert route.nature.unknown_landcover.share == 1
    assert route.nature.score_breakdown.unknown_penalty.share == 1
    assert route.nature.nature_score == route.nature.score_breakdown.final_score
    assert analyzer.edge_contexts((_edge(),)) == (
        nature_analysis_module.NatureEdgeContext("unknown", False, False),
    )


def test_route_bounds_difference_failure_is_fail_soft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_difference(*_args: object, **_kwargs: object) -> object:
        raise GEOSException("forced bounds difference failure")

    monkeypatch.setattr(nature_analysis_module, "difference", fail_difference)
    analysis = NatureRouteAnalyzer(_index()).analyze((_edge(),), 400).analysis

    assert not analysis.available
    assert analysis.warnings == (NATURE_GEOMETRY_OVERLAY_WARNING,)
    assert analysis.unknown_landcover.distance_m == 400


def test_water_buffer_failure_is_local_to_nature_enrichment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    water = _polygon(
        "way/1",
        "water",
        _rectangle(0, 0.004, 0.0005, 0.0007),
    )

    def fail_buffer(
        _geometry: BaseGeometry,
        _distance: float,
        *_args: object,
        **_kwargs: object,
    ) -> BaseGeometry:
        raise GEOSException("forced buffer failure")

    monkeypatch.setattr(BaseGeometry, "buffer", fail_buffer)
    analysis = NatureRouteAnalyzer(_index(water), water_buffer_m=100).analyze(
        (_edge(),),
        400,
    )

    assert not analysis.analysis.available
    assert analysis.analysis.water_crossing.distance_m == 0
    assert analysis.analysis.near_water.distance_m == 0
    assert analysis.analysis.unknown_landcover.distance_m == 400


def test_unavailable_nature_is_neutral_to_waypoint_scoring_and_keeps_route(
    monkeypatch: pytest.MonkeyPatch,
    route_result: RouteResult,
) -> None:
    analyzer = _failed_analysis(
        monkeypatch,
        distance_m=route_result.summary.distance_m,
    )
    unavailable = analyzer.analyze(
        (_edge(distance_m=route_result.summary.distance_m),),
        route_result.summary.distance_m,
    ).analysis
    enriched_route = route_result.model_copy(
        update={
            "analysis": route_result.analysis.model_copy(update={"nature": unavailable})
        }
    )
    request = PLAN_REQUEST_ADAPTER.validate_python(
        {
            "schema_version": 1,
            "kind": "waypoint_route",
            "name": "Fail-soft scoring",
            "topology": "point_to_point",
            "start": {
                "lat": route_result.geometry[0][1],
                "lon": route_result.geometry[0][0],
            },
            "end": {
                "lat": route_result.geometry[-1][1],
                "lon": route_result.geometry[-1][0],
            },
            "routing_profile": "hike",
            "candidate_count": 1,
            "seed": 1,
            "distance_objective": {
                "target_m": route_result.summary.distance_m,
                "tolerance_m": 100,
                "maximum_m": None,
                "priority": "flexible",
            },
            "preferences": {
                "nature": "prefer",
                "loop_geometry": "off",
                "path_selection": "shortest",
            },
            "waypoints": [],
            "waypoint_order": "fixed",
        }
    )
    assert isinstance(request, WaypointPlanRequest)

    def draft(route: RouteResult) -> CandidateDraft:
        return CandidateDraft(
            route=route,
            routing_points=(request.start, request.effective_end),
            topology="point_to_point",
            construction="nature_failsoft_test",
            search_family="waypoint_control",
        )

    scorer = WaypointCandidateScorer()
    baseline = scorer.score(request=request, draft=draft(route_result))
    failed = scorer.score(request=request, draft=draft(enriched_route))

    assert available_nature_score(unavailable) is None
    assert failed == baseline
    assert failed.components["nature_reward"] == 0
    assert enriched_route.geometry == route_result.geometry
    assert enriched_route.analysis.repetition == route_result.analysis.repetition


def test_waypoint_comparison_suppresses_reward_when_any_nature_is_unavailable() -> None:
    measured = PlanScore(total=9.5, components={"nature_reward": 0.5})
    unavailable = PlanScore(total=10.0, components={"nature_reward": 0.0})

    assert waypoint_comparison_total(measured, include_nature=True) == 9.5
    assert waypoint_comparison_total(
        measured, include_nature=False
    ) == waypoint_comparison_total(unavailable, include_nature=False)
