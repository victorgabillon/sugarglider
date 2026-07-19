"""Deterministic destination-progress metrics for graph-routed open paths."""

from dataclasses import dataclass
from math import atan2, cos

from shapely.geometry import LineString, Point

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.domain.models import GeoJsonPosition

MAX_PROGRESS_SAMPLES = 256
LOCAL_REVERSE_TOLERANCE_M = 15.0
NEAR_PARALLEL_DISTANCE_M = 50.0
NEAR_PARALLEL_COSINE = 0.9659258262890683


@dataclass(frozen=True)
class OpenRouteMetrics:
    """Bounded metrics that remain meaningful for a point-to-point route."""

    direct_distance_m: float
    detour_ratio: float
    destination_progress_monotonicity: float
    reverse_progress_distance_m: float
    reverse_progress_share: float
    endpoint_axis_lateral_deviation_m: float
    near_parallel_corridor_share: float


def analyze_open_route(
    *,
    geometry: tuple[GeoJsonPosition, ...],
    route_distance_m: float,
    direct_geometry: tuple[GeoJsonPosition, ...],
    direct_distance_m: float,
) -> OpenRouteMetrics:
    """Project bounded samples onto the routed direct control and endpoint axis."""
    reference_latitude = sum(lat for _, lat in direct_geometry) / len(direct_geometry)
    projection = LocalMetricProjection(reference_latitude)
    reference = projection.project_line(direct_geometry)
    if reference.length <= 0:
        raise ValueError("direct control geometry must have positive length")
    sample_indices = _sample_indices(len(geometry))
    samples = tuple(
        Point(projection.project_position(geometry[index])) for index in sample_indices
    )
    progresses = tuple(reference.project(point) for point in samples)
    reverse = sum(
        max(0.0, previous - current)
        for previous, current in zip(progresses, progresses[1:], strict=False)
        if previous - current > LOCAL_REVERSE_TOLERANCE_M
    )
    forward = sum(
        max(0.0, current - previous)
        for previous, current in zip(progresses, progresses[1:], strict=False)
    )
    movement = forward + reverse
    reverse_share = reverse / movement if movement > 0 else 0.0
    axis = LineString(
        (
            projection.project_position(direct_geometry[0]),
            projection.project_position(direct_geometry[-1]),
        )
    )
    lateral = sum(axis.distance(point) for point in samples) / len(samples)
    near_parallel_share = _near_parallel_share(
        tuple(projection.project_position(position) for position in geometry)
    )
    return OpenRouteMetrics(
        direct_distance_m=direct_distance_m,
        detour_ratio=(route_distance_m / direct_distance_m),
        destination_progress_monotonicity=max(0.0, 1.0 - reverse_share),
        reverse_progress_distance_m=reverse,
        reverse_progress_share=reverse_share,
        endpoint_axis_lateral_deviation_m=lateral,
        near_parallel_corridor_share=near_parallel_share,
    )


def _sample_indices(point_count: int) -> tuple[int, ...]:
    if point_count < 2:
        raise ValueError("open route geometry requires at least two points")
    if point_count <= MAX_PROGRESS_SAMPLES:
        return tuple(range(point_count))
    return tuple(
        (index * (point_count - 1)) // (MAX_PROGRESS_SAMPLES - 1)
        for index in range(MAX_PROGRESS_SAMPLES)
    )


def _near_parallel_share(points: tuple[tuple[float, float], ...]) -> float:
    """Measure bounded non-adjacent nearby parallel corridor segments."""
    if len(points) > MAX_PROGRESS_SAMPLES:
        indices = _sample_indices(len(points))
        points = tuple(points[index] for index in indices)
    segments = tuple(
        LineString((left, right))
        for left, right in zip(points, points[1:], strict=False)
        if left != right
    )
    lengths = tuple(segment.length for segment in segments)
    marked: set[int] = set()
    for left_index, left in enumerate(segments):
        left_angle = atan2(
            left.coords[-1][1] - left.coords[0][1],
            left.coords[-1][0] - left.coords[0][0],
        )
        for right_index in range(left_index + 3, len(segments)):
            right = segments[right_index]
            if left.distance(right) > NEAR_PARALLEL_DISTANCE_M:
                continue
            right_angle = atan2(
                right.coords[-1][1] - right.coords[0][1],
                right.coords[-1][0] - right.coords[0][0],
            )
            if abs(cos(left_angle - right_angle)) >= NEAR_PARALLEL_COSINE:
                marked.update((left_index, right_index))
    total = sum(lengths)
    return sum(lengths[index] for index in marked) / total if total > 0 else 0.0
