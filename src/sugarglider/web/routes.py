"""Routes for the packaged browser application and its runtime configuration."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from sugarglider.nature.models import NatureIndexStatus
from sugarglider.outings.service import OutingOperations
from sugarglider.saved_routes.service import SavedRouteOperations
from sugarglider.web.models import UiConfig

router = APIRouter()
STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"


@router.get("/", response_class=FileResponse, include_in_schema=False)
async def index() -> FileResponse:
    """Return the packaged single-page application independently of the CWD."""
    return FileResponse(STATIC_DIRECTORY / "index.html", media_type="text/html")


@router.get(
    "/manifest.webmanifest",
    response_class=FileResponse,
    include_in_schema=False,
)
async def web_manifest() -> FileResponse:
    """Return the capability-free install manifest from the origin root."""
    return FileResponse(
        STATIC_DIRECTORY / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get(
    "/service-worker.js",
    response_class=FileResponse,
    include_in_schema=False,
)
async def service_worker() -> FileResponse:
    """Return the application worker with an origin-root scope."""
    return FileResponse(
        STATIC_DIRECTORY / "service-worker.js",
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache",
            "Service-Worker-Allowed": "/",
            "X-Content-Type-Options": "nosniff",
        },
    )


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


@router.get(
    "/o/{slug}",
    response_class=FileResponse,
    include_in_schema=False,
    name="shared_outing",
)
def shared_outing(slug: str, request: Request) -> FileResponse:
    """Serve the application shell only for an existing unlisted outing."""
    service: OutingOperations = request.app.state.outing_service
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
