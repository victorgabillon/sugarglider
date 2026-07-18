"""Explainable projected geometry metrics for complete routed loops."""

from collections.abc import Iterable
from dataclasses import dataclass
from math import acos, atan2, degrees, hypot, isclose, log, pi
from typing import cast

from shapely import STRtree
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiPoint,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import ProjectedGeometryEdge
from sugarglider.domain.analysis import (
    DistanceMetric,
    LoopGeometryAnalysis,
    LoopGeometryPenaltyBreakdown,
)

LOOP_CLOSURE_TOLERANCE_M = 25.0
LOOP_GEOMETRY_SECTOR_COUNT = 8
SECTOR_ORIGIN_TOLERANCE_M = 1e-9
SELF_CROSSING_DEDUP_TOLERANCE_M = 0.10
NEAR_PARALLEL_DISTANCE_M = 40.0
NEAR_PARALLEL_MAX_ANGLE_DEGREES = 30.0
NEAR_PARALLEL_MIN_ROUTE_SEPARATION_M = 250.0
OUTBOUND_RETURN_SAMPLE_INTERVAL_M = 60.0
OUTBOUND_RETURN_PROXIMITY_M = 150.0
OUTBOUND_RETURN_ENDPOINT_EXCLUSION_M = 250.0
OUTBOUND_RETURN_MAX_SAMPLES_PER_HALF = 800
MAX_PENALIZED_SELF_CROSSINGS = 8

type MetricPosition = tuple[float, float]


@dataclass(frozen=True)
class LoopGeometryPenaltyWeights:
    """Fixed, public, additive penalty weights; lower total is better."""

    crossing_penalty_per_crossing: float = 0.25
    near_parallel_penalty_weight: float = 3.0
    compactness_penalty_weight: float = 1.25
    sector_imbalance_penalty_weight: float = 0.75
    elongation_penalty_weight: float = 0.25


DEFAULT_LOOP_GEOMETRY_PENALTY_WEIGHTS = LoopGeometryPenaltyWeights()


def score_loop_geometry(
    *,
    self_crossing_count: int,
    near_parallel_share: float,
    compactness: float,
    sector_balance: float,
    elongation: float,
    weights: LoopGeometryPenaltyWeights = DEFAULT_LOOP_GEOMETRY_PENALTY_WEIGHTS,
) -> LoopGeometryPenaltyBreakdown:
    """Expose every fixed input, weight, component, and summed shape penalty."""
    crossing_input = min(MAX_PENALIZED_SELF_CROSSINGS, max(0, self_crossing_count))
    near_parallel_input = _clamp_share(near_parallel_share)
    compactness_input = _clamp_share(compactness)
    sector_balance_input = _clamp_share(sector_balance)
    elongation_input = _clamp_share(elongation)
    crossing_penalty = weights.crossing_penalty_per_crossing * crossing_input
    near_parallel_penalty = weights.near_parallel_penalty_weight * near_parallel_input
    compactness_penalty = weights.compactness_penalty_weight * (1.0 - compactness_input)
    sector_imbalance_penalty = weights.sector_imbalance_penalty_weight * (
        1.0 - sector_balance_input
    )
    elongation_penalty = weights.elongation_penalty_weight * (1.0 - elongation_input)
    return LoopGeometryPenaltyBreakdown(
        crossing_penalty_per_crossing=weights.crossing_penalty_per_crossing,
        crossing_count_input=crossing_input,
        crossing_penalty=crossing_penalty,
        near_parallel_penalty_weight=weights.near_parallel_penalty_weight,
        near_parallel_share_input=near_parallel_input,
        near_parallel_penalty=near_parallel_penalty,
        compactness_penalty_weight=weights.compactness_penalty_weight,
        compactness_input=compactness_input,
        compactness_penalty=compactness_penalty,
        sector_imbalance_penalty_weight=weights.sector_imbalance_penalty_weight,
        sector_balance_input=sector_balance_input,
        sector_imbalance_penalty=sector_imbalance_penalty,
        elongation_penalty_weight=weights.elongation_penalty_weight,
        elongation_input=elongation_input,
        elongation_penalty=elongation_penalty,
        total=(
            crossing_penalty
            + near_parallel_penalty
            + compactness_penalty
            + sector_imbalance_penalty
            + elongation_penalty
        ),
    )


class LoopGeometryRouteAnalyzer:
    """Analyze only complete normalized routed geometry in projected metres."""

    def analyze_route(
        self,
        edges: tuple[ProjectedGeometryEdge, ...],
        route_distance_m: float,
    ) -> LoopGeometryAnalysis:
        if not edges:
            raise ValueError("loop geometry analysis requires at least one route edge")
        positions = (edges[0].start, *(edge.end for edge in edges))
        projection = LocalMetricProjection(positions[0][1])
        metric_positions = tuple(
            projection.project_position(position) for position in positions
        )
        start = metric_positions[0]
        line = LineString(metric_positions)
        lines = tuple(
            LineString((metric_positions[index], metric_positions[index + 1]))
            for index in range(len(edges))
        )
        tree = STRtree(lines)

        start_end_gap_m = _distance(start, metric_positions[-1])
        closed = start_end_gap_m <= LOOP_CLOSURE_TOLERANCE_M
        warnings: set[str] = set()
        if not closed:
            warnings.add("loop_geometry_route_not_closed")

        convex_hull_area_m2 = max(0.0, float(line.convex_hull.area))
        area_line = line
        if closed and metric_positions[-1] != start:
            area_line = LineString((*metric_positions, start))
        enclosed_area_m2 = _enclosed_area(area_line) if closed else 0.0
        if line.length <= SECTOR_ORIGIN_TOLERANCE_M or convex_hull_area_m2 == 0:
            warnings.add("loop_geometry_degenerate")
        elif closed and enclosed_area_m2 == 0:
            warnings.add("loop_geometry_area_unavailable")

        compactness = (
            _clamp_share(4.0 * pi * enclosed_area_m2 / route_distance_m**2)
            if route_distance_m > 0 and enclosed_area_m2 > 0
            else 0.0
        )
        sector_shares = _sector_distance_shares(
            edges, metric_positions, route_distance_m
        )
        sector_balance = _normalized_entropy(sector_shares)
        maximum_sector_share = max(sector_shares, default=0.0)
        occupied_sector_count = sum(share > 0 for share in sector_shares)
        angular_monotonicity = _angular_monotonicity(metric_positions)
        mean_radius_m = _mean_radius(edges, metric_positions, start, route_distance_m)
        max_radius_m = max(_distance(start, position) for position in metric_positions)
        elongation = _elongation(line)
        self_crossing_count = _self_crossing_count(lines, tree, closed)
        near_parallel_distance_m = _near_parallel_distance(
            edges, lines, tree, route_distance_m
        )
        near_parallel = DistanceMetric(
            distance_m=near_parallel_distance_m,
            share=(
                _clamp_share(near_parallel_distance_m / route_distance_m)
                if route_distance_m > 0
                else 0.0
            ),
        )
        outbound_return_share = _outbound_return_proximity_share(metric_positions)
        outbound_return_proximity = DistanceMetric(
            distance_m=route_distance_m * outbound_return_share,
            share=outbound_return_share,
        )
        breakdown = score_loop_geometry(
            self_crossing_count=self_crossing_count,
            near_parallel_share=near_parallel.share,
            compactness=compactness,
            sector_balance=sector_balance,
            elongation=elongation,
        )
        return LoopGeometryAnalysis(
            closed=closed,
            start_end_gap_m=start_end_gap_m,
            enclosed_area_m2=enclosed_area_m2,
            convex_hull_area_m2=convex_hull_area_m2,
            compactness=compactness,
            sector_count=LOOP_GEOMETRY_SECTOR_COUNT,
            sector_distance_shares=sector_shares,
            sector_balance=sector_balance,
            maximum_sector_distance_share=maximum_sector_share,
            occupied_sector_count=occupied_sector_count,
            angular_monotonicity=angular_monotonicity,
            mean_radius_m=mean_radius_m,
            max_radius_m=max_radius_m,
            elongation=elongation,
            self_crossing_count=self_crossing_count,
            near_parallel=near_parallel,
            outbound_return_proximity=outbound_return_proximity,
            penalty_breakdown=breakdown,
            warnings=tuple(sorted(warnings)),
        )


def _angular_monotonicity(positions: tuple[MetricPosition, ...]) -> float:
    """Measure distance-weighted progress around the route centroid."""
    if len(positions) < 4:
        return 0.0
    closed = positions if positions[0] == positions[-1] else (*positions, positions[0])
    ring = closed[:-1]
    center = (
        sum(point[0] for point in ring) / len(ring),
        sum(point[1] for point in ring) / len(ring),
    )
    signed_area = 0.5 * sum(
        left[0] * right[1] - right[0] * left[1]
        for left, right in zip(closed, closed[1:], strict=False)
    )
    if abs(signed_area) <= SECTOR_ORIGIN_TOLERANCE_M:
        return 0.0
    expected_sign = 1.0 if signed_area > 0 else -1.0
    matching_distance = 0.0
    angular_distance = 0.0
    for left, right in zip(closed, closed[1:], strict=False):
        segment_length = _distance(left, right)
        if segment_length <= 0:
            continue
        left_angle = atan2(left[1] - center[1], left[0] - center[0])
        right_angle = atan2(right[1] - center[1], right[0] - center[0])
        delta = (right_angle - left_angle + pi) % (2.0 * pi) - pi
        if abs(delta) <= 1e-12:
            continue
        angular_distance += segment_length
        if delta * expected_sign > 0:
            matching_distance += segment_length
    return _clamp_share(
        matching_distance / angular_distance if angular_distance > 0 else 0.0
    )


def _outbound_return_proximity_share(
    positions: tuple[MetricPosition, ...],
) -> float:
    """Detect edge-disjoint hairpins by comparing outbound and return halves."""
    if len(positions) < 4:
        return 0.0
    start = positions[0]
    split_index = max(
        range(1, len(positions) - 1),
        key=lambda index: (_distance(start, positions[index]), -index),
    )
    outbound = LineString(positions[: split_index + 1])
    returning = LineString(positions[split_index:])
    if (
        outbound.length <= 2 * OUTBOUND_RETURN_ENDPOINT_EXCLUSION_M
        or returning.length <= 2 * OUTBOUND_RETURN_ENDPOINT_EXCLUSION_M
    ):
        return 0.0
    outbound_core = _line_core(outbound)
    returning_core = _line_core(returning)
    if outbound_core is None or returning_core is None:
        return 0.0
    outbound_share = _sampled_near_share(outbound_core, returning_core)
    return_share = _sampled_near_share(returning_core, outbound_core)
    return _clamp_share((outbound_share + return_share) / 2.0)


def _line_core(line: LineString) -> LineString | None:
    start = OUTBOUND_RETURN_ENDPOINT_EXCLUSION_M
    end = float(line.length) - OUTBOUND_RETURN_ENDPOINT_EXCLUSION_M
    if end <= start:
        return None
    sample_count = max(2, int((end - start) / OUTBOUND_RETURN_SAMPLE_INTERVAL_M) + 1)
    sample_count = min(OUTBOUND_RETURN_MAX_SAMPLES_PER_HALF, sample_count)
    positions = tuple(
        line.interpolate(start + (end - start) * index / (sample_count - 1)).coords[0]
        for index in range(sample_count)
    )
    return LineString(positions)


def _sampled_near_share(source: LineString, opposite: LineString) -> float:
    sample_count = max(
        2,
        min(
            OUTBOUND_RETURN_MAX_SAMPLES_PER_HALF,
            int(source.length / OUTBOUND_RETURN_SAMPLE_INTERVAL_M) + 1,
        ),
    )
    near = sum(
        opposite.distance(
            source.interpolate(source.length * index / (sample_count - 1))
        )
        <= OUTBOUND_RETURN_PROXIMITY_M
        for index in range(sample_count)
    )
    return near / sample_count


def _enclosed_area(line: LineString) -> float:
    """Node the network and sum distinct positive polygon faces."""
    noded = unary_union(line)
    return sum(float(face.area) for face in polygonize(noded) if face.area > 0)


def _sector_distance_shares(
    edges: tuple[ProjectedGeometryEdge, ...],
    positions: tuple[MetricPosition, ...],
    route_distance_m: float,
) -> tuple[float, ...]:
    distances = [0.0] * LOOP_GEOMETRY_SECTOR_COUNT
    start_x, start_y = positions[0]
    for index, edge in enumerate(edges):
        start = positions[index]
        end = positions[index + 1]
        midpoint_x = (start[0] + end[0]) / 2.0
        midpoint_y = (start[1] + end[1]) / 2.0
        direction_x = midpoint_x - start_x
        direction_y = midpoint_y - start_y
        if hypot(direction_x, direction_y) <= SECTOR_ORIGIN_TOLERANCE_M:
            direction_x = end[0] - start[0]
            direction_y = end[1] - start[1]
        angle = atan2(direction_y, direction_x) % (2.0 * pi)
        sector = min(
            LOOP_GEOMETRY_SECTOR_COUNT - 1,
            int(angle / (2.0 * pi / LOOP_GEOMETRY_SECTOR_COUNT)),
        )
        distances[sector] += edge.distance_m
    if route_distance_m <= 0:
        return tuple(0.0 for _distance_m in distances)
    shares = [max(0.0, distance / route_distance_m) for distance in distances]
    shares[-1] = max(0.0, 1.0 - sum(shares[:-1]))
    if not isclose(sum(shares), 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("authoritative sector distances must partition route distance")
    return tuple(_clamp_share(share) for share in shares)


def _normalized_entropy(shares: tuple[float, ...]) -> float:
    positive = tuple(share for share in shares if share > 0)
    if not positive:
        return 0.0
    return _clamp_share(-sum(share * log(share) for share in positive) / log(8.0))


def _mean_radius(
    edges: tuple[ProjectedGeometryEdge, ...],
    positions: tuple[MetricPosition, ...],
    start: MetricPosition,
    route_distance_m: float,
) -> float:
    if route_distance_m <= 0:
        return 0.0
    weighted = 0.0
    for index, edge in enumerate(edges):
        left = positions[index]
        right = positions[index + 1]
        midpoint = ((left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0)
        weighted += edge.distance_m * _distance(start, midpoint)
    return max(0.0, weighted / route_distance_m)


def _elongation(line: LineString) -> float:
    rectangle = cast(BaseGeometry, line.convex_hull.minimum_rotated_rectangle)
    if not isinstance(rectangle, Polygon):
        return 0.0
    coordinates = tuple(rectangle.exterior.coords)
    side_lengths = tuple(
        _distance(cast(MetricPosition, left), cast(MetricPosition, right))
        for left, right in zip(coordinates, coordinates[1:], strict=False)
    )
    major = max(side_lengths, default=0.0)
    minor = min(side_lengths, default=0.0)
    return _clamp_share(minor / major) if major > 0 else 0.0


def _self_crossing_count(
    lines: tuple[LineString, ...], tree: STRtree, closed: bool
) -> int:
    candidates: list[MetricPosition] = []
    last_index = len(lines) - 1
    for index, line in enumerate(lines):
        raw: object = tree.query(line)
        for neighbour_raw in cast(Iterable[int], raw):
            neighbour = int(neighbour_raw)
            if neighbour <= index or neighbour == index + 1:
                continue
            if closed and index == 0 and neighbour == last_index:
                continue
            intersection = line.intersection(lines[neighbour])
            for point in _intersection_points(intersection):
                endpoints = (
                    tuple(line.coords[0]),
                    tuple(line.coords[-1]),
                    tuple(lines[neighbour].coords[0]),
                    tuple(lines[neighbour].coords[-1]),
                )
                if any(
                    _distance(point, cast(MetricPosition, endpoint))
                    <= SELF_CROSSING_DEDUP_TOLERANCE_M
                    for endpoint in endpoints
                ):
                    continue
                candidates.append(point)
    unique: list[MetricPosition] = []
    for point in sorted(candidates):
        if not any(
            _distance(point, existing) <= SELF_CROSSING_DEDUP_TOLERANCE_M
            for existing in unique
        ):
            unique.append(point)
    return len(unique)


def _intersection_points(geometry: BaseGeometry) -> tuple[MetricPosition, ...]:
    if isinstance(geometry, Point):
        return ((float(geometry.x), float(geometry.y)),)
    if isinstance(geometry, (MultiPoint, GeometryCollection)):
        return tuple(
            point
            for part in geometry.geoms
            for point in _intersection_points(cast(BaseGeometry, part))
        )
    return ()


def _near_parallel_distance(
    edges: tuple[ProjectedGeometryEdge, ...],
    lines: tuple[LineString, ...],
    tree: STRtree,
    route_distance_m: float,
) -> float:
    cumulative = 0.0
    midpoints: list[float] = []
    for edge in edges:
        midpoints.append(cumulative + edge.distance_m / 2.0)
        cumulative += edge.distance_m
    attributed = 0.0
    for index, (edge, line) in enumerate(zip(edges, lines, strict=True)):
        if line.length <= 0 or edge.distance_m <= 0:
            continue
        raw: object = tree.query(
            line,
            predicate="dwithin",
            distance=NEAR_PARALLEL_DISTANCE_M,
        )
        qualifying: list[BaseGeometry] = []
        for neighbour_raw in cast(Iterable[int], raw):
            neighbour = int(neighbour_raw)
            if (
                neighbour == index
                or abs(neighbour - index) == 1
                or lines[neighbour].length <= 0
            ):
                continue
            route_separation = abs(midpoints[index] - midpoints[neighbour])
            if route_distance_m > 0:
                route_separation = min(
                    route_separation, max(0.0, route_distance_m - route_separation)
                )
            if route_separation < NEAR_PARALLEL_MIN_ROUTE_SEPARATION_M:
                continue
            if _orientation_difference_degrees(line, lines[neighbour]) > (
                NEAR_PARALLEL_MAX_ANGLE_DEGREES
            ):
                continue
            qualifying.append(lines[neighbour].buffer(NEAR_PARALLEL_DISTANCE_M))
        if not qualifying:
            continue
        covered = line.intersection(unary_union(qualifying))
        fraction = _clamp_share(float(covered.length) / float(line.length))
        attributed += edge.distance_m * fraction
    return min(route_distance_m, max(0.0, attributed))


def _orientation_difference_degrees(left: LineString, right: LineString) -> float:
    left_start, left_end = tuple(left.coords)
    right_start, right_end = tuple(right.coords)
    left_vector = (left_end[0] - left_start[0], left_end[1] - left_start[1])
    right_vector = (
        right_end[0] - right_start[0],
        right_end[1] - right_start[1],
    )
    denominator = hypot(*left_vector) * hypot(*right_vector)
    if denominator <= 0:
        return 90.0
    cosine = abs(
        (left_vector[0] * right_vector[0] + left_vector[1] * right_vector[1])
        / denominator
    )
    return degrees(acos(min(1.0, max(-1.0, cosine))))


def _distance(left: MetricPosition, right: MetricPosition) -> float:
    return hypot(left[0] - right[0], left[1] - right[1])


def _clamp_share(value: float) -> float:
    return min(1.0, max(0.0, value))
