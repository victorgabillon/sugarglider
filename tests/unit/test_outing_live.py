"""Durable outing live-position models, persistence, API, and broker tests."""

import asyncio
import hashlib
import json
import threading
from collections.abc import AsyncGenerator, Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from starlette.types import Message, Scope

from sugarglider.api.main import create_app
from sugarglider.api.outing_live import (
    _cursor_requires_reset,
    _event_stream,
    _parse_cursor,
    _replay_covers_state,
)
from sugarglider.config import Settings
from sugarglider.outings.errors import (
    OutingLiveCursorInvalidError,
    OutingNotFoundError,
    OutingPositionInvalidError,
    OutingPositionSequenceConflictError,
    OutingStorageError,
)
from sugarglider.outings.live_broker import OutingLiveBroker, _Subscriber
from sugarglider.outings.live_models import (
    SQLITE_SIGNED_INTEGER_MAX,
    LiveCoordinate,
    OutingLiveEvent,
    OutingPositionUpdate,
    ParticipantLivePosition,
)
from sugarglider.outings.live_repository import (
    OutingLiveAuthorizationContextError,
    OutingLivePositionRecord,
    OutingLiveRepositoryError,
    OutingParticipantAuthorizationRecord,
)
from sugarglider.outings.live_service import OutingLiveService
from sugarglider.outings.live_sqlite_repository import SQLiteOutingLiveRepository
from sugarglider.outings.repository import OutingParticipantRecord, OutingRecord
from sugarglider.outings.service import OutingService
from sugarglider.outings.sqlite_repository import SQLiteOutingRepository
from sugarglider.planning.models import PlanRequest
from sugarglider.planning.pipeline import PlanService
from sugarglider.planning.result import PlanResult
from sugarglider.routing.profiles import RoutingProfileId
from sugarglider.routing.service import RouteService
from sugarglider.saved_routes.service import UnavailableSavedRouteService

NOW = datetime(2026, 7, 28, 12, tzinfo=UTC)
SLUG = "outing_slug_1234567890"
PARTICIPANT_ID = "participant_1234567890"
PARTICIPANT_TOKEN = "p" * 32


class _Clock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class _NoRouteService(RouteService):
    def __init__(self) -> None:
        pass

    async def ensure_profile_available(self, profile: RoutingProfileId) -> None:
        del profile


class _NoPlanService(PlanService):
    def __init__(self) -> None:
        pass

    async def generate(self, request: PlanRequest) -> PlanResult:
        del request
        raise AssertionError("live positions must not invoke planning")


def _repositories(
    tmp_path: Path,
    *,
    clock: _Clock | None = None,
    outing_expires_at: datetime | None = None,
    stream_read_hook: Callable[[], None] | None = None,
) -> tuple[
    SQLiteOutingRepository,
    SQLiteOutingLiveRepository,
    OutingLiveService,
    _Clock,
]:
    active_clock = clock or _Clock()
    path = tmp_path / "outings.sqlite3"
    outings = SQLiteOutingRepository(path)
    outings.initialize()
    live_repository = SQLiteOutingLiveRepository(
        path,
        stream_read_hook=stream_read_hook,
        clock=active_clock,
    )
    outing = OutingRecord(
        id="outing-internal",
        schema_version=1,
        public_slug=SLUG,
        owner_token_hash=hashlib.sha256(b"o" * 32).digest(),
        join_token_hash=hashlib.sha256(b"j" * 32).digest(),
        title="Live outing",
        created_at_utc=NOW - timedelta(hours=1),
        expires_at_utc=outing_expires_at or NOW + timedelta(days=1),
        max_participants=8,
    )
    participant = OutingParticipantRecord(
        id="participant-internal",
        outing_id=outing.id,
        public_id=PARTICIPANT_ID,
        participant_token_hash=hashlib.sha256(PARTICIPANT_TOKEN.encode()).digest(),
        display_name="Walker",
        source_request_json="{}",
        candidate_json="{}",
        joined_at_utc=NOW - timedelta(minutes=30),
        join_order=0,
    )
    outings.create(outing, participant)
    service = OutingLiveService(
        live_repository,
        stale_after_seconds=120,
        expire_after_seconds=3_600,
        maximum_update_age_seconds=600,
        future_tolerance_seconds=30,
        event_retention_seconds=900,
        maximum_events_per_outing=10,
        keepalive_seconds=5,
        clock=active_clock,
    )
    return outings, live_repository, service, active_clock


def _update(
    sequence: int = 0,
    *,
    captured_at: datetime = NOW,
    latitude: float = 48.87,
) -> OutingPositionUpdate:
    return OutingPositionUpdate(
        sequence=sequence,
        coordinate=LiveCoordinate(lat=latitude, lon=2.1),
        accuracy_m=8,
        altitude_m=90,
        speed_m_s=1.5,
        heading_deg=180,
        captured_at=captured_at,
    )


def _cleared_events(*event_ids: int) -> tuple[OutingLiveEvent, ...]:
    return tuple(
        OutingLiveEvent(
            event_id=event_id,
            event_type="position_cleared",
            participant_id=PARTICIPANT_ID,
            occurred_at=NOW,
            clear_reason="stopped",
        )
        for event_id in event_ids
    )


async def _capture_initial_sse(app: FastAPI, path: str) -> list[Message]:
    messages: list[Message] = []
    disconnected = asyncio.Event()
    request_received = False

    async def receive() -> Message:
        nonlocal request_received
        if not request_received:
            request_received = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        messages.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            disconnected.set()

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": (),
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "state": {},
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=2)
    return messages


def test_live_models_reject_invalid_bounds_unknown_fields_and_naive_time() -> None:
    with pytest.raises(ValidationError):
        LiveCoordinate(lat=91, lon=2)
    for field, value in (
        ("accuracy_m", 10_001),
        ("altitude_m", -1_001),
        ("speed_m_s", 151),
        ("heading_deg", 360),
    ):
        payload = _update().model_dump()
        payload[field] = value
        with pytest.raises(ValidationError):
            OutingPositionUpdate.model_validate(payload)
    payload = _update().model_dump()
    payload["unknown"] = True
    with pytest.raises(ValidationError):
        OutingPositionUpdate.model_validate(payload)
    assert _update(SQLITE_SIGNED_INTEGER_MAX).sequence == (SQLITE_SIGNED_INTEGER_MAX)
    with pytest.raises(ValidationError):
        _update(SQLITE_SIGNED_INTEGER_MAX + 1)
    payload = _update().model_dump()
    payload["captured_at"] = NOW.replace(tzinfo=None)
    with pytest.raises(ValidationError):
        OutingPositionUpdate.model_validate(payload)


def test_public_position_and_event_consistency_are_strict() -> None:
    position = ParticipantLivePosition(
        participant_id=PARTICIPANT_ID,
        sequence=1,
        coordinate=LiveCoordinate(lat=48, lon=2),
        accuracy_m=10,
        altitude_m=None,
        speed_m_s=None,
        heading_deg=None,
        captured_at=NOW,
        received_at=NOW,
        stale_at=NOW + timedelta(seconds=120),
        expires_at=NOW + timedelta(seconds=3_600),
    )
    with pytest.raises(ValidationError):
        ParticipantLivePosition(
            **position.model_dump(exclude={"stale_at"}),
            stale_at=NOW,
        )
    with pytest.raises(ValidationError):
        OutingLiveEvent(
            event_id=1,
            event_type="position_updated",
            participant_id=PARTICIPANT_ID,
            occurred_at=NOW,
        )
    with pytest.raises(ValidationError):
        OutingLiveEvent(
            event_id=1,
            event_type="position_cleared",
            participant_id=PARTICIPANT_ID,
            occurred_at=NOW,
            position=position,
            clear_reason="stopped",
        )


def test_schema_is_additive_and_has_exactly_four_application_tables(
    tmp_path: Path,
) -> None:
    outings, _, _, _ = _repositories(tmp_path)
    with outings._connection() as connection:
        tables = {
            str(row["name"])
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        }
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(outing_live_positions)"
        ).fetchall()
    assert tables == {
        "outings",
        "outing_participants",
        "outing_live_positions",
        "outing_live_events",
    }
    assert {str(row["table"]) for row in foreign_keys} == {
        "outings",
        "outing_participants",
    }


def test_update_idempotency_sequence_conflicts_and_restart_snapshot(
    tmp_path: Path,
) -> None:
    _, repository, service, clock = _repositories(tmp_path)
    first = service.update_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN, _update())
    assert first.event_appended
    clock.value += timedelta(seconds=10)
    retry = service.update_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN, _update())
    assert not retry.event_appended
    assert retry.position == first.position
    assert service.snapshot(SLUG).cursor == 1

    with pytest.raises(OutingPositionSequenceConflictError):
        service.update_position(
            SLUG,
            PARTICIPANT_ID,
            PARTICIPANT_TOKEN,
            _update(latitude=48.88),
        )
    accepted = service.update_position(
        SLUG,
        PARTICIPANT_ID,
        PARTICIPANT_TOKEN,
        _update(2, captured_at=clock.value),
    )
    assert accepted.event_appended
    assert service.snapshot(SLUG).cursor == 2

    restarted = OutingLiveService(
        repository,
        maximum_events_per_outing=10,
        keepalive_seconds=5,
        clock=clock,
    )
    snapshot = restarted.snapshot(SLUG)
    assert snapshot.positions == (accepted.position,)
    assert snapshot.cursor == 2
    events = restarted.events_after(SLUG, 0)
    assert [event.event_id for event in events] == [1, 2]


def test_clear_is_idempotent_and_expiry_appends_tombstones(tmp_path: Path) -> None:
    _, _, service, clock = _repositories(tmp_path)
    service.update_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN, _update())
    assert service.clear_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN)
    assert not service.clear_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN)
    assert service.snapshot(SLUG).positions == ()
    assert service.events_after(SLUG, 1)[0].clear_reason == "stopped"

    service.update_position(
        SLUG,
        PARTICIPANT_ID,
        PARTICIPANT_TOKEN,
        _update(2, captured_at=clock.value),
    )
    clock.value += timedelta(seconds=3_601)
    snapshot = service.snapshot(SLUG)
    assert snapshot.positions == ()
    assert service.events_after(SLUG, 3)[0].clear_reason == "expired"


def test_event_retention_is_bounded_by_count_and_age(tmp_path: Path) -> None:
    _, _, service, clock = _repositories(tmp_path)
    for sequence in range(12):
        service.update_position(
            SLUG,
            PARTICIPANT_ID,
            PARTICIPANT_TOKEN,
            _update(sequence, captured_at=clock.value),
        )
    window = service.event_window(SLUG)
    assert window.current_cursor == 12
    assert window.oldest_retained_event_id == 3
    assert [event.event_id for event in service.events_after(SLUG, 0)] == list(
        range(3, 13)
    )

    clock.value += timedelta(seconds=901)
    service.update_position(
        SLUG,
        PARTICIPANT_ID,
        PARTICIPANT_TOKEN,
        _update(12, captured_at=clock.value),
    )
    assert [event.event_id for event in service.events_after(SLUG, 0)] == [13]


@pytest.mark.parametrize(
    ("cursor", "current_cursor", "oldest_event_id", "expected"),
    [
        (6, 5, None, True),
        (5, 5, None, False),
        (4, 5, None, True),
        (2, 5, 4, True),
        (3, 5, 4, False),
    ],
)
def test_cursor_reset_semantics_cover_exhausted_and_retained_windows(
    cursor: int,
    current_cursor: int,
    oldest_event_id: int | None,
    expected: bool,
) -> None:
    assert _cursor_requires_reset(cursor, current_cursor, oldest_event_id) is expected


@pytest.mark.parametrize(
    ("previous_cursor", "represented_cursor", "event_ids", "expected"),
    [
        (2, 12, tuple(range(3, 13)), True),
        (2, 12, tuple(range(3, 14)), True),
        (2, 12, tuple(range(4, 14)), False),
        (2, 12, (3, 4, 6, 7, 8, 9, 10, 11, 12), False),
        (2, 12, (), False),
        (12, 12, (), True),
        (12, 12, (13,), True),
    ],
)
def test_replay_coverage_requires_contiguous_events_through_represented_state(
    previous_cursor: int,
    represented_cursor: int,
    event_ids: tuple[int, ...],
    expected: bool,
) -> None:
    assert (
        _replay_covers_state(
            previous_cursor,
            represented_cursor,
            _cleared_events(*event_ids),
        )
        is expected
    )


@pytest.mark.asyncio
async def test_sse_resets_behind_empty_retained_window_but_not_at_durable_cursor(
    tmp_path: Path,
) -> None:
    _, repository, live, clock = _repositories(tmp_path)
    for sequence in range(5):
        live.update_position(
            SLUG,
            PARTICIPANT_ID,
            PARTICIPANT_TOKEN,
            _update(sequence, captured_at=clock.value),
        )
    assert repository.purge_live_events(clock.value + timedelta(seconds=1)) == 5
    state = live.stream_state(SLUG)
    assert state.snapshot.cursor == 5
    assert state.oldest_retained_event_id is None

    broker = OutingLiveBroker()
    stale_subscription = broker.subscribe(SLUG)
    stale_wakeup = await stale_subscription.__aenter__()
    stale_stream = _event_stream(
        SLUG,
        live,
        stale_wakeup,
        stale_subscription,
        state.snapshot,
        state.snapshot.cursor,
        state.oldest_retained_event_id,
        0,
    )
    reset = await anext(stale_stream)
    assert reset.startswith("id: 5\nevent: reset\n")
    reset_payload = json.loads(reset.split("data: ", maxsplit=1)[1])
    assert reset_payload["cursor"] == 5
    await cast(AsyncGenerator[str], stale_stream).aclose()

    live.keepalive_seconds = 0
    current_subscription = broker.subscribe(SLUG)
    current_wakeup = await current_subscription.__aenter__()
    current_stream = _event_stream(
        SLUG,
        live,
        current_wakeup,
        current_subscription,
        state.snapshot,
        state.snapshot.cursor,
        state.oldest_retained_event_id,
        5,
    )
    first = await anext(current_stream)
    assert first == ": keep-alive\n\n"
    await cast(AsyncGenerator[str], current_stream).aclose()


def test_durable_cursor_survives_complete_purge_restart_and_count_pruning(
    tmp_path: Path,
) -> None:
    _, repository, service, clock = _repositories(tmp_path)
    for sequence in range(5):
        service.update_position(
            SLUG,
            PARTICIPANT_ID,
            PARTICIPANT_TOKEN,
            _update(sequence, captured_at=clock.value),
        )
    assert service.stream_state(SLUG).snapshot.cursor == 5
    assert repository.purge_live_events(clock.value + timedelta(seconds=1)) == 5
    purged_state = service.stream_state(SLUG)
    assert purged_state.snapshot.cursor == 5
    assert purged_state.oldest_retained_event_id is None

    restarted = OutingLiveService(
        repository,
        maximum_events_per_outing=10,
        keepalive_seconds=5,
        clock=clock,
    )
    restarted.update_position(
        SLUG,
        PARTICIPANT_ID,
        PARTICIPANT_TOKEN,
        _update(5, captured_at=clock.value),
    )
    assert [event.event_id for event in restarted.events_after(SLUG, 0)] == [6]
    assert restarted.stream_state(SLUG).snapshot.cursor == 6

    for sequence in range(6, 18):
        restarted.update_position(
            SLUG,
            PARTICIPANT_ID,
            PARTICIPANT_TOKEN,
            _update(sequence, captured_at=clock.value),
        )
    count_pruned = restarted.stream_state(SLUG)
    assert count_pruned.snapshot.cursor == 18
    assert count_pruned.oldest_retained_event_id == 9


def test_exhausted_sqlite_cursor_fails_safely_and_rolls_back_state(
    tmp_path: Path,
) -> None:
    outings, _, service, clock = _repositories(tmp_path)
    first = service.update_position(
        SLUG,
        PARTICIPANT_ID,
        PARTICIPANT_TOKEN,
        _update(),
    )
    with outings._connection() as connection, connection:
        connection.execute(
            """
            UPDATE outings
            SET live_event_cursor = ?
            WHERE public_slug = ?
            """,
            (SQLITE_SIGNED_INTEGER_MAX, SLUG),
        )
    with pytest.raises(OutingStorageError):
        service.update_position(
            SLUG,
            PARTICIPANT_ID,
            PARTICIPANT_TOKEN,
            _update(1, captured_at=clock.value),
        )
    snapshot = service.snapshot(SLUG)
    assert snapshot.cursor == SQLITE_SIGNED_INTEGER_MAX
    assert snapshot.positions == (first.position,)
    assert [event.event_id for event in service.events_after(SLUG, 0)] == [1]


def test_independent_outings_allocate_independent_event_ids(tmp_path: Path) -> None:
    outings, repository, service, clock = _repositories(tmp_path)
    second_slug = "second_outing_123456789"
    second_participant = "second_participant_12345"
    second_token = "s" * 32
    outing = OutingRecord(
        id="second-outing-internal",
        schema_version=1,
        public_slug=second_slug,
        owner_token_hash=hashlib.sha256(b"x" * 32).digest(),
        join_token_hash=hashlib.sha256(b"y" * 32).digest(),
        title="Second live outing",
        created_at_utc=NOW - timedelta(hours=1),
        expires_at_utc=NOW + timedelta(days=1),
        max_participants=8,
    )
    participant = OutingParticipantRecord(
        id="second-participant-internal",
        outing_id=outing.id,
        public_id=second_participant,
        participant_token_hash=hashlib.sha256(second_token.encode()).digest(),
        display_name="Second",
        source_request_json="{}",
        candidate_json="{}",
        joined_at_utc=NOW,
        join_order=0,
    )
    outings.create(outing, participant)
    service.update_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN, _update())
    service.update_position(
        second_slug,
        second_participant,
        second_token,
        _update(),
    )
    first_state = repository.get_live_stream_state(SLUG)
    second_state = repository.get_live_stream_state(second_slug)
    assert first_state is not None and first_state.snapshot.cursor == 1
    assert second_state is not None and second_state.snapshot.cursor == 1
    assert service.events_after(SLUG, 0)[0].event_id == 1
    assert service.events_after(second_slug, 0)[0].event_id == 1
    assert clock.value == NOW


def test_stream_state_read_is_one_sqlite_snapshot_during_update(
    tmp_path: Path,
) -> None:
    _, repository, writer, clock = _repositories(tmp_path)
    read_paused = threading.Event()
    release_read = threading.Event()

    def pause_read() -> None:
        read_paused.set()
        assert release_read.wait(timeout=5)

    reader = OutingLiveService(
        SQLiteOutingLiveRepository(
            tmp_path / "outings.sqlite3",
            stream_read_hook=pause_read,
            clock=clock,
        ),
        maximum_events_per_outing=10,
        keepalive_seconds=5,
        clock=clock,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        state_future = executor.submit(reader.stream_state, SLUG)
        assert read_paused.wait(timeout=5)
        writer.update_position(
            SLUG,
            PARTICIPANT_ID,
            PARTICIPANT_TOKEN,
            _update(),
        )
        release_read.set()
        during_update = state_future.result(timeout=5)
    assert during_update.snapshot.cursor == 0
    assert during_update.snapshot.positions == ()
    after_update = writer.stream_state(SLUG)
    assert after_update.snapshot.cursor == 1
    assert len(after_update.snapshot.positions) == 1
    assert repository.get_live_stream_state(SLUG) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("seed_count", "requested_cursor", "initial_event"),
    [(0, None, "snapshot"), (12, 0, "reset")],
)
async def test_sse_state_load_race_never_skips_concurrent_update(
    tmp_path: Path,
    seed_count: int,
    requested_cursor: int | None,
    initial_event: str,
) -> None:
    _, _, writer, clock = _repositories(tmp_path)
    for sequence in range(seed_count):
        writer.update_position(
            SLUG,
            PARTICIPANT_ID,
            PARTICIPANT_TOKEN,
            _update(sequence, captured_at=clock.value),
        )
    read_paused = threading.Event()
    release_read = threading.Event()

    def pause_read() -> None:
        read_paused.set()
        assert release_read.wait(timeout=5)

    reader = OutingLiveService(
        SQLiteOutingLiveRepository(
            tmp_path / "outings.sqlite3",
            stream_read_hook=pause_read,
            clock=clock,
        ),
        maximum_events_per_outing=10,
        keepalive_seconds=5,
        clock=clock,
    )
    broker = OutingLiveBroker()
    subscription = broker.subscribe(SLUG)
    wakeup = await subscription.__aenter__()
    with ThreadPoolExecutor(max_workers=1) as executor:
        state_future = executor.submit(reader.stream_state, SLUG)
        assert read_paused.wait(timeout=5)
        writer.update_position(
            SLUG,
            PARTICIPANT_ID,
            PARTICIPANT_TOKEN,
            _update(seed_count, captured_at=clock.value),
        )
        broker.notify(SLUG)
        release_read.set()
        state = state_future.result(timeout=5)
    stream = _event_stream(
        SLUG,
        reader,
        wakeup,
        subscription,
        state.snapshot,
        state.snapshot.cursor,
        state.oldest_retained_event_id,
        requested_cursor,
    )
    first_frame = await anext(stream)
    assert f"event: {initial_event}" in first_frame
    represented_cursor = state.snapshot.cursor
    assert f"id: {represented_cursor}\n" in first_frame
    update_frame = await asyncio.wait_for(anext(stream), timeout=5)
    assert "event: position_updated" in update_frame
    assert f"id: {represented_cursor + 1}\n" in update_frame
    await cast(AsyncGenerator[str], stream).aclose()


@pytest.mark.asyncio
async def test_sse_resets_when_count_pruning_races_replay_query(
    tmp_path: Path,
) -> None:
    _, repository, writer, clock = _repositories(tmp_path)
    for sequence in range(12):
        writer.update_position(
            SLUG,
            PARTICIPANT_ID,
            PARTICIPANT_TOKEN,
            _update(sequence, captured_at=clock.value),
        )
    represented_state = writer.stream_state(SLUG)
    assert represented_state.snapshot.cursor == 12
    assert represented_state.oldest_retained_event_id == 3

    replay_paused = threading.Event()
    release_replay = threading.Event()

    class PausedReplayService(OutingLiveService):
        def events_after(self, slug: str, event_id: int) -> tuple[OutingLiveEvent, ...]:
            replay_paused.set()
            assert release_replay.wait(timeout=5)
            return super().events_after(slug, event_id)

    reader = PausedReplayService(
        repository,
        maximum_events_per_outing=10,
        keepalive_seconds=5,
        clock=clock,
    )
    broker = OutingLiveBroker()
    subscription = broker.subscribe(SLUG)
    wakeup = await subscription.__aenter__()
    stream = _event_stream(
        SLUG,
        reader,
        wakeup,
        subscription,
        represented_state.snapshot,
        represented_state.snapshot.cursor,
        represented_state.oldest_retained_event_id,
        2,
    )
    frame_future = asyncio.ensure_future(anext(stream))
    assert await asyncio.to_thread(replay_paused.wait, 5)
    writer.update_position(
        SLUG,
        PARTICIPANT_ID,
        PARTICIPANT_TOKEN,
        _update(12, captured_at=clock.value),
    )
    release_replay.set()
    frame = await asyncio.wait_for(frame_future, timeout=5)
    assert frame.startswith("id: 13\nevent: reset\n")
    reset_payload = json.loads(frame.split("data: ", maxsplit=1)[1])
    assert reset_payload["cursor"] == 13
    assert reset_payload["positions"][0]["sequence"] == 12
    assert [event.event_id for event in writer.events_after(SLUG, 0)] == list(
        range(4, 14)
    )
    await cast(AsyncGenerator[str], stream).aclose()


def test_concurrent_sequences_keep_highest_state_and_unique_event_ids(
    tmp_path: Path,
) -> None:
    _, _, service, _ = _repositories(tmp_path)

    def publish(sequence: int) -> None:
        try:
            service.update_position(
                SLUG,
                PARTICIPANT_ID,
                PARTICIPANT_TOKEN,
                _update(sequence),
            )
        except OutingPositionSequenceConflictError:
            pass

    with ThreadPoolExecutor(max_workers=8) as executor:
        tuple(executor.map(publish, range(20)))
    snapshot = service.snapshot(SLUG)
    assert snapshot.positions[0].sequence == 19
    event_ids = tuple(event.event_id for event in service.events_after(SLUG, 0))
    assert len(event_ids) == len(set(event_ids))
    assert event_ids == tuple(range(event_ids[0], event_ids[-1] + 1))


def test_timestamp_policy_and_capabilities_are_safe(tmp_path: Path) -> None:
    _, _, service, _ = _repositories(tmp_path)
    with pytest.raises(OutingPositionInvalidError):
        service.update_position(
            SLUG,
            PARTICIPANT_ID,
            PARTICIPANT_TOKEN,
            _update(captured_at=NOW - timedelta(seconds=601)),
        )
    with pytest.raises(OutingPositionInvalidError):
        service.update_position(
            SLUG,
            PARTICIPANT_ID,
            PARTICIPANT_TOKEN,
            _update(captured_at=NOW + timedelta(seconds=31)),
        )


def test_expired_outing_is_deleted_during_live_operations(tmp_path: Path) -> None:
    outings, _, service, clock = _repositories(
        tmp_path,
        outing_expires_at=NOW + timedelta(seconds=10),
    )
    service.update_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN, _update())
    clock.value += timedelta(seconds=11)
    with pytest.raises(OutingNotFoundError):
        service.snapshot(SLUG)
    assert outings.get_by_slug(SLUG) is None
    with outings._connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM outings").fetchone()[0] == 0
        assert (
            connection.execute("SELECT COUNT(*) FROM outing_participants").fetchone()[0]
            == 0
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM outing_live_positions").fetchone()[
                0
            ]
            == 0
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM outing_live_events").fetchone()[0]
            == 0
        )
    with pytest.raises(OutingNotFoundError):
        service.update_position(
            SLUG,
            PARTICIPANT_ID,
            PARTICIPANT_TOKEN,
            _update(1, captured_at=clock.value),
        )
    with pytest.raises(OutingNotFoundError):
        service.clear_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN)


def test_update_transaction_rechecks_and_deletes_newly_expired_outing(
    tmp_path: Path,
) -> None:
    outings, repository, _, clock = _repositories(
        tmp_path,
        outing_expires_at=NOW + timedelta(seconds=10),
    )
    authorization = repository.get_participant_authorization(SLUG, PARTICIPANT_ID)
    assert authorization is not None
    position = ParticipantLivePosition(
        participant_id=PARTICIPANT_ID,
        sequence=0,
        coordinate=LiveCoordinate(lat=48.87, lon=2.1),
        accuracy_m=8,
        altitude_m=None,
        speed_m_s=None,
        heading_deg=None,
        captured_at=NOW,
        received_at=NOW,
        stale_at=NOW + timedelta(seconds=120),
        expires_at=NOW + timedelta(seconds=3_600),
    )
    record = OutingLivePositionRecord(
        participant_row_id=authorization.participant_row_id,
        outing_id=authorization.outing_id,
        participant_public_id=authorization.participant_public_id,
        client_sequence=0,
        latitude=48.87,
        longitude=2.1,
        accuracy_m=8,
        altitude_m=None,
        speed_m_s=None,
        heading_deg=None,
        captured_at_utc=NOW,
        received_at_utc=NOW,
        participant_join_order=authorization.participant_join_order,
    )
    clock.value += timedelta(seconds=11)
    with pytest.raises(OutingLiveAuthorizationContextError):
        repository.upsert_live_position(
            authorization,
            record,
            position,
            occurred_at=clock.value,
            retention_cutoff=clock.value - timedelta(minutes=15),
            maximum_event_count=10,
        )
    assert outings.get_by_slug(SLUG) is None


@pytest.mark.asyncio
async def test_sse_emits_outing_closed_after_outing_expiry(
    tmp_path: Path,
) -> None:
    _, _, service, clock = _repositories(
        tmp_path,
        outing_expires_at=NOW + timedelta(seconds=10),
    )
    service.update_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN, _update())
    state = service.stream_state(SLUG)
    broker = OutingLiveBroker()
    subscription = broker.subscribe(SLUG)
    wakeup = await subscription.__aenter__()
    stream = _event_stream(
        SLUG,
        service,
        wakeup,
        subscription,
        state.snapshot,
        state.snapshot.cursor,
        state.oldest_retained_event_id,
        None,
    )
    assert "event: snapshot" in await anext(stream)
    clock.value += timedelta(seconds=11)
    broker.notify(SLUG)
    closed = await asyncio.wait_for(anext(stream), timeout=5)
    assert closed == "event: outing_closed\ndata: {}\n\n"
    with pytest.raises(StopAsyncIteration):
        await anext(stream)


@pytest.mark.asyncio
async def test_expired_outing_live_api_is_uniform_not_found(
    tmp_path: Path,
) -> None:
    outings, live_repository, live, clock = _repositories(
        tmp_path,
        outing_expires_at=NOW + timedelta(seconds=10),
    )
    app = create_app(
        _NoRouteService(),
        settings=Settings(
            nature_index_path=None,
            poi_index_path=None,
            saved_route_database_path=None,
            outing_database_path=None,
        ),
        plan_service=_NoPlanService(),
        saved_route_service=UnavailableSavedRouteService(),
        outing_service=OutingService(
            outings,
            live_repository=live_repository,
            clock=clock,
        ),
        outing_live_service=live,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            path = f"/v2/outings/{SLUG}/participants/{PARTICIPANT_ID}/position"
            headers = {"X-Sugarglider-Participant-Token": PARTICIPANT_TOKEN}
            assert (
                await client.put(
                    path,
                    headers=headers,
                    json=_update().model_dump(mode="json"),
                )
            ).status_code == 200
            clock.value += timedelta(seconds=11)
            responses = (
                await client.get(f"/v2/outings/{SLUG}/live"),
                await client.put(
                    path,
                    headers=headers,
                    json=_update(1, captured_at=clock.value).model_dump(mode="json"),
                ),
                await client.delete(path, headers=headers),
            )
    assert {response.status_code for response in responses} == {404}
    assert {response.json()["error"]["code"] for response in responses} == {
        "outing_not_found"
    }
    assert outings.get_by_slug(SLUG) is None


def test_atomic_participant_leave_keeps_clear_event(tmp_path: Path) -> None:
    outings, live_repository, live, clock = _repositories(tmp_path)
    live.update_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN, _update())
    ordinary = OutingService(
        outings,
        live_repository=live_repository,
        live_maximum_events_per_outing=10,
        clock=clock,
    )
    assert ordinary.remove_participant(
        SLUG,
        PARTICIPANT_ID,
        PARTICIPANT_TOKEN,
    )
    assert outings.get_by_slug(SLUG) is not None
    assert outings.get_by_slug(SLUG).participants == ()  # type: ignore[union-attr]
    event = live.events_after(SLUG, 1)[0]
    assert event.clear_reason == "participant_left"
    assert event.participant_id == PARTICIPANT_ID


@pytest.mark.parametrize("sharing_state", ["active", "stopped", "never"])
def test_every_live_backed_leave_appends_one_participant_left_tombstone(
    tmp_path: Path,
    sharing_state: str,
) -> None:
    outings, live_repository, live, clock = _repositories(tmp_path)
    if sharing_state != "never":
        live.update_position(
            SLUG,
            PARTICIPANT_ID,
            PARTICIPANT_TOKEN,
            _update(),
        )
    if sharing_state == "stopped":
        assert live.clear_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN)
    ordinary = OutingService(
        outings,
        live_repository=live_repository,
        live_maximum_events_per_outing=10,
        clock=clock,
    )
    assert ordinary.remove_participant(
        SLUG,
        PARTICIPANT_ID,
        PARTICIPANT_TOKEN,
    )
    events = live.events_after(SLUG, 0)
    participant_left = tuple(
        event for event in events if event.clear_reason == "participant_left"
    )
    assert len(participant_left) == 1
    assert participant_left[0].participant_id == PARTICIPANT_ID
    aggregate = outings.get_by_slug(SLUG)
    assert aggregate is not None and aggregate.participants == ()
    assert live.snapshot(SLUG).positions == ()


def test_leave_transaction_rolls_back_when_participant_context_mismatches(
    tmp_path: Path,
) -> None:
    outings, repository, live, _ = _repositories(tmp_path)
    live.update_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN, _update())
    authorization = cast(
        OutingParticipantAuthorizationRecord,
        repository.get_participant_authorization(SLUG, PARTICIPANT_ID),
    )
    bad = OutingParticipantAuthorizationRecord(
        **{
            **authorization.__dict__,
            "participant_row_id": "wrong-row",
        }
    )
    with pytest.raises(OutingLiveRepositoryError):
        repository.delete_participant_with_live_cleanup(
            bad,
            occurred_at=NOW,
            retention_cutoff=NOW - timedelta(minutes=15),
            maximum_event_count=10,
        )
    assert len(cast(object, outings.get_by_slug(SLUG)).participants) == 1  # type: ignore[attr-defined]
    assert len(live.snapshot(SLUG).positions) == 1
    assert live.snapshot(SLUG).cursor == 1


@pytest.mark.asyncio
async def test_live_api_authorizes_before_body_validation_and_never_returns_token(
    tmp_path: Path,
) -> None:
    outings, live_repository, live, clock = _repositories(tmp_path)
    app = create_app(
        _NoRouteService(),
        settings=Settings(
            nature_index_path=None,
            poi_index_path=None,
            saved_route_database_path=None,
            outing_database_path=None,
        ),
        plan_service=_NoPlanService(),
        saved_route_service=UnavailableSavedRouteService(),
        outing_service=OutingService(
            outings,
            live_repository=live_repository,
            clock=clock,
        ),
        outing_live_service=live,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            path = f"/v2/outings/{SLUG}/participants/{PARTICIPANT_ID}/position"
            invalid_body = _update().model_dump(mode="json")
            invalid_body["accuracy_m"] = -1
            wrong = await client.put(
                path,
                headers={"X-Sugarglider-Participant-Token": "wrong"},
                json=invalid_body,
            )
            missing = await client.put(path, json=invalid_body)
            valid_invalid = await client.put(
                path,
                headers={"X-Sugarglider-Participant-Token": PARTICIPANT_TOKEN},
                json=invalid_body,
            )
            assert wrong.status_code == missing.status_code == 404
            assert valid_invalid.status_code == 422

            updated = await client.put(
                path,
                headers={"X-Sugarglider-Participant-Token": PARTICIPANT_TOKEN},
                json=_update().model_dump(mode="json"),
            )
            assert updated.status_code == 200
            assert updated.headers["cache-control"] == "no-store"
            assert "token" not in updated.text
            maximum = await client.put(
                path,
                headers={"X-Sugarglider-Participant-Token": PARTICIPANT_TOKEN},
                json=_update(SQLITE_SIGNED_INTEGER_MAX).model_dump(mode="json"),
            )
            assert maximum.status_code == 200
            assert maximum.json()["sequence"] == SQLITE_SIGNED_INTEGER_MAX
            cursor_before_overflow = (
                await client.get(f"/v2/outings/{SLUG}/live")
            ).json()["cursor"]
            overflow = await client.put(
                path,
                headers={"X-Sugarglider-Participant-Token": PARTICIPANT_TOKEN},
                json={
                    **_update().model_dump(mode="json"),
                    "sequence": SQLITE_SIGNED_INTEGER_MAX + 1,
                },
            )
            assert overflow.status_code == 422
            assert "SQLite" not in overflow.text
            assert "traceback" not in overflow.text.lower()
            assert (await client.get(f"/v2/outings/{SLUG}/live")).json()[
                "cursor"
            ] == cursor_before_overflow
            conflict = await client.put(
                path,
                headers={"X-Sugarglider-Participant-Token": PARTICIPANT_TOKEN},
                json=_update(latitude=48.9).model_dump(mode="json"),
            )
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == (
                "outing_position_sequence_conflict"
            )
            snapshot = await client.get(f"/v2/outings/{SLUG}/live")
            assert snapshot.status_code == 200
            assert snapshot.headers["cache-control"] == "private, no-store"
            assert snapshot.headers["x-robots-tag"] == ("noindex, nofollow, noarchive")
            assert "token" not in snapshot.text
            sse_messages = await _capture_initial_sse(
                app,
                f"/v2/outings/{SLUG}/events",
            )
            start = sse_messages[0]
            assert start["type"] == "http.response.start"
            response_headers = dict(cast(list[tuple[bytes, bytes]], start["headers"]))
            assert response_headers[b"content-type"].startswith(b"text/event-stream")
            assert response_headers[b"cache-control"] == b"no-store, no-transform"
            assert response_headers[b"x-accel-buffering"] == b"no"
            body = b"".join(
                cast(bytes, message.get("body", b""))
                for message in sse_messages
                if message["type"] == "http.response.body"
            )
            assert b"event: snapshot" in body
            assert PARTICIPANT_TOKEN.encode() not in body
            clear_headers = {"X-Sugarglider-Participant-Token": PARTICIPANT_TOKEN}
            cleared = await client.delete(path, headers=clear_headers)
            repeated_clear = await client.delete(path, headers=clear_headers)
            assert cleared.status_code == repeated_clear.status_code == 204
            bad_cursor = await client.get(
                f"/v2/outings/{SLUG}/events",
                headers={"Last-Event-ID": "-1"},
            )
            missing_stream = await client.get(
                "/v2/outings/missing_outing_123456/events"
            )
            assert bad_cursor.status_code == 400
            assert bad_cursor.json()["error"]["code"] == ("outing_live_cursor_invalid")
            assert missing_stream.status_code == 404


@pytest.mark.asyncio
async def test_broker_is_per_outing_coalesced_and_cleans_subscribers() -> None:
    broker = OutingLiveBroker()
    async with broker.subscribe(SLUG) as first:
        async with broker.subscribe("other_outing_12345678") as second:
            broker.notify(SLUG)
            broker.notify(SLUG)
            await asyncio.sleep(0)
            assert first.is_set()
            assert not second.is_set()
            assert broker.subscriber_count(SLUG) == 1
    assert broker.subscriber_count(SLUG) == 0


@pytest.mark.asyncio
async def test_broker_notify_discards_failing_loop_and_wakes_healthy_loop() -> None:
    class FailingLoop:
        def is_closed(self) -> bool:
            return False

        def call_soon_threadsafe(self, callback: Callable[[], None]) -> None:
            del callback
            raise RuntimeError("loop is closing")

    broker = OutingLiveBroker()
    stale = _Subscriber(
        loop=cast(asyncio.AbstractEventLoop, FailingLoop()),
        event=asyncio.Event(),
    )
    with broker._lock:
        broker._subscribers.setdefault(SLUG, set()).add(stale)
    async with broker.subscribe(SLUG) as healthy:
        broker.notify(SLUG)
        await asyncio.sleep(0)
        assert healthy.is_set()
        assert broker.subscriber_count(SLUG) == 1
    assert broker.subscriber_count(SLUG) == 0


@pytest.mark.asyncio
async def test_sse_snapshot_and_replay_frames_have_stable_grammar(
    tmp_path: Path,
) -> None:
    _, _, live, _ = _repositories(tmp_path)
    live.update_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN, _update())
    snapshot = live.snapshot(SLUG)
    window = live.event_window(SLUG)
    broker = OutingLiveBroker()
    subscription = broker.subscribe(SLUG)
    wakeup = await subscription.__aenter__()
    stream = _event_stream(
        SLUG,
        live,
        wakeup,
        subscription,
        snapshot,
        window.current_cursor,
        window.oldest_retained_event_id,
        None,
    )
    frame = await anext(stream)
    assert frame.startswith("retry: 5000\nid: 1\nevent: snapshot\n")
    assert frame.endswith("\n\n")
    await cast(AsyncGenerator[str], stream).aclose()
    assert broker.subscriber_count(SLUG) == 0

    replay_subscription = broker.subscribe(SLUG)
    replay_wakeup = await replay_subscription.__aenter__()
    replay_stream = _event_stream(
        SLUG,
        live,
        replay_wakeup,
        replay_subscription,
        snapshot,
        window.current_cursor,
        window.oldest_retained_event_id,
        0,
    )
    replay = await anext(replay_stream)
    assert replay.startswith("id: 1\nevent: position_updated\n")
    await cast(AsyncGenerator[str], replay_stream).aclose()

    reset_subscription = broker.subscribe(SLUG)
    reset_wakeup = await reset_subscription.__aenter__()
    reset_stream = _event_stream(
        SLUG,
        live,
        reset_wakeup,
        reset_subscription,
        snapshot,
        window.current_cursor,
        window.oldest_retained_event_id,
        2,
    )
    reset = await anext(reset_stream)
    assert reset.startswith("id: 1\nevent: reset\n")
    await cast(AsyncGenerator[str], reset_stream).aclose()

    live.keepalive_seconds = 0
    keepalive_subscription = broker.subscribe(SLUG)
    keepalive_wakeup = await keepalive_subscription.__aenter__()
    keepalive_stream = _event_stream(
        SLUG,
        live,
        keepalive_wakeup,
        keepalive_subscription,
        snapshot,
        window.current_cursor,
        window.oldest_retained_event_id,
        1,
    )
    keepalive = await anext(keepalive_stream)
    assert keepalive == ": keep-alive\n\n"
    assert "id:" not in keepalive
    await cast(AsyncGenerator[str], keepalive_stream).aclose()

    assert _parse_cursor("0") == 0
    assert _parse_cursor("123") == 123
    for invalid in ("", "-1", "+1", "１", " 1"):
        with pytest.raises(OutingLiveCursorInvalidError):
            _parse_cursor(invalid)


def test_corrupt_event_json_fails_safe(tmp_path: Path) -> None:
    outings, _, live, _ = _repositories(tmp_path)
    live.update_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN, _update())
    with outings._connection() as connection, connection:
        connection.execute(
            """
            UPDATE outing_live_events
            SET payload_json = ?
            WHERE outing_id = ? AND event_id = 1
            """,
            ('{"event_id":1}', "outing-internal"),
        )
    with pytest.raises(Exception) as error:
        live.events_after(SLUG, 0)
    assert error.type.__name__ == "OutingStorageError"


def test_persisted_current_and_event_timestamps_are_revalidated(
    tmp_path: Path,
) -> None:
    outings, _, live, _ = _repositories(tmp_path)
    live.update_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN, _update())
    with outings._connection() as connection, connection:
        connection.execute(
            """
            UPDATE outing_live_positions
            SET captured_at_utc = ?
            WHERE participant_public_id = ?
            """,
            ("2020-01-01T00:00:00.000000Z", PARTICIPANT_ID),
        )
        row = connection.execute(
            """
            SELECT payload_json
            FROM outing_live_events
            WHERE outing_id = ? AND event_id = 1
            """,
            ("outing-internal",),
        ).fetchone()
        assert row is not None
        payload = json.loads(str(row["payload_json"]))
        payload["position"]["captured_at"] = "2020-01-01T00:00:00Z"
        connection.execute(
            """
            UPDATE outing_live_events
            SET payload_json = ?
            WHERE outing_id = ? AND event_id = 1
            """,
            (
                json.dumps(payload, separators=(",", ":")),
                "outing-internal",
            ),
        )
    with pytest.raises(OutingStorageError):
        live.snapshot(SLUG)
    with pytest.raises(OutingStorageError):
        live.events_after(SLUG, 0)


def test_outing_deletion_cascades_live_state(tmp_path: Path) -> None:
    outings, _, live, _ = _repositories(tmp_path)
    live.update_position(SLUG, PARTICIPANT_ID, PARTICIPANT_TOKEN, _update())
    assert outings.delete_outing_by_id("outing-internal")
    with outings._connection() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM outing_live_positions").fetchone()[
                0
            ]
            == 0
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM outing_live_events").fetchone()[0]
            == 0
        )


def test_live_config_defaults_aliases_and_cross_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = Settings()
    assert defaults.outing_live_stale_after_seconds == 120
    assert defaults.outing_live_expire_after_seconds == 3_600
    assert defaults.outing_live_max_update_age_seconds == 600
    assert defaults.outing_live_future_tolerance_seconds == 30
    assert defaults.outing_live_event_retention_seconds == 900
    assert defaults.outing_live_max_events_per_outing == 1_000
    assert defaults.outing_live_sse_keepalive_seconds == 15
    monkeypatch.setenv("SUGARGLIDER_OUTING_LIVE_STALE_AFTER_SECONDS", "45")
    assert Settings().outing_live_stale_after_seconds == 45
    with pytest.raises(ValidationError):
        Settings(
            outing_live_stale_after_seconds=120,
            outing_live_expire_after_seconds=120,
        )
    with pytest.raises(ValidationError):
        Settings(
            outing_live_sse_keepalive_seconds=60,
            outing_live_event_retention_seconds=60,
        )
