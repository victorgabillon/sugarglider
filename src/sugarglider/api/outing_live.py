"""Authenticated live positions and durable SSE for shared outings."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import Annotated

from fastapi import APIRouter, Body, Header, Response, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from sugarglider.api.dependencies import (
    AuthorizedOutingParticipantTokenDependency,
    OutingLiveBrokerDependency,
    OutingLiveServiceDependency,
)
from sugarglider.outings.errors import (
    OutingLiveCursorInvalidError,
    OutingNotFoundError,
    OutingStorageError,
)
from sugarglider.outings.live_models import (
    SQLITE_SIGNED_INTEGER_MAX,
    OutingLiveEvent,
    OutingLiveSnapshot,
    OutingPositionUpdate,
    ParticipantLivePosition,
)
from sugarglider.outings.live_service import OutingLiveOperations

router = APIRouter(prefix="/v2/outings", tags=["outing live positions"])


@router.put(
    "/{slug}/participants/{participant_id}/position",
    response_model=ParticipantLivePosition,
)
def update_outing_position(
    slug: str,
    participant_id: str,
    update: Annotated[OutingPositionUpdate, Body()],
    live: OutingLiveServiceDependency,
    broker: OutingLiveBrokerDependency,
    response: Response,
    participant_token: AuthorizedOutingParticipantTokenDependency,
) -> ParticipantLivePosition:
    """Publish an unsnapped current position after participant authorization."""
    result = live.update_position(
        slug,
        participant_id,
        participant_token,
        update,
    )
    if result.event_appended:
        broker.notify(slug)
    response.headers["Cache-Control"] = "no-store"
    return result.position


@router.delete(
    "/{slug}/participants/{participant_id}/position",
    status_code=status.HTTP_204_NO_CONTENT,
)
def clear_outing_position(
    slug: str,
    participant_id: str,
    live: OutingLiveServiceDependency,
    broker: OutingLiveBrokerDependency,
    participant_token: AuthorizedOutingParticipantTokenDependency,
) -> Response:
    """Idempotently stop sharing an authorized participant's position."""
    if live.clear_position(slug, participant_id, participant_token):
        broker.notify(slug)
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{slug}/live", response_model=OutingLiveSnapshot)
def get_outing_live_snapshot(
    slug: str,
    live: OutingLiveServiceDependency,
    response: Response,
) -> OutingLiveSnapshot:
    """Return authoritative current state without reconstructing event history."""
    response.headers.update(_snapshot_headers())
    return live.snapshot(slug)


@router.get("/{slug}/events")
async def stream_outing_live_events(
    slug: str,
    live: OutingLiveServiceDependency,
    broker: OutingLiveBrokerDependency,
    last_event_id: Annotated[
        str | None,
        Header(alias="Last-Event-ID"),
    ] = None,
) -> StreamingResponse:
    """Stream snapshot/replay/reset frames backed by durable SQLite polling."""
    cursor = _parse_cursor(last_event_id)
    subscription = broker.subscribe(slug)
    wakeup = await subscription.__aenter__()
    try:
        initial_state = await run_in_threadpool(live.stream_state, slug)
    except BaseException:
        await subscription.__aexit__(None, None, None)
        raise
    stream = _event_stream(
        slug,
        live,
        wakeup,
        subscription,
        initial_state.snapshot,
        initial_state.snapshot.cursor,
        initial_state.oldest_retained_event_id,
        cursor,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store, no-transform",
            "X-Robots-Tag": "noindex, nofollow, noarchive",
            "Referrer-Policy": "no-referrer",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _event_stream(
    slug: str,
    live: OutingLiveOperations,
    wakeup: asyncio.Event,
    subscription: AbstractAsyncContextManager[asyncio.Event],
    initial_snapshot: OutingLiveSnapshot,
    current_cursor: int,
    oldest_event_id: int | None,
    requested_cursor: int | None,
) -> AsyncIterator[str]:
    cursor = requested_cursor
    try:
        if cursor is None:
            cursor = current_cursor
            yield _snapshot_frame("snapshot", initial_snapshot, retry=True)
        elif _cursor_requires_reset(cursor, current_cursor, oldest_event_id):
            cursor = current_cursor
            yield _snapshot_frame("reset", initial_snapshot)
        else:
            try:
                events = await run_in_threadpool(live.events_after, slug, cursor)
            except OutingNotFoundError:
                yield "event: outing_closed\ndata: {}\n\n"
                return
            except OutingStorageError:
                return
            if not _replay_covers_state(cursor, current_cursor, events):
                try:
                    state = await run_in_threadpool(live.stream_state, slug)
                except OutingNotFoundError:
                    yield "event: outing_closed\ndata: {}\n\n"
                    return
                except OutingStorageError:
                    return
                cursor = state.snapshot.cursor
                yield _snapshot_frame("reset", state.snapshot)
            else:
                for event in events:
                    yield _event_frame(event)
                    cursor = event.event_id

        while True:
            timed_out = False
            try:
                await asyncio.wait_for(
                    wakeup.wait(),
                    timeout=live.keepalive_seconds,
                )
            except TimeoutError:
                timed_out = True
            wakeup.clear()
            try:
                state = await run_in_threadpool(live.stream_state, slug)
            except OutingNotFoundError:
                yield "event: outing_closed\ndata: {}\n\n"
                return
            except OutingStorageError:
                return
            if _cursor_requires_reset(
                cursor,
                state.snapshot.cursor,
                state.oldest_retained_event_id,
            ):
                cursor = state.snapshot.cursor
                yield _snapshot_frame("reset", state.snapshot)
                continue
            try:
                events = await run_in_threadpool(live.events_after, slug, cursor)
            except OutingNotFoundError:
                yield "event: outing_closed\ndata: {}\n\n"
                return
            except OutingStorageError:
                return
            if not _replay_covers_state(cursor, state.snapshot.cursor, events):
                try:
                    fresh_state = await run_in_threadpool(live.stream_state, slug)
                except OutingNotFoundError:
                    yield "event: outing_closed\ndata: {}\n\n"
                    return
                except OutingStorageError:
                    return
                cursor = fresh_state.snapshot.cursor
                yield _snapshot_frame("reset", fresh_state.snapshot)
                continue
            if events:
                for event in events:
                    yield _event_frame(event)
                    cursor = event.event_id
            elif timed_out:
                yield ": keep-alive\n\n"
    finally:
        await subscription.__aexit__(None, None, None)


def _parse_cursor(value: str | None) -> int | None:
    if value is None:
        return None
    if not value or any(character not in "0123456789" for character in value):
        raise OutingLiveCursorInvalidError
    try:
        cursor = int(value)
    except ValueError as exc:
        raise OutingLiveCursorInvalidError from exc
    if cursor > SQLITE_SIGNED_INTEGER_MAX:
        raise OutingLiveCursorInvalidError
    return cursor


def _cursor_requires_reset(
    cursor: int,
    current_cursor: int,
    oldest_event_id: int | None,
) -> bool:
    if cursor > current_cursor:
        return True
    if cursor == current_cursor:
        return False
    return oldest_event_id is None or cursor < oldest_event_id - 1


def _replay_covers_state(
    previous_cursor: int,
    represented_current_cursor: int,
    events: tuple[OutingLiveEvent, ...],
) -> bool:
    if represented_current_cursor < previous_cursor:
        return False
    expected_event_id = previous_cursor + 1
    for event in events:
        if event.event_id != expected_event_id:
            return False
        expected_event_id += 1
    return represented_current_cursor == previous_cursor or (
        bool(events) and events[-1].event_id >= represented_current_cursor
    )


def _snapshot_frame(
    event_name: str,
    snapshot: OutingLiveSnapshot,
    *,
    retry: bool = False,
) -> str:
    prefix = "retry: 5000\n" if retry else ""
    return (
        f"{prefix}id: {snapshot.cursor}\nevent: {event_name}\n"
        f"data: {snapshot.model_dump_json()}\n\n"
    )


def _event_frame(event: OutingLiveEvent) -> str:
    return (
        f"id: {event.event_id}\nevent: {event.event_type}\n"
        f"data: {event.model_dump_json()}\n\n"
    )


def _snapshot_headers() -> dict[str, str]:
    return {
        "Cache-Control": "private, no-store",
        "X-Robots-Tag": "noindex, nofollow, noarchive",
        "Referrer-Policy": "no-referrer",
    }
