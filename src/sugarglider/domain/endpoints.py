"""Shared route-topology resolution and hard-endpoint accounting."""

from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt
from typing import Literal

from pydantic import Field
from pydantic_core import PydanticCustomError

from sugarglider.domain.models import Coordinate, GeoJsonPosition, ImmutableModel

type RouteTopology = Literal["auto", "loop", "point_to_point"]
type ResolvedRouteTopology = Literal["loop", "point_to_point"]
type EndpointSource = Literal[
    "explicit",
    "inferred_from_waypoint",
    "inferred_from_requested_place",
    "inferred_from_hard_point",
    "loop_closure",
]
EARTH_RADIUS_M = 6_371_008.8


class EndpointSnapTooFarError(ValueError):
    """GraphHopper snapped a hard endpoint outside the configured maximum."""


def _distance_m(left: GeoJsonPosition, right: GeoJsonPosition) -> float:
    lon1, lat1 = left
    lon2, lat2 = right
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    value = (
        sin(delta_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * atan2(sqrt(value), sqrt(max(0.0, 1 - value)))


class ResolvedEndpoints(ImmutableModel):
    """Effective immutable route endpoints and their public provenance."""

    topology: ResolvedRouteTopology
    start: Coordinate
    end: Coordinate
    start_source: EndpointSource
    end_source: EndpointSource
    start_input_index: int | None = Field(default=None, ge=0)
    end_input_index: int | None = Field(default=None, ge=0)


class EndpointVisit(ImmutableModel):
    """Measured GraphHopper snapping for one requested hard endpoint."""

    requested_coordinate: Coordinate
    snapped_coordinate: GeoJsonPosition | None
    snap_distance_m: float | None = Field(default=None, ge=0)
    source: EndpointSource
    satisfied: bool


@dataclass(frozen=True)
class EndpointSelection:
    """Resolved public endpoints plus input values consumed as endpoints."""

    resolved: ResolvedEndpoints
    consumed_point_indices: frozenset[int] = frozenset()
    consumed_requested_indices: frozenset[int] = frozenset()
    consumed_hard_point_indices: frozenset[int] = frozenset()


def same_coordinate(left: Coordinate, right: Coordinate) -> bool:
    """Compare endpoint identity using exact WGS84 input coordinates."""
    return (left.lat, left.lon) == (right.lat, right.lon)


def endpoint_error(code: str, message: str) -> PydanticCustomError:
    """Create a stable validation error suitable for the public API."""
    return PydanticCustomError(code, message)


def _resolved_topology(
    requested: RouteTopology,
    *,
    start: Coordinate | None,
    end: Coordinate | None,
) -> ResolvedRouteTopology:
    if requested != "auto":
        return requested
    if start is not None and end is not None and not same_coordinate(start, end):
        return "point_to_point"
    return "loop"


def resolve_waypoint_endpoints(
    *,
    start: Coordinate | None,
    end: Coordinate | None,
    points: tuple[Coordinate, ...],
    route_topology: RouteTopology,
) -> EndpointSelection:
    """Resolve Waypoint Route endpoints without changing caller-owned points."""
    effective_start = start
    start_source: EndpointSource = "explicit"
    start_index: int | None = None
    consumed: set[int] = set()
    if effective_start is None:
        if not points:
            raise endpoint_error(
                "endpoint_start_unresolved", "A hard start could not be resolved."
            )
        effective_start = points[0]
        start_source = "inferred_from_waypoint"
        start_index = 0
        consumed.add(0)

    topology = _resolved_topology(route_topology, start=effective_start, end=end)
    effective_end: Coordinate | None
    if topology == "loop":
        if end is not None and not same_coordinate(effective_start, end):
            raise endpoint_error(
                "distinct_end_not_allowed_for_loop",
                "A loop cannot have a hard end distinct from its hard start.",
            )
        effective_end = effective_start
        end_source: EndpointSource = "loop_closure"
        end_index: int | None = start_index
    else:
        effective_end = end
        end_source = "explicit"
        end_index = None
        if effective_end is None:
            for index in range(len(points) - 1, -1, -1):
                if index not in consumed and not same_coordinate(
                    points[index], effective_start
                ):
                    effective_end = points[index]
                    end_source = "inferred_from_waypoint"
                    end_index = index
                    consumed.add(index)
                    break
        if effective_end is None:
            raise endpoint_error(
                "endpoint_end_unresolved", "A hard end could not be resolved."
            )
        if same_coordinate(effective_start, effective_end):
            raise endpoint_error(
                "endpoint_coordinates_equal_for_point_to_point",
                "Point-to-point start and end coordinates must be distinct.",
            )

    assert effective_end is not None
    return EndpointSelection(
        resolved=ResolvedEndpoints(
            topology=topology,
            start=effective_start,
            end=effective_end,
            start_source=start_source,
            end_source=end_source,
            start_input_index=start_index,
            end_input_index=end_index,
        ),
        consumed_point_indices=frozenset(consumed),
    )


def resolve_auto_tour_endpoints(
    *,
    start: Coordinate | None,
    end: Coordinate | None,
    requested_places: tuple[tuple[Coordinate, int | None], ...],
    hard_points: tuple[Coordinate, ...],
    route_topology: RouteTopology,
) -> EndpointSelection:
    """Resolve Auto Tour endpoints with one shared deterministic precedence."""
    consumed_requested: set[int] = set()
    consumed_hard: set[int] = set()
    effective_start = start
    start_source: EndpointSource = "explicit"
    start_index: int | None = None
    if effective_start is None and requested_places:
        request_index = min(
            range(len(requested_places)),
            key=lambda index: (
                requested_places[index][1]
                if requested_places[index][1] is not None
                else index,
                index,
            ),
        )
        effective_start = requested_places[request_index][0]
        start_source = "inferred_from_requested_place"
        start_index = requested_places[request_index][1]
        consumed_requested.add(request_index)
    if effective_start is None and hard_points:
        effective_start = hard_points[0]
        start_source = "inferred_from_hard_point"
        start_index = 0
        consumed_hard.add(0)
    if effective_start is None:
        raise endpoint_error(
            "endpoint_start_unresolved",
            "An Auto Tour hard start could not be resolved.",
        )

    topology = _resolved_topology(route_topology, start=effective_start, end=end)
    effective_end: Coordinate | None
    if topology == "loop":
        if end is not None and not same_coordinate(effective_start, end):
            raise endpoint_error(
                "distinct_end_not_allowed_for_loop",
                "A loop cannot have a hard end distinct from its hard start.",
            )
        effective_end = effective_start
        end_source: EndpointSource = "loop_closure"
        end_index: int | None = start_index
    else:
        effective_end = end
        end_source = "explicit"
        end_index = None
        if effective_end is None and requested_places:
            ordered = sorted(
                range(len(requested_places)),
                key=lambda index: (
                    requested_places[index][1]
                    if requested_places[index][1] is not None
                    else index,
                    index,
                ),
                reverse=True,
            )
            for request_index in ordered:
                coordinate, original_index = requested_places[request_index]
                if request_index not in consumed_requested and not same_coordinate(
                    coordinate, effective_start
                ):
                    effective_end = coordinate
                    end_source = "inferred_from_requested_place"
                    end_index = original_index
                    consumed_requested.add(request_index)
                    break
        if effective_end is None:
            for hard_index in range(len(hard_points) - 1, -1, -1):
                coordinate = hard_points[hard_index]
                if hard_index not in consumed_hard and not same_coordinate(
                    coordinate, effective_start
                ):
                    effective_end = coordinate
                    end_source = "inferred_from_hard_point"
                    end_index = hard_index
                    consumed_hard.add(hard_index)
                    break
        if effective_end is None:
            raise endpoint_error(
                "endpoint_end_unresolved",
                "An Auto Tour hard end could not be resolved.",
            )
        if same_coordinate(effective_start, effective_end):
            raise endpoint_error(
                "endpoint_coordinates_equal_for_point_to_point",
                "Point-to-point start and end coordinates must be distinct.",
            )

    assert effective_end is not None
    return EndpointSelection(
        resolved=ResolvedEndpoints(
            topology=topology,
            start=effective_start,
            end=effective_end,
            start_source=start_source,
            end_source=end_source,
            start_input_index=start_index,
            end_input_index=end_index,
        ),
        consumed_requested_indices=frozenset(consumed_requested),
        consumed_hard_point_indices=frozenset(consumed_hard),
    )


def routing_sequence(
    resolved: ResolvedEndpoints, interior: tuple[Coordinate, ...]
) -> tuple[Coordinate, ...]:
    """Build the exact GraphHopper sequence for the resolved topology."""
    points = (resolved.start, *interior, resolved.end)
    for previous, current in zip(points, points[1:], strict=False):
        if same_coordinate(previous, current):
            if len(points) == 2 and resolved.topology == "loop":
                continue
            raise endpoint_error(
                "adjacent_duplicate_routing_points",
                "Adjacent routing points must have distinct coordinates.",
            )
    return points


def endpoint_visits(
    resolved: ResolvedEndpoints,
    snapped_points: tuple[GeoJsonPosition, ...] | None,
    *,
    maximum_snap_distance_m: float,
) -> tuple[tuple[EndpointVisit, EndpointVisit], tuple[str, ...]]:
    """Measure both routed endpoints without guessing missing snapped data."""
    first = snapped_points[0] if snapped_points else None
    last = snapped_points[-1] if snapped_points else None
    start_distance = (
        _distance_m((resolved.start.lon, resolved.start.lat), first)
        if first is not None
        else None
    )
    end_distance = (
        _distance_m((resolved.end.lon, resolved.end.lat), last)
        if last is not None
        else None
    )
    visits = (
        EndpointVisit(
            requested_coordinate=resolved.start,
            snapped_coordinate=first,
            snap_distance_m=start_distance,
            source=resolved.start_source,
            satisfied=(
                start_distance is not None and start_distance <= maximum_snap_distance_m
            ),
        ),
        EndpointVisit(
            requested_coordinate=resolved.end,
            snapped_coordinate=last,
            snap_distance_m=end_distance,
            source=resolved.end_source,
            satisfied=(
                end_distance is not None and end_distance <= maximum_snap_distance_m
            ),
        ),
    )
    warnings = tuple(
        code
        for visit, code in zip(
            visits,
            ("endpoint_start_snap_too_far", "endpoint_end_snap_too_far"),
            strict=True,
        )
        if not visit.satisfied
    )
    return visits, warnings


def validated_endpoint_visits(
    resolved: ResolvedEndpoints,
    snapped_points: tuple[GeoJsonPosition, ...] | None,
    *,
    maximum_snap_distance_m: float,
) -> tuple[tuple[EndpointVisit, EndpointVisit], tuple[str, ...]]:
    """Return endpoint accounting or reject an unsatisfied hard endpoint."""
    visits, warnings = endpoint_visits(
        resolved,
        snapped_points,
        maximum_snap_distance_m=maximum_snap_distance_m,
    )
    if warnings:
        raise EndpointSnapTooFarError
    return visits, warnings
