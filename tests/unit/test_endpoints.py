"""Shared endpoint-resolution matrix for loop and point-to-point requests."""

from sugarglider.domain.endpoints import (
    resolve_auto_tour_endpoints,
    resolve_waypoint_endpoints,
    routing_sequence,
)
from sugarglider.domain.models import Coordinate
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
    RequestedTourPlace,
)

START = Coordinate(lat=48.853, lon=2.369, name="Bastille")
MIDDLE = Coordinate(lat=48.86, lon=2.25, name="Middle")
END = Coordinate(lat=48.88, lon=2.095, name="Marly")


def test_explicit_distinct_waypoint_endpoints_resolve_open() -> None:
    selection = resolve_waypoint_endpoints(
        start=START,
        end=END,
        points=(MIDDLE,),
        topology="point_to_point",
    )
    assert selection.resolved.topology == "point_to_point"
    assert selection.resolved.start_source == "explicit"
    assert selection.resolved.end_source == "explicit"
    assert routing_sequence(selection.resolved, (MIDDLE,)) == (
        START,
        MIDDLE,
        END,
    )


def test_auto_tour_infers_loop_start_from_lowest_requested_index() -> None:
    later = RequestedTourPlace(name="Later", coordinate=END, original_index=9)
    earlier = RequestedTourPlace(name="Earlier", coordinate=START, original_index=2)
    request = AutoTourSearchRequest(
        target_distance_m=10_000,
        requested_stops=(later, earlier),
    )
    assert request.resolved_endpoints.topology == "loop"
    assert request.effective_start == START
    assert request.resolved_endpoints.start_source == ("inferred_from_requested_place")
    assert request.interior_requested_stops == (later,)


def test_auto_tour_infers_open_end_from_highest_requested_index() -> None:
    request = AutoTourSearchRequest(
        start=START,
        topology="point_to_point",
        target_distance_m=10_000,
        requested_stops=(
            RequestedTourPlace(name="Middle", coordinate=MIDDLE, original_index=2),
            RequestedTourPlace(name="End", coordinate=END, original_index=7),
        ),
    )
    assert request.effective_end == END
    assert request.resolved_endpoints.end_source == "inferred_from_requested_place"
    assert tuple(place.coordinate for place in request.interior_requested_stops) == (
        MIDDLE,
    )


def test_shared_auto_helper_falls_back_to_last_distinct_hard_point() -> None:
    selection = resolve_auto_tour_endpoints(
        start=None,
        end=None,
        requested_stops=(),
        hard_waypoints=(START, MIDDLE, END),
        topology="point_to_point",
    )
    assert selection.resolved.start == START
    assert selection.resolved.end == END
    assert selection.resolved.start_source == "inferred_from_hard_point"
    assert selection.resolved.end_source == "inferred_from_hard_point"
