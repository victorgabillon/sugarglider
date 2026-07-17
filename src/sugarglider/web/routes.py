"""Routes for the packaged browser application and its runtime configuration."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from sugarglider.web.models import UiConfig

router = APIRouter()
STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"


@router.get("/", response_class=FileResponse, include_in_schema=False)
async def index() -> FileResponse:
    """Return the packaged single-page application independently of the CWD."""
    return FileResponse(STATIC_DIRECTORY / "index.html", media_type="text/html")


@router.get("/v1/ui/config", response_model=UiConfig)
async def ui_config(request: Request) -> UiConfig:
    """Return validated, public map settings."""
    config: UiConfig = request.app.state.ui_config
    return config
