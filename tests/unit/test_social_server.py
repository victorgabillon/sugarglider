"""Production social deployment contracts, using only in-process ASGI and SQLite."""

import asyncio
import json
import logging
import shutil
import sqlite3
from collections.abc import AsyncIterator
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import ValidationError
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from sugarglider.gpx.writer import write_plan_gpx
from sugarglider.outings.live_broker import OutingLiveBroker
from sugarglider.outings.live_service import OutingLiveOperations
from sugarglider.planning.models import PlanRequest
from sugarglider.planning.result import PlanCandidate
from sugarglider.saved_routes.models import SavedRouteCreateRequest
from sugarglider.saved_routes.service import SavedRouteService
from sugarglider.saved_routes.sqlite_repository import SQLiteSavedRouteRepository
from sugarglider.social_server.__main__ import PrivateFormatter
from sugarglider.social_server.app import create_social_app
from sugarglider.social_server.http import SocialHttpMiddleware
from sugarglider.social_server.maintenance import cleanup
from sugarglider.social_server.settings import SocialSettings
from sugarglider.social_server.sqlite_repository import (
    BackupError,
    create_backup,
    storage_ready,
    verify_backup,
)

ORIGIN = "https://sugarglider.example"


@pytest.fixture
def social_settings(tmp_path: Path) -> SocialSettings:
    return SocialSettings(
        public_origin=ORIGIN, data_directory=tmp_path / "data", minimum_free_bytes=0
    )


@pytest.fixture
def social_app(
    social_settings: SocialSettings, monkeypatch: pytest.MonkeyPatch
) -> FastAPI:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            "production must never initialize routing or read regional data"
        )

    monkeypatch.setattr(
        "sugarglider.routing.graphhopper.GraphHopperClient.__init__", forbidden
    )
    monkeypatch.setattr("sugarglider.nature.index.load_nature_index", forbidden)
    monkeypatch.setattr("sugarglider.pois.index.load_poi_index", forbidden)
    return create_social_app(social_settings)


@pytest_asyncio.fixture
async def social_client(social_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with (
        social_app.router.lifespan_context(social_app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=social_app), base_url=ORIGIN
        ) as client,
    ):
        yield client


@pytest.fixture
def social_save_request(
    saved_route_source_request: PlanRequest, saved_route_candidate: PlanCandidate
) -> SavedRouteCreateRequest:
    return SavedRouteCreateRequest(
        source_request=saved_route_source_request, candidate=saved_route_candidate
    )


async def _create_outing(
    client: httpx.AsyncClient, save: SavedRouteCreateRequest
) -> tuple[str, dict[str, object]]:
    response = await client.post("/v2/saved-routes", json=save.model_dump(mode="json"))
    assert response.status_code == 201
    saved = response.json()
    response = await client.post(
        "/v2/outings",
        json={
            "title": "Synthetic outing",
            "participant_display_name": "Fixture",
            "saved_route_slug": saved["slug"],
        },
    )
    assert response.status_code == 201
    return str(saved["slug"]), cast(dict[str, object], response.json())


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "http://sugarglider.example",
        "https://user:secret@host",
        "https://host/path",
        "https://host?secret=yes",
        "https://*.example",
        "https://host:wrong",
    ],
)
def test_production_requires_exact_https_origin(origin: str) -> None:
    with pytest.raises(ValidationError):
        SocialSettings(public_origin=origin)


def test_social_environment_does_not_read_reference_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        "SUGARGLIDER_SAVED_ROUTE_DATABASE_PATH=/unwanted\nSUGARGLIDER_OUTING_TTL_DAYS=0\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SUGARGLIDER_SOCIAL_PUBLIC_ORIGIN", ORIGIN)
    settings = SocialSettings(data_directory=tmp_path)
    persistence = settings.persistence_settings()
    assert persistence.saved_route_database_path == tmp_path / "saved-routes.sqlite3"
    assert persistence.outing_ttl_days == 30
    assert persistence.poi_index_path is persistence.nature_index_path is None


async def test_social_startup_and_endpoints_have_no_routing_dependency(
    social_client: httpx.AsyncClient, social_app: FastAPI
) -> None:
    assert (await social_client.get("/health")).json() == {
        "status": "ok",
        "service": "social",
    }
    assert (await social_client.get("/ready")).status_code == 200
    assert not hasattr(social_app.state, "route_service")
    assert not hasattr(social_app.state, "plan_service")
    config = (await social_client.get("/v1/ui/config")).json()
    assert (
        config["saved_routes_available"]
        and config["outings_available"]
        and config["outing_live_positions_available"]
    )
    assert not config["nature_index_available"] and not config["poi_index_available"]
    profiles = (await social_client.get("/v2/routing-profiles")).json()["profiles"]
    assert len(profiles) == 6
    assert all(
        not item["available"] and item["warnings"] == ["server_planning_disabled"]
        for item in profiles
    )
    for path in (
        "/v2/plans/generate",
        "/v2/plans/reverse",
        "/v2/plans/gpx",
        "/v1/pois/search",
        "/route",
        "/regions/build",
    ):
        assert (await social_client.post(path, json={})).status_code == 404
    for path in (
        "/docs",
        "/openapi.json",
        "/tiles/0/0/0.png",
        "/region/marly/manifest.json",
    ):
        assert (await social_client.get(path)).status_code == 404


async def test_snapshot_outing_live_gpx_and_restart(
    social_client: httpx.AsyncClient,
    social_settings: SocialSettings,
    social_save_request: SavedRouteCreateRequest,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="sugarglider.social.http")
    saved_slug, outing = await _create_outing(social_client, social_save_request)
    slug = str(outing["slug"])
    participant_id = str(outing["participant_id"])
    token = str(outing["participant_token"])
    path = f"/v2/outings/{slug}/participants/{participant_id}"
    update = {
        "sequence": 1,
        "coordinate": {"lat": 48.123456789, "lon": 2.123456789},
        "accuracy_m": 8,
        "captured_at": datetime.now(UTC).isoformat(),
    }
    assert (await social_client.put(path + "/position", json=update)).status_code == 404
    assert (
        await social_client.put(
            path + "/position",
            json=update,
            headers={"X-Sugarglider-Participant-Token": token},
        )
    ).status_code == 200
    live = (await social_client.get(f"/v2/outings/{slug}/live")).json()
    assert len(live["positions"]) == 1
    for forbidden in (
        token,
        slug,
        participant_id,
        "48.123456789",
        "2.123456789",
        social_save_request.candidate.route.name,
    ):
        assert forbidden not in caplog.text
    for public_path in (f"/r/{saved_slug}", f"/o/{slug}", f"/v2/outings/{slug}"):
        response = await social_client.get(public_path)
        assert response.status_code == 200
        assert token not in response.text
        assert response.headers["referrer-policy"] == "no-referrer"
    for gpx_path in (f"/v2/saved-routes/{saved_slug}/gpx", path + "/gpx"):
        response = await social_client.get(gpx_path)
        assert response.content == write_plan_gpx(social_save_request.candidate)
    restarted = create_social_app(social_settings)
    async with (
        restarted.router.lifespan_context(restarted),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted), base_url=ORIGIN
        ) as client,
    ):
        saved = (await client.get(f"/v2/saved-routes/{saved_slug}")).json()
        assert saved["candidate"] == social_save_request.candidate.model_dump(
            mode="json"
        )
        assert (await client.get(f"/v2/outings/{slug}/live")).json()[
            "positions"
        ] == live["positions"]
        assert (
            await client.delete(
                path + "/position", headers={"X-Sugarglider-Participant-Token": token}
            )
        ).status_code == 204
        assert (await client.get(f"/v2/outings/{slug}/live")).json()["positions"] == []


async def test_shared_projection_uses_supplied_geometry_only(
    social_client: httpx.AsyncClient, social_save_request: SavedRouteCreateRequest
) -> None:
    response = await social_client.post(
        "/v2/plans/visualization",
        json=social_save_request.candidate.route.model_dump(mode="json"),
    )
    assert response.status_code == 200
    assert response.json()["features"]


@pytest.mark.parametrize(
    ("headers", "query", "expected"),
    [
        ({"Origin": "https://evil.example"}, "", 403),
        ({"Origin": "null"}, "", 403),
        ({"Host": "evil.example"}, "", 400),
        ({}, "?token=do-not-log", 400),
        ({"Content-Encoding": "gzip"}, "", 415),
        ({"Content-Length": "999999999"}, "", 413),
    ],
)
async def test_origin_query_and_body_admission(
    social_client: httpx.AsyncClient,
    headers: dict[str, str],
    query: str,
    expected: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="sugarglider.social.http")
    response = await social_client.post(
        "/v2/outings" + query, content=b"{}", headers=headers
    )
    assert response.status_code == expected
    assert "access-control-allow-origin" not in response.headers
    assert "do-not-log" not in caplog.text


async def test_readiness_detects_storage_loss_and_cleanup_failure(
    social_client: httpx.AsyncClient,
    social_app: FastAPI,
    social_settings: SocialSettings,
) -> None:
    social_app.state.retention_healthy = False
    assert (await social_client.get("/ready")).status_code == 503
    assert (await social_client.get("/health")).status_code == 200
    social_app.state.retention_healthy = True
    database = social_settings.data_directory / "outings.sqlite3"
    database.rename(database.with_suffix(".missing"))
    assert (await social_client.get("/ready")).status_code == 503
    assert not database.exists()


async def test_unavailable_storage_fails_safely(tmp_path: Path) -> None:
    data = tmp_path / "file"
    data.write_text("occupied")
    app = create_social_app(
        SocialSettings(public_origin=ORIGIN, data_directory=data, minimum_free_bytes=0)
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN
        ) as client,
    ):
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/ready")).status_code == 503
        response = await client.get("/v2/saved-routes/abcdefghijklmnopqrstuv")
        assert response.status_code == 503
        assert str(data) not in response.text


async def test_retention_purges_expired_snapshots_without_request(
    social_client: httpx.AsyncClient,
    social_app: FastAPI,
    social_settings: SocialSettings,
    social_save_request: SavedRouteCreateRequest,
) -> None:
    repository = SQLiteSavedRouteRepository(
        social_settings.data_directory / "saved-routes.sqlite3"
    )
    expired = SavedRouteService(
        repository, ttl_days=1, clock=lambda: datetime.now(UTC) - timedelta(days=5)
    ).create(social_save_request)
    assert repository.get_by_slug(expired.slug) is not None
    live = cast(OutingLiveOperations, social_app.state.outing_live_service)
    await asyncio.to_thread(cleanup, social_settings, live)
    assert repository.get_by_slug(expired.slug) is None
    assert storage_ready(social_settings)


async def test_backup_restores_exact_snapshots_but_never_location_history(
    social_client: httpx.AsyncClient,
    social_settings: SocialSettings,
    social_save_request: SavedRouteCreateRequest,
    tmp_path: Path,
) -> None:
    saved_slug, outing = await _create_outing(social_client, social_save_request)
    slug = str(outing["slug"])
    path = f"/v2/outings/{slug}/participants/{outing['participant_id']}/position"
    assert (
        await social_client.put(
            path,
            json={
                "sequence": 1,
                "coordinate": {"lat": 48.1, "lon": 2.2},
                "accuracy_m": 10,
                "captured_at": datetime.now(UTC).isoformat(),
            },
            headers={
                "X-Sugarglider-Participant-Token": str(outing["participant_token"])
            },
        )
    ).status_code == 200
    backup = create_backup(social_settings.data_directory, tmp_path / "backups")
    verify_backup(backup)
    with closing(sqlite3.connect(backup / "outings.sqlite3")) as connection:
        assert connection.execute(
            "SELECT count(*) FROM outing_participants"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM outing_live_positions"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM outing_live_events"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT live_event_cursor FROM outings"
        ).fetchone() == (1,)
    restored_directory = tmp_path / "restored"
    restored_directory.mkdir()
    for name in ("saved-routes.sqlite3", "outings.sqlite3"):
        shutil.copy2(backup / name, restored_directory / name)
    app = create_social_app(
        SocialSettings(
            public_origin=ORIGIN,
            data_directory=restored_directory,
            minimum_free_bytes=0,
        )
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN
        ) as client,
    ):
        assert (await client.get(f"/v2/saved-routes/{saved_slug}")).json()[
            "candidate"
        ] == social_save_request.candidate.model_dump(mode="json")
        assert (await client.get(f"/v2/outings/{slug}/live")).json()["positions"] == []
        assert (await client.get("/ready")).status_code == 200
    manifest = backup / "manifest.json"
    manifest.write_text(
        manifest.read_text().replace('"schema_version": 1', '"schema_version": 2')
    )
    with pytest.raises(BackupError):
        verify_backup(backup)


def test_backup_refuses_missing_source_and_unsafe_destination(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    with pytest.raises(BackupError):
        create_backup(data, data / "backups")
    with pytest.raises(BackupError):
        create_backup(data, tmp_path / "backups")
    assert list(data.iterdir()) == []
    assert list((tmp_path / "backups").iterdir()) == []


async def _ok(scope: Scope, receive: Receive, send: Send) -> None:
    await JSONResponse({"status": "ok"})(scope, receive, send)


async def test_rate_budget_expiry_capacity_and_rejections_do_not_log_clients(
    social_settings: SocialSettings,
) -> None:
    settings = social_settings.model_copy(
        update={
            "max_requests_per_minute": 12,
            "max_creations_per_hour": 1,
            "max_client_buckets": 1,
        }
    )
    now = [0.0]
    app = SocialHttpMiddleware(_ok, settings, clock=lambda: now[0])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("192.0.2.1", 1234)),
        base_url=ORIGIN,
    ) as client:
        assert (await client.post("/v2/saved-routes", json={})).status_code == 200
        assert (await client.post("/v2/saved-routes", json={})).status_code == 429
        now[0] = 3600
        assert (await client.post("/v2/saved-routes", json={})).status_code == 200
        for _ in range(11):
            assert (await client.get("/v2/outings/fixture")).status_code == 200
        assert (await client.get("/v2/outings/fixture")).status_code == 429
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("192.0.2.2", 1234)),
        base_url=ORIGIN,
    ) as client:
        assert (await client.get("/v2/outings/fixture")).status_code == 503
        now[0] += 3600
        assert (await client.get("/v2/outings/fixture")).status_code == 200


def _scope(path: str, method: str = "GET") -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "scheme": "https",
        "query_string": b"",
        "headers": [(b"host", b"sugarglider.example")],
        "client": ("192.0.2.1", 1),
        "server": ("sugarglider.example", 443),
    }


async def test_chunked_body_limit_and_timeout_precede_application(
    social_settings: SocialSettings,
) -> None:
    calls = 0

    async def handler(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal calls
        calls += 1
        await _ok(scope, receive, send)

    app = SocialHttpMiddleware(
        handler,
        social_settings.model_copy(
            update={"max_body_bytes": 1024, "body_timeout_seconds": 0.02}
        ),
    )
    for chunks, expected in (([b"a" * 800, b"b" * 800], 413), ([b"a"], 408)):
        queue: asyncio.Queue[Message] = asyncio.Queue()
        for chunk in chunks:
            queue.put_nowait({"type": "http.request", "body": chunk, "more_body": True})
        messages: list[Message] = []

        async def send(message: Message, output: list[Message] = messages) -> None:
            output.append(message)

        await app(_scope("/v2/outings", "POST"), queue.get, send)
        assert messages[0]["status"] == expected
    assert calls == 0


async def test_sse_disconnect_frees_admission_and_broker(
    social_client: httpx.AsyncClient,
    social_app: FastAPI,
    social_save_request: SavedRouteCreateRequest,
) -> None:
    _, outing = await _create_outing(social_client, social_save_request)
    slug = str(outing["slug"])
    queue: asyncio.Queue[Message] = asyncio.Queue()
    queue.put_nowait({"type": "http.request", "body": b"", "more_body": False})
    received = asyncio.Event()
    messages: list[Message] = []

    async def send(message: Message) -> None:
        messages.append(message)
        if message["type"] == "http.response.body":
            received.set()

    task = asyncio.create_task(
        social_app(_scope(f"/v2/outings/{slug}/events"), queue.get, send)
    )
    await asyncio.wait_for(received.wait(), 2)
    broker = cast(OutingLiveBroker, social_app.state.outing_live_broker)
    assert broker.subscriber_count(slug) == 1
    assert messages[0]["status"] == 200
    serialized = str(messages)
    assert "event: snapshot" in serialized
    assert str(outing["participant_token"]) not in serialized
    queue.put_nowait({"type": "http.disconnect"})
    await asyncio.wait_for(task, 2)
    assert broker.subscriber_count(slug) == 0


async def test_unexpected_exception_and_formatter_cannot_leak_private_values(
    social_settings: SocialSettings, caplog: pytest.LogCaptureFixture
) -> None:
    private = "precise-coordinate-and-private-token"

    async def fail(_scope: Scope, _receive: Receive, _send: Send) -> None:
        raise RuntimeError(private)

    app = SocialHttpMiddleware(fail, social_settings)
    caplog.set_level(logging.INFO, logger="sugarglider.social.http")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN
    ) as client:
        response = await client.get("/v2/outings/" + private)
        assert response.status_code == 500
        assert private not in response.text + caplog.text
    record = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        private,
        1,
        private,
        (),
        (RuntimeError, RuntimeError(private), None),
    )
    assert private not in PrivateFormatter().format(record)
    assert json.loads(PrivateFormatter().format(record))["event"] == "runtime_log"


async def test_active_stream_limit_releases_after_disconnect(
    social_settings: SocialSettings,
) -> None:
    opened = asyncio.Event()

    async def stream(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        opened.set()
        while (await receive())["type"] != "http.disconnect":
            pass
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    app = SocialHttpMiddleware(
        stream, social_settings.model_copy(update={"max_event_streams": 1})
    )
    queue: asyncio.Queue[Message] = asyncio.Queue()
    queue.put_nowait({"type": "http.request", "body": b"", "more_body": False})

    async def discard(_message: Message) -> None:
        pass

    task = asyncio.create_task(
        app(_scope("/v2/outings/fixture/events"), queue.get, discard)
    )
    await asyncio.wait_for(opened.wait(), 1)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN
    ) as client:
        response = await client.get("/v2/outings/second/events")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "stream_capacity_reached"
    queue.put_nowait({"type": "http.disconnect"})
    await asyncio.wait_for(task, 1)
    assert app._streams == 0
    assert all(bucket.streams == 0 for bucket in app._buckets.values())


async def test_active_write_capacity_released_after_cancel(
    social_settings: SocialSettings,
) -> None:
    app = SocialHttpMiddleware(
        _ok, social_settings.model_copy(update={"max_active_writes": 1})
    )
    queue: asyncio.Queue[Message] = asyncio.Queue()
    reading = asyncio.Event()

    async def receive() -> Message:
        reading.set()
        return await queue.get()

    async def discard(_message: Message) -> None:
        pass

    task = asyncio.create_task(
        app(_scope("/v2/saved-routes", "POST"), receive, discard)
    )
    await reading.wait()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN
    ) as client:
        assert (await client.post("/v2/saved-routes", json={})).json()["error"][
            "code"
        ] == "write_capacity_reached"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (await client.post("/v2/saved-routes", json={})).status_code == 200
    assert app._writes == 0 and app._requests == 0


async def test_retention_loop_offloads_work_and_recovers(
    social_settings: SocialSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    import sugarglider.social_server.app as module

    attempts = [0]
    main_thread = threading.get_ident()

    def controlled_cleanup(
        _settings: SocialSettings, _live: OutingLiveOperations
    ) -> None:
        assert threading.get_ident() != main_thread
        attempts[0] += 1
        if attempts[0] == 1:
            raise RuntimeError("private cleanup exception")

    monkeypatch.setattr(module, "cleanup", controlled_cleanup)
    app = create_social_app(
        social_settings.model_copy(update={"cleanup_interval_seconds": 0.02})
    )
    async with app.router.lifespan_context(app):
        async with asyncio.timeout(2):
            while attempts[0] < 2 or not app.state.retention_healthy:
                await asyncio.sleep(0.01)
        assert attempts[0] >= 2 and app.state.retention_healthy


def test_production_entrypoint_cannot_import_reference_factory_or_backend() -> None:
    import ast

    root = Path(__file__).resolve().parents[2] / "src/sugarglider/social_server"
    forbidden = (
        "sugarglider.api.main",
        "sugarglider.api.routes",
        "sugarglider.routing.graphhopper",
        "sugarglider.planning.pipeline",
    )
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in forbidden
            elif isinstance(node, ast.Import):
                assert not any(item.name in forbidden for item in node.names)


async def test_backup_retention_deletes_only_verified_generated_directories(
    social_client: httpx.AsyncClient, social_settings: SocialSettings, tmp_path: Path
) -> None:
    from sugarglider.social_server.sqlite_repository import prune_backups

    destination = tmp_path / "backups"
    recent = create_backup(social_settings.data_directory, destination)
    original = create_backup(social_settings.data_directory, destination)
    old = destination / "sugarglider-20200101T000000Z-1234abcd"
    original.rename(old)
    untouched = destination / "operator-notes"
    untouched.mkdir()
    (untouched / "keep").write_text("preserve")
    symlink = destination / "sugarglider-20200101T000000Z-5678abcd"
    symlink.symlink_to(untouched, target_is_directory=True)
    assert prune_backups(destination) == 1
    assert not old.exists()
    assert recent.is_dir() and untouched.is_dir() and symlink.is_symlink()
    assert (untouched / "keep").read_text() == "preserve"
    with pytest.raises(BackupError):
        prune_backups(destination, retain_days=0)
