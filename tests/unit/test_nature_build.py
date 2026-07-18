"""Nature-index builder tests using only tiny local OSM XML."""

import gzip
import json
from pathlib import Path

import pytest
from shapely.geometry import LineString, Polygon

from sugarglider.nature.build import (
    _valid_polygonal_geometry,
    build_nature_index,
)
from sugarglider.nature.errors import NatureIndexBuildError
from sugarglider.nature.models import NatureIndexDocument, PolygonGeometry

OSM_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="sugarglider-tests">
  <bounds minlat="0.0" minlon="0.0" maxlat="0.1" maxlon="0.1"/>
  <node id="1" lat="0.01" lon="0.01"/>
  <node id="2" lat="0.01" lon="0.02"/>
  <node id="3" lat="0.02" lon="0.02"/>
  <node id="4" lat="0.02" lon="0.01"/>
  <node id="5" lat="0.03" lon="0.01"/>
  <node id="6" lat="0.03" lon="0.02"/>
  <node id="7" lat="0.04" lon="0.02"/>
  <node id="8" lat="0.04" lon="0.01"/>
  <node id="9" lat="0.05" lon="0.01"/>
  <node id="10" lat="0.05" lon="0.02"/>
  <node id="11" lat="0.06" lon="0.02"/>
  <node id="12" lat="0.06" lon="0.01"/>
  <node id="13" lat="0.07" lon="0.01"/>
  <node id="14" lat="0.07" lon="0.02"/>
  <node id="15" lat="0.08" lon="0.02"/>
  <node id="16" lat="0.08" lon="0.01"/>
  <node id="17" lat="0.01" lon="0.03"/>
  <node id="18" lat="0.01" lon="0.04"/>
  <node id="19" lat="0.02" lon="0.04"/>
  <node id="20" lat="0.02" lon="0.03"/>
  <node id="21" lat="0.03" lon="0.03"/>
  <node id="22" lat="0.03" lon="0.06"/>
  <node id="23" lat="0.06" lon="0.06"/>
  <node id="24" lat="0.06" lon="0.03"/>
  <node id="25" lat="0.04" lon="0.04"/>
  <node id="26" lat="0.04" lon="0.05"/>
  <node id="27" lat="0.05" lon="0.05"/>
  <node id="28" lat="0.05" lon="0.04"/>
  <node id="29" lat="0.07" lon="0.03"/>
  <node id="30" lat="0.07" lon="0.04"/>
  <node id="31" lat="0.08" lon="0.04"/>
  <node id="32" lat="0.08" lon="0.03"/>
  <way id="10">
    <nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
    <tag k="natural" v="wood"/><tag k="name" v="not indexed"/>
  </way>
  <way id="20">
    <nd ref="5"/><nd ref="6"/><nd ref="7"/><nd ref="8"/><nd ref="5"/>
    <tag k="landuse" v="meadow"/>
  </way>
  <way id="30">
    <nd ref="9"/><nd ref="10"/><nd ref="11"/><nd ref="12"/><nd ref="9"/>
    <tag k="natural" v="water"/>
  </way>
  <way id="40">
    <nd ref="13"/><nd ref="14"/><nd ref="15"/><nd ref="16"/><nd ref="13"/>
    <tag k="landuse" v="residential"/>
  </way>
  <way id="50">
    <nd ref="17"/><nd ref="18"/><nd ref="19"/><nd ref="20"/><nd ref="17"/>
    <tag k="leisure" v="park"/>
  </way>
  <way id="60">
    <nd ref="29"/><nd ref="30"/><nd ref="31"/><nd ref="32"/><nd ref="29"/>
    <tag k="landuse" v="farmland"/><tag k="amenity" v="parking"/>
  </way>
  <way id="101">
    <nd ref="21"/><nd ref="22"/><nd ref="23"/><nd ref="24"/><nd ref="21"/>
  </way>
  <way id="102">
    <nd ref="25"/><nd ref="26"/><nd ref="27"/><nd ref="28"/><nd ref="25"/>
  </way>
  <relation id="200">
    <member type="way" ref="101" role="outer"/>
    <member type="way" ref="102" role="inner"/>
    <tag k="type" v="multipolygon"/>
    <tag k="landuse" v="forest"/>
    <tag k="boundary" v="protected_area"/>
  </relation>
</osm>
"""


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "tiny.osm"
    source.write_text(OSM_XML, encoding="utf-8")
    return source


def test_builder_selects_areas_metadata_priority_and_holes(tmp_path: Path) -> None:
    source = _source(tmp_path)
    output = tmp_path / "nested" / "nature.json.gz"
    report = build_nature_index(source, output)
    with gzip.open(output, "rt", encoding="utf-8") as stream:
        document = NatureIndexDocument.model_validate(json.load(stream))

    assert report.feature_count == 7
    assert report.category_counts == {
        "open_natural": 1,
        "park_or_protected": 2,
        "urban": 2,
        "water": 1,
        "woodland": 2,
    }
    assert document.metadata.source_basename == "tiny.osm"
    assert document.metadata.source_size_bytes == source.stat().st_size
    assert document.metadata.source_mtime_ns is None
    assert document.metadata.bounding_box == (0, 0, 0.1, 0.1)
    assert tuple(feature.feature_id for feature in document.features) == tuple(
        sorted(feature.feature_id for feature in document.features)
    )
    by_id = {feature.feature_id: feature for feature in document.features}
    assert by_id["way/50"].primary_class is None
    assert by_id["way/50"].park_or_protected
    assert by_id["way/60"].primary_class == "urban"
    assert by_id["way/10"].tags == {"natural": "wood"}
    relation = by_id["relation/200"]
    assert relation.osm_source == "relation"
    assert relation.park_or_protected
    assert isinstance(relation.geometry, PolygonGeometry)
    assert len(relation.geometry.coordinates) == 2
    assert not tuple(output.parent.glob("*.tmp"))


def test_builder_output_is_byte_deterministic(tmp_path: Path) -> None:
    source = _source(tmp_path)
    first = tmp_path / "first.json.gz"
    second = tmp_path / "second.json.gz"
    build_nature_index(source, first)
    build_nature_index(source, second)
    assert first.read_bytes() == second.read_bytes()


def test_polygon_repair_keeps_polygonal_parts_and_discards_non_polygon() -> None:
    bow_tie = Polygon(((0, 0), (1, 1), (1, 0), (0, 1), (0, 0)))
    repaired = _valid_polygonal_geometry(bow_tie)
    assert repaired is not None
    assert repaired.is_valid
    assert _valid_polygonal_geometry(LineString(((0, 0), (1, 1)))) is None


def test_builder_rejects_missing_and_unsupported_inputs(tmp_path: Path) -> None:
    with pytest.raises(NatureIndexBuildError):
        build_nature_index(tmp_path / "missing.osm", tmp_path / "out.json.gz")
    unsupported = tmp_path / "source.geojson"
    unsupported.write_text("{}", encoding="utf-8")
    with pytest.raises(NatureIndexBuildError):
        build_nature_index(unsupported, tmp_path / "out.json.gz")
