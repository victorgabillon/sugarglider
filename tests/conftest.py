"""Shared test fixtures."""

import pytest

from sugarglider.analysis.route import RouteAnalyzer
from sugarglider.domain.models import RouteResult, RouteSummary
from sugarglider.planning.direction.traversal import build_plan_traversal
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.models import PLAN_REQUEST_ADAPTER, PlanRequest
from sugarglider.planning.result import (
    PlanCandidate,
    PlanCandidateDiagnostics,
    PlanScore,
)
from sugarglider.planning.signatures import candidate_signature


@pytest.fixture
def route_result() -> RouteResult:
    """Return a small routed result with GeoJSON-order coordinates."""
    geometry = ((2.096667, 48.871389), (2.1, 48.87), (2.124421, 48.871454))
    return RouteResult(
        name="Marly & woods",
        routing_profile="hike",
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
def saved_route_source_request() -> PlanRequest:
    return PLAN_REQUEST_ADAPTER.validate_python(
        {
            "schema_version": 1,
            "kind": "waypoint_route",
            "name": "Saved woodland route — forêt",
            "topology": "point_to_point",
            "start": {"lat": 48.871389, "lon": 2.096667},
            "end": {"lat": 48.871454, "lon": 2.124421},
            "routing_profile": "hike",
            "candidate_count": 3,
            "seed": 42,
            "distance_objective": {
                "target_m": 3_000,
                "tolerance_m": 500,
                "maximum_m": None,
                "priority": "flexible",
            },
            "preferences": {
                "nature": "off",
                "loop_geometry": "off",
                "path_selection": "shortest",
            },
            "waypoints": [],
            "waypoint_order": "fixed",
        }
    )


@pytest.fixture
def saved_route_candidate(
    route_result: RouteResult,
    saved_route_source_request: PlanRequest,
) -> PlanCandidate:
    traversal = build_plan_traversal(
        saved_route_source_request,
        CandidateDraft(
            route=route_result,
            routing_points=(),
            topology="point_to_point",
            construction="saved_test",
            search_family="submitted_candidate",
        ),
    )
    return PlanCandidate(
        id=candidate_signature(
            route_result,
            topology="point_to_point",
            routing_profile="hike",
        ),
        kind="waypoint_route",
        topology="point_to_point",
        routing_profile="hike",
        rank=2,
        roles=("smooth_low_detour",),
        route=route_result,
        score=PlanScore(total=12.5, components={"distance": 12.5}),
        traversal=traversal,
        diagnostics=PlanCandidateDiagnostics(
            safety_eligible=True,
            target_error_m=499.5,
            within_tolerance=True,
            requested_stop_count=0,
            immediate_backtracking_m=0,
            repeated_distance_m=0,
            details={"construction": "saved-test"},
        ),
    )
