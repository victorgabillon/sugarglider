"""Validation tests for public target-distance generation requests."""

from typing import Literal

import pytest
from pydantic import ValidationError

from sugarglider.domain.generation import (
    GeneratedCandidate,
    RouteGenerationRequest,
    RouteGenerationResult,
    SearchSummary,
)
from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.generation.scoring import score_route


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
    assert request.point_order_mode == "fixed"
    assert request.path_selection_mode == "shortest"


def test_already_closed_request_is_not_closed_twice() -> None:
    supplied = points(3)
    supplied.append(supplied[0])
    request = RouteGenerationRequest(points=supplied, target_distance_m=41_000)
    assert request.points == supplied
    assert request.required_point_count == 4


@pytest.mark.parametrize("count", [0, 1, 31])
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


def test_legacy_close_loop_false_resolves_a_genuine_open_path() -> None:
    supplied = points()
    request = RouteGenerationRequest(
        points=supplied, target_distance_m=41_000, close_loop=False
    )
    assert request.resolved_endpoints.topology == "point_to_point"
    assert request.routing_points == tuple(supplied)
    assert request.routing_points[-1] != request.routing_points[0]


def test_thirty_required_points_are_supported() -> None:
    request = RouteGenerationRequest(
        points=points(30),
        target_distance_m=41_000,
    )
    assert request.required_point_count == 30
    assert len(request.points) == 31
    assert request.points[-1] == request.points[0]


@pytest.mark.parametrize("mode", ["fixed", "optimize_loop"])
def test_supported_point_order_modes(
    mode: Literal["fixed", "optimize_loop"],
) -> None:
    request = RouteGenerationRequest(
        points=points(),
        target_distance_m=41_000,
        point_order_mode=mode,
    )
    assert request.point_order_mode == mode


def test_invalid_point_order_mode_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RouteGenerationRequest.model_validate(
            {
                "points": points(),
                "target_distance_m": 41_000,
                "point_order_mode": "shortest",
            }
        )


def test_low_overlap_path_selection_mode_is_accepted() -> None:
    request = RouteGenerationRequest(
        points=points(),
        target_distance_m=41_000,
        path_selection_mode="low_overlap",
    )
    assert request.path_selection_mode == "low_overlap"


def test_invalid_path_selection_mode_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RouteGenerationRequest.model_validate(
            {
                "points": points(),
                "target_distance_m": 41_000,
                "path_selection_mode": "scenic",
            }
        )


def test_candidate_routing_points_and_construction_are_frozen_and_serialized(
    route_result: RouteResult,
) -> None:
    routing_points = tuple(points())
    candidate = GeneratedCandidate(
        rank=1,
        route=route_result,
        optional_points=(),
        required_point_order=(),
        routing_points=routing_points,
        construction="alternative_leg_beam",
        target_error_m=0,
        within_tolerance=True,
        score=score_route(route_result, route_result.summary.distance_m),
        signature="geometry:" + "a" * 64,
    )
    with pytest.raises(ValidationError):
        candidate.routing_points[0].lat = 1
    dumped = candidate.model_dump(mode="json")
    assert dumped["routing_points"] == [point.model_dump() for point in routing_points]
    assert dumped["construction"] == "alternative_leg_beam"


def test_low_overlap_summary_shares_are_validated(
    generation_result: RouteGenerationResult,
) -> None:
    dumped = generation_result.search.model_dump()
    dumped["best_low_overlap_repeated_share"] = 1.01
    with pytest.raises(ValidationError):
        SearchSummary.model_validate(dumped)


@pytest.mark.parametrize("missing", ["routing_points", "construction"])
def test_candidate_requires_construction_metadata(
    generation_result: RouteGenerationResult, missing: str
) -> None:
    dumped = generation_result.candidates[0].model_dump()
    dumped.pop(missing)
    with pytest.raises(ValidationError):
        GeneratedCandidate.model_validate(dumped)


@pytest.mark.parametrize(
    "missing",
    [
        "best_order_distance_m",
        "low_overlap_requested",
        "pre_low_overlap_repeated_share",
        "best_low_overlap_repeated_share",
        "pre_low_overlap_backtrack_share",
        "best_low_overlap_backtrack_share",
    ],
)
def test_summary_requires_low_overlap_state_fields(
    generation_result: RouteGenerationResult, missing: str
) -> None:
    dumped = generation_result.search.model_dump()
    dumped.pop(missing)
    with pytest.raises(ValidationError):
        SearchSummary.model_validate(dumped)
