"""Project GraphHopper path details onto normalized route geometry edges."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import pairwise
from math import asin, cos, isfinite, radians, sin, sqrt

from sugarglider.domain.analysis import (
    DetailBreakdown,
    DetailBucket,
    DetailValue,
    DistanceMetric,
    RepetitionAnalysis,
    RouteAnalysis,
)
from sugarglider.domain.models import GeoJsonPosition, PathDetailSegment

EARTH_RADIUS_M = 6_371_008.8

# GraphHopper enum values are matched case-insensitively while raw breakdown values
# remain untouched for debugging and forward compatibility.
PAVED_SURFACES = frozenset(
    {"PAVED", "ASPHALT", "CONCRETE", "PAVING_STONES", "COBBLESTONE"}
)
UNPAVED_SURFACES = frozenset(
    {
        "UNPAVED",
        "COMPACTED",
        "FINE_GRAVEL",
        "GRAVEL",
        "GROUND",
        "DIRT",
        "GRASS",
        "SAND",
        "WOOD",
    }
)
TRAIL_LIKE_ROAD_CLASSES = frozenset(
    {"TRACK", "PATH", "FOOTWAY", "BRIDLEWAY", "STEPS", "PEDESTRIAN"}
)
OFFICIAL_HIKING_NETWORKS = frozenset({"INTERNATIONAL", "NATIONAL", "REGIONAL", "LOCAL"})
MAJOR_ROAD_CLASSES = frozenset(
    {"MOTORWAY", "TRUNK", "PRIMARY", "SECONDARY", "TERTIARY"}
)

DERIVED_DETAIL_NAMES = (
    "car_access",
    "edge_id",
    "foot_network",
    "road_class",
    "surface",
)


class RouteAnalysisError(ValueError):
    """The routed geometry or its path-detail intervals are impossible to analyze."""


@dataclass(frozen=True)
class _GeometryEdge:
    from_index: int
    to_index: int
    start: GeoJsonPosition
    end: GeoJsonPosition
    distance_m: float
    details: tuple[tuple[str, DetailValue], ...]

    def detail(self, name: str) -> tuple[bool, DetailValue]:
        for detail_name, value in self.details:
            if detail_name == name:
                return True, value
        return False, None


@dataclass(frozen=True)
class _EdgeRun:
    edge_id: int
    distance_m: float


def haversine_distance_m(start: GeoJsonPosition, end: GeoJsonPosition) -> float:
    """Return great-circle distance between two GeoJSON-order WGS84 positions."""
    start_lon, start_lat = start
    end_lon, end_lat = end
    lat_delta = radians(end_lat - start_lat)
    lon_delta = radians(end_lon - start_lon)
    start_lat_radians = radians(start_lat)
    end_lat_radians = radians(end_lat)
    haversine = sin(lat_delta / 2) ** 2 + (
        cos(start_lat_radians) * cos(end_lat_radians) * sin(lon_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * asin(sqrt(min(1.0, haversine)))


class RouteAnalyzer:
    """Build deterministic analysis from geometry, distance, and typed details."""

    def analyze(
        self,
        geometry: tuple[GeoJsonPosition, ...],
        route_distance_m: float,
        path_details: Mapping[str, tuple[PathDetailSegment, ...]],
    ) -> RouteAnalysis:
        if len(geometry) < 2:
            raise RouteAnalysisError("route geometry must contain at least two points")
        if not isfinite(route_distance_m) or route_distance_m < 0:
            raise RouteAnalysisError("route distance must be finite and non-negative")

        raw_lengths = tuple(
            haversine_distance_m(start, end) for start, end in pairwise(geometry)
        )
        geometry_distance_m = sum(raw_lengths)
        if geometry_distance_m == 0 and route_distance_m > 0:
            raise RouteAnalysisError(
                "positive route distance cannot have zero-length geometry"
            )
        scale_factor = (
            route_distance_m / geometry_distance_m if geometry_distance_m > 0 else 0.0
        )
        normalized = [length * scale_factor for length in raw_lengths]
        if normalized:
            normalized[-1] = max(0.0, route_distance_m - sum(normalized[:-1]))
        normalized_lengths = tuple(normalized)
        edges = self._project_details(
            geometry=geometry,
            edge_lengths=normalized_lengths,
            path_details=path_details,
        )

        breakdowns = {
            detail: self._breakdown(detail, edges, route_distance_m)
            for detail in sorted(path_details)
        }
        paved_distance = self._classified_distance(edges, "surface", PAVED_SURFACES)
        unpaved_distance = self._classified_distance(edges, "surface", UNPAVED_SURFACES)
        unknown_surface_distance = sum(
            edge.distance_m for edge in edges if not self._is_classified_surface(edge)
        )
        warnings = tuple(
            sorted(
                f"{detail}_coverage_incomplete"
                for detail in DERIVED_DETAIL_NAMES
                if any(
                    not (
                        self._known_edge_id(edge) is not None
                        if detail == "edge_id"
                        else edge.detail(detail)[0]
                    )
                    for edge in edges
                )
            )
        )

        return RouteAnalysis(
            route_distance_m=route_distance_m,
            geometry_distance_m=geometry_distance_m,
            distance_scale_factor=scale_factor,
            detail_breakdowns=breakdowns,
            paved=self._metric(paved_distance, route_distance_m),
            unpaved=self._metric(unpaved_distance, route_distance_m),
            unknown_surface=self._metric(unknown_surface_distance, route_distance_m),
            trail_like=self._metric(
                self._classified_distance(edges, "road_class", TRAIL_LIKE_ROAD_CLASSES),
                route_distance_m,
            ),
            official_hiking_network=self._metric(
                self._classified_distance(
                    edges, "foot_network", OFFICIAL_HIKING_NETWORKS
                ),
                route_distance_m,
            ),
            major_road=self._metric(
                self._classified_distance(edges, "road_class", MAJOR_ROAD_CLASSES),
                route_distance_m,
            ),
            car_accessible=self._metric(
                sum(
                    edge.distance_m
                    for edge in edges
                    if self._is_explicitly_true(edge, "car_access")
                ),
                route_distance_m,
            ),
            repetition=self._repetition(edges, route_distance_m),
            warnings=warnings,
        )

    @classmethod
    def _project_details(
        cls,
        *,
        geometry: tuple[GeoJsonPosition, ...],
        edge_lengths: tuple[float, ...],
        path_details: Mapping[str, tuple[PathDetailSegment, ...]],
    ) -> tuple[_GeometryEdge, ...]:
        """Apply [from, to] point intervals to the edges from→from+1 ... to-1→to."""
        projected: list[dict[str, DetailValue]] = [
            {} for _edge_index in range(len(geometry) - 1)
        ]
        for detail in sorted(path_details):
            segments = sorted(
                path_details[detail],
                key=lambda segment: (
                    segment.from_index,
                    segment.to_index,
                    cls._value_sort_key(segment.value),
                ),
            )
            previous_to = -1
            for segment in segments:
                if segment.from_index < 0:
                    raise RouteAnalysisError(f"{detail} interval starts below zero")
                if segment.to_index <= segment.from_index:
                    raise RouteAnalysisError(f"{detail} interval is empty or reversed")
                if segment.to_index >= len(geometry):
                    raise RouteAnalysisError(f"{detail} interval exceeds geometry")
                if segment.from_index < previous_to:
                    raise RouteAnalysisError(f"{detail} intervals overlap")
                for edge_index in range(segment.from_index, segment.to_index):
                    projected[edge_index][detail] = segment.value
                previous_to = segment.to_index

        return tuple(
            _GeometryEdge(
                from_index=index,
                to_index=index + 1,
                start=geometry[index],
                end=geometry[index + 1],
                distance_m=edge_lengths[index],
                details=tuple(sorted(values.items())),
            )
            for index, values in enumerate(projected)
        )

    @classmethod
    def _breakdown(
        cls,
        detail: str,
        edges: tuple[_GeometryEdge, ...],
        route_distance_m: float,
    ) -> DetailBreakdown:
        bucket_distances: dict[tuple[int, str], float] = {}
        bucket_values: dict[tuple[int, str], DetailValue] = {}
        for edge in edges:
            present, value = edge.detail(detail)
            if not present:
                continue
            key = cls._value_sort_key(value)
            bucket_distances[key] = bucket_distances.get(key, 0.0) + edge.distance_m
            bucket_values[key] = value
        buckets = tuple(
            DetailBucket(
                value=bucket_values[key],
                distance_m=bucket_distances[key],
                share=cls._share(bucket_distances[key], route_distance_m),
            )
            for key in sorted(bucket_distances)
        )
        covered_distance = sum(bucket.distance_m for bucket in buckets)
        return DetailBreakdown(
            detail=detail,
            covered_distance_m=covered_distance,
            coverage_share=cls._share(covered_distance, route_distance_m),
            buckets=buckets,
        )

    @staticmethod
    def _value_sort_key(value: DetailValue) -> tuple[int, str]:
        """Sort by None, bool, int, float, str, then canonical representation."""
        if value is None:
            return (0, "")
        if isinstance(value, bool):
            return (1, "1" if value else "0")
        if isinstance(value, int):
            return (2, str(value))
        if isinstance(value, float):
            return (3, value.hex())
        return (4, value)

    @classmethod
    def _metric(cls, distance_m: float, route_distance_m: float) -> DistanceMetric:
        return DistanceMetric(
            distance_m=distance_m,
            share=cls._share(distance_m, route_distance_m),
        )

    @staticmethod
    def _share(distance_m: float, route_distance_m: float) -> float:
        if route_distance_m == 0:
            return 0.0
        return min(1.0, max(0.0, distance_m / route_distance_m))

    @staticmethod
    def _normalized_string(value: DetailValue) -> str | None:
        return value.upper() if isinstance(value, str) else None

    @staticmethod
    def _is_explicitly_true(edge: _GeometryEdge, detail: str) -> bool:
        present, value = edge.detail(detail)
        return present and value is True

    @staticmethod
    def _known_edge_id(edge: _GeometryEdge) -> int | None:
        present, value = edge.detail("edge_id")
        if present and isinstance(value, int) and not isinstance(value, bool):
            return value
        return None

    @classmethod
    def _classified_distance(
        cls,
        edges: tuple[_GeometryEdge, ...],
        detail: str,
        accepted_values: frozenset[str],
    ) -> float:
        return sum(
            edge.distance_m
            for edge in edges
            if cls._normalized_string(edge.detail(detail)[1]) in accepted_values
        )

    @classmethod
    def _is_classified_surface(cls, edge: _GeometryEdge) -> bool:
        value = cls._normalized_string(edge.detail("surface")[1])
        return value in PAVED_SURFACES or value in UNPAVED_SURFACES

    @classmethod
    def _repetition(
        cls, edges: tuple[_GeometryEdge, ...], route_distance_m: float
    ) -> RepetitionAnalysis:
        runs: list[_EdgeRun] = []
        known_distance = 0.0
        current_id: int | None = None
        current_distance = 0.0
        previous_edge: _GeometryEdge | None = None

        for edge in edges:
            edge_id = cls._known_edge_id(edge)
            if edge_id is None:
                if current_id is not None:
                    runs.append(_EdgeRun(current_id, current_distance))
                    current_id = None
                    current_distance = 0.0
                    previous_edge = None
                continue
            known_distance += edge.distance_m
            reverses_previous = (
                previous_edge is not None
                and previous_edge.start == edge.end
                and previous_edge.end == edge.start
            )
            if current_id == edge_id and not reverses_previous:
                current_distance += edge.distance_m
            else:
                if current_id is not None:
                    runs.append(_EdgeRun(current_id, current_distance))
                current_id = edge_id
                current_distance = edge.distance_m
            previous_edge = edge
        if current_id is not None:
            runs.append(_EdgeRun(current_id, current_distance))

        run_counts = Counter(run.edge_id for run in runs)
        seen: set[int] = set()
        repeated_distance = 0.0
        for run in runs:
            if run.edge_id in seen:
                repeated_distance += run.distance_m
            else:
                seen.add(run.edge_id)

        return RepetitionAnalysis(
            edge_id_coverage=cls._metric(known_distance, route_distance_m),
            available=bool(runs),
            unique_edge_count=len(run_counts),
            traversed_edge_run_count=len(runs),
            repeated_edge_count=sum(count > 1 for count in run_counts.values()),
            repeated_distance=cls._metric(repeated_distance, route_distance_m),
        )
