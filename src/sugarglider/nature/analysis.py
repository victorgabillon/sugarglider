"""Fractional route attribution against the local projected nature index."""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite
from typing import Literal, cast

from shapely import (
    STRtree,
    coverage_union_all,
    difference,
    get_coordinates,
    get_parts,
    intersection,
    is_valid,
    length,
    make_valid,
    normalize,
)
from shapely.errors import GEOSException
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon
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
type PolygonalGeometry = Polygon | MultiPolygon

NATURE_GEOMETRY_OVERLAY_WARNING = "nature_geometry_overlay_failed"

logger = logging.getLogger(__name__)


class _NatureGeometryOverlayError(RuntimeError):
    """One expected GEOS overlay failure after bounded polygon repair."""

    def __init__(self, operation: str) -> None:
        super().__init__(f"nature geometry overlay failed during {operation}")
        self.operation = operation


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
        try:
            measurement = self._measure_edges(edges)
        except _NatureGeometryOverlayError as exc:
            return self._unavailable_evaluation(
                edges,
                route_distance_m,
                operation=exc.operation,
            )
        except GEOSException:
            # This final narrow boundary covers GEOS operations such as STRtree
            # predicates and bounds checks which are not overlay helper calls.
            return self._unavailable_evaluation(
                edges,
                route_distance_m,
                operation="nature_measurement",
            )
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
        try:
            return tuple(edge.context for edge in self._measure_edges(edges).edges)
        except _NatureGeometryOverlayError as exc:
            self._log_overlay_failure(exc.operation)
        except GEOSException:
            self._log_overlay_failure("nature_visualization_measurement")
        return tuple(_unknown_edge_context() for _edge in edges)

    def analyze_route(
        self,
        edges: tuple[ProjectedGeometryEdge, ...],
        route_distance_m: float,
    ) -> NatureAnalysis:
        """Return the public enrichment expected by the shared route analyzer."""
        return self.analyze(edges, route_distance_m).analysis

    def _unavailable_evaluation(
        self,
        edges: tuple[ProjectedGeometryEdge, ...],
        route_distance_m: float,
        *,
        operation: str,
    ) -> NatureRouteEvaluation:
        self._log_overlay_failure(operation)

        def metric(distance_m: float) -> DistanceMetric:
            return DistanceMetric(
                distance_m=distance_m,
                share=_share(distance_m, route_distance_m),
            )

        zero = metric(0.0)
        unknown = metric(route_distance_m)
        # An unavailable analysis has no measured score components. The public
        # score remains at its documented neutral base and planning gates on
        # ``available`` rather than treating it as measured nature reward.
        breakdown = score_nature(
            woodland_share=0.0,
            open_natural_share=0.0,
            agriculture_share=0.0,
            park_or_protected_share=0.0,
            near_water_share=0.0,
            urban_share=0.0,
            unknown_share=unknown.share,
            weights=self._weights,
        )
        analysis = NatureAnalysis(
            available=False,
            index_format_version=self._index.metadata.format_version,
            index_feature_count=self._index.metadata.feature_count,
            woodland=zero,
            open_natural=zero,
            agriculture=zero,
            water_crossing=zero,
            urban=zero,
            unknown_landcover=unknown,
            park_or_protected=zero,
            near_water=zero,
            nature_score=breakdown.final_score,
            score_breakdown=breakdown,
            warnings=(NATURE_GEOMETRY_OVERLAY_WARNING,),
        )
        return NatureRouteEvaluation(
            analysis=analysis,
            edge_contexts=tuple(_unknown_edge_context() for _edge in edges),
        )

    def _log_overlay_failure(self, operation: str) -> None:
        logger.warning(
            "Nature geometry overlay failed during %s for an index with %d features; "
            "nature enrichment is unavailable for this route",
            operation,
            self._index.metadata.feature_count,
        )

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
            merged = _robust_polygonal_union(
                polygons,
                operation=f"{category}_union",
            )
            available = (
                merged
                if higher_priority is None
                else _robust_polygonal_difference(
                    merged,
                    higher_priority,
                    operation=f"{category}_priority_difference",
                )
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
    indices = tuple(
        sorted(
            {
                int(index)
                for line in lines
                for index in cast(
                    Iterable[int],
                    tree.query(
                        line,
                        predicate="dwithin",
                        distance=water_buffer_m,
                    ),
                )
            }
        )
    )
    candidates = tuple(water_geometries[index] for index in indices)
    if water_buffer_m > 0:
        candidates = _buffer_water_candidates(candidates, water_buffer_m)
    return _merged_geometries(candidates, operation="near_water_union")


def _buffer_water_candidates(
    geometries: tuple[BaseGeometry, ...], distance_m: float
) -> tuple[BaseGeometry, ...]:
    buffered: list[BaseGeometry] = []
    for geometry in geometries:
        normalized = _normalize_polygonal(geometry, operation="water_buffer_input")
        try:
            result = normalized.buffer(distance_m)
            buffered.append(
                _normalize_polygonal(result, operation="water_buffer_result")
            )
        except (_NatureGeometryOverlayError, GEOSException):
            repaired = _buffer_zero_polygonal(
                normalized,
                operation="water_buffer_repair",
            )
            try:
                result = repaired.buffer(distance_m)
                buffered.append(
                    _normalize_polygonal(
                        result,
                        operation="water_buffer_retry_result",
                    )
                )
            except (_NatureGeometryOverlayError, GEOSException) as exc:
                raise _NatureGeometryOverlayError("water_buffer") from exc
    return tuple(buffered)


def _merged_feature_geometry(
    features: Iterable[IndexedNatureFeature],
) -> BaseGeometry | None:
    return _merged_geometries(
        (feature.metric_geometry for feature in features),
        operation="park_or_protected_union",
    )


def _merge_priority_coverage(
    higher_priority: BaseGeometry,
    available: BaseGeometry,
) -> BaseGeometry:
    """Accumulate priority coverage without assuming numerical disjointness."""
    operands = (
        _normalize_polygonal(
            higher_priority,
            operation="priority_coverage_higher_normalize",
        ),
        _normalize_polygonal(
            available,
            operation="priority_coverage_available_normalize",
        ),
    )
    try:
        result = coverage_union_all(operands)
        return _normalize_polygonal(
            result,
            operation="priority_coverage_union_result",
        )
    except (_NatureGeometryOverlayError, GEOSException):
        # Coverage union is valid only for non-overlapping coverages. Numerical
        # slivers or genuinely overlapping valid inputs require a general union.
        return _general_polygonal_union(
            operands,
            operation="priority_coverage_general_union",
        )


def _merged_geometries(
    geometries: Iterable[BaseGeometry],
    *,
    operation: str,
) -> BaseGeometry | None:
    values = tuple(geometries)
    return _robust_polygonal_union(values, operation=operation) if values else None


def _robust_polygonal_union(
    geometries: Iterable[BaseGeometry],
    *,
    operation: str,
) -> PolygonalGeometry:
    operands = tuple(
        _normalize_polygonal(geometry, operation=f"{operation}_input")
        for geometry in geometries
    )
    nonempty = tuple(geometry for geometry in operands if not geometry.is_empty)
    if not nonempty:
        return Polygon()
    if len(nonempty) == 1:
        return nonempty[0]
    return _general_polygonal_union(nonempty, operation=operation)


def _general_polygonal_union(
    geometries: tuple[PolygonalGeometry, ...],
    *,
    operation: str,
) -> PolygonalGeometry:
    try:
        result = unary_union(geometries)
        return _normalize_polygonal(result, operation=f"{operation}_result")
    except (_NatureGeometryOverlayError, GEOSException):
        pass

    # ``buffer(0)`` is intentionally reserved for the exceptional retry after
    # make_valid/general union failed. It is never applied to ordinary geometry.
    try:
        repaired = tuple(
            _buffer_zero_polygonal(
                geometry,
                operation=f"{operation}_buffer_zero_input",
            )
            for geometry in geometries
        )
        result = unary_union(repaired)
        return _normalize_polygonal(
            result,
            operation=f"{operation}_repaired_result",
        )
    except (_NatureGeometryOverlayError, GEOSException) as exc:
        raise _NatureGeometryOverlayError(operation) from exc


def _robust_polygonal_difference(
    subject: BaseGeometry,
    mask: BaseGeometry,
    *,
    operation: str,
) -> PolygonalGeometry:
    normalized_subject = _normalize_polygonal(
        subject,
        operation=f"{operation}_subject",
    )
    normalized_mask = _normalize_polygonal(mask, operation=f"{operation}_mask")
    try:
        result = difference(normalized_subject, normalized_mask)
        return _normalize_polygonal(result, operation=f"{operation}_result")
    except (_NatureGeometryOverlayError, GEOSException):
        pass

    try:
        repaired_subject = _buffer_zero_polygonal(
            normalized_subject,
            operation=f"{operation}_subject_repair",
        )
        repaired_mask = _buffer_zero_polygonal(
            normalized_mask,
            operation=f"{operation}_mask_repair",
        )
        result = difference(repaired_subject, repaired_mask)
        return _normalize_polygonal(
            result,
            operation=f"{operation}_repaired_result",
        )
    except (_NatureGeometryOverlayError, GEOSException) as exc:
        raise _NatureGeometryOverlayError(operation) from exc


def _normalize_polygonal(
    geometry: BaseGeometry,
    *,
    operation: str,
) -> PolygonalGeometry:
    """Return only finite valid polygon components in canonical deterministic order."""
    if not isinstance(geometry, (Polygon, MultiPolygon, GeometryCollection)):
        raise _NatureGeometryOverlayError(operation)
    try:
        repaired = make_valid(geometry) if not bool(is_valid(geometry)) else geometry
        polygons = tuple(
            part
            for part in _polygon_parts(repaired)
            if not part.is_empty and part.area > 0
        )
        if not polygons:
            return Polygon()
        normalized_parts = tuple(normalize(part) for part in polygons)
        ordered = tuple(sorted(normalized_parts, key=_polygon_sort_key))
        result: PolygonalGeometry = (
            ordered[0] if len(ordered) == 1 else MultiPolygon(ordered)
        )
        result = normalize(result)
        if result.is_empty:
            return Polygon()
        if not bool(is_valid(result)) or not isfinite(float(result.area)):
            raise _NatureGeometryOverlayError(operation)
        coordinates_raw: object = get_coordinates(result)
        coordinates = cast(Iterable[Iterable[float]], coordinates_raw)
        if not all(
            all(isfinite(float(ordinate)) for ordinate in coordinate)
            for coordinate in coordinates
        ):
            raise _NatureGeometryOverlayError(operation)
        if not all(isfinite(float(value)) for value in result.bounds):
            raise _NatureGeometryOverlayError(operation)
        return result
    except _NatureGeometryOverlayError:
        raise
    except GEOSException as exc:
        raise _NatureGeometryOverlayError(operation) from exc


def _polygon_parts(geometry: BaseGeometry) -> Iterable[Polygon]:
    if isinstance(geometry, Polygon):
        yield geometry
        return
    if isinstance(geometry, (MultiPolygon, GeometryCollection)):
        for part in geometry.geoms:
            yield from _polygon_parts(part)


def _polygon_sort_key(
    polygon: Polygon,
) -> tuple[float, float, float, float, float, str]:
    west, south, east, north = polygon.bounds
    return west, south, east, north, polygon.area, polygon.wkb_hex


def _buffer_zero_polygonal(
    geometry: BaseGeometry,
    *,
    operation: str,
) -> PolygonalGeometry:
    try:
        return _normalize_polygonal(geometry.buffer(0), operation=operation)
    except (_NatureGeometryOverlayError, GEOSException) as exc:
        raise _NatureGeometryOverlayError(operation) from exc


def _intersection_lengths(
    lines: tuple[LineString, ...], geometry: BaseGeometry | None
) -> tuple[float, ...]:
    if geometry is None or not lines:
        return tuple(0.0 for _line in lines)
    normalized = _normalize_polygonal(geometry, operation="intersection_input")
    try:
        return _intersection_lengths_once(lines, normalized)
    except GEOSException:
        pass
    try:
        repaired = _buffer_zero_polygonal(
            normalized,
            operation="intersection_input_repair",
        )
        return _intersection_lengths_once(lines, repaired)
    except (_NatureGeometryOverlayError, GEOSException) as exc:
        raise _NatureGeometryOverlayError("line_polygon_intersection") from exc


def _intersection_lengths_once(
    lines: tuple[LineString, ...],
    geometry: PolygonalGeometry,
) -> tuple[float, ...]:
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
        measured = float(value)
        if not isfinite(measured) or measured < 0:
            raise _NatureGeometryOverlayError("line_polygon_intersection_length")
        totals[line_index] += measured
    return tuple(totals)


def _difference_lengths(
    lines: tuple[LineString, ...], geometry: BaseGeometry
) -> tuple[float, ...]:
    if not lines:
        return ()
    normalized = _normalize_polygonal(geometry, operation="route_bounds_input")
    try:
        return _difference_lengths_once(lines, normalized)
    except GEOSException:
        pass
    try:
        repaired = _buffer_zero_polygonal(
            normalized,
            operation="route_bounds_repair",
        )
        return _difference_lengths_once(lines, repaired)
    except (_NatureGeometryOverlayError, GEOSException) as exc:
        raise _NatureGeometryOverlayError("route_bounds_difference") from exc


def _difference_lengths_once(
    lines: tuple[LineString, ...],
    geometry: PolygonalGeometry,
) -> tuple[float, ...]:
    values: object = length(difference(lines, geometry))
    measured = tuple(float(value) for value in cast(Iterable[float], values))
    if any(not isfinite(value) or value < 0 for value in measured):
        raise _NatureGeometryOverlayError("route_bounds_difference_length")
    return measured


def _unknown_edge_context() -> NatureEdgeContext:
    return NatureEdgeContext(
        nature_class="unknown",
        park_or_protected=False,
        near_water=False,
    )


def _fraction(distance: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return min(1.0, max(0.0, distance / total))


def _share(distance_m: float, route_distance_m: float) -> float:
    if route_distance_m <= 0:
        return 0.0
    return min(1.0, max(0.0, distance_m / route_distance_m))
