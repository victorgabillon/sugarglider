"""Pure deterministic mandatory-point ordering proposals for closed loops."""

from math import atan2, cos, pi, radians

from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.models import Coordinate

MAX_ORDER_PROPOSALS = 16
MAX_TWO_OPT_PASSES = 4

type PointOrder = tuple[int, ...]


def validate_point_order(order: PointOrder, point_count: int) -> None:
    """Reject orders that move the start, omit points, or repeat points."""
    if point_count < 2:
        raise ValueError("point ordering requires at least two mandatory points")
    if len(order) != point_count:
        raise ValueError("point order must contain every mandatory point")
    if order[0] != 0:
        raise ValueError("point order must keep the first point fixed")
    if set(order) != set(range(point_count)):
        raise ValueError("point order must contain every original index exactly once")


def ordered_closed_points(
    points: tuple[Coordinate, ...], order: PointOrder
) -> tuple[Coordinate, ...]:
    """Apply a valid mandatory order and append exactly one closing start point."""
    validate_point_order(order, len(points))
    ordered = tuple(points[index] for index in order)
    return (*ordered, ordered[0])


def polar_angle_order(points: tuple[Coordinate, ...], *, clockwise: bool) -> PointOrder:
    """Sweep non-start points around their centroid from the start-facing ray."""
    if len(points) < 2:
        raise ValueError("point ordering requires at least two mandatory points")
    others = points[1:]
    centroid_lat = sum(point.lat for point in others) / len(others)
    centroid_lon = sum(point.lon for point in others) / len(others)
    longitude_scale = cos(radians(centroid_lat))

    def angle(point: Coordinate) -> float:
        return atan2(
            point.lat - centroid_lat,
            (point.lon - centroid_lon) * longitude_scale,
        )

    reference = angle(points[0])

    def sweep_key(index: int) -> tuple[float, int]:
        delta = angle(points[index]) - reference
        sweep = (-delta if clockwise else delta) % (2 * pi)
        return (sweep, index)

    return (0, *sorted(range(1, len(points)), key=sweep_key))


def nearest_neighbor_order(points: tuple[Coordinate, ...]) -> PointOrder:
    """Visit the nearest unvisited point, breaking equal distances by input index."""
    if len(points) < 2:
        raise ValueError("point ordering requires at least two mandatory points")
    remaining = set(range(1, len(points)))
    order = [0]
    while remaining:
        current = points[order[-1]]
        next_index = min(
            remaining,
            key=lambda index: (
                haversine_distance_m(
                    (current.lon, current.lat),
                    (points[index].lon, points[index].lat),
                ),
                index,
            ),
        )
        order.append(next_index)
        remaining.remove(next_index)
    return tuple(order)


def cycle_distance_m(points: tuple[Coordinate, ...], order: PointOrder) -> float:
    validate_point_order(order, len(points))
    closed = (*order, order[0])
    return sum(
        haversine_distance_m(
            (points[left].lon, points[left].lat),
            (points[right].lon, points[right].lat),
        )
        for left, right in zip(closed, closed[1:], strict=False)
    )


def two_opt_refine(points: tuple[Coordinate, ...], order: PointOrder) -> PointOrder:
    """Apply bounded deterministic best-improvement 2-opt with a fixed start."""
    validate_point_order(order, len(points))
    best = order
    best_distance = cycle_distance_m(points, best)
    for _pass in range(MAX_TWO_OPT_PASSES):
        alternatives: list[tuple[float, PointOrder]] = []
        for start in range(1, len(best) - 1):
            for end in range(start + 1, len(best)):
                proposal = (
                    *best[:start],
                    *reversed(best[start : end + 1]),
                    *best[end + 1 :],
                )
                distance = cycle_distance_m(points, proposal)
                if distance < best_distance - 1e-6:
                    alternatives.append((distance, proposal))
        if not alternatives:
            break
        best_distance, best = min(alternatives, key=lambda item: (item[0], item[1]))
    return best


def _rotations(order: PointOrder) -> tuple[PointOrder, ...]:
    tail = order[1:]
    if len(tail) < 3:
        return ()
    cuts = sorted({len(tail) // 4, len(tail) // 2, (3 * len(tail)) // 4})
    return tuple((0, *tail[cut:], *tail[:cut]) for cut in cuts if 0 < cut < len(tail))


def generate_order_proposals(
    points: tuple[Coordinate, ...],
    *,
    limit: int = MAX_ORDER_PROPOSALS,
) -> tuple[PointOrder, ...]:
    """Return a bounded, unique sequence of deterministic geometric cycles."""
    if limit < 1 or limit > MAX_ORDER_PROPOSALS:
        raise ValueError(
            f"order proposal limit must be between 1 and {MAX_ORDER_PROPOSALS}"
        )
    original = tuple(range(len(points)))
    validate_point_order(original, len(points))
    clockwise = polar_angle_order(points, clockwise=True)
    counter_clockwise = polar_angle_order(points, clockwise=False)
    nearest = nearest_neighbor_order(points)
    reversed_nearest = (0, *reversed(nearest[1:]))

    proposals: list[PointOrder] = []
    seen: set[PointOrder] = set()

    def add(order: PointOrder) -> None:
        validate_point_order(order, len(points))
        if order not in seen and len(proposals) < limit:
            seen.add(order)
            proposals.append(order)

    bases = (original, clockwise, counter_clockwise, nearest, reversed_nearest)
    for proposal in bases:
        add(proposal)
    for angular in (clockwise, counter_clockwise):
        for proposal in _rotations(angular):
            add(proposal)
    for proposal in bases:
        add(two_opt_refine(points, proposal))
    return tuple(proposals)
