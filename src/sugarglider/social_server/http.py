"""Bounded ASGI admission and logs that never contain request data."""

import asyncio
import hashlib
import json
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sugarglider.social_server.settings import SocialSettings

logger = logging.getLogger("sugarglider.social.http")
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_METHODS = _SAFE_METHODS | {"POST", "PUT", "DELETE"}


@dataclass
class _Bucket:
    requests: float
    creations: float
    updated: float
    last_seen: float
    streams: int = 0


class _Rejected(Exception):
    def __init__(self, status: int, code: str) -> None:
        self.status = status
        self.code = code


class SocialHttpMiddleware:
    """One-worker limits; SQLite remains authoritative across restarts."""

    def __init__(
        self,
        app: ASGIApp,
        settings: SocialSettings,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self.settings = settings
        self.clock = clock
        self._salt = secrets.token_bytes(32)
        self._buckets: dict[bytes, _Bucket] = {}
        self._requests = 0
        self._writes = 0
        self._streams = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = self.clock()
        status = 500
        response_started = False
        request_id = secrets.token_hex(8)
        method = str(scope["method"])
        path = str(scope["path"])
        operation = _operation(path)
        is_stream = method == "GET" and operation == "events"
        is_write = method not in _SAFE_METHODS
        admitted = False
        bucket: _Bucket | None = None

        async def safe_send(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = int(message["status"])
                response_started = True
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                headers["X-Frame-Options"] = "DENY"
                headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
                if operation != "shell" and "cache-control" not in headers:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        try:
            self._validate_headers(scope)
            if operation != "health":
                client = scope.get("client")
                address = str(client[0]) if client else "unknown"
                key = hashlib.blake2b(
                    address.encode(), key=self._salt, digest_size=16
                ).digest()
                bucket = self._reserve_rate(
                    key,
                    creation=method == "POST"
                    and path in ("/v2/saved-routes", "/v2/outings"),
                )
            self._reserve_active(bucket, is_stream=is_stream, is_write=is_write)
            admitted = True
            # Read and cap bodies before FastAPI/Pydantic parse or authorization.
            # At most max_active_writes such buffers exist at a time.
            body = await self._read_body(receive, is_write=is_write)
            delivered = False

            async def replay() -> Message:
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                # Preserve actual disconnect notification for StreamingResponse.
                return await receive()

            await self.app(scope, replay, safe_send)
        except _Rejected as exc:
            await _error(exc.status, exc.code)(scope, receive, safe_send)
        except Exception:
            # Never let Uvicorn print a traceback containing request URLs, model
            # values, SQLite statements, capabilities or precise coordinates.
            if not response_started:
                await _error(500, "internal_error")(scope, receive, safe_send)
            else:
                status = 500
                await send({"type": "http.response.body", "body": b""})
        finally:
            if admitted:
                if is_stream:
                    self._streams -= 1
                    if bucket is not None:
                        bucket.streams -= 1
                else:
                    self._requests -= 1
                if is_write:
                    self._writes -= 1
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": method if method in _METHODS else "OTHER",
                        "operation": operation,
                        "status": status,
                        "duration_ms": round((self.clock() - started) * 1000),
                    },
                    separators=(",", ":"),
                )
            )

    def _validate_headers(self, scope: Scope) -> None:
        headers = Headers(scope=scope)
        hosts = headers.getlist("host")
        if (
            len(hosts) != 1
            or hosts[0].lower() != urlsplit(self.settings.public_origin).netloc
        ):
            raise _Rejected(400, "invalid_host")
        origin = headers.getlist("origin")
        if origin and origin != [self.settings.public_origin]:
            raise _Rejected(403, "origin_not_allowed")
        if (
            scope["method"] not in _SAFE_METHODS
            and headers.get("sec-fetch-site") == "cross-site"
        ):
            raise _Rejected(403, "origin_not_allowed")
        if scope.get("query_string"):
            raise _Rejected(400, "query_not_supported")
        if scope["method"] not in _METHODS:
            raise _Rejected(405, "method_not_allowed")
        lengths = headers.getlist("content-length")
        if lengths:
            if (
                len(lengths) != 1
                or not lengths[0].isascii()
                or not lengths[0].isdigit()
            ):
                raise _Rejected(400, "invalid_content_length")
            if len(lengths[0]) > 12 or int(lengths[0]) > self.settings.max_body_bytes:
                raise _Rejected(413, "body_too_large")
        if headers.get("content-encoding", "identity").lower() != "identity":
            raise _Rejected(415, "compressed_body_not_supported")

    def _reserve_rate(self, key: bytes, *, creation: bool) -> _Bucket:
        now = self.clock()
        settings = self.settings
        bucket = self._buckets.get(key)
        if bucket is None:
            # A full table rejects new clients instead of evicting recent limits.
            self._buckets = {
                identity: value
                for identity, value in self._buckets.items()
                if value.streams or now - value.last_seen < 3600
            }
            if len(self._buckets) >= settings.max_client_buckets:
                raise _Rejected(503, "client_capacity_reached")
            bucket = _Bucket(
                settings.max_requests_per_minute,
                settings.max_creations_per_hour,
                now,
                now,
            )
            self._buckets[key] = bucket
        elapsed = max(0, now - bucket.updated)
        bucket.requests = min(
            settings.max_requests_per_minute,
            bucket.requests + elapsed * settings.max_requests_per_minute / 60,
        )
        bucket.creations = min(
            settings.max_creations_per_hour,
            bucket.creations + elapsed * settings.max_creations_per_hour / 3600,
        )
        bucket.updated = bucket.last_seen = now
        if bucket.requests < 1 or (creation and bucket.creations < 1):
            raise _Rejected(429, "rate_limited")
        bucket.requests -= 1
        if creation:
            bucket.creations -= 1
        return bucket

    def _reserve_active(
        self, bucket: _Bucket | None, *, is_stream: bool, is_write: bool
    ) -> None:
        settings = self.settings
        if is_stream:
            if self._streams >= settings.max_event_streams or (
                bucket is not None
                and bucket.streams >= settings.max_event_streams_per_client
            ):
                raise _Rejected(503, "stream_capacity_reached")
        elif self._requests >= settings.max_active_requests:
            raise _Rejected(503, "request_capacity_reached")
        if is_write and self._writes >= settings.max_active_writes:
            raise _Rejected(503, "write_capacity_reached")
        if is_stream:
            self._streams += 1
            if bucket is not None:
                bucket.streams += 1
        else:
            self._requests += 1
        if is_write:
            self._writes += 1

    async def _read_body(self, receive: Receive, *, is_write: bool) -> bytes:
        body = bytearray()
        limit = self.settings.max_body_bytes if is_write else 0
        try:
            async with asyncio.timeout(self.settings.body_timeout_seconds):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        raise _Rejected(400, "request_disconnected")
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > limit:
                        raise _Rejected(413, "body_too_large")
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        return bytes(body)
        except TimeoutError:
            raise _Rejected(408, "body_timeout") from None


def _error(status: int, code: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": "The request cannot be accepted."}},
        status_code=status,
        headers={"Retry-After": "60"} if status in (429, 503) else {},
    )


def _operation(path: str) -> str:
    """Return a fixed category, never any part of a user-controlled URL."""
    if path in ("/health", "/ready"):
        return "health"
    if path.startswith("/v2/outings/") and path.endswith("/events"):
        return "events"
    if path.startswith("/v2/outings/") and path.endswith(("/position", "/live")):
        return "live"
    if path == "/v2/outings" or path.startswith("/v2/outings/"):
        return "outings"
    if path == "/v2/saved-routes" or path.startswith("/v2/saved-routes/"):
        return "saved_routes"
    if path.startswith(("/r/", "/o/")):
        return "shared_page"
    if path in ("/", "/manifest.webmanifest", "/service-worker.js") or path.startswith(
        "/static/"
    ):
        return "shell"
    return "other"
