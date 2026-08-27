"""Adapter-neutral persistence boundary for outings."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sugarglider.outings.models import AVATAR_KEYS, AvatarKey


class OutingRepositoryError(Exception):
    """A persistence operation failed without exposing adapter details."""


class OutingSlugCollisionError(OutingRepositoryError):
    """A generated public outing slug already exists."""


class ParticipantIdCollisionError(OutingRepositoryError):
    """A generated participant public ID already exists in the outing."""


class OutingCapacityReachedError(OutingRepositoryError):
    """An atomic participant insertion would exceed capacity."""


@dataclass(frozen=True)
class OutingRecord:
    id: str
    schema_version: int
    public_slug: str
    owner_token_hash: bytes
    join_token_hash: bytes
    title: str
    created_at_utc: datetime
    expires_at_utc: datetime
    max_participants: int

    def __post_init__(self) -> None:
        if (
            not self.id
            or self.schema_version != 1
            or not self.public_slug
            or len(self.owner_token_hash) != 32
            or len(self.join_token_hash) != 32
            or not self.title
            or self.created_at_utc.tzinfo is None
            or self.created_at_utc.utcoffset() is None
            or self.expires_at_utc.tzinfo is None
            or self.expires_at_utc.utcoffset() is None
            or self.expires_at_utc <= self.created_at_utc
            or not 2 <= self.max_participants <= 20
        ):
            raise ValueError("outing persistence record is invalid")


@dataclass(frozen=True)
class OutingParticipantRecord:
    id: str
    outing_id: str
    public_id: str
    participant_token_hash: bytes
    display_name: str
    source_request_json: str
    candidate_json: str
    joined_at_utc: datetime
    join_order: int
    avatar_key: AvatarKey = "blue"

    def __post_init__(self) -> None:
        if (
            not self.id
            or not self.outing_id
            or not self.public_id
            or len(self.participant_token_hash) != 32
            or not self.display_name
            or self.avatar_key not in AVATAR_KEYS
            or not self.source_request_json
            or not self.candidate_json
            or self.joined_at_utc.tzinfo is None
            or self.joined_at_utc.utcoffset() is None
            or self.join_order < 0
        ):
            raise ValueError("outing participant persistence record is invalid")


@dataclass(frozen=True)
class OutingAggregateRecord:
    outing: OutingRecord
    participants: tuple[OutingParticipantRecord, ...]


class OutingRepository(Protocol):
    def initialize(self) -> None: ...

    def create(
        self,
        outing: OutingRecord,
        initial_participant: OutingParticipantRecord,
    ) -> None: ...

    def get_by_slug(self, slug: str) -> OutingAggregateRecord | None: ...

    def add_participant(
        self,
        outing_id: str,
        participant: OutingParticipantRecord,
        *,
        maximum_participants: int,
    ) -> OutingParticipantRecord: ...

    def delete_participant(self, outing_id: str, participant_id: str) -> bool: ...

    def delete_outing_by_id(self, outing_id: str) -> bool: ...

    def purge_expired(self, now: datetime) -> int: ...
