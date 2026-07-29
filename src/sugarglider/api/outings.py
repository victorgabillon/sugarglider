"""Synchronous shared-outing HTTP endpoints."""

from typing import Annotated

from fastapi import APIRouter, Body, Header, Response, status

from sugarglider.api.dependencies import (
    AuthorizedOutingJoinTokenDependency,
    OutingLiveBrokerDependency,
    OutingServiceDependency,
    SavedRouteServiceDependency,
)
from sugarglider.gpx.writer import gpx_filename, write_plan_gpx
from sugarglider.outings.models import (
    OutingCreated,
    OutingCreateRequest,
    OutingJoinRequest,
    OutingParticipantJoined,
    OutingPlannedRoute,
    OutingSnapshot,
)

router = APIRouter(prefix="/v2/outings", tags=["outings"])


@router.post("", response_model=OutingCreated, status_code=status.HTTP_201_CREATED)
def create_outing(
    request: Annotated[OutingCreateRequest, Body()],
    outings: OutingServiceDependency,
    saved_routes: SavedRouteServiceDependency,
    response: Response,
) -> OutingCreated:
    """Copy one exact saved route into a new outing atomically."""
    saved = saved_routes.get(request.saved_route_slug)
    created = outings.create(
        request.title,
        request.participant_display_name,
        OutingPlannedRoute(
            source_request=saved.source_request,
            candidate=saved.candidate,
        ),
    )
    response.headers["Location"] = f"/v2/outings/{created.slug}"
    response.headers["Cache-Control"] = "no-store"
    return created


@router.get("/{slug}", response_model=OutingSnapshot)
def get_outing(
    slug: str,
    outings: OutingServiceDependency,
    response: Response,
) -> OutingSnapshot:
    """Return independently copied routes without invoking saved routes or planning."""
    response.headers.update(_privacy_headers())
    return outings.get(slug)


@router.post(
    "/{slug}/participants",
    response_model=OutingParticipantJoined,
    status_code=status.HTTP_201_CREATED,
)
def join_outing(
    slug: str,
    request: Annotated[OutingJoinRequest, Body()],
    outings: OutingServiceDependency,
    saved_routes: SavedRouteServiceDependency,
    response: Response,
    join_token: AuthorizedOutingJoinTokenDependency,
) -> OutingParticipantJoined:
    """Authorize first, then copy the participant's independent saved route."""
    saved = saved_routes.get(request.saved_route_slug)
    joined = outings.join(
        slug,
        join_token,
        request.display_name,
        OutingPlannedRoute(
            source_request=saved.source_request,
            candidate=saved.candidate,
        ),
    )
    response.headers["Location"] = (
        f"/v2/outings/{slug}/participants/{joined.participant_id}"
    )
    response.headers["Cache-Control"] = "no-store"
    return joined


@router.get("/{slug}/participants/{participant_id}/gpx", response_class=Response)
def get_outing_participant_gpx(
    slug: str,
    participant_id: str,
    outings: OutingServiceDependency,
) -> Response:
    """Serialize only the participant's stored candidate directly."""
    candidate = outings.participant_route(slug, participant_id).candidate
    return Response(
        content=write_plan_gpx(candidate),
        media_type="application/gpx+xml",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{gpx_filename(candidate.route.name)}"'
            ),
            **_privacy_headers(),
        },
    )


@router.delete(
    "/{slug}/participants/{participant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def leave_outing(
    slug: str,
    participant_id: str,
    outings: OutingServiceDependency,
    live_broker: OutingLiveBrokerDependency,
    participant_token: Annotated[
        str | None,
        Header(alias="X-Sugarglider-Participant-Token"),
    ] = None,
) -> Response:
    live_changed = outings.remove_participant(slug, participant_id, participant_token)
    if live_changed:
        live_broker.notify(slug)
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={"Cache-Control": "no-store"},
    )


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_outing(
    slug: str,
    outings: OutingServiceDependency,
    live_broker: OutingLiveBrokerDependency,
    owner_token: Annotated[
        str | None,
        Header(alias="X-Sugarglider-Outing-Owner-Token"),
    ] = None,
) -> Response:
    outings.delete(slug, owner_token)
    live_broker.notify(slug)
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={"Cache-Control": "no-store"},
    )


def _privacy_headers() -> dict[str, str]:
    return {
        "Cache-Control": "private, no-store",
        "X-Robots-Tag": "noindex, nofollow, noarchive",
        "Referrer-Policy": "no-referrer",
    }
