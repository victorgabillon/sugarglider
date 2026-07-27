"""Routes for the packaged browser application and its runtime configuration."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from sugarglider.nature.models import NatureIndexStatus
from sugarglider.saved_routes.service import SavedRouteOperations
from sugarglider.web.models import UiConfig

router = APIRouter()
STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"


@router.get("/", response_class=FileResponse, include_in_schema=False)
async def index() -> FileResponse:
    """Return the packaged single-page application independently of the CWD."""
    return FileResponse(STATIC_DIRECTORY / "index.html", media_type="text/html")


@router.get(
    "/r/{slug}",
    response_class=FileResponse,
    include_in_schema=False,
    name="shared_saved_route",
)
def shared_saved_route(slug: str, request: Request) -> FileResponse:
    """Serve the read-only application only for an existing unlisted snapshot."""
    service: SavedRouteOperations = request.app.state.saved_route_service
    service.get(slug)
    return FileResponse(
        STATIC_DIRECTORY / "index.html",
        media_type="text/html",
        headers={
            "Cache-Control": "private, no-store",
            "X-Robots-Tag": "noindex, nofollow, noarchive",
            "Referrer-Policy": "no-referrer",
        },
    )


@router.get("/v1/ui/config", response_model=UiConfig)
async def ui_config(request: Request) -> UiConfig:
    """Return validated, public map settings."""
    config: UiConfig = request.app.state.ui_config
    return config


@router.get("/v1/nature/status", response_model=NatureIndexStatus)
async def nature_status(request: Request) -> NatureIndexStatus:
    """Return safe local-index availability without exposing a host path."""
    status: NatureIndexStatus = request.app.state.nature_status
    return status
