"""POI status and bounded-search API behavior."""

import gzip
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from sugarglider.api.main import create_app
from sugarglider.config import Settings
from sugarglider.domain.models import RouteRequest, RouteResult
from sugarglider.pois.models import PoiFeature, PoiIndexDocument, PoiIndexMetadata
from sugarglider.routing.service import RouteService


class _UnusedRouteService(RouteService):
    def __init__(self) -> None:
        pass

    async def route(self, request: RouteRequest) -> RouteResult:
        raise AssertionError(f"routing was unexpectedly called for {request.name}")

    async def ready(self) -> bool:
        return True


def _feature(
    osm_id: int,
    *,
    name: str,
    category: str,
    potability: str,
    access: str = "public",
) -> PoiFeature:
    hydration = category in {"drinking_water", "fountain", "water_tap"}
    return PoiFeature.model_validate(
        {
            "id": f"node/{osm_id}",
            "osm_type": "node",
            "osm_id": osm_id,
            "coordinate": {"lat": 48.87 + osm_id / 10_000, "lon": 2.1},
            "category": category,
            "group": "hydration" if hydration else "scenic",
            "display_name": name,
            "name_source": "name",
            "scenic_confidence": "none" if hydration else "primary",
            "potability": potability,
            "access_status": access,
            "tags": [["operator", "Eau & été"]],
        }
    )


def _document() -> PoiIndexDocument:
    features = (
        _feature(
            1,
            name="Belvédère d'été",
            category="viewpoint",
            potability="not_applicable",
        ),
        _feature(
            2,
            name="Fontaine",
            category="drinking_water",
            potability="verified",
        ),
        _feature(
            3,
            name="Privée",
            category="fountain",
            potability="unknown",
            access="private",
        ),
    )
    return PoiIndexDocument(
        metadata=PoiIndexMetadata(
            source_basename="region.osm.pbf",
            source_size_bytes=1,
            feature_count=3,
            category_counts={"drinking_water": 1, "fountain": 1, "viewpoint": 1},
            potability_counts={
                "not_applicable": 1,
                "unknown": 1,
                "verified": 1,
            },
            access_counts={"private": 1, "public": 2},
            bounding_box=(2, 48, 3, 49),
            skipped_invalid_count=0,
        ),
        features=features,
    )


def _write_index(path: Path) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as output:
        json.dump(_document().model_dump(mode="json"), output, ensure_ascii=False)


async def _client_for(
    path: Path | None, *, max_limit: int = 2
) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        nature_index_path=None,
        poi_index_path=path,
        poi_default_limit=2,
        poi_max_limit=max_limit,
    )
    app = create_app(_UnusedRouteService(), settings=settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            yield client


@pytest_asyncio.fixture
async def available_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    path = tmp_path / "local-pois.json.gz"
    _write_index(path)
    async for client in _client_for(path):
        yield client


@pytest.mark.asyncio
async def test_status_available_and_safe(available_client: httpx.AsyncClient) -> None:
    response = await available_client.get("/v1/pois/status")
    assert response.status_code == 200
    assert response.json() == {
        "configured": True,
        "available": True,
        "index_path_basename": "local-pois.json.gz",
        "format_version": 2,
        "source_basename": "region.osm.pbf",
        "feature_count": 3,
        "category_counts": {"drinking_water": 1, "fountain": 1, "viewpoint": 1},
        "potability_counts": {
            "not_applicable": 1,
            "unknown": 1,
            "verified": 1,
        },
        "access_counts": {"private": 1, "public": 2},
        "approach_counts": {},
        "warnings": [],
    }


@pytest.mark.asyncio
async def test_search_is_bounded_unicode_and_returns_no_geometry(
    available_client: httpx.AsyncClient,
) -> None:
    response = await available_client.post(
        "/v1/pois/search",
        json={
            "bbox": {"west": 2, "south": 48, "east": 3, "north": 49},
            "groups": ["scenic", "hydration"],
            "potability": ["verified"],
            "limit": 2,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["returned_count"] == 2
    assert body["total_matching"] == 2
    assert {feature["display_name"] for feature in body["features"]} == {
        "Belvédère d'été",
        "Fontaine",
    }
    assert all("geometry" not in feature for feature in body["features"])
    assert response.encoding is not None
    assert response.encoding.lower() == "utf-8"


@pytest.mark.asyncio
async def test_invalid_bbox_and_configured_limit_are_structured(
    available_client: httpx.AsyncClient,
) -> None:
    invalid = await available_client.post(
        "/v1/pois/search",
        json={"bbox": {"west": 2, "south": 49, "east": 3, "north": 48}},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_request"

    excessive = await available_client.post(
        "/v1/pois/search",
        json={
            "bbox": {"west": 2, "south": 48, "east": 3, "north": 49},
            "limit": 3,
        },
    )
    assert excessive.status_code == 422
    assert excessive.json()["error"]["code"] == "poi_limit_exceeded"


@pytest.mark.asyncio
async def test_unavailable_index_keeps_status_and_search_operational(
    tmp_path: Path,
) -> None:
    async for client in _client_for(tmp_path / "missing.json.gz"):
        status = await client.get("/v1/pois/status")
        search = await client.post(
            "/v1/pois/search",
            json={"bbox": {"west": 2, "south": 48, "east": 3, "north": 49}},
        )
        health = await client.get("/health")
    assert status.status_code == search.status_code == health.status_code == 200
    assert status.json()["available"] is False
    assert status.json()["index_path_basename"] == "missing.json.gz"
    assert search.json() == {
        "available": False,
        "total_matching": 0,
        "returned_count": 0,
        "truncated": False,
        "features": [],
        "warnings": ["poi_index_unavailable"],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("contents", "warning"),
    [
        (None, "poi_index_unavailable"),
        (b"not a gzip index", "poi_index_invalid"),
    ],
)
async def test_expected_index_failure_is_path_safe_and_preserved_by_search(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    contents: bytes | None,
    warning: str,
) -> None:
    private_parent = tmp_path / "private-parent-must-not-leak"
    private_parent.mkdir()
    path = private_parent / "configured-pois.json.gz"
    if contents is not None:
        path.write_bytes(contents)

    with caplog.at_level(logging.INFO, logger="sugarglider.api.main"):
        async for client in _client_for(path):
            status = await client.get("/v1/pois/status")
            search = await client.post(
                "/v1/pois/search",
                json={"bbox": {"west": 2, "south": 48, "east": 3, "north": 49}},
            )
            health = await client.get("/health")
            ready = await client.get("/ready")

    assert status.status_code == search.status_code == 200
    assert health.json() == ready.json() == {"status": "ok"}
    assert status.json()["warnings"] == [warning]
    assert search.json()["warnings"] == [warning]
    public_output = json.dumps(
        {"status": status.json(), "search": search.json()}, sort_keys=True
    )
    assert str(private_parent) not in public_output
    assert private_parent.name not in public_output
    assert str(private_parent) not in caplog.text
    assert private_parent.name not in caplog.text
    poi_records = [
        record
        for record in caplog.records
        if record.name == "sugarglider.api.main" and "POI index" in record.message
    ]
    assert len(poi_records) == 1
    assert poi_records[0].exc_info is None
    assert poi_records[0].message == (
        f"POI index {path.name} is "
        f"{'unavailable' if contents is None else 'invalid'}; "
        "place discovery is disabled"
    )
