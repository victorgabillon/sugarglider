"""Validation tests for public target-distance generation requests."""

import pytest
from pydantic import ValidationError

from sugarglider.domain.generation import RouteGenerationRequest
from sugarglider.domain.models import Coordinate


def points(count: int = 2) -> list[Coordinate]:
    return [
        Coordinate(lat=48.0 + index * 0.01, lon=2.0 + index * 0.01)
        for index in range(count)
    ]


def test_valid_generation_request_closes_without_mutating_caller() -> None:
    supplied = points()
    request = RouteGenerationRequest(points=supplied, target_distance_m=41_000)
    assert len(supplied) == 2
    assert request.points == [supplied[0], supplied[1], supplied[0]]
    assert request.required_point_count == 2


def test_already_closed_request_is_not_closed_twice() -> None:
    supplied = points(3)
    supplied.append(supplied[0])
    request = RouteGenerationRequest(points=supplied, target_distance_m=41_000)
    assert request.points == supplied
    assert request.required_point_count == 4


@pytest.mark.parametrize("count", [0, 1, 21])
def test_required_point_count_bounds(count: int) -> None:
    with pytest.raises(ValidationError):
        RouteGenerationRequest(points=points(count), target_distance_m=41_000)


@pytest.mark.parametrize("target", [999, 200_001])
def test_target_distance_bounds(target: float) -> None:
    with pytest.raises(ValidationError):
        RouteGenerationRequest(points=points(), target_distance_m=target)


@pytest.mark.parametrize("tolerance", [99, 10_001])
def test_tolerance_bounds(tolerance: float) -> None:
    with pytest.raises(ValidationError):
        RouteGenerationRequest(
            points=points(), target_distance_m=41_000, tolerance_m=tolerance
        )


@pytest.mark.parametrize("candidate_count", [0, 6])
def test_candidate_count_bounds(candidate_count: int) -> None:
    with pytest.raises(ValidationError):
        RouteGenerationRequest(
            points=points(),
            target_distance_m=41_000,
            candidate_count=candidate_count,
        )


def test_adjacent_duplicate_required_points_are_rejected() -> None:
    point = Coordinate(lat=48, lon=2)
    with pytest.raises(ValidationError, match="adjacent required points"):
        RouteGenerationRequest(points=[point, point], target_distance_m=41_000)


def test_open_generation_is_rejected() -> None:
    with pytest.raises(ValidationError, match="close_loop=true"):
        RouteGenerationRequest(
            points=points(), target_distance_m=41_000, close_loop=False
        )
