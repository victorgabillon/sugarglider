"""Shared display projection of submitted geometry, with no routing calls."""

from typing import Annotated

from fastapi import APIRouter, Body, Request

from sugarglider.analysis.route import RouteAnalysisError
from sugarglider.analysis.visualization import build_route_visualization
from sugarglider.analysis.visualization_models import RouteVisualization
from sugarglider.api.errors import RouteVisualizationError
from sugarglider.domain.models import RouteResult
from sugarglider.nature.analysis import NatureRouteAnalyzer

router = APIRouter()


@router.post("/v2/plans/visualization", response_model=RouteVisualization)
def visualize_route(
    route: Annotated[RouteResult, Body()],
    request: Request,
) -> RouteVisualization:
    """Return server-classified contiguous map sections for a route result."""
    try:
        nature_analyzer: NatureRouteAnalyzer | None = request.app.state.nature_analyzer
        return build_route_visualization(route, nature_analyzer)
    except RouteAnalysisError as exc:
        raise RouteVisualizationError from exc
