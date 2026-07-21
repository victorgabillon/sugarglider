"""HTTP endpoint definitions."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Body, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict

from sugarglider.analysis.route import RouteAnalysisError
from sugarglider.analysis.visualization import build_route_visualization
from sugarglider.analysis.visualization_models import RouteVisualization
from sugarglider.api.dependencies import PlanServiceDependency, RouteServiceDependency
from sugarglider.api.errors import RouteVisualizationError
from sugarglider.domain.models import RouteResult
from sugarglider.gpx.writer import gpx_filename, write_plan_gpx
from sugarglider.nature.analysis import NatureRouteAnalyzer
from sugarglider.planning.models import PlanRequest
from sugarglider.planning.result import PlanGpxRequest, PlanResult
from sugarglider.pois.errors import PoiSearchLimitError
from sugarglider.pois.index import PoiIndex, unavailable_poi_search
from sugarglider.pois.models import (
    PoiIndexStatus,
    PoiSearchRequest,
    PoiSearchResponse,
)
from sugarglider.routing.graphhopper import RoutingError, RoutingUnavailableError

router = APIRouter()


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report application liveness without consulting GraphHopper."""
    return HealthResponse()


@router.get("/v1/pois/status", response_model=PoiIndexStatus)
async def poi_status(request: Request) -> PoiIndexStatus:
    """Return local POI-index availability without exposing a host path."""
    status: PoiIndexStatus = request.app.state.poi_status
    return status


@router.post("/v1/pois/search", response_model=PoiSearchResponse)
async def search_pois(
    query: Annotated[PoiSearchRequest, Body()], request: Request
) -> PoiSearchResponse:
    """Return one bounded viewport slice from the lifespan-loaded point index."""
    limit = query.limit or cast(int, request.app.state.poi_default_limit)
    maximum = cast(int, request.app.state.poi_max_limit)
    if limit > maximum:
        raise PoiSearchLimitError
    index = cast(PoiIndex | None, request.app.state.poi_index)
    if index is None:
        status = cast(PoiIndexStatus, request.app.state.poi_status)
        return unavailable_poi_search(warnings=status.warnings)
    return index.search(query, limit=limit)


@router.get("/ready", response_model=HealthResponse)
async def ready(service: RouteServiceDependency) -> HealthResponse:
    """Report readiness only when the GraphHopper hike profile is loaded."""
    try:
        is_ready = await service.ready()
    except RoutingError as exc:
        raise RoutingUnavailableError("GraphHopper readiness check failed") from exc
    if not is_ready:
        raise RoutingUnavailableError("GraphHopper does not advertise hike")
    return HealthResponse()


@router.post("/v2/plans/visualization", response_model=RouteVisualization)
async def visualize_route(
    route: Annotated[RouteResult, Body()],
    request: Request,
) -> RouteVisualization:
    """Return server-classified contiguous map sections for a route result."""
    try:
        nature_analyzer: NatureRouteAnalyzer | None = request.app.state.nature_analyzer
        return build_route_visualization(route, nature_analyzer)
    except RouteAnalysisError as exc:
        raise RouteVisualizationError from exc


@router.post("/v2/plans/generate", response_model=PlanResult)
async def generate_plan(
    request: PlanRequest,
    service: PlanServiceDependency,
) -> PlanResult:
    """Generate one canonical portfolio for either supported planning mode."""
    return await service.generate(request)


@router.post("/v2/plans/gpx", response_class=Response)
async def create_plan_gpx(request: Annotated[PlanGpxRequest, Body()]) -> Response:
    """Export a previously returned canonical candidate without rerouting."""
    filename = gpx_filename(request.candidate.route.name)
    return Response(
        content=write_plan_gpx(request.candidate),
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
