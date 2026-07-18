"""Runtime point-index loading, bounded search, filtering, and status tests."""

import gzip
import json
from pathlib import Path

import pytest
from shapely.geometry import box

from sugarglider.domain.models import Coordinate
from sugarglider.pois.errors import PoiIndexFormatError, PoiIndexMissingError
from sugarglider.pois.index import (
    PoiIndex,
    _matches,
    available_poi_status,
    load_poi_index,
    unavailable_poi_status,
)
from sugarglider.pois.models import (
    PoiBoundingBox,
    PoiFeature,
    PoiIndexDocument,
    PoiIndexMetadata,
    PoiSearchRequest,
)


def _feature(
    osm_id: int,
    *,
    lon: float,
    lat: float,
    category: str = "viewpoint",
    name: str = "Viewpoint",
    potability: str = "not_applicable",
    access: str = "public",
) -> PoiFeature:
    hydration = category in {"drinking_water", "fountain", "water_tap"}
    return PoiFeature.model_validate(
        {
            "id": f"node/{osm_id}",
            "osm_type": "node",
            "osm_id": osm_id,
            "coordinate": {"lat": lat, "lon": lon},
            "category": category,
            "group": "hydration" if hydration else "scenic",
            "display_name": name,
            "name_source": "name",
            "scenic_confidence": "none" if hydration else "primary",
            "potability": potability,
            "access_status": access,
        }
    )


def _document() -> PoiIndexDocument:
    features = tuple(
        sorted(
            (
                _feature(1, lon=2.02, lat=48.02, name="Été"),
                _feature(2, lon=2.03, lat=48.03, name="alpha"),
                _feature(
                    3,
                    lon=2.04,
                    lat=48.04,
                    category="drinking_water",
                    name="Source",
                    potability="verified",
                ),
                _feature(
                    4,
                    lon=2.05,
                    lat=48.05,
                    category="fountain",
                    name="Fontaine",
                    potability="unknown",
                    access="private",
                ),
                _feature(
                    5,
                    lon=2.06,
                    lat=48.06,
                    category="water_tap",
                    name="Do not drink",
                    potability="non_potable",
                ),
                _feature(6, lon=3.0, lat=49.0, name="Remote"),
            ),
            key=lambda feature: feature.id,
        )
    )
    return PoiIndexDocument(
        metadata=PoiIndexMetadata(
            source_basename="region.osm.pbf",
            source_size_bytes=123,
            feature_count=6,
            category_counts={
                "drinking_water": 1,
                "fountain": 1,
                "viewpoint": 3,
                "water_tap": 1,
            },
            potability_counts={
                "non_potable": 1,
                "not_applicable": 3,
                "unknown": 1,
                "verified": 1,
            },
            access_counts={"private": 1, "public": 5},
            bounding_box=(2, 48, 3, 49),
            skipped_invalid_count=0,
        ),
        features=features,
    )


def _write_index(path: Path, document: PoiIndexDocument) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as output:
        json.dump(document.model_dump(mode="json"), output, ensure_ascii=False)


def _request(**updates: object) -> PoiSearchRequest:
    values: dict[str, object] = {
        "bbox": {"west": 2.0, "south": 48.0, "east": 2.1, "north": 48.1}
    }
    values.update(updates)
    return PoiSearchRequest.model_validate(values)


def test_valid_index_loads_and_query_uses_only_bbox_candidates(tmp_path: Path) -> None:
    path = tmp_path / "index.json.gz"
    _write_index(path, _document())
    index = load_poi_index(path)

    response = index.search(_request(), limit=10)

    assert index.metadata.feature_count == 6
    assert response.total_matching == 3
    assert tuple(feature.id for feature in response.features) == (
        "node/3",
        "node/2",
        "node/1",
    )
    query_polygon = index.projection.project_polygon(box(2, 48, 2.1, 48.1))
    assert index.query_indices(query_polygon) == (0, 1, 2, 3, 4)


def test_category_potability_private_and_access_filters() -> None:
    index = PoiIndex(_document())
    scenic = index.search(
        _request(groups=["scenic"], categories=["viewpoint"]), limit=10
    )
    assert tuple(feature.id for feature in scenic.features) == ("node/2", "node/1")

    unknown_hidden = index.search(
        _request(groups=["hydration"], potability=["unknown"], access=["private"]),
        limit=10,
    )
    assert unknown_hidden.features == ()
    unknown_visible = index.search(
        _request(
            groups=["hydration"],
            potability=["unknown"],
            access=["private"],
            include_private=True,
        ),
        limit=10,
    )
    assert tuple(feature.id for feature in unknown_visible.features) == ("node/4",)
    non_potable = index.search(
        _request(groups=["hydration"], potability=["non_potable"]), limit=10
    )
    assert tuple(feature.id for feature in non_potable.features) == ("node/5",)

    scenic_non_potable = _feature(
        99,
        lon=2.07,
        lat=48.07,
        category="viewpoint",
        name="Viewpoint fountain",
        potability="non_potable",
    )
    assert not _matches(scenic_non_potable, _request(groups=["scenic"]))
    assert _matches(
        scenic_non_potable,
        _request(groups=["scenic"], potability=["non_potable"]),
    )


def test_search_is_deterministic_and_reports_truncation() -> None:
    index = PoiIndex(_document())
    first = index.search(_request(groups=["scenic"]), limit=1)
    second = index.search(_request(groups=["scenic"]), limit=1)

    assert first == second
    assert first.total_matching == 2
    assert first.returned_count == 1
    assert first.truncated
    assert first.warnings == ("poi_results_truncated",)


def test_missing_corrupt_unsupported_and_out_of_bounds_indexes(
    tmp_path: Path,
) -> None:
    with pytest.raises(PoiIndexMissingError):
        load_poi_index(tmp_path / "missing.json.gz")
    corrupt = tmp_path / "corrupt.json.gz"
    corrupt.write_bytes(b"not gzip")
    with pytest.raises(PoiIndexFormatError):
        load_poi_index(corrupt)

    unsupported = _document().model_dump(mode="json")
    metadata = unsupported["metadata"]
    assert isinstance(metadata, dict)
    metadata["format_version"] = 2
    unsupported_path = tmp_path / "unsupported.json.gz"
    with gzip.open(unsupported_path, "wt", encoding="utf-8") as output:
        json.dump(unsupported, output)
    with pytest.raises(PoiIndexFormatError):
        load_poi_index(unsupported_path)

    document = _document()
    bad_feature = document.features[0].model_copy(
        update={"coordinate": Coordinate(lat=47, lon=1)}
    )
    bad_document = document.model_copy(
        update={"features": (bad_feature, *document.features[1:])}
    )
    with pytest.raises(PoiIndexFormatError):
        PoiIndex(bad_document)


def test_statuses_do_not_expose_parent_paths(tmp_path: Path) -> None:
    path = tmp_path / "private" / "pois.json.gz"
    unavailable = unavailable_poi_status(path, warnings=("z", "a", "a"))
    assert unavailable.index_path_basename == "pois.json.gz"
    assert str(tmp_path) not in unavailable.model_dump_json()
    assert unavailable.warnings == ("a", "z")

    available = available_poi_status(PoiIndex(_document()), path)
    assert available.index_path_basename == "pois.json.gz"
    assert available.source_basename == "region.osm.pbf"


def test_bbox_validation_rejects_invalid_or_dateline_queries() -> None:
    with pytest.raises(ValueError):
        PoiBoundingBox(west=2, south=48, east=2, north=49)
    with pytest.raises(ValueError):
        PoiBoundingBox(west=170, south=-1, east=-170, north=1)
    with pytest.raises(ValueError):
        PoiBoundingBox(west=2, south=float("nan"), east=3, north=49)
