"""Canonical public and persisted saved-route documents."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from sugarglider.planning.models import CanonicalModel, PlanRequest
from sugarglider.planning.result import PlanCandidate

Slug = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{20,64}$")]
OwnerToken = Annotated[str, Field(min_length=32, max_length=128)]


class SavedRouteCreateRequest(CanonicalModel):
    """One source request and the exact returned candidate selected by the user."""

    schema_version: Literal[1] = 1
    source_request: PlanRequest
    candidate: PlanCandidate


class SavedRouteSnapshot(CanonicalModel):
    """Public immutable snapshot addressed by an opaque unlisted slug."""

    schema_version: Literal[1] = 1
    slug: Slug
    created_at: AwareDatetime
    expires_at: AwareDatetime
    source_request: PlanRequest
    candidate: PlanCandidate


class SavedRouteCreated(SavedRouteSnapshot):
    """Creation response containing the one-time deletion capability."""

    owner_token: OwnerToken
    share_path: str
    gpx_path: str


def created_response(
    snapshot: SavedRouteSnapshot, owner_token: str
) -> SavedRouteCreated:
    """Build safe relative links without trusting an HTTP Host header."""
    return SavedRouteCreated(
        **snapshot.model_dump(),
        owner_token=owner_token,
        share_path=f"/r/{snapshot.slug}",
        gpx_path=f"/v2/saved-routes/{snapshot.slug}/gpx",
    )
