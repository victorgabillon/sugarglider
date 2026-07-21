"""Deterministic requested-stop measurement and routed insertion."""

from dataclasses import dataclass
from math import atan2

from shapely.geometry import LineString, Point

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.models import Coordinate, GeoJsonPosition
from sugarglider.planning.auto_tour.models import (
    PoiDropReason,
    RequestedPlaceFailureReason,
    RequestedTourPlace,
    RequestedTourPlaceVisit,
)


@dataclass(frozen=True)
class RequestedPlaceOpportunity:
    original_index: int
    place: RequestedTourPlace
    insertion_index: int
    route_progress_share: float
    measured_distance_m: float


def requested_place_order_proposals(
    *,
    start: Coordinate,
    end: Coordinate,
    indexed_places: tuple[tuple[int, RequestedTourPlace], ...],
    topology: str,
    direct_geometry: tuple[GeoJsonPosition, ...] = (),
) -> tuple[tuple[int, ...], ...]:
    """Build deterministic bounded order families; GraphHopper evaluates each one."""
    if not indexed_places:
        return ()
    indices = tuple(index for index, _place in indexed_places)
    coordinates = {index: place.routing_coordinate for index, place in indexed_places}
    spatial: list[tuple[int, ...]] = []
    if topology == "loop":
        center_lat = sum(point.lat for point in coordinates.values()) / len(coordinates)
        center_lon = sum(point.lon for point in coordinates.values()) / len(coordinates)
        angular = tuple(
            index
            for index, _place in sorted(
                indexed_places,
                key=lambda value: (
                    atan2(
                        value[1].routing_coordinate.lat - center_lat,
                        value[1].routing_coordinate.lon - center_lon,
                    ),
                    value[0],
                ),
            )
        )
        spatial.extend((angular, tuple(reversed(angular))))
    elif direct_geometry:
        projection = LocalMetricProjection(direct_geometry[0][1])
        line = projection.project_line(direct_geometry)
        spatial.append(
            tuple(
                index
                for index, _place in sorted(
                    indexed_places,
                    key=lambda value: (
                        line.project(
                            Point(
                                projection.project_position(
                                    (
                                        value[1].routing_coordinate.lon,
                                        value[1].routing_coordinate.lat,
                                    )
                                )
                            )
                        ),
                        value[0],
                    ),
                )
            )
        )
    cheapest = _cheapest_insertion_order(start, end, indices, coordinates)
    proposals = [
        cheapest,
        _bounded_relocate(start, end, cheapest, coordinates),
        _bounded_two_opt(start, end, cheapest, coordinates),
        indices,
        *spatial,
    ]
    return tuple(dict.fromkeys(proposals))


def _sequence_cost(
    start: Coordinate,
    end: Coordinate,
    order: tuple[int, ...],
    coordinates: dict[int, Coordinate],
) -> float:
    points = (start, *(coordinates[index] for index in order), end)
    return sum(
        haversine_distance_m((left.lon, left.lat), (right.lon, right.lat))
        for left, right in zip(points, points[1:], strict=False)
    )


def _cheapest_insertion_order(
    start: Coordinate,
    end: Coordinate,
    indices: tuple[int, ...],
    coordinates: dict[int, Coordinate],
) -> tuple[int, ...]:
    order: tuple[int, ...] = ()
    for requested_index in indices:
        order = min(
            (
                (*order[:position], requested_index, *order[position:])
                for position in range(len(order) + 1)
            ),
            key=lambda candidate: (
                _sequence_cost(start, end, candidate, coordinates),
                candidate,
            ),
        )
    return order


def _bounded_two_opt(
    start: Coordinate,
    end: Coordinate,
    initial: tuple[int, ...],
    coordinates: dict[int, Coordinate],
) -> tuple[int, ...]:
    best = initial
    best_cost = _sequence_cost(start, end, best, coordinates)
    for _pass in range(2):
        improved = False
        for left in range(len(best) - 1):
            for right in range(left + 2, len(best) + 1):
                candidate = (*best[:left], *reversed(best[left:right]), *best[right:])
                cost = _sequence_cost(start, end, candidate, coordinates)
                if (cost, candidate) < (best_cost - 1e-6, best):
                    best = candidate
                    best_cost = cost
                    improved = True
        if not improved:
            break
    return best


def _bounded_relocate(
    start: Coordinate,
    end: Coordinate,
    initial: tuple[int, ...],
    coordinates: dict[int, Coordinate],
) -> tuple[int, ...]:
    """Run two deterministic fixed-endpoint relocate passes."""
    best = initial
    best_cost = _sequence_cost(start, end, best, coordinates)
    for _pass in range(2):
        improved = False
        for source in range(len(best)):
            value = best[source]
            remaining = (*best[:source], *best[source + 1 :])
            for destination in range(len(remaining) + 1):
                candidate = (
                    *remaining[:destination],
                    value,
                    *remaining[destination:],
                )
                cost = _sequence_cost(start, end, candidate, coordinates)
                if (cost, candidate) < (best_cost - 1e-6, best):
                    best = candidate
                    best_cost = cost
                    improved = True
        if not improved:
            break
    return best


def measure_requested_place_visits(
    *,
    route_geometry: tuple[GeoJsonPosition, ...],
    requested_stops: tuple[RequestedTourPlace, ...],
    deliberately_routed_indices: frozenset[int] = frozenset(),
    routing_points: tuple[Coordinate, ...] = (),
    snapped_routing_points: tuple[GeoJsonPosition, ...] | None = None,
    failure_reasons: dict[int, RequestedPlaceFailureReason] | None = None,
) -> tuple[RequestedTourPlaceVisit, ...]:
    """Measure every requested place against final graph-routed geometry."""
    if not requested_stops:
        return ()
    projection = LocalMetricProjection(route_geometry[0][1])
    line = projection.project_line(route_geometry)
    visits: list[RequestedTourPlaceVisit] = []
    for index, place in enumerate(requested_stops):
        approach = place.chosen_approach
        target = approach.coordinate if approach is not None else place.coordinate
        point = Point(projection.project_position((target.lon, target.lat)))
        measured = float(line.distance(point))
        progress = float(line.project(point) / line.length) if line.length > 0 else 0.0
        deliberate = index in deliberately_routed_indices
        graph_snap_distance: float | None = None
        if deliberate and snapped_routing_points is not None:
            point_index = next(
                (
                    point_index
                    for point_index, routing_point in enumerate(routing_points)
                    if (routing_point.lat, routing_point.lon)
                    == (target.lat, target.lon)
                ),
                None,
            )
            if point_index is not None and point_index < len(snapped_routing_points):
                graph_snap_distance = haversine_distance_m(
                    (target.lon, target.lat),
                    snapped_routing_points[point_index],
                )
        arrived = approach is not None and measured <= approach.arrival_tolerance_m
        if (
            arrived
            and approach is not None
            and approach.kind == "strict_graph_snap"
            and deliberate
        ):
            arrived = graph_snap_distance is not None and graph_snap_distance <= 25.0
        prior_failure = (failure_reasons or {}).get(index)
        drop_reason: PoiDropReason | None
        if arrived:
            drop_reason = None
        elif approach is None:
            drop_reason = (
                place.approach_resolution_drop_reason or "no_meaningful_approach"
            )
        elif (
            approach.kind == "strict_graph_snap"
            and deliberate
            and graph_snap_distance is not None
            and graph_snap_distance > 25.0
        ):
            drop_reason = "approach_snap_too_far"
        elif prior_failure in {
            "requested_place_graph_unreachable",
            "requested_place_snap_too_far",
        }:
            drop_reason = (
                "graph_unreachable"
                if prior_failure == "requested_place_graph_unreachable"
                else "approach_snap_too_far"
            )
        elif prior_failure in {
            "requested_place_route_budget_exhausted",
            "requested_place_search_budget_exhausted",
        }:
            drop_reason = "search_budget_exhausted"
        elif prior_failure == "requested_place_safety_rejected":
            drop_reason = "route_safety_rejected"
        elif prior_failure in {
            "requested_place_distance_ceiling_rejected",
            "requested_place_user_maximum_rejected",
            "requested_place_server_maximum_rejected",
        }:
            drop_reason = "maximum_distance_rejected"
        elif prior_failure == "requested_place_lower_utility_subset" or not deliberate:
            drop_reason = "lower_utility_candidate"
        else:
            drop_reason = "arrival_tolerance_not_met"
        measured_approach = (
            approach.model_copy(update={"graph_snap_distance_m": graph_snap_distance})
            if approach is not None and graph_snap_distance is not None
            else approach
        )
        visits.append(
            RequestedTourPlaceVisit(
                requested_place=place,
                measured_distance_m=measured,
                closest_route_distance_m=measured,
                chosen_approach=measured_approach,
                arrival_tolerance_m=(
                    approach.arrival_tolerance_m
                    if approach is not None
                    else place.arrival_tolerance_m
                ),
                route_progress_share=min(1.0, max(0.0, progress)),
                decision="selected" if arrived else "dropped",
                deliberately_routed=deliberate,
                deliberately_considered=True,
                graph_snap_distance_m=graph_snap_distance,
                selection_reason=(
                    "requested_must_visit"
                    if arrived and place.importance == "must_visit"
                    else "requested_preferred"
                    if arrived and deliberate
                    else "already_on_route"
                    if arrived
                    else None
                ),
                drop_reason=drop_reason,
            )
        )
    return tuple(visits)


def requested_place_opportunities(
    *,
    route_geometry: tuple[GeoJsonPosition, ...],
    routing_points: tuple[Coordinate, ...],
    requested_stops: tuple[RequestedTourPlace, ...],
) -> tuple[RequestedPlaceOpportunity, ...]:
    """Return all dropped requested places, independent of the OSM POI corridor."""
    if len(routing_points) < 2 or not requested_stops:
        return ()
    projection = LocalMetricProjection(route_geometry[0][1])
    line = projection.project_line(route_geometry)
    routing_progress = _routing_progress(line, projection, routing_points)
    values: list[RequestedPlaceOpportunity] = []
    for original_index, place in enumerate(requested_stops):
        target = place.routing_coordinate
        point = Point(projection.project_position((target.lon, target.lat)))
        measured = float(line.distance(point))
        tolerance = (
            place.chosen_approach.arrival_tolerance_m
            if place.chosen_approach is not None
            else place.arrival_tolerance_m
        )
        if measured <= tolerance:
            continue
        progress = float(line.project(point) / line.length) if line.length > 0 else 0.0
        insertion_index = next(
            (
                index
                for index in range(1, len(routing_progress))
                if progress <= routing_progress[index]
            ),
            len(routing_points) - 1,
        )
        values.append(
            RequestedPlaceOpportunity(
                original_index=original_index,
                place=place,
                insertion_index=insertion_index,
                route_progress_share=min(1.0, max(0.0, progress)),
                measured_distance_m=measured,
            )
        )
    return tuple(
        sorted(
            values,
            key=lambda value: (
                value.route_progress_share,
                0 if value.place.importance == "must_visit" else 1,
                value.place.original_index
                if value.place.original_index is not None
                else value.original_index,
                value.place.name.casefold(),
            ),
        )
    )


def insert_requested_place_opportunities(
    routing_points: tuple[Coordinate, ...],
    opportunities: tuple[RequestedPlaceOpportunity, ...],
) -> tuple[Coordinate, ...]:
    """Insert a progress-ordered opportunity set without changing loop endpoints."""
    grouped: dict[int, list[RequestedPlaceOpportunity]] = {}
    for opportunity in opportunities:
        grouped.setdefault(opportunity.insertion_index, []).append(opportunity)
    output: list[Coordinate] = [routing_points[0]]
    for insertion_index in range(1, len(routing_points)):
        output.extend(
            opportunity.place.routing_coordinate
            for opportunity in grouped.get(insertion_index, ())
        )
        output.append(routing_points[insertion_index])
    return tuple(output)


def insert_coordinate_after(
    routing_points: tuple[Coordinate, ...],
    *,
    after: Coordinate,
    coordinate: Coordinate,
) -> tuple[Coordinate, ...] | None:
    """Insert a continuation immediately after a stable routing point."""
    for index in range(1, len(routing_points) - 1):
        point = routing_points[index]
        if (point.lat, point.lon) == (after.lat, after.lon):
            return (
                *routing_points[: index + 1],
                coordinate,
                *routing_points[index + 1 :],
            )
    return None


def _routing_progress(
    line: LineString,
    projection: LocalMetricProjection,
    routing_points: tuple[Coordinate, ...],
) -> tuple[float, ...]:
    progress: list[float] = []
    previous = 0.0
    for index, point in enumerate(routing_points):
        if index == len(routing_points) - 1 and (
            point.lat,
            point.lon,
        ) == (routing_points[0].lat, routing_points[0].lon):
            value = 1.0
        else:
            metric = Point(projection.project_position((point.lon, point.lat)))
            value = (
                float(line.project(metric) / line.length) if line.length > 0 else 0.0
            )
        previous = max(previous, value)
        progress.append(previous)
    return tuple(progress)
