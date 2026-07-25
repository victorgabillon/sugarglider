"""Private corridor areas and bounded guide points for spur connectors."""

from __future__ import annotations

from hashlib import sha256
from math import ceil, hypot

from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import substring

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.domain.models import Coordinate
from sugarglider.planning.optimization.models import (
    ConnectorGenerationStrategy,
    GlobalOptimizationSettings,
    InboundCorridorEvidence,
    RejoinPosition,
    SpurOptimizationTarget,
)
from sugarglider.routing.backend import CorridorAvoidanceArea


def inbound_corridor_evidence(
    target: SpurOptimizationTarget,
    settings: GlobalOptimizationSettings,
) -> InboundCorridorEvidence | None:
    """Exclude the allowed turnaround stem from ordered inbound geometry."""
    if len(target.inbound_geometry) < 2 or target.inbound_distance_m <= 0:
        return None
    projection = LocalMetricProjection(target.turnaround_coordinate.lat)
    line = projection.project_line(target.inbound_geometry)
    allowed = min(
        settings.maximum_shared_distance_near_turnaround_m,
        target.inbound_distance_m,
    )
    avoid_distance = max(0.0, target.inbound_distance_m - allowed)
    if line.length <= 0 or avoid_distance <= 0:
        return None
    avoid_metric_length = line.length * avoid_distance / target.inbound_distance_m
    avoid_line = substring(line, 0.0, avoid_metric_length)
    if not isinstance(avoid_line, LineString) or len(avoid_line.coords) < 2:
        return None
    geometry = tuple(
        projection.unproject_position((float(x), float(y)))
        for x, y, *_rest in avoid_line.coords
    )
    stable = sha256(
        repr(
            (
                target.stable_id,
                round(allowed, 6),
                tuple((round(lon, 7), round(lat, 7)) for lon, lat in geometry),
            )
        ).encode()
    ).hexdigest()[:16]
    return InboundCorridorEvidence(
        targeted_spur_id=target.spur_id,
        turnaround_coordinate=target.turnaround_coordinate,
        inbound_traversals=target.inbound_traversals,
        inbound_distance_m=target.inbound_distance_m,
        allowed_stem_distance_m=allowed,
        avoid_geometry=geometry,
        avoid_distance_m=avoid_distance,
        stable_id=f"inbound/{stable}",
    )


def corridor_avoidance_area(
    evidence: InboundCorridorEvidence,
    rejoin: RejoinPosition,
    settings: GlobalOptimizationSettings,
) -> CorridorAvoidanceArea | None:
    """Buffer only avoidable inbound geometry and carve out the rejoin area."""
    projection = LocalMetricProjection(evidence.turnaround_coordinate.lat)
    line = projection.project_line(evidence.avoid_geometry)
    polygonal = line.buffer(
        settings.corridor_buffer_width_m,
        cap_style="flat",
        join_style="round",
    ).simplify(settings.corridor_simplification_m, preserve_topology=True)
    rejoin_metric = projection.project_position(
        (rejoin.coordinate.lon, rejoin.coordinate.lat)
    )
    polygonal = polygonal.difference(
        Point(rejoin_metric).buffer(settings.corridor_buffer_width_m * 2)
    )
    polygon = _largest_polygon(polygonal)
    if polygon is None or polygon.is_empty:
        return None
    ring = tuple(
        projection.unproject_position((float(x), float(y)))
        for x, y, *_rest in polygon.exterior.coords
    )
    ring = _cap_ring(ring, settings.maximum_corridor_polygon_vertices)
    if not Polygon(ring).is_valid:
        return None
    digest = sha256(
        repr((evidence.stable_id, rejoin.stable_id, ring)).encode()
    ).hexdigest()[:16]
    return CorridorAvoidanceArea(
        id=f"avoid_{digest}",
        polygon=ring,
        source_distance_m=evidence.avoid_distance_m,
        buffer_width_m=settings.corridor_buffer_width_m,
    )


def guide_candidates(
    target: SpurOptimizationTarget,
    rejoin: RejoinPosition,
    area: CorridorAvoidanceArea | None,
    settings: GlobalOptimizationSettings,
) -> tuple[tuple[ConnectorGenerationStrategy, Coordinate], ...]:
    """Generate and then balance a deterministic two-sided multi-scale fan."""
    projection = LocalMetricProjection(target.turnaround_coordinate.lat)
    start = projection.project_position(
        (target.turnaround_coordinate.lon, target.turnaround_coordinate.lat)
    )
    end = projection.project_position((rejoin.coordinate.lon, rejoin.coordinate.lat))
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    length = hypot(delta_x, delta_y)
    if length <= 0:
        return ()
    normal_x = -delta_y / length
    normal_y = delta_x / length
    polygon = (
        projection.project_polygon(Polygon(area.polygon)) if area is not None else None
    )
    values: list[tuple[int, int, ConnectorGenerationStrategy, Coordinate]] = []
    sides: tuple[tuple[float, ConnectorGenerationStrategy], ...] = (
        (1.0, "guide_point_left"),
        (-1.0, "guide_point_right"),
    )
    for scale_index, (offset, share) in enumerate(
        zip(
            settings.guide_lateral_offsets_m,
            settings.guide_forward_shares,
            strict=True,
        )
    ):
        for side_index, (side, strategy) in enumerate(sides):
            position = (
                start[0] + delta_x * share + normal_x * offset * side,
                start[1] + delta_y * share + normal_y * offset * side,
            )
            if (
                hypot(position[0] - start[0], position[1] - start[1]) < 100.0
                or hypot(position[0] - end[0], position[1] - end[1]) < 100.0
                or (
                    polygon is not None
                    and (
                        polygon.contains(Point(position))
                        or polygon.touches(Point(position))
                    )
                )
            ):
                continue
            lon, lat = projection.unproject_position(position)
            values.append(
                (
                    scale_index,
                    side_index,
                    strategy,
                    Coordinate(lat=lat, lon=lon, name=None),
                )
            )
    if len(values) <= settings.maximum_guide_candidates_per_rejoin:
        return tuple((strategy, coordinate) for _, _, strategy, coordinate in values)

    # Prefer both sides at the smallest and largest surviving scales before
    # considering middle scales. This keeps the bounded fan local enough to be
    # useful while ensuring the outer escape scale is not systematically lost.
    scale_order = (
        0,
        len(settings.guide_lateral_offsets_m) - 1,
        *range(1, len(settings.guide_lateral_offsets_m) - 1),
    )
    priority = {
        (scale_index, side_index): order
        for order, (scale_index, side_index) in enumerate(
            (scale_index, side_index)
            for scale_index in scale_order
            for side_index in range(len(sides))
        )
    }
    selected = sorted(
        values,
        key=lambda value: (
            priority[(value[0], value[1])],
            value[2],
            value[3].lat,
            value[3].lon,
        ),
    )[: settings.maximum_guide_candidates_per_rejoin]
    return tuple((strategy, coordinate) for _, _, strategy, coordinate in selected)


def _largest_polygon(value: object) -> Polygon | None:
    if isinstance(value, Polygon):
        return value
    if isinstance(value, MultiPolygon) and value.geoms:
        return max(
            value.geoms,
            key=lambda polygon: (
                polygon.area,
                tuple(polygon.exterior.coords),
            ),
        )
    return None


def _cap_ring(
    ring: tuple[tuple[float, float], ...], maximum_vertices: int
) -> tuple[tuple[float, float], ...]:
    if len(ring) <= maximum_vertices:
        return ring
    open_ring = ring[:-1]
    step = ceil(len(open_ring) / (maximum_vertices - 1))
    retained = open_ring[::step][: maximum_vertices - 1]
    return (*retained, retained[0])
