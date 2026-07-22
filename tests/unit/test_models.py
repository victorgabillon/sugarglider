"""Domain model validation tests."""

import pytest
from pydantic import ValidationError

from sugarglider.domain.models import Coordinate, RouteRequest


def test_valid_coordinate() -> None:
    coordinate = Coordinate(lat=48.87, lon=2.09, name="Marly")
    assert coordinate.lat == 48.87
    assert coordinate.lon == 2.09


@pytest.mark.parametrize("latitude", [-90.01, 90.01])
def test_invalid_latitude(latitude: float) -> None:
    with pytest.raises(ValidationError):
        Coordinate(lat=latitude, lon=2.0)


@pytest.mark.parametrize("longitude", [-180.01, 180.01])
def test_invalid_longitude(longitude: float) -> None:
    with pytest.raises(ValidationError):
        Coordinate(lat=48.0, lon=longitude)


def test_route_requires_two_points() -> None:
    with pytest.raises(ValidationError):
        RouteRequest(profile="hike", points=[Coordinate(lat=48.0, lon=2.0)])


def test_route_rejects_adjacent_duplicates() -> None:
    with pytest.raises(ValidationError, match="adjacent route points"):
        RouteRequest(
            profile="hike",
            points=[
                Coordinate(lat=48.0, lon=2.0),
                Coordinate(lat=48.0, lon=2.0, name="Same position"),
            ],
        )


def test_loop_closure_does_not_mutate_caller_list() -> None:
    points = [Coordinate(lat=48.0, lon=2.0), Coordinate(lat=48.1, lon=2.1)]
    request = RouteRequest(profile="hike", points=points, closed=True)

    assert len(points) == 2
    assert request.points == [points[0], points[1], points[0]]
    assert request.input_point_count == 2


def test_already_closed_loop_is_not_closed_twice() -> None:
    first = Coordinate(lat=48.0, lon=2.0)
    request = RouteRequest(
        profile="hike",
        points=[first, Coordinate(lat=48.1, lon=2.1), first],
        closed=True,
    )
    assert len(request.points) == 3
    assert request.input_point_count == 3
