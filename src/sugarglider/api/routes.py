"""HTTP endpoint definitions."""

from typing import Annotated, Literal

from fastapi import APIRouter, Body
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict

from sugarglider.api.dependencies import RouteServiceDependency
from sugarglider.domain.models import RouteRequest, RouteResult
from sugarglider.gpx.writer import gpx_filename, write_gpx
from sugarglider.routing.graphhopper import RoutingError, RoutingUnavailableError

router = APIRouter()


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report application liveness without consulting GraphHopper."""
    return HealthResponse()


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
