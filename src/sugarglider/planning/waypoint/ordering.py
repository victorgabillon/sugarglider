"""Pure deterministic required-waypoint ordering proposals for closed loops."""

from math import atan2, cos, pi, radians

from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.models import Coordinate
from sugarglider.planning.models import WaypointPlanRequest
from sugarglider.planning.waypoint.models import (
    OrderingProposalStats,
    WaypointSequenceProposal,
)

MAX_ORDER_PROPOSALS = 16
MAX_TWO_OPT_PASSES = 4
MAX_RELOCATE_PASSES = 3

type PointOrder = tuple[int, ...]


def ordering_proposals(
    request: WaypointPlanRequest, *, limit: int
) -> tuple[tuple[WaypointSequenceProposal, ...], OrderingProposalStats]:
    """Return immutable endpoint-safe canonical proposals after the control."""
    if request.waypoint_order == "fixed":
        return (), OrderingProposalStats(0, 0, 0)
    interior = tuple(
        waypoint.coordinate.model_copy(update={"name": waypoint.name})
        for waypoint in request.waypoints
    )
    if request.topology == "loop":
        mandatory = (request.start, *interior)
        orders = generate_order_proposals(mandatory, limit=limit)[1:]
        proposals = tuple(
            _ordered_proposal(
                request, ordered_closed_points(mandatory, order), (*order, 0)
            )
            for order in orders
        )
    else:
        assert request.end is not None
        mandatory = (request.start, *interior, request.end)
        orders = generate_path_order_proposals(mandatory, limit=limit)[1:]
        proposals = tuple(
            _ordered_proposal(request, ordered_open_points(mandatory, order), order)
            for order in orders
        )
    return proposals, OrderingProposalStats(
        generated=len(proposals),
        deduplicated=0,
        rejected_before_routing=0,
    )


def _ordered_proposal(
    request: WaypointPlanRequest,
    routing_points: tuple[Coordinate, ...],
    routed_original_indices: tuple[int, ...],
) -> WaypointSequenceProposal:
    last_original = len(request.waypoints) + 1

    def is_exact(original_index: int) -> bool:
        return (
            original_index == 0
            or (
                request.topology == "point_to_point" and original_index == last_original
            )
            or (
                1 <= original_index <= len(request.waypoints)
                and request.waypoints[original_index - 1].constraint_strength == "exact"
            )
        )

    exact_positions = tuple(
        position
        for position, original_index in enumerate(routed_original_indices)
        if is_exact(original_index)
    )

    def exact_id(original_index: int) -> str:
        if original_index == 0:
            return "start"
        if request.topology == "point_to_point" and original_index == last_original:
            return "end"
        return request.waypoints[original_index - 1].id

    return WaypointSequenceProposal(
        routing_points=routing_points,
        exact_points=tuple(routing_points[position] for position in exact_positions),
        exact_point_positions=exact_positions,
        original_indices=tuple(
            routed_original_indices[position] for position in exact_positions
        ),
        exact_point_ids=tuple(
            exact_id(routed_original_indices[position]) for position in exact_positions
        ),
        topology=request.topology,
        construction="optimized_order",
        order_provenance=(
            "bounded_loop_heuristic"
            if request.topology == "loop"
            else "bounded_open_heuristic"
        ),
    )


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


def nearest_insertion_order(points: tuple[Coordinate, ...]) -> PointOrder:
    """Build a bounded cycle by cheapest insertion with stable index ties."""
    if len(points) < 2:
        raise ValueError("point ordering requires at least two mandatory points")
    first = min(
        range(1, len(points)),
        key=lambda index: (_distance(points[0], points[index]), index),
    )
    order = [0, first]
    remaining = set(range(1, len(points))) - {first}
    while remaining:
        _, point_index, insertion = min(
            (
                _distance(points[left], points[point_index])
                + _distance(points[point_index], points[right])
                - _distance(points[left], points[right]),
                point_index,
                position + 1,
            )
            for point_index in remaining
            for position, (left, right) in enumerate(
                zip(order, (*order[1:], order[0]), strict=True)
            )
        )
        order.insert(insertion, point_index)
        remaining.remove(point_index)
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


def relocate_refine(points: tuple[Coordinate, ...], order: PointOrder) -> PointOrder:
    """Apply bounded best-improvement relocation without moving the start."""
    validate_point_order(order, len(points))
    best = order
    for _pass in range(MAX_RELOCATE_PASSES):
        alternatives: list[tuple[float, PointOrder]] = []
        baseline = cycle_distance_m(points, best)
        for source in range(1, len(best)):
            removed = (*best[:source], *best[source + 1 :])
            for destination in range(1, len(removed) + 1):
                proposal = (
                    *removed[:destination],
                    best[source],
                    *removed[destination:],
                )
                distance = cycle_distance_m(points, proposal)
                if distance < baseline - 1e-6:
                    alternatives.append((distance, proposal))
        if not alternatives:
            break
        _, best = min(alternatives, key=lambda value: (value[0], value[1]))
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
    inserted = nearest_insertion_order(points)
    reversed_nearest = (0, *reversed(nearest[1:]))

    proposals: list[PointOrder] = []
    seen: set[PointOrder] = set()

    def add(order: PointOrder) -> None:
        validate_point_order(order, len(points))
        if order not in seen and len(proposals) < limit:
            seen.add(order)
            proposals.append(order)

    bases = (
        original,
        clockwise,
        counter_clockwise,
        nearest,
        inserted,
        reversed_nearest,
    )
    for proposal in bases:
        add(proposal)
    for angular in (clockwise, counter_clockwise):
        for proposal in _rotations(angular):
            add(proposal)
    for proposal in bases:
        add(two_opt_refine(points, proposal))
        add(relocate_refine(points, proposal))
    return tuple(proposals)


def ordered_open_points(
    points: tuple[Coordinate, ...], order: PointOrder
) -> tuple[Coordinate, ...]:
    """Apply an endpoint-fixed order to an open mandatory-point sequence."""
    validate_path_order(order, len(points))
    return tuple(points[index] for index in order)


def validate_path_order(order: PointOrder, point_count: int) -> None:
    """Reject open orders that move either endpoint or lose interior points."""
    if point_count < 2:
        raise ValueError("open point ordering requires two endpoints")
    if len(order) != point_count or set(order) != set(range(point_count)):
        raise ValueError("path order must contain every original index exactly once")
    if order[0] != 0 or order[-1] != point_count - 1:
        raise ValueError("path order must keep both endpoints fixed")


def path_distance_m(points: tuple[Coordinate, ...], order: PointOrder) -> float:
    validate_path_order(order, len(points))
    return sum(
        haversine_distance_m(
            (points[left].lon, points[left].lat),
            (points[right].lon, points[right].lat),
        )
        for left, right in zip(order, order[1:], strict=False)
    )


def generate_path_order_proposals(
    points: tuple[Coordinate, ...], *, limit: int = MAX_ORDER_PROPOSALS
) -> tuple[PointOrder, ...]:
    """Return bounded deterministic endpoint-fixed open-path permutations."""
    if not 1 <= limit <= MAX_ORDER_PROPOSALS:
        raise ValueError(
            f"order proposal limit must be between 1 and {MAX_ORDER_PROPOSALS}"
        )
    original = tuple(range(len(points)))
    validate_path_order(original, len(points))
    if len(points) <= 3:
        return (original,)
    proposals: list[PointOrder] = [original]
    seen = {original}

    def add(order: PointOrder) -> None:
        validate_path_order(order, len(points))
        if order not in seen and len(proposals) < limit:
            seen.add(order)
            proposals.append(order)

    # Greedy progress from the fixed start, always reserving the fixed end.
    remaining = set(range(1, len(points) - 1))
    nearest: list[int] = [0]
    while remaining:
        current = points[nearest[-1]]
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
        nearest.append(next_index)
        remaining.remove(next_index)
    nearest.append(len(points) - 1)
    add(tuple(nearest))
    add(_direct_progress_order(points))
    add((0, *reversed(range(1, len(points) - 1)), len(points) - 1))

    best = min(proposals, key=lambda order: (path_distance_m(points, order), order))
    for _pass in range(MAX_TWO_OPT_PASSES):
        improvements: list[tuple[float, PointOrder]] = []
        for start in range(1, len(best) - 2):
            for end in range(start + 1, len(best) - 1):
                proposal = (
                    *best[:start],
                    *reversed(best[start : end + 1]),
                    *best[end + 1 :],
                )
                distance = path_distance_m(points, proposal)
                if distance < path_distance_m(points, best) - 1e-6:
                    improvements.append((distance, proposal))
                add(proposal)
        if not improvements:
            break
        _, best = min(improvements, key=lambda item: (item[0], item[1]))
    return tuple(proposals)


def _direct_progress_order(points: tuple[Coordinate, ...]) -> PointOrder:
    """Order interiors by stable progress along the fixed endpoint axis."""
    start = points[0]
    end = points[-1]
    axis_lon = end.lon - start.lon
    axis_lat = end.lat - start.lat
    denominator = axis_lon * axis_lon + axis_lat * axis_lat

    def key(index: int) -> tuple[float, int]:
        point = points[index]
        progress = (
            (point.lon - start.lon) * axis_lon + (point.lat - start.lat) * axis_lat
        ) / denominator
        return progress, index

    return (0, *sorted(range(1, len(points) - 1), key=key), len(points) - 1)


def _distance(left: Coordinate, right: Coordinate) -> float:
    return haversine_distance_m((left.lon, left.lat), (right.lon, right.lat))
