"""Exact practical-place rules, legacy precedence and offline API compatibility."""

from pathlib import Path

import httpx
import pytest

from sugarglider.api.main import create_app
from sugarglider.config import Settings
from sugarglider.pois.build import build_poi_index
from sugarglider.pois.classification import classify_osm_tags
from sugarglider.pois.index import PoiIndex, load_poi_index
from sugarglider.pois.models import (
    PoiBoundingBox,
    PoiCategory,
    PoiIndexDocument,
    PoiSearchRequest,
)


@pytest.mark.parametrize(
    ("tags", "category", "group", "name"),
    [
        ({"amenity": "toilets"}, "toilets", "practical", "Toilets"),
        ({"amenity": "cafe"}, "cafe", "refreshment", "Café"),
        ({"shop": "bakery"}, "bakery", "refreshment", "Bakery"),
        ({"tourism": "picnic_site"}, "picnic_area", "practical", "Picnic area"),
    ],
)
def test_exact_practical_rules_and_bounded_plain_text(
    tags: dict[str, str], category: str, group: str, name: str
) -> None:
    result = classify_osm_tags(tags)
    assert result is not None
    assert (result.category, result.group, result.display_name) == (
        category,
        group,
        name,
    )
    assert result.potability == "not_applicable"
    assert result.access_status == "unknown"
    assert result.name_source == "category_fallback"
    named = classify_osm_tags(
        {
            **tags,
            "name": " <script>été</script> ",
            "fee": "yes",
            "access": "customers",
            "phone": "hidden",
            "email": "hidden",
            "description": "hidden",
        }
    )
    assert named is not None
    assert named.display_name == "<script>été</script>"
    assert named.access_status == "restricted"
    assert dict(named.tags)["fee"] == "yes"
    assert not {"phone", "email", "description"} & dict(named.tags).keys()


@pytest.mark.parametrize(
    "tags",
    [
        {"toilets": "yes"},
        {"name": "Toilets"},
        {"name": "Boulangerie"},
        {"amenity": "restaurant"},
        {"amenity": "fast_food"},
        {"amenity": "pub"},
        {"amenity": "bar"},
        {"shop": "coffee"},
        {"cuisine": "coffee"},
        {"shop": "supermarket"},
        {"shop": "convenience"},
        {"cuisine": "bakery"},
        {"leisure": "picnic_table"},
        {"amenity": "bench"},
        {"amenity": "bbq"},
        {"tourism": "camp_site"},
    ],
)
def test_nearby_or_attached_tags_do_not_invent_practical_places(
    tags: dict[str, str],
) -> None:
    assert classify_osm_tags(tags) is None


def test_attached_toilets_and_new_rule_overlap_have_deliberate_precedence() -> None:
    cafe = classify_osm_tags({"amenity": "cafe", "toilets": "yes"})
    assert (
        cafe is not None and cafe.category == "cafe" and not cafe.secondary_categories
    )
    combined = classify_osm_tags({"amenity": "cafe", "shop": "bakery"})
    assert combined is not None
    assert combined.category == "cafe" and combined.secondary_categories == ("bakery",)


@pytest.mark.parametrize(
    ("tags", "primary", "group", "potability", "fallback"),
    [
        (
            {"amenity": "drinking_water", "shop": "bakery"},
            "drinking_water",
            "hydration",
            "verified",
            "Drinking water",
        ),
        (
            {"tourism": "viewpoint", "amenity": "cafe"},
            "viewpoint",
            "scenic",
            "not_applicable",
            "Viewpoint",
        ),
        (
            {"amenity": "cafe", "cuisine": "ice_cream"},
            "ice_cream",
            "refreshment",
            "not_applicable",
            "Ice cream",
        ),
        (
            {"historic": "castle", "tourism": "picnic_site"},
            "castle",
            "scenic",
            "not_applicable",
            "Castle",
        ),
        (
            {"man_made": "water_tap", "drinking_water": "yes", "amenity": "toilets"},
            "drinking_water",
            "hydration",
            "verified",
            "Drinking water",
        ),
        (
            {"man_made": "water_tap", "amenity": "toilets"},
            "water_tap",
            "hydration",
            "unknown",
            "Water tap — potability unknown",
        ),
        (
            {"shop": "ice_cream", "tourism": "picnic_site"},
            "ice_cream",
            "refreshment",
            "not_applicable",
            "Ice cream",
        ),
    ],
)
@pytest.mark.parametrize("access", ["yes", "customers", "private", ""])
def test_classifier_two_primary_semantics_survive_practical_overlap(
    tags: dict[str, str],
    primary: str,
    group: str,
    potability: str,
    fallback: str,
    access: str,
) -> None:
    for name in ("", "Mapped old name"):
        result = classify_osm_tags({**tags, "access": access, "name": name})
        assert result is not None
        assert (result.category, result.group, result.potability) == (
            primary,
            group,
            potability,
        )
        assert not result.secondary_categories
        assert (
            result.access_status
            == {
                "yes": "public",
                "customers": "restricted",
                "private": "private",
                "": "unknown",
            }[access]
        )
        assert result.display_name == (name or fallback)
        assert result.name_source == ("name" if name else "category_fallback")


@pytest.fixture
def practical_index(tmp_path: Path) -> PoiIndex:
    source = tmp_path / "practical.osm"
    tags = [
        ("amenity", "toilets"),
        ("amenity", "cafe"),
        ("shop", "bakery"),
        ("tourism", "picnic_site"),
        ("tourism", "viewpoint"),
        ("amenity", "drinking_water"),
        ("shop", "ice_cream"),
    ]
    nodes = "".join(
        f'<node id="{i}" lat="48.{i}" lon="2.{i}">'
        f'<tag k="{key}" v="{value}"/>'
        f'<tag k="name" v="Mapped {value}"/></node>'
        for i, (key, value) in enumerate(tags, 1)
    )
    source.write_text(
        '<osm version="0.6"><bounds minlat="48" minlon="2" maxlat="49" maxlon="3"/>'
        + nodes
        + "</osm>"
    )
    first, second = tmp_path / "first.gz", tmp_path / "second.gz"
    build_poi_index(source, first)
    build_poi_index(source, second)
    assert first.read_bytes() == second.read_bytes()
    return load_poi_index(first)


def test_build_bbox_group_category_truncation_and_routing_exclusion(
    practical_index: PoiIndex,
) -> None:
    assert practical_index.metadata.format_version == 2
    assert (
        practical_index.metadata.classifier_version
        == practical_index.metadata.build_configuration.classifier_version
        == "3"
    )
    assert practical_index.status().classifier_version == "3"
    bbox = PoiBoundingBox(west=2, south=48, east=3, north=49)
    for group, categories in [
        ("practical", {"toilets", "picnic_area"}),
        ("refreshment", {"ice_cream", "cafe", "bakery"}),
    ]:
        result = practical_index.search(
            PoiSearchRequest.model_validate(
                {"bbox": bbox.model_dump(), "groups": [group]}
            ),
            limit=10,
        )
        assert {f.category for f in result.features} == categories
    for category in ("toilets", "cafe", "bakery", "picnic_area"):
        typed: PoiCategory = category
        query = PoiSearchRequest(bbox=bbox, categories=(typed,))
        assert practical_index.search(query, limit=10).returned_count == 1
        assert (
            practical_index.search(
                query.model_copy(
                    update={
                        "bbox": PoiBoundingBox(
                            west=2.8, south=48.8, east=2.9, north=48.9
                        )
                    }
                ),
                limit=10,
            ).returned_count
            == 0
        )
    query = PoiSearchRequest(bbox=bbox)
    limited = practical_index.search(query, limit=2)
    assert (limited.total_matching, limited.returned_count, limited.truncated) == (
        7,
        2,
        True,
    )
    assert limited == practical_index.search(query, limit=2)
    assert all(f.category in {"drinking_water", "ice_cream"} for f in limited.features)
    assert all(
        m.feature.group in {"scenic", "hydration"}
        for m in practical_index.query_near_route(((2.1, 48.1), (2.7, 48.7)), 100000)
    )


@pytest.mark.parametrize("version", ["1", "2"])
def test_old_index_reader_remains_compatible(
    practical_index: PoiIndex, version: str
) -> None:
    features = tuple(
        f
        for f in practical_index.search(
            PoiSearchRequest(bbox=PoiBoundingBox(west=2, south=48, east=3, north=49)),
            limit=10,
        ).features
        if f.group == "scenic"
    )
    feature = features[0]
    metadata = practical_index.metadata.model_dump(mode="json")
    raw = {
        "metadata": metadata,
        "features": [feature.model_dump(mode="json")],
    }
    metadata.update(
        classifier_version=version,
        feature_count=1,
        category_counts={feature.category: 1},
        access_counts={feature.access_status: 1},
        potability_counts={feature.potability: 1},
        approach_counts={
            a.kind: sum(b.kind == a.kind for b in feature.approach_candidates)
            for a in feature.approach_candidates
        },
    )
    metadata["build_configuration"]["classifier_version"] = version
    old = PoiIndex(PoiIndexDocument.model_validate(raw))
    assert old.status().classifier_version == version
    assert old.metadata.feature_count == 1


async def test_practical_api_filters(practical_index: PoiIndex) -> None:
    app = create_app(settings=Settings(poi_index_path=None, nature_index_path=None))
    async with app.router.lifespan_context(app):
        app.state.poi_index = practical_index
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for group, count in [("practical", 2), ("refreshment", 3)]:
                response = await client.post(
                    "/v1/pois/search",
                    json={
                        "bbox": {"west": 2, "south": 48, "east": 3, "north": 49},
                        "groups": [group],
                    },
                )
                assert response.status_code == 200
                assert response.json()["returned_count"] == count
