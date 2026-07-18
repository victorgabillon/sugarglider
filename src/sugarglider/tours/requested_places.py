"""Deterministic close-enough requested-place measurement and route insertion."""

from dataclasses import dataclass

from shapely.geometry import LineString, Point

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.domain.models import Coordinate, GeoJsonPosition
from sugarglider.tours.models import (
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


def measure_requested_place_visits(
    *,
    route_geometry: tuple[GeoJsonPosition, ...],
    requested_places: tuple[RequestedTourPlace, ...],
    deliberately_routed_indices: frozenset[int] = frozenset(),
) -> tuple[RequestedTourPlaceVisit, ...]:
    """Measure every requested place against final graph-routed geometry."""
    if not requested_places:
        return ()
    projection = LocalMetricProjection(route_geometry[0][1])
    line = projection.project_line(route_geometry)
    visits: list[RequestedTourPlaceVisit] = []
    for index, place in enumerate(requested_places):
        point = Point(
            projection.project_position((place.coordinate.lon, place.coordinate.lat))
        )
        measured = float(line.distance(point))
        progress = float(line.project(point) / line.length) if line.length > 0 else 0.0
        deliberate = index in deliberately_routed_indices
        satisfied = measured <= place.visit_radius_m
        visits.append(
            RequestedTourPlaceVisit(
                requested_place=place,
                measured_distance_m=measured,
                route_progress_share=min(1.0, max(0.0, progress)),
                satisfied=satisfied,
                deliberately_routed=deliberate,
                reason=(
                    "deliberately_routed_close_enough"
                    if satisfied and deliberate
                    else "already_on_route"
                    if satisfied
                    else "snapped_outside_visit_radius"
                    if deliberate
                    else "not_reached"
                ),
            )
        )
    return tuple(visits)


def requested_place_opportunities(
    *,
    route_geometry: tuple[GeoJsonPosition, ...],
    routing_points: tuple[Coordinate, ...],
    requested_places: tuple[RequestedTourPlace, ...],
) -> tuple[RequestedPlaceOpportunity, ...]:
    """Return all missed requested places, independent of the OSM POI corridor."""
    if len(routing_points) < 2 or not requested_places:
        return ()
    projection = LocalMetricProjection(route_geometry[0][1])
    line = projection.project_line(route_geometry)
    routing_progress = _routing_progress(line, projection, routing_points)
    values: list[RequestedPlaceOpportunity] = []
    for original_index, place in enumerate(requested_places):
        point = Point(
            projection.project_position((place.coordinate.lon, place.coordinate.lat))
        )
        measured = float(line.distance(point))
        if measured <= place.visit_radius_m:
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
            opportunity.place.coordinate
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
