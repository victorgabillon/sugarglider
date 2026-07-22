"""Bounded stable shape-anchor sampling for loop reversal."""

from shapely.geometry import Point

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.domain.models import Coordinate, GeoJsonPosition
from sugarglider.planning.direction.models import InternalShapeAnchor

SHAPE_PROGRESS = (0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875)
MAX_SHAPE_ANCHORS = 8
MIN_ROUTE_LENGTH_M = 1_000.0


def sample_shape_anchors(
    geometry: tuple[GeoJsonPosition, ...],
) -> tuple[InternalShapeAnchor, ...]:
    """Sample cumulative routed progress without exposing internal constraints."""
    if len(geometry) < 3:
        return ()
    projection = LocalMetricProjection(geometry[0][1])
    line = projection.project_line(geometry)
    if line.length < MIN_ROUTE_LENGTH_M:
        return ()
    minimum_spacing = max(150.0, line.length / 30.0)
    anchors: list[InternalShapeAnchor] = []
    for progress in SHAPE_PROGRESS:
        point = line.interpolate(progress * line.length)
        if any(
            point.distance(
                Point(
                    projection.project_position(
                        (anchor.coordinate.lon, anchor.coordinate.lat)
                    )
                )
            )
            < minimum_spacing
            for anchor in anchors
        ):
            continue
        lon, lat = projection.unproject_position((point.x, point.y))
        anchors.append(
            InternalShapeAnchor(
                coordinate=Coordinate(lat=lat, lon=lon),
                source_progress=progress,
            )
        )
        if len(anchors) == MAX_SHAPE_ANCHORS:
            break
    return tuple(anchors)
