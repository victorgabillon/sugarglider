"""Shared endpoint-resolution matrix for loop and point-to-point requests."""

import pytest
from pydantic import ValidationError

from sugarglider.domain.endpoints import (
    resolve_auto_tour_endpoints,
    resolve_waypoint_endpoints,
    routing_sequence,
)
from sugarglider.domain.generation import RouteGenerationRequest
from sugarglider.domain.models import Coordinate
from sugarglider.tours.models import AutoTourRequest, RequestedTourPlace

START = Coordinate(lat=48.853, lon=2.369, name="Bastille")
MIDDLE = Coordinate(lat=48.86, lon=2.25, name="Middle")
END = Coordinate(lat=48.88, lon=2.095, name="Marly")


def test_explicit_distinct_waypoint_endpoints_resolve_open() -> None:
    selection = resolve_waypoint_endpoints(
        start=START,
        end=END,
        points=(MIDDLE,),
        route_topology="auto",
    )
    assert selection.resolved.topology == "point_to_point"
    assert selection.resolved.start_source == "explicit"
    assert selection.resolved.end_source == "explicit"
    assert routing_sequence(selection.resolved, (MIDDLE,)) == (
        START,
        MIDDLE,
        END,
    )


def test_start_only_waypoint_request_resolves_legacy_loop() -> None:
    request = RouteGenerationRequest(
        start=START,
        points=[MIDDLE],
        target_distance_m=10_000,
    )
    assert request.resolved_endpoints.topology == "loop"
    assert request.resolved_endpoints.end_source == "loop_closure"
    assert request.routing_points == (START, MIDDLE, START)


def test_end_only_waypoint_request_infers_start_from_first_point() -> None:
    request = RouteGenerationRequest(
        end=END,
        points=[START, MIDDLE],
        target_distance_m=10_000,
    )
    assert request.resolved_endpoints.topology == "point_to_point"
    assert request.resolved_endpoints.start_source == "inferred_from_waypoint"
    assert request.routing_points == (START, MIDDLE, END)


def test_direct_waypoint_path_allows_zero_intermediate_points() -> None:
    request = RouteGenerationRequest(
        start=START,
        end=END,
        points=[],
        route_topology="point_to_point",
        target_distance_m=10_000,
    )
    assert request.routing_points == (START, END)


def test_explicit_same_coordinate_endpoints_resolve_a_loop() -> None:
    request = RouteGenerationRequest(
        start=START,
        end=START,
        points=[],
        target_distance_m=10_000,
    )
    assert request.resolved_endpoints.topology == "loop"
    assert request.routing_points == (START, START)


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (
            {"points": [], "route_topology": "point_to_point"},
            "endpoint_start_unresolved",
        ),
        (
            {
                "start": START,
                "points": [],
                "route_topology": "point_to_point",
            },
            "endpoint_end_unresolved",
        ),
        (
            {
                "start": START,
                "end": START,
                "points": [],
                "route_topology": "point_to_point",
            },
            "endpoint_coordinates_equal_for_point_to_point",
        ),
        (
            {
                "start": START,
                "end": END,
                "points": [MIDDLE],
                "route_topology": "loop",
            },
            "distinct_end_not_allowed_for_loop",
        ),
    ],
)
def test_invalid_waypoint_endpoint_combinations_are_stable(
    payload: dict[str, object], code: str
) -> None:
    with pytest.raises(ValidationError) as raised:
        RouteGenerationRequest.model_validate({**payload, "target_distance_m": 10_000})
    assert raised.value.errors()[0]["type"] == code


def test_contradictory_legacy_and_topology_inputs_reject() -> None:
    with pytest.raises(ValidationError) as raised:
        RouteGenerationRequest(
            start=START,
            end=END,
            points=[],
            target_distance_m=10_000,
            route_topology="point_to_point",
            close_loop=True,
        )
    assert raised.value.errors()[0]["type"] == (
        "route_topology_conflicts_with_close_loop"
    )


def test_auto_tour_infers_loop_start_from_lowest_requested_index() -> None:
    later = RequestedTourPlace(name="Later", coordinate=END, original_index=9)
    earlier = RequestedTourPlace(name="Earlier", coordinate=START, original_index=2)
    request = AutoTourRequest(
        target_distance_m=10_000,
        requested_places=(later, earlier),
    )
    assert request.resolved_endpoints.topology == "loop"
    assert request.effective_start == START
    assert request.resolved_endpoints.start_source == ("inferred_from_requested_place")
    assert request.interior_requested_places == (later,)


def test_auto_tour_infers_open_end_from_highest_requested_index() -> None:
    request = AutoTourRequest(
        start=START,
        route_topology="point_to_point",
        target_distance_m=10_000,
        requested_places=(
            RequestedTourPlace(name="Middle", coordinate=MIDDLE, original_index=2),
            RequestedTourPlace(name="End", coordinate=END, original_index=7),
        ),
    )
    assert request.effective_end == END
    assert request.resolved_endpoints.end_source == "inferred_from_requested_place"
    assert tuple(place.coordinate for place in request.interior_requested_places) == (
        MIDDLE,
    )


def test_adjacent_duplicate_routing_points_reject() -> None:
    with pytest.raises(ValidationError, match="Adjacent routing points"):
        RouteGenerationRequest(
            start=START,
            end=END,
            points=[START],
            route_topology="point_to_point",
            target_distance_m=10_000,
        )


def test_shared_auto_helper_falls_back_to_last_distinct_hard_point() -> None:
    selection = resolve_auto_tour_endpoints(
        start=None,
        end=None,
        requested_places=(),
        hard_points=(START, MIDDLE, END),
        route_topology="point_to_point",
    )
    assert selection.resolved.start == START
    assert selection.resolved.end == END
    assert selection.resolved.start_source == "inferred_from_hard_point"
    assert selection.resolved.end_source == "inferred_from_hard_point"
