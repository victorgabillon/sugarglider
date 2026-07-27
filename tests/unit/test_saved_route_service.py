"""Saved-route service trust, capability, expiry, and collision tests."""

import hashlib
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from sugarglider.domain.models import Coordinate
from sugarglider.planning.models import PlanRequest
from sugarglider.planning.result import PlanCandidate
from sugarglider.saved_routes.errors import (
    SavedRouteCollisionExhaustedError,
    SavedRouteInvalidSnapshotError,
    SavedRouteNotFoundError,
    SavedRouteStorageError,
    SavedRouteTooLargeError,
)
from sugarglider.saved_routes.models import SavedRouteCreateRequest
from sugarglider.saved_routes.repository import (
    SavedRouteRecord,
    SavedRouteSlugCollisionError,
)
from sugarglider.saved_routes.service import SavedRouteService

NOW = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
SLUG = "abcdefghijklmnopqrstuv"
OWNER_TOKEN = "owner-capability-token-that-is-never-persisted"


class MemoryRepository:
    def __init__(self) -> None:
        self.records: dict[str, SavedRouteRecord] = {}
        self.create_calls = 0
        self.delete_calls: list[str] = []
        self.collisions = 0

    def initialize(self) -> None:
        return None

    def create(self, record: SavedRouteRecord) -> None:
        self.create_calls += 1
        if self.collisions:
            self.collisions -= 1
            raise SavedRouteSlugCollisionError
        self.records[record.public_slug] = record

    def get_by_slug(self, slug: str) -> SavedRouteRecord | None:
        return self.records.get(slug)

    def delete_by_id(self, route_id: str) -> bool:
        self.delete_calls.append(route_id)
        for slug, record in tuple(self.records.items()):
            if record.id == route_id:
                del self.records[slug]
                return True
        return False

    def purge_expired(self, now: datetime) -> int:
        expired = [
            slug
            for slug, record in self.records.items()
            if record.expires_at_utc <= now
        ]
        for slug in expired:
            del self.records[slug]
        return len(expired)


def _factory(values: Iterator[str]) -> Callable[[], str]:
    return lambda: next(values)


def _service(
    repository: MemoryRepository,
    *,
    clock: Callable[[], datetime] = lambda: NOW,
    maximum_snapshot_bytes: int = 10_000_000,
    slugs: tuple[str, ...] = (SLUG,),
) -> SavedRouteService:
    return SavedRouteService(
        repository,
        ttl_days=90,
        maximum_snapshot_bytes=maximum_snapshot_bytes,
        clock=clock,
        slug_factory=_factory(iter(slugs)),
        owner_token_factory=lambda: OWNER_TOKEN,
        route_id_factory=_factory(iter(f"route-{index}" for index in range(10))),
    )


def _request(source: PlanRequest, candidate: PlanCandidate) -> SavedRouteCreateRequest:
    return SavedRouteCreateRequest(source_request=source, candidate=candidate)


def test_create_round_trips_exact_snapshot_and_hashes_owner_token(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryRepository()
    created = _service(repository).create(
        _request(saved_route_source_request, saved_route_candidate)
    )

    record = repository.records[SLUG]
    assert created.owner_token == OWNER_TOKEN
    assert created.created_at == NOW
    assert created.expires_at == NOW + timedelta(days=90)
    assert created.source_request == saved_route_source_request
    assert created.candidate == saved_route_candidate
    assert record.owner_token_hash == hashlib.sha256(OWNER_TOKEN.encode()).digest()
    assert OWNER_TOKEN not in record.source_request_json
    assert OWNER_TOKEN not in record.candidate_json
    loaded = _service(repository).get(SLUG)
    assert loaded.source_request == saved_route_source_request
    assert loaded.candidate == saved_route_candidate
    assert "owner_token" not in loaded.model_dump()


def test_size_limit_is_enforced_before_repository_create(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryRepository()
    with pytest.raises(SavedRouteTooLargeError):
        _service(repository, maximum_snapshot_bytes=1).create(
            _request(saved_route_source_request, saved_route_candidate)
        )
    assert repository.create_calls == 0


def test_arbitrary_candidate_id_is_rejected_before_persistence(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryRepository()
    forged = saved_route_candidate.model_copy(update={"id": "arbitrary-candidate-id"})
    with pytest.raises(SavedRouteInvalidSnapshotError):
        _service(repository).create(_request(saved_route_source_request, forged))
    assert repository.create_calls == 0


def test_slug_collision_retries_then_succeeds(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryRepository()
    repository.collisions = 2
    created = _service(
        repository,
        slugs=(
            "collision_slug_value1",
            "collision_slug_value2",
            SLUG,
        ),
    ).create(_request(saved_route_source_request, saved_route_candidate))
    assert created.slug == SLUG
    assert repository.create_calls == 3


def test_slug_collision_exhaustion_is_bounded(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryRepository()
    repository.collisions = 5
    with pytest.raises(SavedRouteCollisionExhaustedError):
        _service(repository, slugs=(SLUG,) * 5).create(
            _request(saved_route_source_request, saved_route_candidate)
        )
    assert repository.create_calls == 5


def test_expired_snapshot_is_lazily_deleted_and_indistinguishable_from_unknown(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryRepository()
    _service(repository).create(
        _request(saved_route_source_request, saved_route_candidate)
    )
    expired_service = _service(repository, clock=lambda: NOW + timedelta(days=91))
    with pytest.raises(SavedRouteNotFoundError):
        expired_service.get(SLUG)
    assert SLUG not in repository.records
    with pytest.raises(SavedRouteNotFoundError):
        expired_service.get("unknown_slug_value_123")


@pytest.mark.parametrize("owner_token", [None, "", "wrong-owner-token"])
def test_delete_missing_or_invalid_capability_is_uniform_not_found(
    owner_token: str | None,
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryRepository()
    service = _service(repository)
    service.create(_request(saved_route_source_request, saved_route_candidate))
    with pytest.raises(SavedRouteNotFoundError):
        service.delete(SLUG, owner_token)
    assert SLUG in repository.records


def test_delete_with_owner_capability_removes_record(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryRepository()
    service = _service(repository)
    service.create(_request(saved_route_source_request, saved_route_candidate))
    service.delete(SLUG, OWNER_TOKEN)
    assert not repository.records


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_request_json", "{"),
        ("candidate_json", "{"),
        ("candidate_json", "{}"),
    ],
)
def test_corrupt_persisted_json_fails_closed(
    field: str,
    value: str,
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryRepository()
    service = _service(repository)
    service.create(_request(saved_route_source_request, saved_route_candidate))
    record = repository.records[SLUG]
    repository.records[SLUG] = (
        replace(record, source_request_json=value)
        if field == "source_request_json"
        else replace(record, candidate_json=value)
    )
    with pytest.raises(SavedRouteStorageError):
        service.get(SLUG)


def test_tampered_profile_is_rejected_on_read(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryRepository()
    service = _service(repository)
    service.create(_request(saved_route_source_request, saved_route_candidate))
    tampered = saved_route_candidate.model_copy(update={"routing_profile": "trail_run"})
    repository.records[SLUG] = replace(
        repository.records[SLUG],
        candidate_json=tampered.model_dump_json(),
    )
    with pytest.raises(SavedRouteStorageError):
        service.get(SLUG)


def test_tampered_route_profile_is_rejected_on_read(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryRepository()
    service = _service(repository)
    service.create(_request(saved_route_source_request, saved_route_candidate))
    route = saved_route_candidate.route.model_copy(
        update={"routing_profile": "trail_run"}
    )
    tampered = saved_route_candidate.model_copy(update={"route": route})
    repository.records[SLUG] = replace(
        repository.records[SLUG],
        candidate_json=tampered.model_dump_json(),
    )
    with pytest.raises(SavedRouteStorageError):
        service.get(SLUG)


def test_tampered_geometry_is_rejected_on_read(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryRepository()
    service = _service(repository)
    service.create(_request(saved_route_source_request, saved_route_candidate))
    route = saved_route_candidate.route.model_copy(
        update={"geometry": ((0.0, 0.0), (0.1, 0.1))}
    )
    tampered = saved_route_candidate.model_copy(update={"route": route})
    repository.records[SLUG] = replace(
        repository.records[SLUG],
        candidate_json=tampered.model_dump_json(),
    )
    with pytest.raises(SavedRouteStorageError):
        service.get(SLUG)


def test_tampered_traversal_anchor_is_rejected_on_read(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryRepository()
    service = _service(repository)
    service.create(_request(saved_route_source_request, saved_route_candidate))
    first = saved_route_candidate.traversal.anchors[0].model_copy(
        update={"routed_coordinate": Coordinate(lat=0.0, lon=0.0)}
    )
    traversal = saved_route_candidate.traversal.model_copy(
        update={"anchors": (first, *saved_route_candidate.traversal.anchors[1:])}
    )
    tampered = saved_route_candidate.model_copy(update={"traversal": traversal})
    repository.records[SLUG] = replace(
        repository.records[SLUG],
        candidate_json=tampered.model_dump_json(),
    )
    with pytest.raises(SavedRouteStorageError):
        service.get(SLUG)


def test_tampered_traversal_direction_is_rejected_on_read(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryRepository()
    service = _service(repository)
    service.create(_request(saved_route_source_request, saved_route_candidate))
    traversal = saved_route_candidate.traversal.model_copy(
        update={"direction": "clockwise"}
    )
    tampered = saved_route_candidate.model_copy(update={"traversal": traversal})
    repository.records[SLUG] = replace(
        repository.records[SLUG],
        candidate_json=tampered.model_dump_json(),
    )
    with pytest.raises(SavedRouteStorageError):
        service.get(SLUG)
