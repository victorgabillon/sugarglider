"""Deterministic orientation analysis over final routed geometry."""

from math import hypot

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.models import GeoJsonPosition
from sugarglider.planning.models import RouteTopology
from sugarglider.planning.result import RouteTraversalDirection

MIN_CLOSED_AREA_M2 = 1_000.0
MIN_NORMALIZED_AREA = 0.002
MIN_AREA_COHERENCE = 0.35
MAX_CLOSURE_GAP_M = 50.0


def analyze_route_direction(
    geometry: tuple[GeoJsonPosition, ...], topology: RouteTopology
) -> RouteTraversalDirection:
    """Classify a final route without overstating ambiguous loop orientation."""
    if topology == "point_to_point":
        return "start_to_end"
    if len(geometry) < 4:
        return "complex_loop"
    if haversine_distance_m(geometry[0], geometry[-1]) > MAX_CLOSURE_GAP_M:
        return "complex_loop"
    positions = geometry[:-1] if geometry[0] == geometry[-1] else geometry
    if len(positions) < 3:
        return "complex_loop"
    projection = LocalMetricProjection(positions[0][1])
    projected = tuple(projection.project_position(position) for position in positions)
    origin_x, origin_y = projected[0]
    points = tuple((x - origin_x, y - origin_y) for x, y in projected)
    closed = (*points, points[0])
    cross_terms = tuple(
        left[0] * right[1] - right[0] * left[1]
        for left, right in zip(closed, closed[1:], strict=False)
    )
    signed_area = sum(cross_terms) / 2.0
    absolute_area = sum(abs(value) for value in cross_terms) / 2.0
    perimeter = sum(
        hypot(right[0] - left[0], right[1] - left[1])
        for left, right in zip(closed, closed[1:], strict=False)
    )
    if (
        abs(signed_area) < MIN_CLOSED_AREA_M2
        or perimeter <= 0
        or abs(signed_area) / (perimeter * perimeter) < MIN_NORMALIZED_AREA
        or absolute_area <= 0
        or abs(signed_area) / absolute_area < MIN_AREA_COHERENCE
    ):
        return "complex_loop"
    return "counterclockwise" if signed_area > 0 else "clockwise"
