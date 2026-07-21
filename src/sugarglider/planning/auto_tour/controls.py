"""Pure deterministic start-on-perimeter Auto Tour control construction."""

from dataclasses import dataclass
from math import atan2, cos, hypot, pi, radians, sin, sqrt

from shapely.geometry import LineString, MultiPoint, MultiPolygon, Point, Polygon

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.domain.models import Coordinate, GeoJsonPosition
from sugarglider.planning.auto_tour.models import (
    DirectionPreference,
    TourDirection,
)

ELLIPSE_INITIAL_BEARINGS_DEGREES = (0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0)
ELLIPSE_ASPECT_RATIOS = (1.0, 0.75, 0.55)
ELLIPSE_PERIMETER_SCALES = (0.85, 1.0)
ELLIPSE_VERTEX_COUNT = 6
ELLIPSE_SOLVE_ITERATIONS = 80
ELLIPSE_SHRINK_ITERATIONS = 48
MIN_ELLIPSE_CONTAINMENT_SCALE = 0.35
DIRECTION_MONOTONICITY_THRESHOLD = 0.65
HIGHLY_MIXED_MONOTONICITY_THRESHOLD = 0.55
SIGNED_AREA_EPSILON_M2 = 1.0
SAMPLED_ROUND_TRIP_MIN_ANCHORS = 5
SAMPLED_ROUND_TRIP_MAX_ANCHORS = 8
SAMPLED_ROUND_TRIP_MIN_ANCHOR_SEPARATION_M = 250.0

type MetricPosition = tuple[float, float]


@dataclass(frozen=True)
class LoopSkeleton:
    """Six requested WGS84 vertices for one directed ellipse family."""

    skeleton_id: str
    direction: TourDirection
    bearing_degrees: float
    aspect_ratio: float
    perimeter_scale: float
    containment_scale: float
    requested_perimeter_m: float
    major_radius_m: float
    minor_radius_m: float
    vertices: tuple[Coordinate, ...]
    center_metric: MetricPosition

    @property
    def closed_vertices(self) -> tuple[Coordinate, ...]:
        return (*self.vertices, self.vertices[0])


@dataclass(frozen=True)
class DirectionAnalysis:
    direction: TourDirection
    signed_area_m2: float
    angular_monotonicity: float
    warnings: tuple[str, ...]


def ramanujan_perimeter(major_radius_m: float, minor_radius_m: float) -> float:
    """Return Ramanujan's second ellipse-perimeter approximation."""
    if major_radius_m <= 0 or minor_radius_m <= 0:
        raise ValueError("ellipse radii must be positive")
    h = ((major_radius_m - minor_radius_m) / (major_radius_m + minor_radius_m)) ** 2
    return pi * (major_radius_m + minor_radius_m) * (1 + 3 * h / (10 + sqrt(4 - 3 * h)))


def solve_ellipse_axes(perimeter_m: float, aspect_ratio: float) -> tuple[float, float]:
    """Solve the major radius by a fixed-iteration monotone binary search."""
    if perimeter_m <= 0:
        raise ValueError("ellipse perimeter must be positive")
    if not 0 < aspect_ratio <= 1:
        raise ValueError("ellipse aspect ratio must be within (0, 1]")
    lower = 0.0
    upper = perimeter_m
    for _iteration in range(ELLIPSE_SOLVE_ITERATIONS):
        major = (lower + upper) / 2
        approximation = ramanujan_perimeter(major, major * aspect_ratio)
        if approximation < perimeter_m:
            lower = major
        else:
            upper = major
    major = (lower + upper) / 2
    return major, major * aspect_ratio


def ellipse_vertices(
    *,
    start: Coordinate,
    bearing_degrees: float,
    major_radius_m: float,
    minor_radius_m: float,
    direction: TourDirection,
    projection: LocalMetricProjection | None = None,
) -> tuple[tuple[Coordinate, ...], MetricPosition]:
    """Construct six directed vertices with the supplied start exactly at index zero."""
    if direction not in {"clockwise", "counterclockwise"}:
        raise ValueError("ellipse input direction cannot be mixed")
    if major_radius_m <= 0 or minor_radius_m <= 0:
        raise ValueError("ellipse radii must be positive")
    local = projection or LocalMetricProjection(start.lat)
    start_metric = local.project_position((start.lon, start.lat))
    bearing = radians(bearing_degrees)
    major_unit = (sin(bearing), cos(bearing))
    minor_unit = (-major_unit[1], major_unit[0])
    center = (
        start_metric[0] - major_radius_m * major_unit[0],
        start_metric[1] - major_radius_m * major_unit[1],
    )
    sign = -1.0 if direction == "clockwise" else 1.0
    vertices: list[Coordinate] = [start]
    for index in range(1, ELLIPSE_VERTEX_COUNT):
        angle = sign * 2 * pi * index / ELLIPSE_VERTEX_COUNT
        x = (
            center[0]
            + major_radius_m * cos(angle) * major_unit[0]
            + minor_radius_m * sin(angle) * minor_unit[0]
        )
        y = (
            center[1]
            + major_radius_m * cos(angle) * major_unit[1]
            + minor_radius_m * sin(angle) * minor_unit[1]
        )
        lon, lat = local.unproject_position((x, y))
        vertices.append(Coordinate(lat=lat, lon=lon))
    return tuple(vertices), center


def generate_isochrone_skeletons(
    *,
    start: Coordinate,
    target_distance_m: float,
    envelope: Polygon | MultiPolygon,
    direction_preference: DirectionPreference = "any",
    minimum_scale: float = MIN_ELLIPSE_CONTAINMENT_SCALE,
) -> tuple[LoopSkeleton, ...]:
    """Generate fitting deterministic ellipses without boundary projection."""
    if target_distance_m <= 0:
        raise ValueError("target distance must be positive")
    if not 0 < minimum_scale <= 1:
        raise ValueError("minimum ellipse scale must be within (0, 1]")
    if envelope.is_empty or not envelope.is_valid:
        raise ValueError("isochrone envelope must be non-empty and valid")
    projection = LocalMetricProjection(start.lat)
    metric_envelope = projection.project_polygon(envelope)
    directions: tuple[TourDirection, ...] = (
        ("clockwise", "counterclockwise")
        if direction_preference == "any"
        else (direction_preference,)
    )
    skeletons: list[LoopSkeleton] = []
    # Shape-first ordering gives the strict route budget all eight bearings and
    # both directions before considering less central aspect/scale variants.
    parameter_order = (
        (0.75, 1.0),
        (1.0, 1.0),
        (0.55, 0.85),
        (0.75, 0.85),
        (1.0, 0.85),
        (0.55, 1.0),
    )
    for aspect_ratio, perimeter_scale in parameter_order:
        perimeter = target_distance_m * perimeter_scale
        major, minor = solve_ellipse_axes(perimeter, aspect_ratio)
        for bearing in ELLIPSE_INITIAL_BEARINGS_DEGREES:
            for direction in directions:
                scale = _containment_scale(
                    start=start,
                    bearing_degrees=bearing,
                    major_radius_m=major,
                    minor_radius_m=minor,
                    direction=direction,
                    projection=projection,
                    metric_envelope=metric_envelope,
                    minimum_scale=minimum_scale,
                )
                if scale is None:
                    continue
                vertices, center = ellipse_vertices(
                    start=start,
                    bearing_degrees=bearing,
                    major_radius_m=major * scale,
                    minor_radius_m=minor * scale,
                    direction=direction,
                    projection=projection,
                )
                skeletons.append(
                    LoopSkeleton(
                        skeleton_id=(
                            f"ellipse-b{bearing:g}-a{aspect_ratio:g}-"
                            f"p{perimeter_scale:g}-{direction}"
                        ),
                        direction=direction,
                        bearing_degrees=bearing,
                        aspect_ratio=aspect_ratio,
                        perimeter_scale=perimeter_scale,
                        containment_scale=scale,
                        requested_perimeter_m=perimeter,
                        major_radius_m=major * scale,
                        minor_radius_m=minor * scale,
                        vertices=vertices,
                        center_metric=center,
                    )
                )
    return tuple(skeletons)


def routing_points_with_hard_anchors(
    skeleton: LoopSkeleton,
    hard_waypoints: tuple[Coordinate, ...],
) -> tuple[Coordinate, ...]:
    """Insert exact hard points by monotone angular progress and close the loop."""
    if not hard_waypoints:
        return skeleton.closed_vertices
    projection = LocalMetricProjection(skeleton.vertices[0].lat)
    direction_sign = -1.0 if skeleton.direction == "clockwise" else 1.0

    def progress(point: Coordinate) -> float:
        x, y = projection.project_position((point.lon, point.lat))
        angle = atan2(y - skeleton.center_metric[1], x - skeleton.center_metric[0])
        start = atan2(
            projection.project_position(
                (skeleton.vertices[0].lon, skeleton.vertices[0].lat)
            )[1]
            - skeleton.center_metric[1],
            projection.project_position(
                (skeleton.vertices[0].lon, skeleton.vertices[0].lat)
            )[0]
            - skeleton.center_metric[0],
        )
        return ((direction_sign * (angle - start)) % (2 * pi)) / (2 * pi)

    entries: list[tuple[float, int, int, Coordinate]] = []
    for index, vertex in enumerate(skeleton.vertices[1:], start=1):
        entries.append((index / ELLIPSE_VERTEX_COUNT, 0, index, vertex))
    for index, point in enumerate(hard_waypoints):
        entries.append((progress(point), 1, index, point))
    entries.sort(key=lambda value: (value[0], value[1], value[2]))
    start = skeleton.vertices[0]
    return (start, *(entry[3] for entry in entries), start)


def sample_round_trip_routing_points(
    *,
    start: Coordinate,
    geometry: tuple[GeoJsonPosition, ...],
    route_distance_m: float,
) -> tuple[Coordinate, ...] | None:
    """Sample a stable ordered skeleton from graph-routed round-trip geometry."""
    if len(geometry) < 4 or route_distance_m <= 0:
        return None
    projection = LocalMetricProjection(start.lat)
    metric_geometry = tuple(
        projection.project_position(position) for position in geometry
    )
    line = LineString(metric_geometry)
    if line.length <= 0:
        return None
    anchor_count = min(
        SAMPLED_ROUND_TRIP_MAX_ANCHORS,
        max(SAMPLED_ROUND_TRIP_MIN_ANCHORS, round(route_distance_m / 6_000.0)),
    )
    start_metric = projection.project_position((start.lon, start.lat))
    anchors: list[tuple[float, Coordinate, tuple[float, float], int]] = []
    occupied_sectors: set[int] = set()
    spacing = 1.0 / (anchor_count + 1)
    for ordinal in range(1, anchor_count + 1):
        target = ordinal * spacing
        candidates: list[
            tuple[int, float, float, Coordinate, tuple[float, float], int]
        ] = []
        for offset in (0.0, -0.22, 0.22, -0.38, 0.38):
            progress = target + offset * spacing
            metric = line.interpolate(progress * line.length)
            metric_position = (float(metric.x), float(metric.y))
            if any(
                hypot(
                    metric_position[0] - previous[2][0],
                    metric_position[1] - previous[2][1],
                )
                < SAMPLED_ROUND_TRIP_MIN_ANCHOR_SEPARATION_M
                for previous in anchors
            ):
                continue
            if (
                hypot(
                    metric_position[0] - start_metric[0],
                    metric_position[1] - start_metric[1],
                )
                < SAMPLED_ROUND_TRIP_MIN_ANCHOR_SEPARATION_M
            ):
                continue
            angle = atan2(
                metric_position[1] - start_metric[1],
                metric_position[0] - start_metric[0],
            ) % (2.0 * pi)
            sector = min(7, int(angle / (2.0 * pi / 8.0)))
            lon, lat = projection.unproject_position(metric_position)
            coordinate = Coordinate(
                lat=lat,
                lon=lon,
                name=f"Sampled loop anchor {ordinal}",
            )
            candidates.append(
                (
                    0 if sector not in occupied_sectors else 1,
                    abs(offset),
                    progress,
                    coordinate,
                    metric_position,
                    sector,
                )
            )
        if not candidates:
            return None
        _new_sector, _offset, progress, coordinate, metric_position, sector = min(
            candidates
        )
        anchors.append((progress, coordinate, metric_position, sector))
        occupied_sectors.add(sector)
    anchors.sort(key=lambda value: value[0])
    return (start, *(anchor[1] for anchor in anchors), start)


def routing_points_with_sampled_hard_anchors(
    sampled_points: tuple[Coordinate, ...],
    hard_waypoints: tuple[Coordinate, ...],
) -> tuple[Coordinate, ...]:
    """Insert exact hard anchors monotonically into a sampled routed skeleton."""
    if not hard_waypoints:
        return sampled_points
    start = sampled_points[0]
    projection = LocalMetricProjection(start.lat)
    line = LineString(
        tuple(
            projection.project_position((point.lon, point.lat))
            for point in sampled_points
        )
    )

    def progress(point: Coordinate) -> float:
        metric = Point(projection.project_position((point.lon, point.lat)))
        return float(line.project(metric) / line.length) if line.length > 0 else 0.0

    entries = [
        (index / (len(sampled_points) - 1), 0, index, point)
        for index, point in enumerate(sampled_points[1:-1], start=1)
    ]
    entries.extend(
        (progress(point), 1, index, point) for index, point in enumerate(hard_waypoints)
    )
    entries.sort(key=lambda value: (value[0], value[1], value[2]))
    return (start, *(entry[3] for entry in entries), start)


def classify_route_direction(
    geometry: tuple[GeoJsonPosition, ...],
) -> DirectionAnalysis:
    """Classify a routed loop using signed area and weighted angular monotonicity."""
    if len(geometry) < 4:
        return DirectionAnalysis(
            "mixed", 0.0, 0.0, ("auto_tour_direction_highly_mixed",)
        )
    reference_latitude = sum(position[1] for position in geometry) / len(geometry)
    projection = LocalMetricProjection(reference_latitude)
    points = tuple(projection.project_position(position) for position in geometry)
    closed = points if points[0] == points[-1] else (*points, points[0])
    signed_area = 0.5 * sum(
        left[0] * right[1] - right[0] * left[1]
        for left, right in zip(closed, closed[1:], strict=False)
    )
    center = (
        sum(point[0] for point in closed[:-1]) / (len(closed) - 1),
        sum(point[1] for point in closed[:-1]) / (len(closed) - 1),
    )
    expected_sign = 1.0 if signed_area > 0 else -1.0
    matching_distance = 0.0
    angular_distance = 0.0
    for left, right in zip(closed, closed[1:], strict=False):
        segment_length = hypot(right[0] - left[0], right[1] - left[1])
        if segment_length <= 0:
            continue
        left_angle = atan2(left[1] - center[1], left[0] - center[0])
        right_angle = atan2(right[1] - center[1], right[0] - center[0])
        delta = (right_angle - left_angle + pi) % (2 * pi) - pi
        if abs(delta) <= 1e-12:
            continue
        angular_distance += segment_length
        if delta * expected_sign > 0:
            matching_distance += segment_length
    monotonicity = matching_distance / angular_distance if angular_distance > 0 else 0.0
    direction: TourDirection
    if (
        abs(signed_area) <= SIGNED_AREA_EPSILON_M2
        or monotonicity < DIRECTION_MONOTONICITY_THRESHOLD
    ):
        direction = "mixed"
    else:
        direction = "counterclockwise" if signed_area > 0 else "clockwise"
    warnings = (
        ("auto_tour_direction_highly_mixed",)
        if (
            monotonicity < HIGHLY_MIXED_MONOTONICITY_THRESHOLD
            or abs(signed_area) <= SIGNED_AREA_EPSILON_M2
        )
        else ()
    )
    return DirectionAnalysis(direction, signed_area, monotonicity, warnings)


def _containment_scale(
    *,
    start: Coordinate,
    bearing_degrees: float,
    major_radius_m: float,
    minor_radius_m: float,
    direction: TourDirection,
    projection: LocalMetricProjection,
    metric_envelope: Polygon | MultiPolygon,
    minimum_scale: float,
) -> float | None:
    def fits(scale: float) -> bool:
        vertices, _center = ellipse_vertices(
            start=start,
            bearing_degrees=bearing_degrees,
            major_radius_m=major_radius_m * scale,
            minor_radius_m=minor_radius_m * scale,
            direction=direction,
            projection=projection,
        )
        points = MultiPoint(
            tuple(
                projection.project_position((vertex.lon, vertex.lat))
                for vertex in vertices[1:]
            )
        )
        return bool(metric_envelope.covers(points))

    if fits(1.0):
        return 1.0
    if not fits(minimum_scale):
        return None
    lower = minimum_scale
    upper = 1.0
    for _iteration in range(ELLIPSE_SHRINK_ITERATIONS):
        middle = (lower + upper) / 2
        if fits(middle):
            lower = middle
        else:
            upper = middle
    return lower if fits(lower) else None
