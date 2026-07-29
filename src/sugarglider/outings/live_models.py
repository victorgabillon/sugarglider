"""Strict public models for authenticated outing live positions."""

from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from sugarglider.outings.models import OutingSlug, PublicParticipantId
from sugarglider.planning.models import CanonicalModel

SQLITE_SIGNED_INTEGER_MAX = 9_223_372_036_854_775_807

LiveEventType = Literal["position_updated", "position_cleared"]
PositionClearReason = Literal["stopped", "expired", "participant_left"]


class LiveCoordinate(CanonicalModel):
    """One unsnapped coordinate supplied by a participant device."""

    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]


class OutingPositionUpdate(CanonicalModel):
    """Authenticated position payload ordered by its client sequence."""

    schema_version: Literal[1] = 1
    sequence: Annotated[int, Field(ge=0, le=SQLITE_SIGNED_INTEGER_MAX)]
    coordinate: LiveCoordinate
    accuracy_m: Annotated[float, Field(ge=0, le=10_000)]
    altitude_m: Annotated[float, Field(ge=-1_000, le=12_000)] | None = None
    speed_m_s: Annotated[float, Field(ge=0, le=150)] | None = None
    heading_deg: Annotated[float, Field(ge=0, lt=360)] | None = None
    captured_at: AwareDatetime


class ParticipantLivePosition(CanonicalModel):
    """Current public position with server-controlled freshness timestamps."""

    schema_version: Literal[1] = 1
    participant_id: PublicParticipantId
    sequence: Annotated[int, Field(ge=0, le=SQLITE_SIGNED_INTEGER_MAX)]
    coordinate: LiveCoordinate
    accuracy_m: Annotated[float, Field(ge=0, le=10_000)]
    altitude_m: Annotated[float, Field(ge=-1_000, le=12_000)] | None
    speed_m_s: Annotated[float, Field(ge=0, le=150)] | None
    heading_deg: Annotated[float, Field(ge=0, lt=360)] | None
    captured_at: AwareDatetime
    received_at: AwareDatetime
    stale_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_timestamp_order(self) -> Self:
        if not self.received_at < self.stale_at < self.expires_at:
            raise ValueError(
                "position freshness timestamps must be strictly increasing"
            )
        return self


class OutingLiveSnapshot(CanonicalModel):
    """Authoritative current positions in immutable participant join order."""

    schema_version: Literal[1] = 1
    slug: OutingSlug
    generated_at: AwareDatetime
    cursor: Annotated[int, Field(ge=0, le=SQLITE_SIGNED_INTEGER_MAX)]
    stale_after_seconds: Annotated[int, Field(gt=0)]
    expire_after_seconds: Annotated[int, Field(gt=0)]
    positions: tuple[ParticipantLivePosition, ...]

    @model_validator(mode="after")
    def validate_durations_and_participants(self) -> Self:
        if self.stale_after_seconds >= self.expire_after_seconds:
            raise ValueError("live stale duration must be below expiry duration")
        participant_ids = tuple(position.participant_id for position in self.positions)
        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("live snapshot participant IDs must be unique")
        return self


class OutingLiveEvent(CanonicalModel):
    """One durable event in an outing's bounded replay log."""

    schema_version: Literal[1] = 1
    event_id: Annotated[
        int,
        Field(ge=1, le=SQLITE_SIGNED_INTEGER_MAX),
    ]
    event_type: LiveEventType
    participant_id: PublicParticipantId
    occurred_at: AwareDatetime
    position: ParticipantLivePosition | None = None
    clear_reason: PositionClearReason | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        if self.event_type == "position_updated":
            if (
                self.position is None
                or self.clear_reason is not None
                or self.position.participant_id != self.participant_id
            ):
                raise ValueError("position-updated event payload is inconsistent")
        elif self.position is not None or self.clear_reason is None:
            raise ValueError("position-cleared event payload is inconsistent")
        return self
