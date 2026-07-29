"""Process-local, payload-free wakeups for durable outing live events."""

import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass


@dataclass(frozen=True)
class _Subscriber:
    loop: asyncio.AbstractEventLoop
    event: asyncio.Event


class OutingLiveBroker:
    """Coalesce per-subscriber wakeups while SQLite remains durable truth."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[_Subscriber]] = {}

    @asynccontextmanager
    async def subscribe(self, slug: str) -> AsyncIterator[asyncio.Event]:
        subscriber = _Subscriber(
            loop=asyncio.get_running_loop(),
            event=asyncio.Event(),
        )
        with self._lock:
            self._subscribers.setdefault(slug, set()).add(subscriber)
        try:
            yield subscriber.event
        finally:
            with self._lock:
                subscribers = self._subscribers.get(slug)
                if subscribers is not None:
                    subscribers.discard(subscriber)
                    if not subscribers:
                        self._subscribers.pop(slug, None)

    def notify(self, slug: str) -> None:
        """Wake only subscribers for one outing from any worker thread."""
        with self._lock:
            subscribers = tuple(self._subscribers.get(slug, ()))
        for subscriber in subscribers:
            if subscriber.loop.is_closed():
                self._discard(slug, subscriber)
                continue
            try:
                subscriber.loop.call_soon_threadsafe(subscriber.event.set)
            except RuntimeError:
                self._discard(slug, subscriber)

    def subscriber_count(self, slug: str) -> int:
        """Expose bounded state for deterministic tests."""
        with self._lock:
            return len(self._subscribers.get(slug, ()))

    def _discard(self, slug: str, subscriber: _Subscriber) -> None:
        with self._lock:
            subscribers = self._subscribers.get(slug)
            if subscribers is not None:
                subscribers.discard(subscriber)
                if not subscribers:
                    self._subscribers.pop(slug, None)
