"""Outing service trust, independence, capability, and expiry tests."""

import hashlib
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from sugarglider.outings.errors import (
    OutingCandidateInvalidError,
    OutingCollisionExhaustedError,
    OutingFullError,
    OutingNotFoundError,
    OutingRouteTooLargeError,
    OutingStorageError,
)
from sugarglider.outings.models import OutingPlannedRoute
from sugarglider.outings.repository import (
    OutingAggregateRecord,
    OutingCapacityReachedError,
    OutingParticipantRecord,
    OutingRecord,
    OutingSlugCollisionError,
    ParticipantIdCollisionError,
)
from sugarglider.outings.service import OutingService
from sugarglider.planning.direction.traversal import build_plan_traversal
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.models import PLAN_REQUEST_ADAPTER, PlanRequest
from sugarglider.planning.result import PlanCandidate
from sugarglider.planning.signatures import candidate_signature

NOW = datetime(2026, 7, 27, 10, tzinfo=UTC)
SLUG = "abcdefghijklmnopqrstuv"
OWNER = "owner-token-capability-at-least-thirty-two-characters"
JOIN = "join-token-capability-at-least-thirty-two-characters"
PARTICIPANT_TOKEN = "participant-capability-at-least-thirty-two-characters"
PUBLIC_IDS = ("participant_public_01", "participant_public_02")


class MemoryOutingRepository:
    def __init__(self) -> None:
        self.aggregate: OutingAggregateRecord | None = None
        self.slug_collisions = 0
        self.participant_collisions = 0

    def initialize(self) -> None:
        return None

    def create(
        self,
        outing: OutingRecord,
        initial_participant: OutingParticipantRecord,
    ) -> None:
        if self.slug_collisions:
            self.slug_collisions -= 1
            raise OutingSlugCollisionError
        self.aggregate = OutingAggregateRecord(outing, (initial_participant,))

    def get_by_slug(self, slug: str) -> OutingAggregateRecord | None:
        if self.aggregate is not None and self.aggregate.outing.public_slug == slug:
            return self.aggregate
        return None

    def add_participant(
        self,
        outing_id: str,
        participant: OutingParticipantRecord,
        *,
        maximum_participants: int,
    ) -> OutingParticipantRecord:
        if self.aggregate is None or self.aggregate.outing.id != outing_id:
            raise AssertionError("unknown outing")
        if len(self.aggregate.participants) >= maximum_participants:
            raise OutingCapacityReachedError
        if self.participant_collisions:
            self.participant_collisions -= 1
            raise ParticipantIdCollisionError
        persisted = replace(
            participant,
            join_order=max(
                (item.join_order for item in self.aggregate.participants),
                default=-1,
            )
            + 1,
        )
        self.aggregate = replace(
            self.aggregate,
            participants=(*self.aggregate.participants, persisted),
        )
        return persisted

    def delete_participant(self, outing_id: str, participant_id: str) -> bool:
        if self.aggregate is None or self.aggregate.outing.id != outing_id:
            return False
        retained = tuple(
            participant
            for participant in self.aggregate.participants
            if participant.public_id != participant_id
        )
        if len(retained) == len(self.aggregate.participants):
            return False
        self.aggregate = replace(self.aggregate, participants=retained)
        return True

    def delete_outing_by_id(self, outing_id: str) -> bool:
        if self.aggregate is None or self.aggregate.outing.id != outing_id:
            return False
        self.aggregate = None
        return True

    def purge_expired(self, now: datetime) -> int:
        if self.aggregate and self.aggregate.outing.expires_at_utc <= now:
            self.aggregate = None
            return 1
        return 0


def _factory(values: Iterator[str]) -> Callable[[], str]:
    return lambda: next(values)


def _service(
    repository: MemoryOutingRepository,
    *,
    clock: Callable[[], datetime] = lambda: NOW,
    max_participants: int = 8,
    maximum_bytes: int = 10_000_000,
    slugs: tuple[str, ...] = (SLUG,),
    public_ids: tuple[str, ...] = PUBLIC_IDS,
) -> OutingService:
    return OutingService(
        repository,
        ttl_days=30,
        max_participants=max_participants,
        maximum_route_snapshot_bytes=maximum_bytes,
        clock=clock,
        slug_factory=_factory(iter(slugs)),
        owner_token_factory=lambda: OWNER,
        join_token_factory=lambda: JOIN,
        participant_token_factory=lambda: PARTICIPANT_TOKEN,
        participant_public_id_factory=_factory(iter(public_ids)),
        outing_id_factory=_factory(iter(f"outing-{index}" for index in range(10))),
        participant_id_factory=_factory(
            iter(f"participant-{index}" for index in range(10))
        ),
    )


def _route(source: PlanRequest, candidate: PlanCandidate) -> OutingPlannedRoute:
    return OutingPlannedRoute(source_request=source, candidate=candidate)


def _cycling_route(source: PlanRequest, candidate: PlanCandidate) -> OutingPlannedRoute:
    geometry = (
        (2.20, 48.80),
        (2.215, 48.805),
        (2.23, 48.81),
    )
    source_payload = source.model_dump(mode="json")
    source_payload.update(
        {
            "name": "Independent short cycling route",
            "start": {"lat": geometry[0][1], "lon": geometry[0][0]},
            "end": {"lat": geometry[-1][1], "lon": geometry[-1][0]},
            "routing_profile": "city_bike",
        }
    )
    cycling_source = PLAN_REQUEST_ADAPTER.validate_python(source_payload)
    route = candidate.route.model_copy(
        update={
            "name": "Independent short cycling route",
            "routing_profile": "city_bike",
            "geometry": geometry,
            "snapped_points": (geometry[0], geometry[-1]),
            "summary": candidate.route.summary.model_copy(
                update={
                    "distance_m": 1_400.0,
                    "routed_point_count": len(geometry),
                }
            ),
        }
    )
    traversal = build_plan_traversal(
        cycling_source,
        CandidateDraft(
            route=route,
            routing_points=(),
            topology="point_to_point",
            construction="outing_test",
            search_family="submitted_candidate",
        ),
    )
    cycling_candidate = candidate.model_copy(
        update={
            "id": candidate_signature(
                route,
                topology="point_to_point",
                routing_profile="city_bike",
            ),
            "routing_profile": "city_bike",
            "route": route,
            "traversal": traversal,
        }
    )
    return _route(cycling_source, cycling_candidate)


def test_create_hashes_all_capabilities_and_round_trips_exact_route(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryOutingRepository()
    created = _service(repository).create(
        "  Forest day  ",
        "  Victor  ",
        _route(saved_route_source_request, saved_route_candidate),
        participant_avatar_key="forest",
    )
    assert created.title == "Forest day"
    assert created.participants[0].display_name == "Victor"
    assert created.participants[0].avatar_key == "forest"
    assert created.participants[0].planned_route.source_request == (
        saved_route_source_request
    )
    assert created.participants[0].planned_route.candidate == saved_route_candidate
    assert repository.aggregate is not None
    assert (
        repository.aggregate.outing.owner_token_hash
        == hashlib.sha256(OWNER.encode()).digest()
    )
    assert (
        repository.aggregate.outing.join_token_hash
        == hashlib.sha256(JOIN.encode()).digest()
    )
    assert repository.aggregate.participants[0].participant_token_hash == (
        hashlib.sha256(PARTICIPANT_TOKEN.encode()).digest()
    )
    persisted = repr(repository.aggregate)
    assert OWNER not in persisted and JOIN not in persisted


def test_two_participants_keep_independent_profiles_geometry_and_distance(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryOutingRepository()
    service = _service(repository)
    created = service.create(
        "Mixed outing",
        "Runner",
        _route(saved_route_source_request, saved_route_candidate),
    )
    cycling = _cycling_route(saved_route_source_request, saved_route_candidate)
    joined = service.join(SLUG, JOIN, "Cyclist", cycling, avatar_key="mask")
    first, second = joined.outing.participants
    assert first.planned_route.candidate.routing_profile == "hike"
    assert second.planned_route.candidate.routing_profile == "city_bike"
    assert first.planned_route.candidate.route.geometry != (
        second.planned_route.candidate.route.geometry
    )
    assert first.planned_route.candidate.route.summary.distance_m != (
        second.planned_route.candidate.route.summary.distance_m
    )
    assert created.participants[0].planned_route == first.planned_route
    assert first.avatar_key == "blue"
    assert second.avatar_key == "mask"
    assert service.participant_route(SLUG, second.participant_id) == cycling


@pytest.mark.parametrize("token", [None, "", "wrong-token"])
def test_join_capability_failures_are_uniform_not_found(
    token: str | None,
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    service = _service(MemoryOutingRepository())
    service.create(
        "Outing",
        "Runner",
        _route(saved_route_source_request, saved_route_candidate),
    )
    with pytest.raises(OutingNotFoundError):
        service.authorize_join(SLUG, token)


def test_full_is_reported_only_after_valid_join_capability(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    service = _service(MemoryOutingRepository(), max_participants=2)
    route = _route(saved_route_source_request, saved_route_candidate)
    service.create("Outing", "First", route)
    service.join(SLUG, JOIN, "Second", route)
    with pytest.raises(OutingNotFoundError):
        service.authorize_join(SLUG, "wrong")
    with pytest.raises(OutingFullError):
        service.authorize_join(SLUG, JOIN)


def test_participant_and_owner_capabilities_remove_only_their_targets(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryOutingRepository()
    service = _service(repository)
    created = service.create(
        "Outing",
        "Runner",
        _route(saved_route_source_request, saved_route_candidate),
    )
    with pytest.raises(OutingNotFoundError):
        service.remove_participant(SLUG, created.participant_id, "wrong")
    service.remove_participant(SLUG, created.participant_id, created.participant_token)
    assert service.get(SLUG).participants == ()
    with pytest.raises(OutingNotFoundError):
        service.delete(SLUG, "wrong")
    service.delete(SLUG, OWNER)
    assert repository.aggregate is None


def test_expiry_lazily_deletes_and_source_saved_route_is_not_needed(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryOutingRepository()
    _service(repository).create(
        "Outing",
        "Runner",
        _route(saved_route_source_request, saved_route_candidate),
    )
    assert _service(repository).get(SLUG).participants[0].planned_route.candidate == (
        saved_route_candidate
    )
    with pytest.raises(OutingNotFoundError):
        _service(repository, clock=lambda: NOW + timedelta(days=31)).get(SLUG)
    assert repository.aggregate is None


def test_invalid_or_large_route_is_rejected_before_persistence(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryOutingRepository()
    forged = saved_route_candidate.model_copy(update={"id": "forged"})
    with pytest.raises(OutingCandidateInvalidError):
        _service(repository).create(
            "Outing",
            "Runner",
            _route(saved_route_source_request, forged),
        )
    with pytest.raises(OutingRouteTooLargeError):
        large_candidate = saved_route_candidate.model_copy(
            update={
                "diagnostics": saved_route_candidate.diagnostics.model_copy(
                    update={"details": {"payload": "x" * 101_000}}
                )
            }
        )
        _service(repository, maximum_bytes=100_000).create(
            "Outing",
            "Runner",
            _route(saved_route_source_request, large_candidate),
        )


def test_corrupt_persisted_json_fails_closed(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryOutingRepository()
    service = _service(repository)
    service.create(
        "Outing",
        "Runner",
        _route(saved_route_source_request, saved_route_candidate),
    )
    assert repository.aggregate is not None
    corrupted = replace(
        repository.aggregate.participants[0],
        candidate_json='{"tampered":true}',
    )
    repository.aggregate = replace(
        repository.aggregate,
        participants=(corrupted,),
    )
    with pytest.raises(OutingStorageError):
        service.get(SLUG)


def test_public_snapshot_order_uses_join_order_not_timestamps(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryOutingRepository()
    service = _service(repository)
    route = _route(saved_route_source_request, saved_route_candidate)
    service.create("Outing", "First", route)
    service.join(SLUG, JOIN, "Second", route)
    assert repository.aggregate is not None
    first, second = repository.aggregate.participants
    repository.aggregate = replace(
        repository.aggregate,
        participants=(
            replace(first, joined_at_utc=NOW + timedelta(hours=1)),
            replace(second, joined_at_utc=NOW),
        ),
    )
    assert tuple(item.display_name for item in service.get(SLUG).participants) == (
        "First",
        "Second",
    )


def test_slug_collision_retries_and_exhausts(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    route = _route(saved_route_source_request, saved_route_candidate)
    repository = MemoryOutingRepository()
    repository.slug_collisions = 2
    created = _service(
        repository,
        slugs=("collision_slug_value01", "collision_slug_value02", SLUG),
        public_ids=(
            "participant_public_01",
            "participant_public_02",
            "participant_public_03",
        ),
    ).create("Outing", "Runner", route)
    assert created.slug == SLUG

    exhausted_repository = MemoryOutingRepository()
    exhausted_repository.slug_collisions = 5
    with pytest.raises(OutingCollisionExhaustedError):
        _service(
            exhausted_repository,
            slugs=tuple(f"collision_slug_value0{index}" for index in range(5)),
            public_ids=tuple(f"participant_public_0{index}" for index in range(5)),
        ).create("Outing", "Runner", route)


def test_participant_public_id_collision_retries_and_exhausts(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    route = _route(saved_route_source_request, saved_route_candidate)
    repository = MemoryOutingRepository()
    service = _service(
        repository,
        public_ids=(
            "participant_public_01",
            "participant_public_02",
            "participant_public_03",
        ),
    )
    service.create("Outing", "First", route)
    repository.participant_collisions = 1
    joined = service.join(SLUG, JOIN, "Second", route)
    assert joined.participant_id == "participant_public_03"

    exhausted_repository = MemoryOutingRepository()
    exhausted_service = _service(
        exhausted_repository,
        public_ids=tuple(f"participant_public_{index:02d}" for index in range(6)),
    )
    exhausted_service.create("Outing", "First", route)
    exhausted_repository.participant_collisions = 5
    with pytest.raises(OutingCollisionExhaustedError):
        exhausted_service.join(SLUG, JOIN, "Second", route)


@pytest.mark.parametrize(
    "candidate",
    [
        pytest.param(
            lambda value: value.model_copy(update={"routing_profile": "city_bike"}),
            id="profile",
        ),
        pytest.param(
            lambda value: value.model_copy(
                update={
                    "traversal": value.traversal.model_copy(
                        update={"direction": "loop"}
                    )
                }
            ),
            id="traversal",
        ),
    ],
)
def test_tampered_profile_or_traversal_is_rejected_before_persistence(
    candidate: Callable[[PlanCandidate], PlanCandidate],
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    repository = MemoryOutingRepository()
    with pytest.raises(OutingCandidateInvalidError):
        _service(repository).create(
            "Outing",
            "Runner",
            OutingPlannedRoute.model_construct(
                source_request=saved_route_source_request,
                candidate=candidate(saved_route_candidate),
            ),
        )
    assert repository.aggregate is None
