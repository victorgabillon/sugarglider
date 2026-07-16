"""Pure geometry sampling and ordered waypoint insertion helpers."""

from itertools import pairwise

from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.models import Coordinate, GeoJsonPosition

SAMPLE_FRACTIONS = (0.25, 0.50, 0.75)
MIN_OPTIONAL_POINT_SEPARATION_M = 50.0


def sample_optional_points(
    geometry: tuple[GeoJsonPosition, ...],
    start: Coordinate,
    *,
    minimum_separation_m: float = MIN_OPTIONAL_POINT_SEPARATION_M,
) -> tuple[Coordinate, ...]:
    """Sample proposal positions at cumulative, rather than array-index, fractions."""
    if len(geometry) < 2:
        return ()
    lengths = tuple(
        haversine_distance_m(left, right) for left, right in pairwise(geometry)
    )
    total_distance = sum(lengths)
    if total_distance <= 0:
        return ()

    start_position = (start.lon, start.lat)
    sampled: list[GeoJsonPosition] = []
    for fraction in SAMPLE_FRACTIONS:
        target_distance = total_distance * fraction
        traversed = 0.0
        position: GeoJsonPosition | None = None
        for index, segment_distance in enumerate(lengths):
            next_distance = traversed + segment_distance
            if next_distance >= target_distance and segment_distance > 0:
                ratio = (target_distance - traversed) / segment_distance
                start_lon, start_lat = geometry[index]
                end_lon, end_lat = geometry[index + 1]
                position = (
                    start_lon + (end_lon - start_lon) * ratio,
                    start_lat + (end_lat - start_lat) * ratio,
                )
                break
            traversed = next_distance
        if position is None:
            continue
        if haversine_distance_m(start_position, position) < minimum_separation_m:
            continue
        if any(
            haversine_distance_m(existing, position) < minimum_separation_m
            for existing in sampled
        ):
            continue
        if (
            position == geometry[-1]
            and haversine_distance_m(geometry[-1], start_position)
            < minimum_separation_m
        ):
            continue
        sampled.append(position)

    return tuple(
        Coordinate(lat=lat, lon=lon, name=f"Generated detour {index}")
        for index, (lon, lat) in enumerate(sampled, start=1)
    )


def insert_optional_points(
    required_points: tuple[Coordinate, ...],
    insertion_index: int,
    optional_points: tuple[Coordinate, ...],
) -> tuple[Coordinate, ...]:
    """Insert optional points after one anchor without changing required order."""
    if insertion_index < 0 or insertion_index >= len(required_points) - 1:
        raise ValueError("optional-point insertion index is outside the closed route")
    return (
        *required_points[: insertion_index + 1],
        *optional_points,
        *required_points[insertion_index + 1 :],
    )


def point_sequence_key(
    points: tuple[Coordinate, ...],
) -> tuple[tuple[float, float], ...]:
    """Return an exact deterministic cache key without point names."""
    return tuple((point.lat, point.lon) for point in points)
