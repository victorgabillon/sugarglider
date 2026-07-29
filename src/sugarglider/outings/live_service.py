"""Policy and public reconstruction for durable outing live positions."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from pydantic import ValidationError

from sugarglider.outings.errors import (
    OutingNotFoundError,
    OutingPositionInvalidError,
    OutingPositionSequenceConflictError,
    OutingStorageError,
)
from sugarglider.outings.live_models import (
    LiveCoordinate,
    OutingLiveEvent,
    OutingLiveSnapshot,
    OutingPositionUpdate,
    ParticipantLivePosition,
)
from sugarglider.outings.live_repository import (
    OutingLiveAuthorizationContextError,
    OutingLiveEventWindow,
    OutingLivePositionRecord,
    OutingLiveRepository,
    OutingLiveRepositoryError,
    OutingLiveSequenceConflictError,
    OutingParticipantAuthorizationRecord,
)

_EVENT_READ_LIMIT = 100_000


@dataclass(frozen=True)
class LivePositionMutation:
    """Public update result plus whether durable replay state advanced."""

    position: ParticipantLivePosition
    event_appended: bool


@dataclass(frozen=True)
class LiveStreamState:
    """One public snapshot and its transactionally consistent replay bound."""

    outing_id: str
    snapshot: OutingLiveSnapshot
    oldest_retained_event_id: int | None


class OutingLiveOperations(Protocol):
    """API-facing contract for available and unavailable live services."""

    available: bool
    keepalive_seconds: int

    def authorize_participant(
        self,
        slug: str,
        participant_id: str,
        participant_token: str | None,
    ) -> None: ...

    def update_position(
        self,
        slug: str,
        participant_id: str,
        participant_token: str | None,
        update: OutingPositionUpdate,
    ) -> LivePositionMutation: ...

    def clear_position(
        self,
        slug: str,
        participant_id: str,
        participant_token: str | None,
    ) -> bool: ...

    def snapshot(self, slug: str) -> OutingLiveSnapshot: ...

    def stream_state(self, slug: str) -> LiveStreamState: ...

    def event_window(self, slug: str) -> OutingLiveEventWindow: ...

    def events_after(self, slug: str, event_id: int) -> tuple[OutingLiveEvent, ...]: ...

    def expire_positions(self, slug: str | None = None) -> int: ...

    def startup_cleanup(self) -> None: ...


class OutingLiveService:
    """Own live authorization, timestamps, sequence policy, and public models."""

    available = True

    def __init__(
        self,
        repository: OutingLiveRepository,
        *,
        stale_after_seconds: int = 120,
        expire_after_seconds: int = 3_600,
        maximum_update_age_seconds: int = 600,
        future_tolerance_seconds: int = 30,
        event_retention_seconds: int = 900,
        maximum_events_per_outing: int = 1_000,
        keepalive_seconds: int = 15,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not 15 <= stale_after_seconds <= 3_600:
            raise ValueError("live stale duration is out of bounds")
        if not 60 <= expire_after_seconds <= 86_400:
            raise ValueError("live expiry duration is out of bounds")
        if stale_after_seconds >= expire_after_seconds:
            raise ValueError("live stale duration must be below expiry duration")
        if not 30 <= maximum_update_age_seconds <= 86_400:
            raise ValueError("live maximum update age is out of bounds")
        if not 0 <= future_tolerance_seconds <= 600:
            raise ValueError("live future tolerance is out of bounds")
        if not 60 <= event_retention_seconds <= 86_400:
            raise ValueError("live event retention is out of bounds")
        if not 10 <= maximum_events_per_outing <= 100_000:
            raise ValueError("live event maximum is out of bounds")
        if not 5 <= keepalive_seconds <= 60:
            raise ValueError("live SSE keepalive is out of bounds")
        if keepalive_seconds >= event_retention_seconds:
            raise ValueError("live SSE keepalive must be below event retention")
        self._repository = repository
        self._stale_after = timedelta(seconds=stale_after_seconds)
        self._expire_after = timedelta(seconds=expire_after_seconds)
        self._maximum_update_age = timedelta(seconds=maximum_update_age_seconds)
        self._future_tolerance = timedelta(seconds=future_tolerance_seconds)
        self._event_retention = timedelta(seconds=event_retention_seconds)
        self._maximum_events = maximum_events_per_outing
        self.keepalive_seconds = keepalive_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    def authorize_participant(
        self,
        slug: str,
        participant_id: str,
        participant_token: str | None,
    ) -> None:
        self._ensure_unexpired(slug, self._now())
        authorization = self._authorization(slug, participant_id)
        if not _authorized(authorization.participant_token_hash, participant_token):
            raise OutingNotFoundError

    def update_position(
        self,
        slug: str,
        participant_id: str,
        participant_token: str | None,
        update: OutingPositionUpdate,
    ) -> LivePositionMutation:
        received_at = self._now()
        self._ensure_unexpired(slug, received_at)
        self._expire(slug, received_at)
        authorization = self._authorization(slug, participant_id)
        if not _authorized(authorization.participant_token_hash, participant_token):
            raise OutingNotFoundError
        captured_at = _utc_position_timestamp(update.captured_at)
        if (
            captured_at < received_at - self._maximum_update_age
            or captured_at > received_at + self._future_tolerance
        ):
            raise OutingPositionInvalidError
        position = ParticipantLivePosition(
            participant_id=participant_id,
            sequence=update.sequence,
            coordinate=update.coordinate,
            accuracy_m=update.accuracy_m,
            altitude_m=update.altitude_m,
            speed_m_s=update.speed_m_s,
            heading_deg=update.heading_deg,
            captured_at=captured_at,
            received_at=received_at,
            stale_at=received_at + self._stale_after,
            expires_at=received_at + self._expire_after,
        )
        record = OutingLivePositionRecord(
            participant_row_id=authorization.participant_row_id,
            outing_id=authorization.outing_id,
            participant_public_id=authorization.participant_public_id,
            client_sequence=update.sequence,
            latitude=update.coordinate.lat,
            longitude=update.coordinate.lon,
            accuracy_m=update.accuracy_m,
            altitude_m=update.altitude_m,
            speed_m_s=update.speed_m_s,
            heading_deg=update.heading_deg,
            captured_at_utc=captured_at,
            received_at_utc=received_at,
            participant_join_order=authorization.participant_join_order,
        )
        try:
            result = self._repository.upsert_live_position(
                authorization,
                record,
                position,
                occurred_at=received_at,
                retention_cutoff=received_at - self._event_retention,
                maximum_event_count=self._maximum_events,
            )
        except OutingLiveSequenceConflictError as exc:
            raise OutingPositionSequenceConflictError from exc
        except OutingLiveAuthorizationContextError as exc:
            raise OutingNotFoundError from exc
        except OutingLiveRepositoryError as exc:
            raise OutingStorageError from exc
        if result.position_record is None:
            raise OutingStorageError
        return LivePositionMutation(
            position=self._public_position(result.position_record),
            event_appended=result.event is not None,
        )

    def clear_position(
        self,
        slug: str,
        participant_id: str,
        participant_token: str | None,
    ) -> bool:
        now = self._now()
        self._ensure_unexpired(slug, now)
        authorization = self._authorization(slug, participant_id)
        if not _authorized(authorization.participant_token_hash, participant_token):
            raise OutingNotFoundError
        try:
            result = self._repository.clear_live_position(
                authorization,
                "stopped",
                occurred_at=now,
                retention_cutoff=now - self._event_retention,
                maximum_event_count=self._maximum_events,
            )
        except OutingLiveAuthorizationContextError as exc:
            raise OutingNotFoundError from exc
        except OutingLiveRepositoryError as exc:
            raise OutingStorageError from exc
        return result.event is not None

    def snapshot(self, slug: str) -> OutingLiveSnapshot:
        return self.stream_state(slug).snapshot

    def stream_state(self, slug: str) -> LiveStreamState:
        now = self._now()
        self._ensure_unexpired(slug, now)
        self._expire(slug, now)
        try:
            state = self._repository.get_live_stream_state(slug)
        except OutingLiveRepositoryError as exc:
            raise OutingStorageError from exc
        if state is None or state.snapshot.outing_expires_at_utc <= now:
            raise OutingNotFoundError
        record = state.snapshot
        try:
            return LiveStreamState(
                outing_id=record.outing_id,
                snapshot=OutingLiveSnapshot(
                    slug=record.public_slug,
                    generated_at=now,
                    cursor=record.cursor,
                    stale_after_seconds=int(self._stale_after.total_seconds()),
                    expire_after_seconds=int(self._expire_after.total_seconds()),
                    positions=tuple(
                        self._public_position(position) for position in record.positions
                    ),
                ),
                oldest_retained_event_id=state.oldest_retained_event_id,
            )
        except (ValidationError, ValueError) as exc:
            raise OutingStorageError from exc

    def event_window(self, slug: str) -> OutingLiveEventWindow:
        state = self.stream_state(slug)
        return OutingLiveEventWindow(
            outing_id=state.outing_id,
            current_cursor=state.snapshot.cursor,
            oldest_retained_event_id=state.oldest_retained_event_id,
        )

    def events_after(self, slug: str, event_id: int) -> tuple[OutingLiveEvent, ...]:
        self._ensure_unexpired(slug, self._now())
        try:
            records = self._repository.get_live_events_after(
                slug,
                event_id,
                limit=_EVENT_READ_LIMIT,
            )
        except OutingLiveRepositoryError as exc:
            raise OutingStorageError from exc
        if records is None:
            raise OutingNotFoundError
        events = tuple(record.event for record in records)
        for event in events:
            if event.position is not None:
                self._validate_position_timestamp_policy(event.position)
        return events

    def expire_positions(self, slug: str | None = None) -> int:
        return len(self._expire(slug, self._now()))

    def startup_cleanup(self) -> None:
        now = self._now()
        self._expire(None, now)
        try:
            self._repository.purge_live_events(now - self._event_retention)
        except OutingLiveRepositoryError as exc:
            raise OutingStorageError from exc

    def _authorization(
        self, slug: str, participant_id: str
    ) -> OutingParticipantAuthorizationRecord:
        try:
            authorization = self._repository.get_participant_authorization(
                slug, participant_id
            )
        except OutingLiveRepositoryError as exc:
            raise OutingStorageError from exc
        if authorization is None:
            raise OutingNotFoundError
        now = self._now()
        if authorization.outing_expires_at_utc <= now:
            self._ensure_unexpired(slug, now)
            raise OutingNotFoundError
        return authorization

    def _expire(self, slug: str | None, now: datetime) -> tuple[OutingLiveEvent, ...]:
        try:
            return self._repository.expire_live_positions(
                slug=slug,
                expiration_cutoff=now - self._expire_after,
                occurred_at=now,
                retention_cutoff=now - self._event_retention,
                maximum_event_count=self._maximum_events,
            )
        except OutingLiveRepositoryError as exc:
            raise OutingStorageError from exc

    def _public_position(
        self, record: OutingLivePositionRecord
    ) -> ParticipantLivePosition:
        try:
            position = ParticipantLivePosition(
                participant_id=record.participant_public_id,
                sequence=record.client_sequence,
                coordinate=LiveCoordinate(
                    lat=record.latitude,
                    lon=record.longitude,
                ),
                accuracy_m=record.accuracy_m,
                altitude_m=record.altitude_m,
                speed_m_s=record.speed_m_s,
                heading_deg=record.heading_deg,
                captured_at=record.captured_at_utc,
                received_at=record.received_at_utc,
                stale_at=record.received_at_utc + self._stale_after,
                expires_at=record.received_at_utc + self._expire_after,
            )
            self._validate_position_timestamp_policy(position)
            return position
        except (ValidationError, ValueError) as exc:
            raise OutingStorageError from exc

    def _validate_position_timestamp_policy(
        self, position: ParticipantLivePosition
    ) -> None:
        if (
            position.captured_at < position.received_at - self._maximum_update_age
            or position.captured_at > position.received_at + self._future_tolerance
            or not position.received_at < position.stale_at < position.expires_at
        ):
            raise OutingStorageError

    def _ensure_unexpired(self, slug: str, now: datetime) -> None:
        try:
            deleted = self._repository.delete_expired_outing(slug, now)
        except OutingLiveRepositoryError as exc:
            raise OutingStorageError from exc
        if deleted:
            raise OutingNotFoundError

    def _now(self) -> datetime:
        try:
            return _utc_position_timestamp(self._clock())
        except OutingPositionInvalidError as exc:
            raise OutingStorageError from exc


class UnavailableOutingLiveService:
    """Nonfatal live service used when shared outing storage is unavailable."""

    available = False
    keepalive_seconds = 15

    def authorize_participant(
        self,
        slug: str,
        participant_id: str,
        participant_token: str | None,
    ) -> None:
        del slug, participant_id, participant_token
        raise OutingStorageError

    def update_position(
        self,
        slug: str,
        participant_id: str,
        participant_token: str | None,
        update: OutingPositionUpdate,
    ) -> LivePositionMutation:
        del slug, participant_id, participant_token, update
        raise OutingStorageError

    def clear_position(
        self,
        slug: str,
        participant_id: str,
        participant_token: str | None,
    ) -> bool:
        del slug, participant_id, participant_token
        raise OutingStorageError

    def snapshot(self, slug: str) -> OutingLiveSnapshot:
        del slug
        raise OutingStorageError

    def stream_state(self, slug: str) -> LiveStreamState:
        del slug
        raise OutingStorageError

    def event_window(self, slug: str) -> OutingLiveEventWindow:
        del slug
        raise OutingStorageError

    def events_after(self, slug: str, event_id: int) -> tuple[OutingLiveEvent, ...]:
        del slug, event_id
        raise OutingStorageError

    def expire_positions(self, slug: str | None = None) -> int:
        del slug
        raise OutingStorageError

    def startup_cleanup(self) -> None:
        raise OutingStorageError


def _authorized(expected: bytes, token: str | None) -> bool:
    supplied = hashlib.sha256((token or "").encode()).digest()
    return token is not None and hmac.compare_digest(expected, supplied)


def _utc_position_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise OutingPositionInvalidError
    return value.astimezone(UTC)
