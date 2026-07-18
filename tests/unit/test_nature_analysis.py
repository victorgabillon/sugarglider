"""Fractional nature attribution and explainable score tests."""

from collections.abc import Sequence

import pytest
from shapely.errors import GEOSException
from shapely.geometry.base import BaseGeometry

import sugarglider.nature.analysis as nature_analysis_module
from sugarglider.analysis.route import ProjectedGeometryEdge
from sugarglider.nature.analysis import NatureRouteAnalyzer
from sugarglider.nature.classification import PrimaryNatureClass
from sugarglider.nature.index import NatureIndex
from sugarglider.nature.models import (
    NatureIndexDocument,
    NatureIndexFeature,
    NatureIndexMetadata,
    PolygonGeometry,
)
from sugarglider.nature.scoring import score_nature


def _polygon(
    feature_id: str,
    primary_class: PrimaryNatureClass | None,
    coordinates: Sequence[tuple[float, float]],
    *,
    park: bool = False,
    holes: Sequence[Sequence[tuple[float, float]]] = (),
) -> NatureIndexFeature:
    return NatureIndexFeature(
        feature_id=feature_id,
        osm_id=int(feature_id.split("/")[1]),
        osm_source="way",
        primary_class=primary_class,
        park_or_protected=park,
        tags={},
        geometry=PolygonGeometry(
            coordinates=(tuple(coordinates), *(tuple(hole) for hole in holes))
        ),
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
                source_basename="synthetic.osm",
                reference_latitude=0,
                bounding_box=(-0.01, -0.01, 0.02, 0.01),
                category_counts={key: counts[key] for key in sorted(counts)},
                feature_count=len(features),
            ),
            features=tuple(sorted(features, key=lambda item: item.feature_id)),
        )
    )


def _edge(
    start: tuple[float, float],
    end: tuple[float, float],
    distance_m: float = 100,
) -> ProjectedGeometryEdge:
    return ProjectedGeometryEdge(0, 1, start, end, distance_m, ())


def _rectangle(
    west: float, east: float, south: float = -0.001, north: float = 0.001
) -> tuple[tuple[float, float], ...]:
    return (
        (west, south),
        (east, south),
        (east, north),
        (west, north),
        (west, south),
    )


@pytest.mark.parametrize(
    ("category", "attribute"),
    [
        ("woodland", "woodland"),
        ("open_natural", "open_natural"),
        ("agriculture", "agriculture"),
        ("water", "water_crossing"),
        ("urban", "urban"),
    ],
)
def test_route_fully_inside_each_primary_class(
    category: PrimaryNatureClass, attribute: str
) -> None:
    analyzer = NatureRouteAnalyzer(
        _index(_polygon("way/1", category, _rectangle(-0.002, 0.002)))
    )
    result = analyzer.analyze((_edge((-0.001, 0), (0.001, 0)),), 100)
    metric = getattr(result.analysis, attribute)
    assert metric.distance_m == pytest.approx(100)
    assert metric.share == pytest.approx(1)
    assert result.analysis.unknown_landcover.distance_m == pytest.approx(0)


def test_fractional_crossing_priority_overlays_and_authoritative_normalization() -> (
    None
):
    index = _index(
        _polygon("way/1", "woodland", _rectangle(0, 0.003), park=True),
        _polygon("way/2", "urban", _rectangle(0.001, 0.002)),
        _polygon("way/3", "water", _rectangle(0.003, 0.004)),
    )
    analysis = (
        NatureRouteAnalyzer(index, water_buffer_m=100)
        .analyze(
            (_edge((0, 0), (0.004, 0), 1000),),
            1000,
        )
        .analysis
    )
    assert analysis.woodland.distance_m == pytest.approx(500, abs=1e-5)
    assert analysis.urban.distance_m == pytest.approx(250, abs=1e-5)
    assert analysis.water_crossing.distance_m == pytest.approx(250, abs=1e-5)
    assert analysis.unknown_landcover.distance_m == pytest.approx(0, abs=1e-5)
    assert analysis.park_or_protected.distance_m == pytest.approx(750, abs=1e-5)
    assert analysis.near_water.distance_m > analysis.water_crossing.distance_m
    partition = sum(
        metric.distance_m
        for metric in (
            analysis.woodland,
            analysis.open_natural,
            analysis.agriculture,
            analysis.water_crossing,
            analysis.urban,
            analysis.unknown_landcover,
        )
    )
    assert partition == pytest.approx(1000)


def test_priority_union_falls_back_for_numerical_coverage_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_coverage_union(_geometries: object) -> object:
        raise GEOSException("overlapping coverage")

    monkeypatch.setattr(
        nature_analysis_module,
        "coverage_union_all",
        fail_coverage_union,
    )
    analyzer = NatureRouteAnalyzer(
        _index(
            _polygon("way/1", "woodland", _rectangle(0, 0.003)),
            _polygon("way/2", "urban", _rectangle(0.001, 0.002)),
        )
    )
    analysis = analyzer.analyze((_edge((0, 0), (0.003, 0), 300),), 300).analysis
    assert analysis.urban.distance_m == pytest.approx(100, abs=1e-5)
    assert analysis.woodland.distance_m == pytest.approx(200, abs=1e-5)
    assert analysis.unknown_landcover.distance_m == pytest.approx(0, abs=1e-5)


def test_unknown_hole_touch_zero_length_and_outside_are_explicit() -> None:
    shell = _rectangle(-0.002, 0.002, -0.002, 0.002)
    hole = _rectangle(-0.0005, 0.0005, -0.0005, 0.0005)
    analyzer = NatureRouteAnalyzer(
        _index(_polygon("way/1", "woodland", shell, holes=(hole,)))
    )
    hole_route = analyzer.analyze((_edge((-0.001, 0), (0.001, 0)),), 100)
    assert hole_route.analysis.woodland.distance_m == pytest.approx(50, abs=1e-5)
    assert hole_route.analysis.unknown_landcover.distance_m == pytest.approx(
        50, abs=1e-5
    )

    point_touch = analyzer.analyze((_edge((-0.003, 0.002), (-0.002, 0.002)),), 100)
    assert point_touch.analysis.woodland.distance_m == pytest.approx(0)
    assert point_touch.analysis.unknown_landcover.distance_m == pytest.approx(100)

    zero = analyzer.analyze((_edge((0, 0), (0, 0), 40),), 40)
    assert zero.analysis.unknown_landcover.distance_m == pytest.approx(40)

    outside = analyzer.analyze((_edge((-0.02, 0), (0, 0)),), 100)
    assert outside.analysis.warnings == ("nature_index_route_partly_outside",)
    assert outside.analysis.unknown_landcover.distance_m > 0


def test_near_water_is_buffered_overlay_without_claiming_crossing() -> None:
    water = _polygon("way/1", "water", _rectangle(-0.001, 0.001, 0.0005, 0.0007))
    analysis = (
        NatureRouteAnalyzer(_index(water), water_buffer_m=100)
        .analyze((_edge((-0.001, 0), (0.001, 0)),), 100)
        .analysis
    )
    assert analysis.water_crossing.distance_m == pytest.approx(0)
    assert analysis.near_water.distance_m == pytest.approx(100)


def test_analyzer_construction_keeps_unbuffered_water_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _index(
        _polygon("way/1", "water", _rectangle(-0.001, 0.001, 0.0005, 0.0007))
    )

    def fail_buffer(
        _geometry: BaseGeometry,
        _distance: float,
        *args: object,
        **kwargs: object,
    ) -> BaseGeometry:
        raise AssertionError("water geometry must not be buffered at startup")

    monkeypatch.setattr(BaseGeometry, "buffer", fail_buffer)
    analyzer = NatureRouteAnalyzer(index, water_buffer_m=100)
    assert analyzer._water_geometries == (index.features[0].metric_geometry,)


def test_no_water_and_distant_water_are_not_buffered_per_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty = NatureRouteAnalyzer(_index(), water_buffer_m=100).analyze(
        (_edge((-0.001, 0), (0.001, 0)),),
        100,
    )
    assert empty.analysis.near_water.distance_m == 0

    nearby = _polygon(
        "way/1",
        "water",
        _rectangle(-0.001, 0.001, 0.0005, 0.0007),
    )
    distant = _polygon(
        "way/2",
        "water",
        _rectangle(-0.001, 0.001, 0.005, 0.006),
    )
    buffered_counts: list[int] = []

    def record_candidates(
        geometries: tuple[BaseGeometry, ...], distance_m: float
    ) -> tuple[BaseGeometry, ...]:
        buffered_counts.append(len(geometries))
        return tuple(geometry.buffer(distance_m) for geometry in geometries)

    monkeypatch.setattr(
        nature_analysis_module,
        "_buffer_water_candidates",
        record_candidates,
    )
    result = NatureRouteAnalyzer(_index(nearby, distant), water_buffer_m=100).analyze(
        (_edge((-0.001, 0), (0.001, 0)),), 100
    )
    assert buffered_counts == [1]
    assert result.analysis.water_crossing.distance_m == 0
    assert result.analysis.near_water.distance_m == pytest.approx(100)


def test_overlapping_water_buffers_do_not_double_count() -> None:
    result = NatureRouteAnalyzer(
        _index(
            _polygon(
                "way/1",
                "water",
                _rectangle(-0.001, 0.0002, 0.0005, 0.0007),
            ),
            _polygon(
                "way/2",
                "water",
                _rectangle(-0.0002, 0.001, 0.0005, 0.0007),
            ),
        ),
        water_buffer_m=100,
    ).analyze((_edge((-0.001, 0), (0.001, 0)),), 100)
    assert result.analysis.near_water.distance_m == pytest.approx(100)
    assert result.analysis.near_water.share == 1


def test_zero_water_buffer_matches_exact_water_crossing() -> None:
    result = NatureRouteAnalyzer(
        _index(_polygon("way/1", "water", _rectangle(0, 0.002))),
        water_buffer_m=0,
    ).analyze((_edge((-0.001, 0), (0.001, 0)),), 100)
    assert result.analysis.water_crossing.distance_m == pytest.approx(50, abs=1e-5)
    assert result.analysis.near_water.distance_m == pytest.approx(50, abs=1e-5)


def test_score_extremes_unknown_and_mixed_are_public_and_bounded() -> None:
    all_natural = score_nature(
        woodland_share=1,
        open_natural_share=0,
        agriculture_share=0,
        park_or_protected_share=1,
        near_water_share=1,
        urban_share=0,
        unknown_share=0,
    )
    all_urban = score_nature(
        woodland_share=0,
        open_natural_share=0,
        agriculture_share=0,
        park_or_protected_share=0,
        near_water_share=0,
        urban_share=1,
        unknown_share=0,
    )
    all_unknown = score_nature(
        woodland_share=0,
        open_natural_share=0,
        agriculture_share=0,
        park_or_protected_share=0,
        near_water_share=0,
        urban_share=0,
        unknown_share=1,
    )
    mixed = score_nature(
        woodland_share=0.25,
        open_natural_share=0.25,
        agriculture_share=0.25,
        park_or_protected_share=0.1,
        near_water_share=0.1,
        urban_share=0.25,
        unknown_share=0,
    )
    assert all_natural.final_score == 100
    assert all_urban.final_score == 0
    assert all_unknown.final_score == 45
    assert 0 < mixed.final_score < 100
    assert mixed.raw_score == pytest.approx(
        mixed.base_score
        + mixed.woodland_reward.points
        + mixed.open_natural_reward.points
        + mixed.agriculture_reward.points
        + mixed.park_or_protected_reward.points
        + mixed.near_water_reward.points
        + mixed.urban_penalty.points
        + mixed.unknown_penalty.points
    )
