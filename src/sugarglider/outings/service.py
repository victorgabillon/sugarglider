"""Application service for shared outings with independent route snapshots."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import unicodedata
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from pydantic import ValidationError

from sugarglider.outings.errors import (
    OutingCandidateInvalidError,
    OutingCollisionExhaustedError,
    OutingFullError,
    OutingNotFoundError,
    OutingRouteTooLargeError,
    OutingStorageError,
)
from sugarglider.outings.live_repository import (
    OutingLiveAuthorizationContextError,
    OutingLiveRepository,
    OutingLiveRepositoryError,
    OutingParticipantAuthorizationRecord,
)
from sugarglider.outings.models import (
    AvatarKey,
    OutingCreated,
    OutingParticipantJoined,
    OutingParticipantSnapshot,
    OutingPlannedRoute,
    OutingSnapshot,
)
from sugarglider.outings.repository import (
    OutingAggregateRecord,
    OutingCapacityReachedError,
    OutingParticipantRecord,
    OutingRecord,
    OutingRepository,
    OutingRepositoryError,
    OutingSlugCollisionError,
    ParticipantIdCollisionError,
)
from sugarglider.planning.models import PLAN_REQUEST_ADAPTER
from sugarglider.planning.result import PlanCandidate
from sugarglider.planning.submitted_candidate import (
    SubmittedCandidateInvalidError,
    validate_submitted_candidate,
)

_COLLISION_ATTEMPTS = 5


class OutingOperations(Protocol):
    """API-facing contract implemented by available and unavailable services."""

    available: bool

    def create(
        self,
        title: str,
        participant_display_name: str,
        planned_route: OutingPlannedRoute,
        participant_avatar_key: AvatarKey = "blue",
    ) -> OutingCreated: ...

    def get(self, slug: str) -> OutingSnapshot: ...

    def authorize_join(self, slug: str, join_token: str | None) -> None: ...

    def join(
        self,
        slug: str,
        join_token: str | None,
        display_name: str,
        planned_route: OutingPlannedRoute,
        avatar_key: AvatarKey = "blue",
    ) -> OutingParticipantJoined: ...

    def participant_route(
        self, slug: str, participant_id: str
    ) -> OutingPlannedRoute: ...

    def remove_participant(
        self,
        slug: str,
        participant_id: str,
        participant_token: str | None,
    ) -> bool: ...

    def delete(self, slug: str, owner_token: str | None) -> None: ...


class OutingService:
    """Own copying, validation, capabilities, expiry, and public reconstruction."""

    available = True

    def __init__(
        self,
        repository: OutingRepository,
        *,
        ttl_days: int = 30,
        max_participants: int = 8,
        maximum_route_snapshot_bytes: int = 10_000_000,
        clock: Callable[[], datetime] | None = None,
        slug_factory: Callable[[], str] | None = None,
        owner_token_factory: Callable[[], str] | None = None,
        join_token_factory: Callable[[], str] | None = None,
        participant_token_factory: Callable[[], str] | None = None,
        participant_public_id_factory: Callable[[], str] | None = None,
        outing_id_factory: Callable[[], str] | None = None,
        participant_id_factory: Callable[[], str] | None = None,
        live_repository: OutingLiveRepository | None = None,
        live_event_retention_seconds: int = 900,
        live_maximum_events_per_outing: int = 1_000,
    ) -> None:
        if not 1 <= ttl_days <= 365:
            raise ValueError("outing TTL must be between 1 and 365 days")
        if not 2 <= max_participants <= 20:
            raise ValueError("outing capacity must be between 2 and 20")
        if not 100_000 <= maximum_route_snapshot_bytes <= 50_000_000:
            raise ValueError("outing route snapshot limit is out of bounds")
        if not 60 <= live_event_retention_seconds <= 86_400:
            raise ValueError("outing live event retention is out of bounds")
        if not 10 <= live_maximum_events_per_outing <= 100_000:
            raise ValueError("outing live event maximum is out of bounds")
        self._repository = repository
        self._ttl_days = ttl_days
        self._max_participants = max_participants
        self._maximum_route_snapshot_bytes = maximum_route_snapshot_bytes
        self._clock = clock or (lambda: datetime.now(UTC))
        self._slug_factory = slug_factory or (lambda: secrets.token_urlsafe(16))
        self._owner_token_factory = owner_token_factory or (
            lambda: secrets.token_urlsafe(32)
        )
        self._join_token_factory = join_token_factory or (
            lambda: secrets.token_urlsafe(32)
        )
        self._participant_token_factory = participant_token_factory or (
            lambda: secrets.token_urlsafe(32)
        )
        self._participant_public_id_factory = participant_public_id_factory or (
            lambda: secrets.token_urlsafe(16)
        )
        self._outing_id_factory = outing_id_factory or (lambda: str(uuid.uuid4()))
        self._participant_id_factory = participant_id_factory or (
            lambda: str(uuid.uuid4())
        )
        self._live_repository = live_repository
        self._live_event_retention = timedelta(seconds=live_event_retention_seconds)
        self._live_maximum_events = live_maximum_events_per_outing

    def create(
        self,
        title: str,
        participant_display_name: str,
        planned_route: OutingPlannedRoute,
        participant_avatar_key: AvatarKey = "blue",
    ) -> OutingCreated:
        source_json, candidate_json = self._validated_route_json(planned_route)
        title = _text(title, maximum=120)
        participant_display_name = _text(participant_display_name, maximum=80)
        created_at = _utc(self._clock())
        expires_at = created_at + timedelta(days=self._ttl_days)
        owner_token = self._capability(self._owner_token_factory())
        join_token = self._capability(self._join_token_factory())
        participant_token = self._capability(self._participant_token_factory())
        owner_hash = _hash(owner_token)
        join_hash = _hash(join_token)
        participant_hash = _hash(participant_token)

        for _attempt in range(_COLLISION_ATTEMPTS):
            slug = self._identifier(self._slug_factory())
            public_id = self._identifier(self._participant_public_id_factory())
            outing = OutingRecord(
                id=self._outing_id_factory(),
                schema_version=1,
                public_slug=slug,
                owner_token_hash=owner_hash,
                join_token_hash=join_hash,
                title=title,
                created_at_utc=created_at,
                expires_at_utc=expires_at,
                max_participants=self._max_participants,
            )
            participant = OutingParticipantRecord(
                id=self._participant_id_factory(),
                outing_id=outing.id,
                public_id=public_id,
                participant_token_hash=participant_hash,
                display_name=participant_display_name,
                avatar_key=participant_avatar_key,
                source_request_json=source_json,
                candidate_json=candidate_json,
                joined_at_utc=created_at,
                join_order=0,
            )
            try:
                self._repository.create(outing, participant)
            except (OutingSlugCollisionError, ParticipantIdCollisionError):
                continue
            except OutingRepositoryError as exc:
                raise OutingStorageError from exc
            snapshot = self._snapshot(
                OutingAggregateRecord(outing=outing, participants=(participant,))
            )
            return OutingCreated(
                **snapshot.model_dump(),
                owner_token=owner_token,
                join_token=join_token,
                participant_id=public_id,
                participant_token=participant_token,
                share_path=f"/o/{slug}",
                invite_path=f"/o/{slug}#invite={join_token}",
            )
        raise OutingCollisionExhaustedError

    def get(self, slug: str) -> OutingSnapshot:
        return self._snapshot(self._aggregate(slug))

    def authorize_join(self, slug: str, join_token: str | None) -> None:
        aggregate = self._aggregate(slug)
        if not _authorized(aggregate.outing.join_token_hash, join_token):
            raise OutingNotFoundError
        if len(aggregate.participants) >= aggregate.outing.max_participants:
            raise OutingFullError

    def join(
        self,
        slug: str,
        join_token: str | None,
        display_name: str,
        planned_route: OutingPlannedRoute,
        avatar_key: AvatarKey = "blue",
    ) -> OutingParticipantJoined:
        aggregate = self._aggregate(slug)
        if not _authorized(aggregate.outing.join_token_hash, join_token):
            raise OutingNotFoundError
        if len(aggregate.participants) >= aggregate.outing.max_participants:
            raise OutingFullError
        source_json, candidate_json = self._validated_route_json(planned_route)
        display_name = _text(display_name, maximum=80)
        participant_token = self._capability(self._participant_token_factory())
        joined_at = _utc(self._clock())
        for _attempt in range(_COLLISION_ATTEMPTS):
            public_id = self._identifier(self._participant_public_id_factory())
            participant = OutingParticipantRecord(
                id=self._participant_id_factory(),
                outing_id=aggregate.outing.id,
                public_id=public_id,
                participant_token_hash=_hash(participant_token),
                display_name=display_name,
                avatar_key=avatar_key,
                source_request_json=source_json,
                candidate_json=candidate_json,
                joined_at_utc=joined_at,
                join_order=0,
            )
            try:
                self._repository.add_participant(
                    aggregate.outing.id,
                    participant,
                    maximum_participants=aggregate.outing.max_participants,
                )
            except ParticipantIdCollisionError:
                continue
            except OutingCapacityReachedError as exc:
                raise OutingFullError from exc
            except OutingRepositoryError as exc:
                raise OutingStorageError from exc
            updated = self._aggregate(slug)
            return OutingParticipantJoined(
                outing=self._snapshot(updated),
                participant_id=public_id,
                participant_token=participant_token,
            )
        raise OutingCollisionExhaustedError

    def participant_route(self, slug: str, participant_id: str) -> OutingPlannedRoute:
        aggregate = self._aggregate(slug)
        for participant in aggregate.participants:
            if participant.public_id == participant_id:
                return self._planned_route(participant)
        raise OutingNotFoundError

    def remove_participant(
        self,
        slug: str,
        participant_id: str,
        participant_token: str | None,
    ) -> bool:
        aggregate = self._aggregate(slug)
        participant = next(
            (
                item
                for item in aggregate.participants
                if item.public_id == participant_id
            ),
            None,
        )
        if participant is None or not _authorized(
            participant.participant_token_hash, participant_token
        ):
            raise OutingNotFoundError
        try:
            if self._live_repository is None:
                removed = self._repository.delete_participant(
                    aggregate.outing.id, participant_id
                )
                live_changed = False
            else:
                now = _utc(self._clock())
                result = self._live_repository.delete_participant_with_live_cleanup(
                    OutingParticipantAuthorizationRecord(
                        outing_id=aggregate.outing.id,
                        participant_row_id=participant.id,
                        participant_public_id=participant.public_id,
                        participant_token_hash=participant.participant_token_hash,
                        outing_expires_at_utc=aggregate.outing.expires_at_utc,
                        participant_join_order=participant.join_order,
                    ),
                    occurred_at=now,
                    retention_cutoff=now - self._live_event_retention,
                    maximum_event_count=self._live_maximum_events,
                )
                removed = result.removed
                live_changed = result.event is not None
        except OutingLiveAuthorizationContextError as exc:
            raise OutingNotFoundError from exc
        except (OutingRepositoryError, OutingLiveRepositoryError) as exc:
            raise OutingStorageError from exc
        if not removed:
            raise OutingNotFoundError
        return live_changed

    def delete(self, slug: str, owner_token: str | None) -> None:
        aggregate = self._aggregate(slug)
        if not _authorized(aggregate.outing.owner_token_hash, owner_token):
            raise OutingNotFoundError
        try:
            deleted = self._repository.delete_outing_by_id(aggregate.outing.id)
        except OutingRepositoryError as exc:
            raise OutingStorageError from exc
        if not deleted:
            raise OutingNotFoundError

    def purge_expired(self) -> int:
        try:
            return self._repository.purge_expired(_utc(self._clock()))
        except OutingRepositoryError as exc:
            raise OutingStorageError from exc

    def _aggregate(self, slug: str) -> OutingAggregateRecord:
        try:
            aggregate = self._repository.get_by_slug(slug)
        except OutingRepositoryError as exc:
            raise OutingStorageError from exc
        if aggregate is None:
            raise OutingNotFoundError
        if aggregate.outing.expires_at_utc <= _utc(self._clock()):
            try:
                self._repository.delete_outing_by_id(aggregate.outing.id)
            except OutingRepositoryError as exc:
                raise OutingStorageError from exc
            raise OutingNotFoundError
        return aggregate

    def _snapshot(self, aggregate: OutingAggregateRecord) -> OutingSnapshot:
        try:
            participants = tuple(
                OutingParticipantSnapshot(
                    participant_id=participant.public_id,
                    display_name=participant.display_name,
                    avatar_key=participant.avatar_key,
                    joined_at=participant.joined_at_utc,
                    planned_route=self._planned_route(participant),
                )
                for participant in sorted(
                    aggregate.participants, key=lambda value: value.join_order
                )
            )
            return OutingSnapshot(
                slug=aggregate.outing.public_slug,
                title=aggregate.outing.title,
                created_at=aggregate.outing.created_at_utc,
                expires_at=aggregate.outing.expires_at_utc,
                max_participants=aggregate.outing.max_participants,
                participants=participants,
            )
        except (ValidationError, ValueError) as exc:
            raise OutingStorageError from exc

    def _planned_route(
        self, participant: OutingParticipantRecord
    ) -> OutingPlannedRoute:
        try:
            request = PLAN_REQUEST_ADAPTER.validate_json(
                participant.source_request_json
            )
            candidate = PlanCandidate.model_validate_json(participant.candidate_json)
            validate_submitted_candidate(request, candidate)
            return OutingPlannedRoute(
                source_request=request,
                candidate=candidate,
            )
        except (ValidationError, SubmittedCandidateInvalidError, ValueError) as exc:
            raise OutingStorageError from exc

    def _validated_route_json(
        self, planned_route: OutingPlannedRoute
    ) -> tuple[str, str]:
        try:
            validate_submitted_candidate(
                planned_route.source_request, planned_route.candidate
            )
        except SubmittedCandidateInvalidError as exc:
            raise OutingCandidateInvalidError from exc
        source_json = planned_route.source_request.model_dump_json()
        candidate_json = planned_route.candidate.model_dump_json()
        size = len(source_json.encode()) + len(candidate_json.encode())
        if size > self._maximum_route_snapshot_bytes:
            raise OutingRouteTooLargeError
        try:
            reconstructed_request = PLAN_REQUEST_ADAPTER.validate_json(source_json)
            reconstructed_candidate = PlanCandidate.model_validate_json(candidate_json)
            if (
                reconstructed_request != planned_route.source_request
                or reconstructed_candidate != planned_route.candidate
            ):
                raise OutingCandidateInvalidError
        except ValidationError as exc:
            raise OutingCandidateInvalidError from exc
        return source_json, candidate_json

    @staticmethod
    def _capability(value: str) -> str:
        if not 32 <= len(value) <= 128:
            raise OutingStorageError
        return value

    @staticmethod
    def _identifier(value: str) -> str:
        if not _valid_identifier(value):
            raise OutingStorageError
        return value


class UnavailableOutingService:
    """Nonfatal service used when outing storage is disabled or unavailable."""

    available = False

    def create(
        self,
        title: str,
        participant_display_name: str,
        planned_route: OutingPlannedRoute,
        participant_avatar_key: AvatarKey = "blue",
    ) -> OutingCreated:
        del title, participant_display_name, planned_route, participant_avatar_key
        raise OutingStorageError

    def get(self, slug: str) -> OutingSnapshot:
        del slug
        raise OutingStorageError

    def authorize_join(self, slug: str, join_token: str | None) -> None:
        del slug, join_token
        raise OutingStorageError

    def join(
        self,
        slug: str,
        join_token: str | None,
        display_name: str,
        planned_route: OutingPlannedRoute,
        avatar_key: AvatarKey = "blue",
    ) -> OutingParticipantJoined:
        del slug, join_token, display_name, planned_route, avatar_key
        raise OutingStorageError

    def participant_route(self, slug: str, participant_id: str) -> OutingPlannedRoute:
        del slug, participant_id
        raise OutingStorageError

    def remove_participant(
        self,
        slug: str,
        participant_id: str,
        participant_token: str | None,
    ) -> bool:
        del slug, participant_id, participant_token
        raise OutingStorageError

    def delete(self, slug: str, owner_token: str | None) -> None:
        del slug, owner_token
        raise OutingStorageError


def _authorized(expected: bytes, token: str | None) -> bool:
    supplied = _hash(token or "")
    return token is not None and hmac.compare_digest(expected, supplied)


def _hash(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise OutingStorageError
    return value.astimezone(UTC)


def _valid_identifier(value: str) -> bool:
    return 20 <= len(value) <= 64 and all(
        character.isascii() and (character.isalnum() or character in "_-")
        for character in value
    )


def _text(value: str, *, maximum: int) -> str:
    stripped = value.strip()
    if not 1 <= len(stripped) <= maximum or any(
        unicodedata.category(character).startswith("C") for character in stripped
    ):
        raise OutingStorageError
    return stripped
