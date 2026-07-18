"""Fractional route attribution against the local projected nature index."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, cast

from shapely import (
    STRtree,
    coverage_union_all,
    difference,
    get_parts,
    intersection,
    length,
)
from shapely.errors import GEOSException
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from sugarglider.analysis.route import ProjectedGeometryEdge
from sugarglider.domain.analysis import DistanceMetric, NatureAnalysis
from sugarglider.nature.classification import (
    PRIMARY_CLASS_PRIORITY,
    PrimaryNatureClass,
)
from sugarglider.nature.index import IndexedNatureFeature, NatureIndex
from sugarglider.nature.scoring import (
    DEFAULT_NATURE_SCORING_WEIGHTS,
    NatureScoringWeights,
    score_nature,
)

type NatureVisualizationClass = Literal[
    "woodland",
    "open_natural",
    "agriculture",
    "water",
    "urban",
    "unknown",
]


@dataclass(frozen=True)
class NatureEdgeContext:
    """Server-derived dominant edge class and independent overlays for display."""

    nature_class: NatureVisualizationClass
    park_or_protected: bool
    near_water: bool


@dataclass(frozen=True)
class NatureRouteEvaluation:
    analysis: NatureAnalysis
    edge_contexts: tuple[NatureEdgeContext, ...]


@dataclass(frozen=True)
class _EdgeMeasurement:
    primary_fractions: dict[PrimaryNatureClass, float]
    unknown_fraction: float
    park_fraction: float
    near_water_fraction: float
    context: NatureEdgeContext


@dataclass(frozen=True)
class _RouteMeasurement:
    edges: tuple[_EdgeMeasurement, ...]
    outside_index: bool


class NatureRouteAnalyzer:
    """Reuse one immutable index and unbuffered water tree for route analysis."""

    def __init__(
        self,
        index: NatureIndex,
        *,
        water_buffer_m: float = 100.0,
        weights: NatureScoringWeights = DEFAULT_NATURE_SCORING_WEIGHTS,
    ) -> None:
        if not 0 <= water_buffer_m <= 1000:
            raise ValueError("nature water buffer must be between 0 and 1000 metres")
        self._index = index
        self._water_buffer_m = water_buffer_m
        self._weights = weights
        water_geometries = tuple(
            feature.metric_geometry
            for feature in index.features
            if feature.primary_class == "water"
        )
        self._water_geometries = water_geometries
        self._water_tree = STRtree(water_geometries)

    @property
    def index(self) -> NatureIndex:
        return self._index

    @property
    def water_buffer_m(self) -> float:
        return self._water_buffer_m

    def analyze(
        self,
        edges: tuple[ProjectedGeometryEdge, ...],
        route_distance_m: float,
    ) -> NatureRouteEvaluation:
        """Attribute normalized authoritative edge distances by exact line fractions."""
        measurement = self._measure_edges(edges)
        distances: dict[PrimaryNatureClass, float] = {
            category: 0.0 for category in PRIMARY_CLASS_PRIORITY
        }
        park_distance = 0.0
        near_water_distance = 0.0
        for edge, edge_measurement in zip(edges, measurement.edges, strict=True):
            for category, fraction in edge_measurement.primary_fractions.items():
                distances[category] += edge.distance_m * fraction
            park_distance += edge.distance_m * edge_measurement.park_fraction
            near_water_distance += (
                edge.distance_m * edge_measurement.near_water_fraction
            )

        known_total = sum(distances.values())
        unknown_distance = max(0.0, route_distance_m - known_total)
        park_distance = min(route_distance_m, max(0.0, park_distance))
        near_water_distance = min(route_distance_m, max(0.0, near_water_distance))

        def metric(distance: float) -> DistanceMetric:
            return DistanceMetric(
                distance_m=distance,
                share=_share(distance, route_distance_m),
            )

        woodland = metric(distances["woodland"])
        open_natural = metric(distances["open_natural"])
        agriculture = metric(distances["agriculture"])
        water = metric(distances["water"])
        urban = metric(distances["urban"])
        unknown = metric(unknown_distance)
        park = metric(park_distance)
        near_water = metric(near_water_distance)
        breakdown = score_nature(
            woodland_share=woodland.share,
            open_natural_share=open_natural.share,
            agriculture_share=agriculture.share,
            park_or_protected_share=park.share,
            near_water_share=near_water.share,
            urban_share=urban.share,
            unknown_share=unknown.share,
            weights=self._weights,
        )
        warnings = (
            ("nature_index_route_partly_outside",) if measurement.outside_index else ()
        )
        analysis = NatureAnalysis(
            available=True,
            index_format_version=self._index.metadata.format_version,
            index_feature_count=self._index.metadata.feature_count,
            woodland=woodland,
            open_natural=open_natural,
            agriculture=agriculture,
            water_crossing=water,
            urban=urban,
            unknown_landcover=unknown,
            park_or_protected=park,
            near_water=near_water,
            nature_score=breakdown.final_score,
            score_breakdown=breakdown,
            warnings=warnings,
        )
        return NatureRouteEvaluation(
            analysis,
            tuple(edge.context for edge in measurement.edges),
        )

    def edge_contexts(
        self, edges: tuple[ProjectedGeometryEdge, ...]
    ) -> tuple[NatureEdgeContext, ...]:
        """Classify display edges through the same server-side intersection path."""
        return tuple(edge.context for edge in self._measure_edges(edges).edges)

    def analyze_route(
        self,
        edges: tuple[ProjectedGeometryEdge, ...],
        route_distance_m: float,
    ) -> NatureAnalysis:
        """Return the public enrichment expected by the shared route analyzer."""
        return self.analyze(edges, route_distance_m).analysis

    def _measure_edges(
        self, edges: tuple[ProjectedGeometryEdge, ...]
    ) -> _RouteMeasurement:
        lines = tuple(
            self._index.projection.project_line((edge.start, edge.end))
            for edge in edges
        )
        line_lengths = tuple(line.length for line in lines)
        candidate_indices = _route_query_indices(self._index, lines)
        candidate_features = tuple(
            self._index.features[index] for index in candidate_indices
        )

        primary_lengths: dict[PrimaryNatureClass, tuple[float, ...]] = {}
        higher_priority: BaseGeometry | None = None
        for category in PRIMARY_CLASS_PRIORITY:
            polygons = tuple(
                feature.metric_geometry
                for feature in candidate_features
                if feature.primary_class == category
            )
            if not polygons:
                primary_lengths[category] = tuple(0.0 for _line in lines)
                continue
            merged = unary_union(polygons)
            available = (
                merged
                if higher_priority is None
                else merged.difference(higher_priority)
            )
            primary_lengths[category] = _intersection_lengths(lines, available)
            higher_priority = (
                merged
                if higher_priority is None
                else _merge_priority_coverage(higher_priority, available)
            )

        park_geometry = _merged_feature_geometry(
            feature for feature in candidate_features if feature.park_or_protected
        )
        park_lengths = _intersection_lengths(lines, park_geometry)
        water_geometry = _near_water_geometry(
            self._water_tree,
            self._water_geometries,
            lines,
            self._water_buffer_m,
        )
        near_water_lengths = _intersection_lengths(lines, water_geometry)
        outside_lengths = _difference_lengths(lines, self._index.metric_bounds)

        measurements: list[_EdgeMeasurement] = []
        for index, line_length in enumerate(line_lengths):
            if line_length <= 0:
                measurements.append(
                    _EdgeMeasurement(
                        {category: 0.0 for category in PRIMARY_CLASS_PRIORITY},
                        1.0,
                        0.0,
                        0.0,
                        NatureEdgeContext("unknown", False, False),
                    )
                )
                continue
            fractions = {
                category: _fraction(primary_lengths[category][index], line_length)
                for category in PRIMARY_CLASS_PRIORITY
            }
            unknown_fraction = max(0.0, 1.0 - sum(fractions.values()))
            park_fraction = _fraction(park_lengths[index], line_length)
            near_water_fraction = _fraction(near_water_lengths[index], line_length)
            display_lengths: dict[NatureVisualizationClass, float] = {
                "woodland": primary_lengths["woodland"][index],
                "open_natural": primary_lengths["open_natural"][index],
                "agriculture": primary_lengths["agriculture"][index],
                "water": primary_lengths["water"][index],
                "urban": primary_lengths["urban"][index],
                "unknown": unknown_fraction * line_length,
            }
            display_priority: tuple[NatureVisualizationClass, ...] = (
                *PRIMARY_CLASS_PRIORITY,
                "unknown",
            )
            nature_class = min(
                display_priority,
                key=lambda category: (
                    -display_lengths[category],
                    display_priority.index(category),
                ),
            )
            measurements.append(
                _EdgeMeasurement(
                    fractions,
                    unknown_fraction,
                    park_fraction,
                    near_water_fraction,
                    NatureEdgeContext(
                        nature_class,
                        park_or_protected=park_lengths[index] > 1e-7,
                        near_water=near_water_lengths[index] > 1e-7,
                    ),
                )
            )
        return _RouteMeasurement(
            tuple(measurements),
            any(
                outside > 1e-7
                or (line_length <= 0 and not self._index.metric_bounds.covers(line))
                for line, line_length, outside in zip(
                    lines, line_lengths, outside_lengths, strict=True
                )
            ),
        )


def _route_query_indices(
    index: NatureIndex, lines: tuple[LineString, ...]
) -> tuple[int, ...]:
    return tuple(
        sorted(
            {
                feature_index
                for line in lines
                for feature_index in index.query_indices(line)
            }
        )
    )


def _near_water_geometry(
    tree: STRtree,
    water_geometries: tuple[BaseGeometry, ...],
    lines: tuple[LineString, ...],
    water_buffer_m: float,
) -> BaseGeometry | None:
    if not water_geometries or not lines:
        return None
    route_geometry = unary_union(lines)
    raw: object = tree.query(
        route_geometry,
        predicate="dwithin",
        distance=water_buffer_m,
    )
    indices = tuple(sorted(int(index) for index in cast(Iterable[int], raw)))
    candidates = tuple(water_geometries[index] for index in indices)
    if water_buffer_m > 0:
        candidates = _buffer_water_candidates(candidates, water_buffer_m)
    return _merged_geometries(candidates)


def _buffer_water_candidates(
    geometries: tuple[BaseGeometry, ...], distance_m: float
) -> tuple[BaseGeometry, ...]:
    return tuple(geometry.buffer(distance_m) for geometry in geometries)


def _merged_feature_geometry(
    features: Iterable[IndexedNatureFeature],
) -> BaseGeometry | None:
    return _merged_geometries(feature.metric_geometry for feature in features)


def _merge_priority_coverage(
    higher_priority: BaseGeometry,
    available: BaseGeometry,
) -> BaseGeometry:
    """Use the fast coverage union, falling back for numerical overlap slivers."""
    try:
        return coverage_union_all((higher_priority, available))
    except GEOSException:
        return unary_union((higher_priority, available))


def _merged_geometries(geometries: Iterable[BaseGeometry]) -> BaseGeometry | None:
    values = tuple(geometries)
    return unary_union(values) if values else None


def _intersection_lengths(
    lines: tuple[LineString, ...], geometry: BaseGeometry | None
) -> tuple[float, ...]:
    if geometry is None or not lines:
        return tuple(0.0 for _line in lines)
    parts_raw: object = get_parts(geometry)
    parts = tuple(cast(Iterable[BaseGeometry], parts_raw))
    if not parts:
        return tuple(0.0 for _line in lines)
    pair_indices_raw: object = STRtree(parts).query(lines)
    pair_indices = tuple(cast(Iterable[Iterable[int]], pair_indices_raw))
    if len(pair_indices) != 2:
        raise RuntimeError("unexpected nature intersection index shape")
    line_indices = tuple(int(index) for index in pair_indices[0])
    part_indices = tuple(int(index) for index in pair_indices[1])
    if not line_indices:
        return tuple(0.0 for _line in lines)
    values_raw: object = length(
        intersection(
            tuple(lines[index] for index in line_indices),
            tuple(parts[index] for index in part_indices),
        )
    )
    totals = [0.0 for _line in lines]
    for line_index, value in zip(
        line_indices,
        cast(Iterable[float], values_raw),
        strict=True,
    ):
        totals[line_index] += float(value)
    return tuple(totals)


def _difference_lengths(
    lines: tuple[LineString, ...], geometry: BaseGeometry
) -> tuple[float, ...]:
    if not lines:
        return ()
    values: object = length(difference(lines, geometry))
    return tuple(float(value) for value in cast(Iterable[float], values))


def _fraction(distance: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return min(1.0, max(0.0, distance / total))


def _share(distance_m: float, route_distance_m: float) -> float:
    if route_distance_m <= 0:
        return 0.0
    return min(1.0, max(0.0, distance_m / route_distance_m))
