"""Adapter-neutral persistence boundary for outing live positions."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sugarglider.outings.live_models import (
    SQLITE_SIGNED_INTEGER_MAX,
    OutingLiveEvent,
    ParticipantLivePosition,
    PositionClearReason,
)


class OutingLiveRepositoryError(Exception):
    """A live persistence operation failed without adapter details."""


class OutingLiveSequenceConflictError(OutingLiveRepositoryError):
    """A client sequence would not deterministically advance current state."""


class OutingLiveAuthorizationContextError(OutingLiveRepositoryError):
    """An authorized participant disappeared before a write transaction."""


@dataclass(frozen=True)
class OutingParticipantAuthorizationRecord:
    """Internal context required to authorize and mutate one participant."""

    outing_id: str
    participant_row_id: str
    participant_public_id: str
    participant_token_hash: bytes
    outing_expires_at_utc: datetime
    participant_join_order: int

    def __post_init__(self) -> None:
        if (
            not self.outing_id
            or not self.participant_row_id
            or not self.participant_public_id
            or len(self.participant_token_hash) != 32
            or self.outing_expires_at_utc.tzinfo is None
            or self.outing_expires_at_utc.utcoffset() is None
            or self.participant_join_order < 0
        ):
            raise ValueError("live authorization record is invalid")


@dataclass(frozen=True)
class OutingLivePositionRecord:
    """Validated authoritative current position plus immutable join order."""

    participant_row_id: str
    outing_id: str
    participant_public_id: str
    client_sequence: int
    latitude: float
    longitude: float
    accuracy_m: float
    altitude_m: float | None
    speed_m_s: float | None
    heading_deg: float | None
    captured_at_utc: datetime
    received_at_utc: datetime
    participant_join_order: int

    def __post_init__(self) -> None:
        optional_values_in_bounds = (
            self.altitude_m is None or -1_000 <= self.altitude_m <= 12_000
        ) and (self.speed_m_s is None or 0 <= self.speed_m_s <= 150)
        heading_in_bounds = self.heading_deg is None or 0 <= self.heading_deg < 360
        if (
            not self.participant_row_id
            or not self.outing_id
            or not self.participant_public_id
            or self.client_sequence < 0
            or self.client_sequence > SQLITE_SIGNED_INTEGER_MAX
            or not -90 <= self.latitude <= 90
            or not -180 <= self.longitude <= 180
            or not 0 <= self.accuracy_m <= 10_000
            or not optional_values_in_bounds
            or not heading_in_bounds
            or self.captured_at_utc.tzinfo is None
            or self.captured_at_utc.utcoffset() is None
            or self.received_at_utc.tzinfo is None
            or self.received_at_utc.utcoffset() is None
            or self.participant_join_order < 0
        ):
            raise ValueError("live position record is invalid")


@dataclass(frozen=True)
class OutingLiveEventRecord:
    """Validated durable event reconstructed from canonical JSON."""

    outing_id: str
    event: OutingLiveEvent

    def __post_init__(self) -> None:
        if not self.outing_id:
            raise ValueError("live event record is invalid")


@dataclass(frozen=True)
class OutingLiveSnapshotRecord:
    """Current database state and cursor for one extant outing."""

    outing_id: str
    public_slug: str
    outing_expires_at_utc: datetime
    cursor: int
    positions: tuple[OutingLivePositionRecord, ...]

    def __post_init__(self) -> None:
        if (
            not self.outing_id
            or not self.public_slug
            or self.outing_expires_at_utc.tzinfo is None
            or self.outing_expires_at_utc.utcoffset() is None
            or self.cursor < 0
            or self.cursor > SQLITE_SIGNED_INTEGER_MAX
            or any(position.outing_id != self.outing_id for position in self.positions)
        ):
            raise ValueError("live snapshot record is invalid")


@dataclass(frozen=True)
class OutingLiveEventWindow:
    """Bounds of the retained replay window for one extant outing."""

    outing_id: str
    current_cursor: int
    oldest_retained_event_id: int | None

    def __post_init__(self) -> None:
        if (
            not self.outing_id
            or self.current_cursor < 0
            or self.current_cursor > SQLITE_SIGNED_INTEGER_MAX
            or (
                self.oldest_retained_event_id is not None
                and (
                    self.oldest_retained_event_id < 1
                    or self.oldest_retained_event_id > self.current_cursor
                )
            )
        ):
            raise ValueError("live event window is invalid")


@dataclass(frozen=True)
class OutingLiveStreamStateRecord:
    """One transactionally consistent current snapshot and replay bound."""

    snapshot: OutingLiveSnapshotRecord
    oldest_retained_event_id: int | None

    def __post_init__(self) -> None:
        if self.oldest_retained_event_id is not None and (
            self.oldest_retained_event_id < 1
            or self.oldest_retained_event_id > self.snapshot.cursor
        ):
            raise ValueError("live stream state record is invalid")


@dataclass(frozen=True)
class OutingLiveMutationResult:
    """Result of an idempotent update or clear transaction."""

    position_record: OutingLivePositionRecord | None
    event: OutingLiveEvent | None


@dataclass(frozen=True)
class OutingParticipantRemovalResult:
    """Atomic participant removal and optional live clear event."""

    removed: bool
    event: OutingLiveEvent | None


class OutingLiveRepository(Protocol):
    def get_participant_authorization(
        self, slug: str, participant_public_id: str
    ) -> OutingParticipantAuthorizationRecord | None: ...

    def get_live_snapshot(self, slug: str) -> OutingLiveSnapshotRecord | None: ...

    def get_live_stream_state(
        self, slug: str
    ) -> OutingLiveStreamStateRecord | None: ...

    def upsert_live_position(
        self,
        authorization: OutingParticipantAuthorizationRecord,
        record: OutingLivePositionRecord,
        position: ParticipantLivePosition,
        *,
        occurred_at: datetime,
        retention_cutoff: datetime,
        maximum_event_count: int,
    ) -> OutingLiveMutationResult: ...

    def clear_live_position(
        self,
        authorization: OutingParticipantAuthorizationRecord,
        reason: PositionClearReason,
        *,
        occurred_at: datetime,
        retention_cutoff: datetime,
        maximum_event_count: int,
    ) -> OutingLiveMutationResult: ...

    def delete_participant_with_live_cleanup(
        self,
        authorization: OutingParticipantAuthorizationRecord,
        *,
        occurred_at: datetime,
        retention_cutoff: datetime,
        maximum_event_count: int,
    ) -> OutingParticipantRemovalResult: ...

    def expire_live_positions(
        self,
        *,
        slug: str | None,
        expiration_cutoff: datetime,
        occurred_at: datetime,
        retention_cutoff: datetime,
        maximum_event_count: int,
    ) -> tuple[OutingLiveEvent, ...]: ...

    def get_live_event_window(self, slug: str) -> OutingLiveEventWindow | None: ...

    def get_live_events_after(
        self, slug: str, event_id: int, *, limit: int
    ) -> tuple[OutingLiveEventRecord, ...] | None: ...

    def purge_live_events(self, cutoff: datetime) -> int: ...

    def delete_expired_outing(self, slug: str, now: datetime) -> bool: ...
