"""Typed persistence boundary for saved-route snapshots."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class SavedRouteRepositoryError(Exception):
    """A persistence operation failed without exposing adapter details."""


class SavedRouteSlugCollisionError(SavedRouteRepositoryError):
    """A generated public slug already exists."""


@dataclass(frozen=True)
class SavedRouteRecord:
    """Strict persistence record independent of SQLite representation."""

    id: str
    schema_version: int
    public_slug: str
    owner_token_hash: bytes
    source_request_json: str
    candidate_json: str
    created_at_utc: datetime
    expires_at_utc: datetime

    def __post_init__(self) -> None:
        if (
            not self.id
            or self.schema_version != 1
            or not self.public_slug
            or len(self.owner_token_hash) != 32
            or not self.source_request_json
            or not self.candidate_json
            or self.created_at_utc.tzinfo is None
            or self.created_at_utc.utcoffset() is None
            or self.expires_at_utc.tzinfo is None
            or self.expires_at_utc.utcoffset() is None
            or self.expires_at_utc <= self.created_at_utc
        ):
            raise ValueError("saved-route persistence record is invalid")


class SavedRouteRepository(Protocol):
    """Persistence operations required by the saved-route service."""

    def initialize(self) -> None: ...

    def create(self, record: SavedRouteRecord) -> None: ...

    def get_by_slug(self, slug: str) -> SavedRouteRecord | None: ...

    def delete_by_id(self, route_id: str) -> bool: ...

    def purge_expired(self, now: datetime) -> int: ...
