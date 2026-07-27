"""Immutable saved-route application service."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from pydantic import ValidationError

from sugarglider.planning.models import PLAN_REQUEST_ADAPTER
from sugarglider.planning.result import PlanCandidate
from sugarglider.planning.submitted_candidate import (
    SubmittedCandidateInvalidError,
    validate_submitted_candidate,
)
from sugarglider.saved_routes.errors import (
    SavedRouteCollisionExhaustedError,
    SavedRouteInvalidSnapshotError,
    SavedRouteNotFoundError,
    SavedRouteStorageError,
    SavedRouteTooLargeError,
)
from sugarglider.saved_routes.models import (
    SavedRouteCreated,
    SavedRouteCreateRequest,
    SavedRouteSnapshot,
    created_response,
)
from sugarglider.saved_routes.repository import (
    SavedRouteRecord,
    SavedRouteRepository,
    SavedRouteRepositoryError,
    SavedRouteSlugCollisionError,
)

_CREATE_ATTEMPTS = 5


class SavedRouteOperations(Protocol):
    """API-facing service contract, including an unavailable implementation."""

    available: bool

    def create(self, request: SavedRouteCreateRequest) -> SavedRouteCreated: ...

    def get(self, slug: str) -> SavedRouteSnapshot: ...

    def delete(self, slug: str, owner_token: str | None) -> None: ...


class SavedRouteService:
    """Own trust validation, expiry, capabilities, and strict serialization."""

    available = True

    def __init__(
        self,
        repository: SavedRouteRepository,
        *,
        ttl_days: int = 90,
        maximum_snapshot_bytes: int = 10_000_000,
        clock: Callable[[], datetime] | None = None,
        slug_factory: Callable[[], str] | None = None,
        owner_token_factory: Callable[[], str] | None = None,
        route_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if not 1 <= ttl_days <= 365:
            raise ValueError("saved-route TTL must be between 1 and 365 days")
        if maximum_snapshot_bytes < 1:
            raise ValueError("saved-route snapshot limit must be positive")
        self._repository = repository
        self._ttl_days = ttl_days
        self._maximum_snapshot_bytes = maximum_snapshot_bytes
        self._clock = clock or (lambda: datetime.now(UTC))
        self._slug_factory = slug_factory or (lambda: secrets.token_urlsafe(16))
        self._owner_token_factory = owner_token_factory or (
            lambda: secrets.token_urlsafe(32)
        )
        self._route_id_factory = route_id_factory or (lambda: str(uuid.uuid4()))

    def create(self, request: SavedRouteCreateRequest) -> SavedRouteCreated:
        """Validate and persist one exact canonical request/candidate snapshot."""
        try:
            validate_submitted_candidate(request.source_request, request.candidate)
        except SubmittedCandidateInvalidError as exc:
            raise SavedRouteInvalidSnapshotError from exc
        source_json = request.source_request.model_dump_json()
        candidate_json = request.candidate.model_dump_json()
        payload_bytes = len(source_json.encode()) + len(candidate_json.encode())
        if payload_bytes > self._maximum_snapshot_bytes:
            raise SavedRouteTooLargeError
        created_at = _utc(self._clock())
        expires_at = created_at + timedelta(days=self._ttl_days)
        owner_token = self._owner_token_factory()
        if len(owner_token) < 32:
            raise SavedRouteStorageError
        owner_hash = hashlib.sha256(owner_token.encode()).digest()
        for _attempt in range(_CREATE_ATTEMPTS):
            slug = self._slug_factory()
            if not _valid_slug(slug):
                raise SavedRouteStorageError
            record = SavedRouteRecord(
                id=self._route_id_factory(),
                schema_version=1,
                public_slug=slug,
                owner_token_hash=owner_hash,
                source_request_json=source_json,
                candidate_json=candidate_json,
                created_at_utc=created_at,
                expires_at_utc=expires_at,
            )
            try:
                self._repository.create(record)
            except SavedRouteSlugCollisionError:
                continue
            except SavedRouteRepositoryError as exc:
                raise SavedRouteStorageError from exc
            snapshot = _snapshot(record)
            return created_response(snapshot, owner_token)
        raise SavedRouteCollisionExhaustedError

    def get(self, slug: str) -> SavedRouteSnapshot:
        """Return one unexpired, strictly reconstructed public snapshot."""
        record = self._record(slug)
        return _snapshot(record)

    def delete(self, slug: str, owner_token: str | None) -> None:
        """Delete only with the creation-time owner capability."""
        record = self._record(slug)
        supplied_hash = hashlib.sha256((owner_token or "").encode()).digest()
        if owner_token is None or not hmac.compare_digest(
            record.owner_token_hash, supplied_hash
        ):
            raise SavedRouteNotFoundError
        try:
            deleted = self._repository.delete_by_id(record.id)
        except SavedRouteRepositoryError as exc:
            raise SavedRouteStorageError from exc
        if not deleted:
            raise SavedRouteNotFoundError

    def purge_expired(self) -> int:
        """Remove expired records during application startup."""
        try:
            return self._repository.purge_expired(_utc(self._clock()))
        except SavedRouteRepositoryError as exc:
            raise SavedRouteStorageError from exc

    def _record(self, slug: str) -> SavedRouteRecord:
        try:
            record = self._repository.get_by_slug(slug)
        except SavedRouteRepositoryError as exc:
            raise SavedRouteStorageError from exc
        if record is None:
            raise SavedRouteNotFoundError
        if record.expires_at_utc <= _utc(self._clock()):
            try:
                self._repository.delete_by_id(record.id)
            except SavedRouteRepositoryError as exc:
                raise SavedRouteStorageError from exc
            raise SavedRouteNotFoundError
        return record


class UnavailableSavedRouteService:
    """Typed nonfatal service installed when persistence is disabled or unavailable."""

    available = False

    def create(self, request: SavedRouteCreateRequest) -> SavedRouteCreated:
        del request
        raise SavedRouteStorageError

    def get(self, slug: str) -> SavedRouteSnapshot:
        del slug
        raise SavedRouteStorageError

    def delete(self, slug: str, owner_token: str | None) -> None:
        del slug, owner_token
        raise SavedRouteStorageError


def _snapshot(record: SavedRouteRecord) -> SavedRouteSnapshot:
    try:
        request = PLAN_REQUEST_ADAPTER.validate_json(record.source_request_json)
        candidate = PlanCandidate.model_validate_json(record.candidate_json)
        validate_submitted_candidate(request, candidate)
        return SavedRouteSnapshot(
            slug=record.public_slug,
            created_at=record.created_at_utc,
            expires_at=record.expires_at_utc,
            source_request=request,
            candidate=candidate,
        )
    except (ValidationError, SubmittedCandidateInvalidError, ValueError) as exc:
        raise SavedRouteStorageError from exc


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SavedRouteStorageError
    return value.astimezone(UTC)


def _valid_slug(value: str) -> bool:
    return 20 <= len(value) <= 64 and all(
        character.isascii() and (character.isalnum() or character in "_-")
        for character in value
    )
