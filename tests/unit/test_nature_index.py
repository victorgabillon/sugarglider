"""Runtime nature-index, projection, and safe status tests."""

import gzip
import json
from pathlib import Path

import pytest

from sugarglider.nature.errors import (
    NatureIndexFormatError,
    NatureIndexMissingError,
)
from sugarglider.nature.index import (
    NatureIndex,
    available_nature_status,
    load_nature_index,
    unavailable_nature_status,
)
from sugarglider.nature.models import (
    NatureIndexDocument,
    NatureIndexFeature,
    NatureIndexMetadata,
    PolygonGeometry,
)
from sugarglider.nature.projection import LocalMetricProjection


def _feature() -> NatureIndexFeature:
    return NatureIndexFeature(
        feature_id="way/10",
        osm_id=10,
        osm_source="way",
        primary_class="woodland",
        park_or_protected=False,
        tags={"natural": "wood"},
        geometry=PolygonGeometry(
            coordinates=(((2.0, 48.0), (2.1, 48.0), (2.1, 48.1), (2.0, 48.0)),)
        ),
    )


def _document(*, format_version: int = 1) -> dict[str, object]:
    feature = _feature()
    return {
        "metadata": {
            "format_version": format_version,
            "source_basename": "region.osm.pbf",
            "source_size_bytes": 12,
            "source_mtime_ns": None,
            "reference_latitude": 48.05,
            "bounding_box": [2.0, 48.0, 2.1, 48.1],
            "category_counts": {"woodland": 1},
            "feature_count": 1,
        },
        "features": [feature.model_dump(mode="json")],
    }


def _write_index(path: Path, document: dict[str, object]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as output:
        json.dump(document, output)


def test_valid_index_loads_independently_of_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "index.json.gz"
    _write_index(path, _document())
    monkeypatch.chdir(tmp_path.parent)
    index = load_nature_index(path)
    assert index.metadata.feature_count == 1
    assert index.features[0].feature_id == "way/10"
    assert index.features[0].tags == (("natural", "wood"),)
    assert index.query_indices(index.features[0].metric_geometry) == (0,)
    assert index.features == index.features


def test_empty_index_is_supported() -> None:
    document = NatureIndexDocument(
        metadata=NatureIndexMetadata(
            source_basename="empty.osm",
            reference_latitude=48.0,
            bounding_box=(2.0, 48.0, 2.1, 48.1),
            category_counts={},
            feature_count=0,
        ),
        features=(),
    )
    index = NatureIndex(document)
    assert index.features == ()
    assert index.query_indices(index.metric_bounds) == ()


def test_missing_and_corrupt_indexes_are_distinct(tmp_path: Path) -> None:
    with pytest.raises(NatureIndexMissingError):
        load_nature_index(tmp_path / "missing.json.gz")
    corrupt = tmp_path / "corrupt.json.gz"
    corrupt.write_bytes(b"not gzip")
    with pytest.raises(NatureIndexFormatError):
        load_nature_index(corrupt)


@pytest.mark.parametrize(
    "mutation",
    [
        "unsupported_version",
        "invalid_coordinate",
        "non_polygon",
        "wrong_counts",
        "large_latitude_span",
    ],
)
def test_invalid_index_content_is_rejected(tmp_path: Path, mutation: str) -> None:
    document = _document()
    metadata = document["metadata"]
    features = document["features"]
    assert isinstance(metadata, dict)
    assert isinstance(features, list)
    feature = features[0]
    assert isinstance(feature, dict)
    if mutation == "unsupported_version":
        metadata["format_version"] = 2
    elif mutation == "invalid_coordinate":
        feature["geometry"] = {
            "type": "Polygon",
            "coordinates": [[[200, 48], [2, 48], [2, 49], [200, 48]]],
        }
    elif mutation == "non_polygon":
        feature["geometry"] = {
            "type": "LineString",
            "coordinates": [[2, 48], [2.1, 48.1]],
        }
    elif mutation == "wrong_counts":
        metadata["category_counts"] = {}
    else:
        metadata["bounding_box"] = [2, 30, 2.1, 48]
    path = tmp_path / f"{mutation}.json.gz"
    _write_index(path, document)
    with pytest.raises(NatureIndexFormatError):
        load_nature_index(path)


def test_status_never_exposes_parent_path(tmp_path: Path) -> None:
    path = tmp_path / "private" / "nature.json.gz"
    missing = unavailable_nature_status(
        path,
        water_buffer_m=75,
        warnings=("z", "a", "a"),
    )
    assert missing.index_path_basename == "nature.json.gz"
    assert str(tmp_path) not in missing.model_dump_json()
    assert missing.warnings == ("a", "z")

    index = NatureIndex(NatureIndexDocument.model_validate(_document()))
    available = available_nature_status(index, path, water_buffer_m=75)
    assert available.index_path_basename == "nature.json.gz"
    assert available.source_basename == "region.osm.pbf"


def test_projection_round_trip_and_expected_distances() -> None:
    projection = LocalMetricProjection(48.0)
    position = (2.0, 48.1)
    unprojected = projection.unproject_position(projection.project_position(position))
    assert unprojected == pytest.approx(position)
    x0, y0 = projection.project_position((2.0, 48.0))
    x1, y1 = projection.project_position((2.001, 48.001))
    assert x1 - x0 == pytest.approx(74.4, rel=0.01)
    assert y1 - y0 == pytest.approx(111.2, rel=0.01)
