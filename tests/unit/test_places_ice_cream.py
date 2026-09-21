"""Ice-cream ingestion, filtering and wire format use tiny independent OSM data."""

from pathlib import Path

import httpx
import pytest

from sugarglider.api.main import create_app
from sugarglider.config import Settings
from sugarglider.pois.build import build_poi_index
from sugarglider.pois.index import load_poi_index
from sugarglider.pois.models import PoiBoundingBox, PoiSearchRequest, PoiSearchResponse

XML = """<osm version="0.6">
<bounds minlat="48" minlon="2" maxlat="49" maxlon="3"/>
<node id="1" lat="48.1" lon="2.1"><tag k="amenity" v="ice_cream"/>
<tag k="name" v="Glacier &amp; été"/><tag k="addr:street" v="Rue des Glaces"/></node>
<node id="2" lat="48.2" lon="2.2"><tag k="shop" v="ice_cream"/></node>
<node id="3" lat="48.3" lon="2.3"><tag k="amenity" v="cafe"/>
<tag k="cuisine" v="coffee_shop;ice_cream"/><tag k="access" v="private"/></node>
<node id="4" lat="48.4" lon="2.4"><tag k="tourism" v="viewpoint"/></node>
<node id="5" lat="48.5" lon="2.5"><tag k="amenity" v="drinking_water"/></node>
<node id="6" lat="48.6" lon="2.6"/><node id="7" lat="48.6" lon="2.7"/>
<node id="8" lat="48.7" lon="2.7"/><node id="9" lat="48.7" lon="2.6"/>
<way id="10"><nd ref="6"/><nd ref="7"/><nd ref="8"/><nd ref="9"/><nd ref="6"/>
<tag k="shop" v="ice_cream"/><tag k="name" v="Area ice cream"/></way>
</osm>"""
BOUNDS = PoiBoundingBox(west=2, south=48, east=3, north=49)


@pytest.fixture
def index_path(tmp_path: Path) -> Path:
    source = tmp_path / "places.osm"
    source.write_text(XML)
    path = tmp_path / "places.json.gz"
    build_poi_index(source, path)
    repeated = tmp_path / "repeated.json.gz"
    build_poi_index(source, repeated)
    assert path.read_bytes() == repeated.read_bytes()
    return path


def test_ice_cream_index_retains_identity_metadata_and_bounded_filters(
    index_path: Path,
) -> None:
    index = load_poi_index(index_path)
    assert index.metadata.classifier_version == "2"
    assert index.metadata.build_configuration.classifier_version == "2"
    assert index.metadata.category_counts["ice_cream"] == 4
    request = PoiSearchRequest(bbox=BOUNDS, categories=("ice_cream",))
    result = index.search(request, limit=2)
    assert result.total_matching == 3 and result.returned_count == 2
    assert result.truncated
    assert {feature.id for feature in result.features} == {"way/10", "node/1"}
    assert dict(result.features[1].tags)["addr:street"] == "Rue des Glaces"
    assert all(feature.group == "refreshment" for feature in result.features)
    assert all(feature.potability == "not_applicable" for feature in result.features)
    private = index.search(
        request.model_copy(update={"include_private": True, "access": ("private",)}),
        limit=10,
    )
    assert [feature.id for feature in private.features] == ["node/3"]
    assert not private.features[0].approach_candidates
    assert (
        index.search(
            request.model_copy(update={"groups": ("scenic",)}), limit=10
        ).returned_count
        == 0
    )
    assert not any(
        match.feature.category == "ice_cream"
        for match in index.query_near_route(((2.0, 48.0), (2.8, 48.8)), 1000)
    )


async def test_ice_cream_api_serialization_and_filtering(index_path: Path) -> None:
    app = create_app(
        settings=Settings(poi_index_path=index_path, nature_index_path=None)
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/pois/search",
                json={"bbox": BOUNDS.model_dump(), "categories": ["ice_cream"]},
            )
            assert response.status_code == 200
            result = PoiSearchResponse.model_validate(response.json())
            assert result.total_matching == 3
            assert all(feature.category == "ice_cream" for feature in result.features)
            for category in ("viewpoint", "drinking_water"):
                response = await client.post(
                    "/v1/pois/search",
                    json={"bbox": BOUNDS.model_dump(), "categories": [category]},
                )
                assert response.status_code == 200
                assert response.json()["returned_count"] == 1
