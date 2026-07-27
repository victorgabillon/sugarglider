"""Saved-route HTTP, startup, GPX, and browser contract tests."""

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import ValidationError

from sugarglider.api.main import create_app
from sugarglider.config import Settings
from sugarglider.gpx.writer import write_plan_gpx
from sugarglider.planning.models import PlanRequest
from sugarglider.planning.pipeline import PlanService
from sugarglider.planning.result import PlanCandidate, PlanResult
from sugarglider.routing.service import RouteService
from sugarglider.saved_routes.errors import SavedRouteStorageError
from sugarglider.saved_routes.models import (
    SavedRouteCreated,
    SavedRouteCreateRequest,
    SavedRouteSnapshot,
)
from sugarglider.saved_routes.service import (
    SavedRouteOperations,
    SavedRouteService,
    UnavailableSavedRouteService,
)
from sugarglider.saved_routes.sqlite_repository import SQLiteSavedRouteRepository
from sugarglider.web.routes import STATIC_DIRECTORY


class _NoRoutingService(RouteService):
    def __init__(self) -> None:
        self.calls = 0


class _NoPlanningService(PlanService):
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, _request: PlanRequest) -> PlanResult:
        self.calls += 1
        raise AssertionError("saved routes must not invoke planning")


class _FailingSavedRoutes:
    available = True

    def create(self, request: SavedRouteCreateRequest) -> SavedRouteCreated:
        del request
        raise SavedRouteStorageError("sqlite detail /private/database.sqlite3")

    def get(self, slug: str) -> SavedRouteSnapshot:
        del slug
        raise SavedRouteStorageError("sqlite detail /private/database.sqlite3")

    def delete(self, slug: str, owner_token: str | None) -> None:
        del slug, owner_token
        raise SavedRouteStorageError("sqlite detail /private/database.sqlite3")


@pytest.fixture
def save_request(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> SavedRouteCreateRequest:
    return SavedRouteCreateRequest(
        source_request=saved_route_source_request,
        candidate=saved_route_candidate,
    )


@pytest.fixture
def route_service() -> _NoRoutingService:
    return _NoRoutingService()


@pytest.fixture
def plan_service() -> _NoPlanningService:
    return _NoPlanningService()


def _saved_service(
    path: Path,
    *,
    maximum_snapshot_bytes: int = 10_000_000,
    clock: Callable[[], datetime] | None = None,
) -> SavedRouteService:
    repository = SQLiteSavedRouteRepository(path)
    repository.initialize()
    return SavedRouteService(
        repository,
        maximum_snapshot_bytes=maximum_snapshot_bytes,
        clock=clock,
    )


def _app(
    route_service: RouteService,
    plan_service: PlanService,
    saved_route_service: SavedRouteOperations,
) -> FastAPI:
    return create_app(
        route_service,
        settings=Settings(
            nature_index_path=None,
            poi_index_path=None,
            saved_route_database_path=None,
        ),
        plan_service=plan_service,
        saved_route_service=saved_route_service,
    )


def test_saved_route_settings_defaults_aliases_and_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults = Settings()
    assert defaults.saved_route_database_path == Path(
        "/data/saved-routes/saved-routes.sqlite3"
    )
    assert defaults.saved_route_ttl_days == 90
    assert defaults.saved_route_max_snapshot_bytes == 10_000_000

    database = tmp_path / "injected.sqlite3"
    monkeypatch.setenv("SUGARGLIDER_SAVED_ROUTE_DATABASE_PATH", str(database))
    monkeypatch.setenv("SUGARGLIDER_SAVED_ROUTE_TTL_DAYS", "365")
    monkeypatch.setenv("SUGARGLIDER_SAVED_ROUTE_MAX_SNAPSHOT_BYTES", "50000000")
    configured = Settings()
    assert configured.saved_route_database_path == database
    assert configured.saved_route_ttl_days == 365
    assert configured.saved_route_max_snapshot_bytes == 50_000_000

    monkeypatch.setenv("SUGARGLIDER_SAVED_ROUTE_TTL_DAYS", "0")
    with pytest.raises(ValidationError):
        Settings()


@pytest_asyncio.fixture
async def client(
    tmp_path: Path,
    route_service: _NoRoutingService,
    plan_service: _NoPlanningService,
) -> AsyncIterator[httpx.AsyncClient]:
    app = _app(
        route_service,
        plan_service,
        _saved_service(tmp_path / "saved-routes.sqlite3"),
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as http_client:
            yield http_client


@pytest.mark.asyncio
async def test_post_get_page_and_gpx_preserve_exact_snapshot_without_services(
    client: httpx.AsyncClient,
    save_request: SavedRouteCreateRequest,
    route_service: _NoRoutingService,
    plan_service: _NoPlanningService,
) -> None:
    response = await client.post(
        "/v2/saved-routes", json=save_request.model_dump(mode="json")
    )
    assert response.status_code == 201
    created = response.json()
    slug = created["slug"]
    owner_token = created["owner_token"]
    assert response.headers["location"] == f"/v2/saved-routes/{slug}"
    assert response.headers["cache-control"] == "no-store"
    assert owner_token not in created["share_path"]
    assert owner_token not in created["gpx_path"]

    fetched = await client.get(f"/v2/saved-routes/{slug}")
    shared_page = await client.get(f"/r/{slug}")
    gpx = await client.get(f"/v2/saved-routes/{slug}/gpx")

    assert fetched.status_code == shared_page.status_code == gpx.status_code == 200
    assert fetched.json()["source_request"] == created["source_request"]
    assert fetched.json()["candidate"] == created["candidate"]
    assert "profile" not in fetched.json()
    assert "owner_token" not in fetched.json()
    assert owner_token.encode() not in gpx.content
    assert gpx.content == write_plan_gpx(save_request.candidate)
    root = ElementTree.fromstring(gpx.content)
    namespace = {"g": "http://www.topografix.com/GPX/1/1"}
    assert len(root.findall("g:trk", namespace)) == 1
    assert len(root.findall("g:trk/g:trkseg", namespace)) == 1
    assert not root.findall("g:rte", namespace)
    assert fetched.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
    assert fetched.headers["referrer-policy"] == "no-referrer"
    assert gpx.headers["referrer-policy"] == "no-referrer"
    assert shared_page.headers["cache-control"] == "private, no-store"
    assert shared_page.headers["referrer-policy"] == "no-referrer"
    assert route_service.calls == plan_service.calls == 0


@pytest.mark.asyncio
async def test_unknown_saved_route_is_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get("/v2/saved-routes/abcdefghijklmnopqrstuv")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "saved_route_not_found"


@pytest.mark.asyncio
async def test_expired_saved_route_is_not_found_and_deleted(
    tmp_path: Path,
    route_service: _NoRoutingService,
    plan_service: _NoPlanningService,
    save_request: SavedRouteCreateRequest,
) -> None:
    now = datetime(2026, 7, 27, tzinfo=UTC)
    clock_value = [now]
    service = _saved_service(tmp_path / "expiry.sqlite3", clock=lambda: clock_value[0])
    app = _app(route_service, plan_service, service)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as api:
            created = (
                await api.post(
                    "/v2/saved-routes", json=save_request.model_dump(mode="json")
                )
            ).json()
            clock_value[0] = now + timedelta(days=91)
            response = await api.get(f"/v2/saved-routes/{created['slug']}")
            assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_requires_valid_owner_token_but_never_reveals_existence(
    client: httpx.AsyncClient,
    save_request: SavedRouteCreateRequest,
) -> None:
    created = (
        await client.post("/v2/saved-routes", json=save_request.model_dump(mode="json"))
    ).json()
    path = f"/v2/saved-routes/{created['slug']}"
    for headers in (
        {},
        {"X-Saved-Route-Owner-Token": "malformed"},
        {"X-Saved-Route-Owner-Token": "x" * 43},
    ):
        response = await client.delete(path, headers=headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "saved_route_not_found"
    deleted = await client.delete(
        path,
        headers={"X-Saved-Route-Owner-Token": created["owner_token"]},
    )
    assert deleted.status_code == 204
    assert (await client.get(path)).status_code == 404


@pytest.mark.asyncio
async def test_invalid_candidate_is_422(
    client: httpx.AsyncClient,
    save_request: SavedRouteCreateRequest,
) -> None:
    payload = save_request.model_dump(mode="json")
    payload["candidate"]["routing_profile"] = "trail_run"
    response = await client.post("/v2/saved-routes", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "saved_route_candidate_invalid"


@pytest.mark.asyncio
async def test_oversized_snapshot_is_413_before_persistence(
    tmp_path: Path,
    route_service: _NoRoutingService,
    plan_service: _NoPlanningService,
    save_request: SavedRouteCreateRequest,
) -> None:
    app = _app(
        route_service,
        plan_service,
        _saved_service(tmp_path / "small.sqlite3", maximum_snapshot_bytes=1),
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as api:
            response = await api.post(
                "/v2/saved-routes", json=save_request.model_dump(mode="json")
            )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_disabled_and_failed_storage_return_safe_503(
    route_service: _NoRoutingService,
    plan_service: _NoPlanningService,
    save_request: SavedRouteCreateRequest,
) -> None:
    for service in (UnavailableSavedRouteService(), _FailingSavedRoutes()):
        app = _app(route_service, plan_service, service)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as api:
                response = await api.post(
                    "/v2/saved-routes", json=save_request.model_dump(mode="json")
                )
                assert response.status_code == 503
                body = response.text
                assert "sqlite" not in body.lower()
                assert "/private" not in body


@pytest.mark.asyncio
async def test_sqlite_snapshot_persists_across_application_restart(
    tmp_path: Path,
    route_service: _NoRoutingService,
    plan_service: _NoPlanningService,
    save_request: SavedRouteCreateRequest,
) -> None:
    database = tmp_path / "persistent.sqlite3"
    slug = ""
    for run in range(2):
        service = _saved_service(database)
        app = _app(route_service, plan_service, service)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as api:
                if run == 0:
                    slug = (
                        await api.post(
                            "/v2/saved-routes",
                            json=save_request.model_dump(mode="json"),
                        )
                    ).json()["slug"]
                else:
                    response = await api.get(f"/v2/saved-routes/{slug}")
                    assert response.status_code == 200
                    assert response.json()[
                        "candidate"
                    ] == save_request.candidate.model_dump(mode="json")


@pytest.mark.asyncio
async def test_startup_initializes_purges_and_isolates_expected_failure(
    tmp_path: Path,
    route_service: _NoRoutingService,
    plan_service: _NoPlanningService,
    save_request: SavedRouteCreateRequest,
) -> None:
    database = tmp_path / "startup.sqlite3"
    app = create_app(
        route_service,
        settings=Settings(
            nature_index_path=None,
            poi_index_path=None,
            saved_route_database_path=database,
        ),
        plan_service=plan_service,
    )
    async with app.router.lifespan_context(app):
        assert app.state.saved_route_service.available is True
        assert database.exists()

    expiry_database = tmp_path / "startup-expiry.sqlite3"
    expired_repository = SQLiteSavedRouteRepository(expiry_database)
    expired_repository.initialize()
    expired = SavedRouteService(
        expired_repository,
        ttl_days=1,
        clock=lambda: datetime(2020, 1, 1, tzinfo=UTC),
    ).create(save_request)
    purge_app = create_app(
        route_service,
        settings=Settings(
            nature_index_path=None,
            poi_index_path=None,
            saved_route_database_path=expiry_database,
        ),
        plan_service=plan_service,
    )
    async with purge_app.router.lifespan_context(purge_app):
        assert expired_repository.get_by_slug(expired.slug) is None

    disabled_app = create_app(
        route_service,
        settings=Settings(
            nature_index_path=None,
            poi_index_path=None,
            saved_route_database_path=None,
        ),
        plan_service=plan_service,
    )
    async with disabled_app.router.lifespan_context(disabled_app):
        assert disabled_app.state.saved_route_service.available is False

    failed_app = create_app(
        route_service,
        settings=Settings(
            nature_index_path=None,
            poi_index_path=None,
            saved_route_database_path=tmp_path,
        ),
        plan_service=plan_service,
    )
    async with failed_app.router.lifespan_context(failed_app):
        assert failed_app.state.saved_route_service.available is False
        transport = httpx.ASGITransport(app=failed_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as api:
            assert (await api.get("/health")).status_code == 200


def test_shared_frontend_uses_snapshot_endpoints_without_generation_or_storage() -> (
    None
):
    saved_routes = (STATIC_DIRECTORY / "saved_routes.js").read_text(encoding="utf-8")
    application = (STATIC_DIRECTORY / "app.js").read_text(encoding="utf-8")
    map_source = (STATIC_DIRECTORY / "map.js").read_text(encoding="utf-8")
    html = (STATIC_DIRECTORY / "index.html").read_text(encoding="utf-8")

    assert 'fetch("/v2/saved-routes"' in saved_routes
    assert "/v2/saved-routes/${encodeURIComponent(slug)}/gpx" in saved_routes
    assert "/v2/plans/generate" not in saved_routes
    assert "/v2/saved-routes" not in map_source
    assert "getSavedRoute(sharedSlug)" in application
    assert "getRoutingProfiles()" in application
    assert application.index("if (sharedSlug)") < application.index(
        "getRoutingProfiles()", application.index("async function start()")
    )
    assert "navigator.share" in saved_routes
    assert "navigator.clipboard.writeText" in application
    assert "localStorage" not in saved_routes + application
    assert "sessionStorage" not in saved_routes + application
    assert 'name="referrer" content="no-referrer"' in html
    assert 'id="save-route-selected"' in html
    assert "saved_routes_available" in application
    assert "createSavedRoute(sourceRequest, candidate)" in application
    assert "!state.savedRouteReceipt?.owner_token" in application
    assert "savedSearchDiagnostics" not in application
    assert "search_diagnostics:" not in application
    assert "state.generationResult = {" not in application
    assert "sharedSnapshot.profile" not in application
    assert "available: true" not in application
    assert (
        "applyCanonicalRequestState(saved.source_request, "
        "{ requireKnownProfile: false })" in application
    )
    assert 'id="use-saved-route"' in html
    assert 'id="share-saved-route"' in html
    assert 'id="dismiss-saved-route"' in html

    save_function = application[
        application.index("async function saveSelectedRoute()") : application.index(
            "async function copySavedRouteLink()"
        )
    ]
    assert "shareSavedRoute" not in save_function
    assert "navigator.clipboard" not in save_function
    assert "state.savedRouteReceipt =" in save_function

    fork_function = application[
        application.index(
            "async function useSavedRouteAsNewPlan()"
        ) : application.index("function failedExactPoint()")
    ]
    assert "getRoutingProfiles()" in fork_function
    assert "getPoiStatus()" in fork_function
    assert "state.savedRouteSnapshotDisplay = false" in fork_function
    assert "generatePlan(" not in fork_function

    invalidation = (
        (STATIC_DIRECTORY / "state.js")
        .read_text(encoding="utf-8")
        .split("export function invalidateCandidates()", 1)[1]
        .split("export function requestedPlaceIdentifier", 1)[0]
    )
    assert "savedRouteReceipt" not in invalidation
    assert 'closest(".panel.controls").inert = readOnly' in application
    assert "if (isSavedRouteSnapshotDisplay()) return;" in application
    assert 'if (error.name === "AbortError")' in application
