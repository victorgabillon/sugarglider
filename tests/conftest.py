"""Shared test fixtures."""

import pytest

from sugarglider.analysis.route import RouteAnalyzer
from sugarglider.domain.models import RouteResult, RouteSummary


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
