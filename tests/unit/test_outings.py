"""Outing API, startup, GPX, privacy, and copied-snapshot tests."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from xml.etree import ElementTree

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from sugarglider.api.main import create_app
from sugarglider.config import Settings
from sugarglider.outings.models import OutingPlannedRoute
from sugarglider.outings.service import (
    OutingService,
    UnavailableOutingService,
)
from sugarglider.outings.sqlite_repository import SQLiteOutingRepository
from sugarglider.planning.diagnostics import (
    BudgetDiagnostics,
    CacheDiagnostics,
    PlanSearchDiagnostics,
)
from sugarglider.planning.direction.traversal import build_plan_traversal
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.models import PLAN_REQUEST_ADAPTER, PlanRequest
from sugarglider.planning.pipeline import PlanService
from sugarglider.planning.result import PlanCandidate, PlanResult
from sugarglider.planning.signatures import candidate_signature
from sugarglider.routing.profiles import RoutingProfileId
from sugarglider.routing.service import RouteService
from sugarglider.saved_routes.models import (
    SavedRouteCreateRequest,
    SavedRouteSnapshot,
)
from sugarglider.saved_routes.service import (
    SavedRouteService,
    UnavailableSavedRouteService,
)
from sugarglider.saved_routes.sqlite_repository import SQLiteSavedRouteRepository


class NoRouteService(RouteService):
    def __init__(self) -> None:
        self.calls = 0

    async def ensure_profile_available(self, profile: RoutingProfileId) -> None:
        del profile


class NoPlanService(PlanService):
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: PlanRequest) -> PlanResult:
        del request
        self.calls += 1
        raise AssertionError("outings must not invoke planning")


class OperationalPlanService(PlanService):
    def __init__(self, candidate: PlanCandidate) -> None:
        self.candidate = candidate
        self.calls = 0

    async def generate(self, request: PlanRequest) -> PlanResult:
        self.calls += 1
        return PlanResult(
            kind=request.kind,
            topology=request.topology,
            routing_profile=request.routing_profile,
            effective_start=request.start,
            effective_end=request.end or request.start,
            candidates=(self.candidate,),
            search_diagnostics=PlanSearchDiagnostics(
                budget=BudgetDiagnostics(
                    phases={},
                    total_used=0,
                    total_limit=1,
                    total_remaining=1,
                    global_exhausted=False,
                ),
                cache=CacheDiagnostics(
                    lookup_count=0,
                    hit_count=0,
                    miss_count=0,
                    entry_count=0,
                    successful_entry_count=0,
                    failed_entry_count=0,
                    backend_call_count=0,
                ),
            ),
        )


class CountingSavedRouteService(SavedRouteService):
    def __init__(self, repository: SQLiteSavedRouteRepository) -> None:
        super().__init__(repository)
        self.get_calls = 0

    def get(self, slug: str) -> SavedRouteSnapshot:
        self.get_calls += 1
        return super().get(slug)


def _app(
    tmp_path: Path,
    route_service: RouteService,
    plan_service: PlanService,
) -> FastAPI:
    saved_repository = SQLiteSavedRouteRepository(tmp_path / "saved-routes.sqlite3")
    saved_repository.initialize()
    outing_repository = SQLiteOutingRepository(tmp_path / "outings.sqlite3")
    outing_repository.initialize()
    return create_app(
        route_service,
        settings=Settings(
            nature_index_path=None,
            poi_index_path=None,
            saved_route_database_path=None,
            outing_database_path=None,
        ),
        plan_service=plan_service,
        saved_route_service=SavedRouteService(saved_repository),
        outing_service=OutingService(outing_repository),
    )


@pytest_asyncio.fixture
async def outing_client(
    tmp_path: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, NoRouteService, NoPlanService]]:
    route_service = NoRouteService()
    plan_service = NoPlanService()
    app = _app(tmp_path, route_service, plan_service)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            yield client, route_service, plan_service


async def _saved(
    client: httpx.AsyncClient,
    source: PlanRequest,
    candidate: PlanCandidate,
) -> dict[str, object]:
    response = await client.post(
        "/v2/saved-routes",
        json=SavedRouteCreateRequest(
            source_request=source,
            candidate=candidate,
        ).model_dump(mode="json"),
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


def _independent_cycling_route(
    source: PlanRequest,
    candidate: PlanCandidate,
) -> tuple[PlanRequest, PlanCandidate]:
    geometry = ((2.20, 48.80), (2.215, 48.805), (2.23, 48.81))
    source_payload = source.model_dump(mode="json")
    source_payload.update(
        {
            "name": "Independent cycling route",
            "start": {"lat": geometry[0][1], "lon": geometry[0][0]},
            "end": {"lat": geometry[-1][1], "lon": geometry[-1][0]},
            "routing_profile": "city_bike",
        }
    )
    cycling_source = PLAN_REQUEST_ADAPTER.validate_python(source_payload)
    route = candidate.route.model_copy(
        update={
            "name": "Independent cycling route",
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
    return cycling_source, candidate.model_copy(
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


@pytest.mark.asyncio
async def test_create_get_gpx_copy_survives_source_deletion_without_planning(
    outing_client: tuple[httpx.AsyncClient, NoRouteService, NoPlanService],
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    client, route_service, plan_service = outing_client
    saved = await _saved(client, saved_route_source_request, saved_route_candidate)
    response = await client.post(
        "/v2/outings",
        json={
            "schema_version": 1,
            "title": "Independent routes",
            "participant_display_name": "Runner",
            "saved_route_slug": saved["slug"],
        },
    )
    assert response.status_code == 201
    created = response.json()
    assert response.headers["location"] == f"/v2/outings/{created['slug']}"
    assert "#invite=" in created["invite_path"]
    assert "?" not in created["invite_path"]
    assert created["join_token"] in created["invite_path"]

    fetched = await client.get(f"/v2/outings/{created['slug']}")
    page = await client.get(f"/o/{created['slug']}")
    participant_id = created["participant_id"]
    gpx = await client.get(
        f"/v2/outings/{created['slug']}/participants/{participant_id}/gpx"
    )
    assert fetched.status_code == page.status_code == gpx.status_code == 200
    assert fetched.json()["participants"][0]["planned_route"] == {
        "source_request": saved["source_request"],
        "candidate": saved["candidate"],
    }
    public_body = fetched.text
    for field in ("owner_token", "join_token", "participant_token"):
        assert field not in public_body
    assert fetched.headers["cache-control"] == "private, no-store"
    assert fetched.headers["referrer-policy"] == "no-referrer"
    assert page.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
    root = ElementTree.fromstring(gpx.content)
    namespace = {"g": "http://www.topografix.com/GPX/1/1"}
    assert len(root.findall("g:trk", namespace)) == 1
    assert len(root.findall("g:trk/g:trkseg", namespace)) == 1
    assert not root.findall("g:rte", namespace)

    deleted = await client.delete(
        f"/v2/saved-routes/{saved['slug']}",
        headers={"X-Saved-Route-Owner-Token": str(saved["owner_token"])},
    )
    assert deleted.status_code == 204
    after_delete = await client.get(f"/v2/outings/{created['slug']}")
    assert after_delete.status_code == 200
    assert after_delete.json() == fetched.json()
    assert route_service.calls == plan_service.calls == 0


@pytest.mark.asyncio
async def test_join_leave_and_delete_capabilities_are_safe(
    outing_client: tuple[httpx.AsyncClient, NoRouteService, NoPlanService],
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    client, _, _ = outing_client
    saved = await _saved(client, saved_route_source_request, saved_route_candidate)
    created = (
        await client.post(
            "/v2/outings",
            json={
                "title": "Outing",
                "participant_display_name": "First",
                "saved_route_slug": saved["slug"],
            },
        )
    ).json()
    wrong_join = await client.post(
        f"/v2/outings/{created['slug']}/participants",
        headers={"X-Sugarglider-Outing-Join-Token": "wrong"},
        json={
            "display_name": "Second",
            "saved_route_slug": "missing_saved_route_01",
        },
    )
    assert wrong_join.status_code == 404
    assert wrong_join.json()["error"]["code"] == "outing_not_found"

    joined_response = await client.post(
        f"/v2/outings/{created['slug']}/participants",
        headers={"X-Sugarglider-Outing-Join-Token": created["join_token"]},
        json={
            "display_name": "Second",
            "saved_route_slug": saved["slug"],
        },
    )
    assert joined_response.status_code == 201
    joined = joined_response.json()
    assert len(joined["outing"]["participants"]) == 2
    participant_id = joined["participant_id"]
    wrong_leave = await client.delete(
        f"/v2/outings/{created['slug']}/participants/{participant_id}",
        headers={"X-Sugarglider-Participant-Token": "wrong"},
    )
    assert wrong_leave.status_code == 404
    left = await client.delete(
        f"/v2/outings/{created['slug']}/participants/{participant_id}",
        headers={"X-Sugarglider-Participant-Token": joined["participant_token"]},
    )
    assert left.status_code == 204
    assert left.headers["cache-control"] == "no-store"
    remaining = await client.get(f"/v2/outings/{created['slug']}")
    assert len(remaining.json()["participants"]) == 1

    wrong_delete = await client.delete(
        f"/v2/outings/{created['slug']}",
        headers={"X-Sugarglider-Outing-Owner-Token": "wrong"},
    )
    assert wrong_delete.status_code == 404
    deleted = await client.delete(
        f"/v2/outings/{created['slug']}",
        headers={"X-Sugarglider-Outing-Owner-Token": created["owner_token"]},
    )
    assert deleted.status_code == 204
    assert deleted.headers["cache-control"] == "no-store"
    assert (await client.get(f"/v2/outings/{created['slug']}")).status_code == 404


@pytest.mark.asyncio
async def test_join_authorization_precedes_invalid_body_field_validation(
    tmp_path: Path,
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    saved_repository = SQLiteSavedRouteRepository(tmp_path / "saved.sqlite3")
    saved_repository.initialize()
    saved_service = CountingSavedRouteService(saved_repository)
    outing_repository = SQLiteOutingRepository(tmp_path / "outings.sqlite3")
    outing_repository.initialize()
    app = create_app(
        NoRouteService(),
        settings=Settings(
            nature_index_path=None,
            poi_index_path=None,
            saved_route_database_path=None,
            outing_database_path=None,
        ),
        plan_service=NoPlanService(),
        saved_route_service=saved_service,
        outing_service=OutingService(outing_repository, max_participants=2),
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            saved = await _saved(
                client,
                saved_route_source_request,
                saved_route_candidate,
            )
            created = (
                await client.post(
                    "/v2/outings",
                    json={
                        "title": "Authorization ordering",
                        "participant_display_name": "First",
                        "saved_route_slug": saved["slug"],
                    },
                )
            ).json()
            saved_service.get_calls = 0

            wrong_token = await client.post(
                f"/v2/outings/{created['slug']}/participants",
                headers={"X-Sugarglider-Outing-Join-Token": "wrong"},
                json={
                    "display_name": "",
                    "saved_route_slug": saved["slug"],
                },
            )
            missing_token = await client.post(
                f"/v2/outings/{created['slug']}/participants",
                json={
                    "display_name": "Second",
                    "saved_route_slug": "invalid",
                },
            )
            valid_non_full = await client.post(
                f"/v2/outings/{created['slug']}/participants",
                headers={
                    "X-Sugarglider-Outing-Join-Token": created["join_token"],
                },
                json={
                    "display_name": "",
                    "saved_route_slug": saved["slug"],
                },
            )
            assert saved_service.get_calls == 0

            filled = await client.post(
                f"/v2/outings/{created['slug']}/participants",
                headers={
                    "X-Sugarglider-Outing-Join-Token": created["join_token"],
                },
                json={
                    "display_name": "Second",
                    "saved_route_slug": saved["slug"],
                },
            )
            assert filled.status_code == 201
            saved_service.get_calls = 0
            valid_full = await client.post(
                f"/v2/outings/{created['slug']}/participants",
                headers={
                    "X-Sugarglider-Outing-Join-Token": created["join_token"],
                },
                json={
                    "display_name": "",
                    "saved_route_slug": saved["slug"],
                },
            )

    assert wrong_token.status_code == missing_token.status_code == 404
    assert wrong_token.json()["error"]["code"] == "outing_not_found"
    assert missing_token.json()["error"]["code"] == "outing_not_found"
    assert valid_full.status_code == 409
    assert valid_full.json()["error"]["code"] == "outing_full"
    assert valid_non_full.status_code == 422
    assert saved_service.get_calls == 0


@pytest.mark.asyncio
async def test_each_participant_gpx_contains_only_its_stored_route(
    outing_client: tuple[httpx.AsyncClient, NoRouteService, NoPlanService],
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    client, route_service, plan_service = outing_client
    hiking_saved = await _saved(
        client,
        saved_route_source_request,
        saved_route_candidate,
    )
    cycling_source, cycling_candidate = _independent_cycling_route(
        saved_route_source_request,
        saved_route_candidate,
    )
    cycling_saved = await _saved(client, cycling_source, cycling_candidate)
    created = (
        await client.post(
            "/v2/outings",
            json={
                "title": "Independent GPX",
                "participant_display_name": "Hiker",
                "saved_route_slug": hiking_saved["slug"],
            },
        )
    ).json()
    joined = (
        await client.post(
            f"/v2/outings/{created['slug']}/participants",
            headers={
                "X-Sugarglider-Outing-Join-Token": created["join_token"],
            },
            json={
                "display_name": "Cyclist",
                "saved_route_slug": cycling_saved["slug"],
            },
        )
    ).json()
    hiking_gpx = await client.get(
        f"/v2/outings/{created['slug']}/participants/{created['participant_id']}/gpx"
    )
    cycling_gpx = await client.get(
        f"/v2/outings/{created['slug']}/participants/{joined['participant_id']}/gpx"
    )
    assert hiking_gpx.status_code == cycling_gpx.status_code == 200
    namespace = {"g": "http://www.topografix.com/GPX/1/1"}
    hiking_points = ElementTree.fromstring(hiking_gpx.content).findall(
        "g:trk/g:trkseg/g:trkpt",
        namespace,
    )
    cycling_points = ElementTree.fromstring(cycling_gpx.content).findall(
        "g:trk/g:trkseg/g:trkpt",
        namespace,
    )
    assert [float(point.attrib["lon"]) for point in hiking_points] == [
        coordinate[0] for coordinate in saved_route_candidate.route.geometry
    ]
    assert [float(point.attrib["lon"]) for point in cycling_points] == [
        coordinate[0] for coordinate in cycling_candidate.route.geometry
    ]
    assert route_service.calls == plan_service.calls == 0


@pytest.mark.asyncio
async def test_zero_participant_outing_remains_public_and_owner_deletable(
    outing_client: tuple[httpx.AsyncClient, NoRouteService, NoPlanService],
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    client, _, _ = outing_client
    saved = await _saved(client, saved_route_source_request, saved_route_candidate)
    created = (
        await client.post(
            "/v2/outings",
            json={
                "title": "Quiet outing",
                "participant_display_name": "Only participant",
                "saved_route_slug": saved["slug"],
            },
        )
    ).json()
    left = await client.delete(
        f"/v2/outings/{created['slug']}/participants/{created['participant_id']}",
        headers={
            "X-Sugarglider-Participant-Token": created["participant_token"],
        },
    )
    fetched = await client.get(f"/v2/outings/{created['slug']}")
    page = await client.get(f"/o/{created['slug']}")
    assert left.status_code == 204
    assert fetched.status_code == page.status_code == 200
    assert fetched.json()["participants"] == []
    deleted = await client.delete(
        f"/v2/outings/{created['slug']}",
        headers={"X-Sugarglider-Outing-Owner-Token": created["owner_token"]},
    )
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_saved_route_failure_blocks_create_and_join_but_not_existing_get(
    tmp_path: Path,
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    route_service = NoRouteService()
    plan_service = NoPlanService()
    app = _app(tmp_path, route_service, plan_service)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            saved = await _saved(
                client,
                saved_route_source_request,
                saved_route_candidate,
            )
            created = (
                await client.post(
                    "/v2/outings",
                    json={
                        "title": "Existing outing",
                        "participant_display_name": "First",
                        "saved_route_slug": saved["slug"],
                    },
                )
            ).json()
            app.state.saved_route_service = UnavailableSavedRouteService()
            blocked_create = await client.post(
                "/v2/outings",
                json={
                    "title": "Blocked",
                    "participant_display_name": "First",
                    "saved_route_slug": saved["slug"],
                },
            )
            blocked_join = await client.post(
                f"/v2/outings/{created['slug']}/participants",
                headers={
                    "X-Sugarglider-Outing-Join-Token": created["join_token"],
                },
                json={
                    "display_name": "Second",
                    "saved_route_slug": saved["slug"],
                },
            )
            fetched = await client.get(f"/v2/outings/{created['slug']}")
    assert blocked_create.status_code == blocked_join.status_code == 503
    assert fetched.status_code == 200
    for response in (blocked_create, blocked_join):
        assert response.json()["error"]["code"] == "saved_route_storage_unavailable"
        assert str(tmp_path) not in response.text
        assert "SELECT " not in response.text


@pytest.mark.asyncio
async def test_disabled_outing_storage_is_isolated(
    tmp_path: Path,
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    route_service = NoRouteService()
    plan_service = NoPlanService()
    saved_repository = SQLiteSavedRouteRepository(tmp_path / "saved.sqlite3")
    saved_repository.initialize()
    app = create_app(
        route_service,
        settings=Settings(
            nature_index_path=None,
            poi_index_path=None,
            saved_route_database_path=None,
            outing_database_path=None,
        ),
        plan_service=plan_service,
        saved_route_service=SavedRouteService(saved_repository),
        outing_service=UnavailableOutingService(),
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            saved = await _saved(
                client, saved_route_source_request, saved_route_candidate
            )
            response = await client.post(
                "/v2/outings",
                json={
                    "title": "Outing",
                    "participant_display_name": "Runner",
                    "saved_route_slug": saved["slug"],
                },
            )
            config = await client.get("/v1/ui/config")
            health = await client.get("/health")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "outing_storage_unavailable"
    assert config.json()["outings_available"] is False
    assert health.status_code == 200


@pytest.mark.asyncio
async def test_real_app_startup_initializes_outing_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "runtime" / "outings.sqlite3"
    app = create_app(
        NoRouteService(),
        settings=Settings(
            nature_index_path=None,
            poi_index_path=None,
            saved_route_database_path=None,
            outing_database_path=database_path,
        ),
        plan_service=NoPlanService(),
        saved_route_service=UnavailableSavedRouteService(),
    )
    async with app.router.lifespan_context(app):
        assert app.state.outing_service.available
        assert app.state.outing_live_service.available
        assert app.state.outing_live_broker is not None
        assert database_path.exists()
        with SQLiteOutingRepository(database_path)._connection() as connection:
            tables = {
                str(row["name"])
                for row in connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                )
            }
    assert tables == {
        "outings",
        "outing_participants",
        "outing_live_positions",
        "outing_live_events",
    }


@pytest.mark.asyncio
async def test_real_app_startup_purges_expired_outings(
    tmp_path: Path,
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    database_path = tmp_path / "outings.sqlite3"
    repository = SQLiteOutingRepository(database_path)
    repository.initialize()
    expired = OutingService(
        repository,
        clock=lambda: datetime(2020, 1, 1, tzinfo=UTC),
    ).create(
        "Expired outing",
        "Participant",
        OutingPlannedRoute(
            source_request=saved_route_source_request,
            candidate=saved_route_candidate,
        ),
    )
    app = create_app(
        NoRouteService(),
        settings=Settings(
            nature_index_path=None,
            poi_index_path=None,
            saved_route_database_path=None,
            outing_database_path=database_path,
        ),
        plan_service=NoPlanService(),
        saved_route_service=UnavailableSavedRouteService(),
    )
    async with app.router.lifespan_context(app):
        assert repository.get_by_slug(expired.slug) is None


@pytest.mark.asyncio
async def test_outing_startup_failure_isolated_from_saved_routes_and_planning(
    tmp_path: Path,
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    invalid_database_path = tmp_path / "database-is-a-directory"
    invalid_database_path.mkdir()
    saved_repository = SQLiteSavedRouteRepository(tmp_path / "saved.sqlite3")
    saved_repository.initialize()
    plan_service = OperationalPlanService(saved_route_candidate)
    app = create_app(
        NoRouteService(),
        settings=Settings(
            nature_index_path=None,
            poi_index_path=None,
            saved_route_database_path=None,
            outing_database_path=invalid_database_path,
        ),
        plan_service=plan_service,
        saved_route_service=SavedRouteService(saved_repository),
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            saved = await _saved(
                client,
                saved_route_source_request,
                saved_route_candidate,
            )
            fetched = await client.get(f"/v2/saved-routes/{saved['slug']}")
            planned = await client.post(
                "/v2/plans/generate",
                json=saved_route_source_request.model_dump(mode="json"),
            )
            health = await client.get("/health")
            failed = await client.post(
                "/v2/outings",
                json={
                    "title": "Unavailable",
                    "participant_display_name": "Participant",
                    "saved_route_slug": saved["slug"],
                },
            )
        assert app.state.plan_service is plan_service
        assert app.state.outing_service.available is False
        assert app.state.outing_live_service.available is False
    assert fetched.status_code == planned.status_code == health.status_code == 200
    assert plan_service.calls == 1
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "outing_storage_unavailable"
    assert str(invalid_database_path) not in failed.text
    assert "sqlite" not in failed.text.lower()


def test_outing_settings_defaults_aliases_and_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults = Settings()
    assert defaults.outing_database_path == Path("/data/outings/outings.sqlite3")
    assert defaults.outing_ttl_days == 30
    assert defaults.outing_max_participants == 8
    assert defaults.outing_max_route_snapshot_bytes == 10_000_000
    path = tmp_path / "injected.sqlite3"
    monkeypatch.setenv("SUGARGLIDER_OUTING_DATABASE_PATH", str(path))
    monkeypatch.setenv("SUGARGLIDER_OUTING_TTL_DAYS", "365")
    monkeypatch.setenv("SUGARGLIDER_OUTING_MAX_PARTICIPANTS", "20")
    configured = Settings()
    assert configured.outing_database_path == path
    assert configured.outing_ttl_days == 365
    assert configured.outing_max_participants == 20
