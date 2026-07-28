"""Strict public models for unlisted shared outings."""

import unicodedata
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    Field,
    field_validator,
    model_validator,
)

from sugarglider.planning.models import CanonicalModel, PlanRequest
from sugarglider.planning.result import PlanCandidate

OutingSlug = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{20,64}$")]
PublicParticipantId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{20,64}$")]
CapabilityToken = Annotated[str, Field(min_length=32, max_length=128)]
OutingTitle = Annotated[str, Field(min_length=1, max_length=120)]
ParticipantDisplayName = Annotated[str, Field(min_length=1, max_length=80)]
SavedRouteSlugReference = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{20,64}$")]


class OutingPlannedRoute(CanonicalModel):
    """One exact request and selected candidate copied from a saved route."""

    source_request: PlanRequest
    candidate: PlanCandidate


class OutingParticipantSnapshot(CanonicalModel):
    """Public immutable participant state in stable join order."""

    participant_id: PublicParticipantId
    display_name: ParticipantDisplayName
    joined_at: AwareDatetime
    planned_route: OutingPlannedRoute

    @field_validator("display_name", mode="before")
    @classmethod
    def validate_display_name(cls, value: object) -> object:
        return _bounded_text(value) if isinstance(value, str) else value


class OutingSnapshot(CanonicalModel):
    """One unlisted outing and its independently planned participant routes."""

    schema_version: Literal[1] = 1
    slug: OutingSlug
    title: OutingTitle
    created_at: AwareDatetime
    expires_at: AwareDatetime
    max_participants: Annotated[int, Field(ge=2, le=20)]
    participants: tuple[OutingParticipantSnapshot, ...]

    @field_validator("title", mode="before")
    @classmethod
    def validate_title(cls, value: object) -> object:
        return _bounded_text(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_outing(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("outing expiration must follow creation")
        if len(self.participants) > self.max_participants:
            raise ValueError("outing participants exceed capacity")
        identifiers = tuple(
            participant.participant_id for participant in self.participants
        )
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("participant IDs must be unique")
        return self


class OutingCreateRequest(CanonicalModel):
    schema_version: Literal[1] = 1
    title: OutingTitle
    participant_display_name: ParticipantDisplayName
    saved_route_slug: SavedRouteSlugReference

    @field_validator("title", "participant_display_name", mode="before")
    @classmethod
    def validate_text(cls, value: object) -> object:
        return _bounded_text(value) if isinstance(value, str) else value


class OutingJoinRequest(CanonicalModel):
    schema_version: Literal[1] = 1
    display_name: ParticipantDisplayName
    saved_route_slug: SavedRouteSlugReference

    @field_validator("display_name", mode="before")
    @classmethod
    def validate_text(cls, value: object) -> object:
        return _bounded_text(value) if isinstance(value, str) else value


class OutingCreated(OutingSnapshot):
    """Creation response containing one-time capabilities."""

    owner_token: CapabilityToken
    join_token: CapabilityToken
    participant_id: PublicParticipantId
    participant_token: CapabilityToken
    share_path: str
    invite_path: str


class OutingParticipantJoined(CanonicalModel):
    """Join response containing only the new participant capability."""

    schema_version: Literal[1] = 1
    outing: OutingSnapshot
    participant_id: PublicParticipantId
    participant_token: CapabilityToken


def _bounded_text(value: str) -> str:
    stripped = value.strip()
    if not stripped or any(
        unicodedata.category(character).startswith("C") for character in stripped
    ):
        raise ValueError("text must be nonempty and contain no control characters")
    return stripped
