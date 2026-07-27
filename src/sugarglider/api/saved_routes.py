"""Immutable saved-route persistence and unlisted-sharing endpoints."""

from typing import Annotated

from fastapi import APIRouter, Body, Header, Response, status

from sugarglider.api.dependencies import SavedRouteServiceDependency
from sugarglider.gpx.writer import gpx_filename, write_plan_gpx
from sugarglider.saved_routes.models import (
    SavedRouteCreated,
    SavedRouteCreateRequest,
    SavedRouteSnapshot,
)

router = APIRouter(prefix="/v2/saved-routes", tags=["saved routes"])


@router.post(
    "",
    response_model=SavedRouteCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_saved_route(
    request: Annotated[SavedRouteCreateRequest, Body()],
    service: SavedRouteServiceDependency,
    response: Response,
) -> SavedRouteCreated:
    """Persist the exact request/candidate pair without invoking planning."""
    created = service.create(request)
    response.headers["Location"] = f"/v2/saved-routes/{created.slug}"
    response.headers["Cache-Control"] = "no-store"
    return created


@router.get("/{slug}", response_model=SavedRouteSnapshot)
def get_saved_route(
    slug: str,
    service: SavedRouteServiceDependency,
    response: Response,
) -> SavedRouteSnapshot:
    """Return one immutable unlisted snapshot without regeneration."""
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["Referrer-Policy"] = "no-referrer"
    return service.get(slug)


@router.get("/{slug}/gpx", response_class=Response)
def get_saved_route_gpx(
    slug: str,
    service: SavedRouteServiceDependency,
) -> Response:
    """Serialize the stored candidate directly as a clean GPX track."""
    candidate = service.get(slug).candidate
    filename = gpx_filename(candidate.route.name)
    return Response(
        content=write_plan_gpx(candidate),
        media_type="application/gpx+xml",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Robots-Tag": "noindex, nofollow, noarchive",
            "Referrer-Policy": "no-referrer",
        },
    )


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_route(
    slug: str,
    service: SavedRouteServiceDependency,
    owner_token: Annotated[
        str | None,
        Header(alias="X-Saved-Route-Owner-Token"),
    ] = None,
) -> Response:
    """Delete a snapshot using the creation-time capability token."""
    service.delete(slug, owner_token)
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={"Cache-Control": "no-store"},
    )
