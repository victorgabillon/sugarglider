"""Shared test fixtures."""

import pytest

from sugarglider.analysis.route import RouteAnalyzer
from sugarglider.domain.generation import (
    GeneratedCandidate,
    RequiredPointVisit,
    RouteGenerationResult,
    SearchSummary,
)
from sugarglider.domain.models import Coordinate, RouteResult, RouteSummary
from sugarglider.generation.scoring import score_route


@pytest.fixture
def route_result() -> RouteResult:
    """Return a small routed result with GeoJSON-order coordinates."""
    geometry = ((2.096667, 48.871389), (2.1, 48.87), (2.124421, 48.871454))
    return RouteResult(
        name="Marly & woods",
        summary=RouteSummary(
            distance_m=2500.5,
            duration_ms=1_800_000,
            ascend_m=None,
            descend_m=None,
            input_point_count=2,
            routed_point_count=len(geometry),
        ),
        geometry=geometry,
        snapped_points=(geometry[0], geometry[-1]),
        analysis=RouteAnalyzer().analyze(geometry, 2500.5, {}),
    )


@pytest.fixture
def generation_result(route_result: RouteResult) -> RouteGenerationResult:
    """Return one deterministic generated candidate for API tests."""
    candidate = GeneratedCandidate(
        rank=1,
        route=route_result,
        optional_points=(),
        required_point_order=(
            RequiredPointVisit(
                original_index=0,
                coordinate=Coordinate(lat=48.871389, lon=2.096667),
            ),
            RequiredPointVisit(
                original_index=1,
                coordinate=Coordinate(lat=48.871454, lon=2.124421),
            ),
        ),
        routing_points=(
            Coordinate(lat=48.871389, lon=2.096667),
            Coordinate(lat=48.871454, lon=2.124421),
        ),
        construction="alternative_leg_beam",
        target_error_m=499.5,
        within_tolerance=True,
        score=score_route(route_result, 3_000),
        signature="geometry:" + "a" * 64,
    )
    return RouteGenerationResult(
        baseline=route_result,
        candidates=(candidate,),
        search=SearchSummary(
            status="within_tolerance",
            target_distance_m=3_000,
            tolerance_m=500,
            baseline_distance_m=2500.5,
            best_order_distance_m=2500.5,
            evaluated_candidate_count=0,
            successful_candidate_count=0,
            rejected_candidate_count=0,
            round_trip_proposal_count=0,
            evaluated_order_count=0,
            successful_order_count=0,
            rejected_order_count=0,
            fixed_order_repeated_share=0,
            best_order_repeated_share=0,
            fixed_order_backtrack_share=0,
            best_order_backtrack_share=0,
            low_overlap_requested=False,
            pre_low_overlap_repeated_share=None,
            best_low_overlap_repeated_share=None,
            pre_low_overlap_backtrack_share=None,
            best_low_overlap_backtrack_share=None,
            nature_requested=False,
            nature_index_available=False,
            nature_index_feature_count=None,
            recommended_nature_score=None,
            best_available_nature_score=None,
            search_budget=48,
            search_budget_exhausted=False,
            seed=42,
            warnings=(),
        ),
    )
