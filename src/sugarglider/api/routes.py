"""HTTP endpoint definitions."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Body, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict

from sugarglider.analysis.route import RouteAnalysisError
from sugarglider.analysis.visualization import build_route_visualization
from sugarglider.api.dependencies import (
    AutoTourServiceDependency,
    GenerationServiceDependency,
    RouteServiceDependency,
)
from sugarglider.api.errors import RouteVisualizationError
from sugarglider.domain.generation import (
    RouteGenerationRequest,
    RouteGenerationResult,
)
from sugarglider.domain.models import RouteRequest, RouteResult
from sugarglider.generation.service import (
    RouteGenerationNoCandidateError,
    TargetDistanceInfeasibleError,
)
from sugarglider.gpx.writer import gpx_filename, write_gpx
from sugarglider.nature.analysis import NatureRouteAnalyzer
from sugarglider.pois.errors import PoiSearchLimitError
from sugarglider.pois.index import PoiIndex, unavailable_poi_search
from sugarglider.pois.models import (
    PoiIndexStatus,
    PoiSearchRequest,
    PoiSearchResponse,
)
from sugarglider.routing.graphhopper import RoutingError, RoutingUnavailableError
from sugarglider.tours.models import AutoTourRequest, AutoTourResult
from sugarglider.web.models import RouteVisualization

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


@router.post("/v1/routes", response_model=RouteResult)
async def create_route(
    request: Annotated[RouteRequest, Body()], service: RouteServiceDependency
) -> RouteResult:
    """Return routed geometry and route metrics as JSON."""
    return await service.route(request)


@router.post("/v1/routes/gpx", response_class=Response)
async def create_route_gpx(
    request: Annotated[RouteRequest, Body()], service: RouteServiceDependency
) -> Response:
    """Return the same routed result as one downloadable GPX track."""
    result = await service.route(request)
    filename = gpx_filename(result.name)
    return Response(
        content=write_gpx(result),
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/v1/routes/gpx/from-result", response_class=Response)
async def create_route_gpx_from_result(
    route: Annotated[RouteResult, Body()],
) -> Response:
    """Export an already generated immutable route without calling routing."""
    filename = gpx_filename(route.name)
    return Response(
        content=write_gpx(route),
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/v1/routes/visualization", response_model=RouteVisualization)
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


@router.post("/v1/routes/generate", response_model=RouteGenerationResult)
async def generate_route(
    request: Annotated[RouteGenerationRequest, Body()],
    service: GenerationServiceDependency,
) -> RouteGenerationResult:
    """Return a baseline and ranked target-distance candidates."""
    return await service.generate(request)


@router.post("/v1/tours/generate", response_model=AutoTourResult)
async def generate_auto_tour(
    request: Annotated[AutoTourRequest, Body()],
    service: AutoTourServiceDependency,
) -> AutoTourResult:
    """Build a skeleton-first loop and conservatively collect nearby POIs."""
    return await service.generate(request)


@router.post("/v1/routes/generate/gpx", response_class=Response)
async def generate_route_gpx(
    request: Annotated[RouteGenerationRequest, Body()],
    service: GenerationServiceDependency,
) -> Response:
    """Generate and export the best candidate as a clean GPX track."""
    result = await service.generate(request)
    if result.search.status == "infeasible":
        raise TargetDistanceInfeasibleError
    if not result.candidates:
        raise RouteGenerationNoCandidateError
    best = result.candidates[0].route
    filename = gpx_filename(best.name)
    return Response(
        content=write_gpx(best),
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
