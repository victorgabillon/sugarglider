"""POI-index builder tests using only tiny local OSM XML."""

import gzip
import json
from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon

from sugarglider.pois.build import _validated_position, build_poi_index
from sugarglider.pois.errors import PoiIndexBuildError
from sugarglider.pois.models import PoiIndexDocument

OSM_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="sugarglider-tests">
  <bounds minlat="48.0" minlon="2.0" maxlat="48.1" maxlon="2.1"/>
  <node id="1" lat="48.010" lon="2.010">
    <tag k="tourism" v="viewpoint"/><tag k="name" v="Belvédère été"/>
  </node>
  <node id="2" lat="48.020" lon="2.020">
    <tag k="amenity" v="fountain"/><tag k="drinking_water" v="yes"/>
    <tag k="access" v="private"/>
  </node>
  <node id="3" lat="48.030" lon="2.030">
    <tag k="amenity" v="fountain"/>
  </node>
  <node id="4" lat="48.040" lon="2.010"/>
  <node id="5" lat="48.040" lon="2.030"/>
  <node id="6" lat="48.060" lon="2.010"/>
  <node id="7" lat="48.060" lon="2.030"/>
  <node id="8" lat="48.070" lon="2.010"/>
  <node id="9" lat="48.070" lon="2.030"/>
  <node id="10" lat="48.090" lon="2.030"/>
  <node id="11" lat="48.090" lon="2.010"/>
  <node id="12" lat="48.075" lon="2.015"/>
  <node id="13" lat="48.075" lon="2.025"/>
  <node id="14" lat="48.085" lon="2.025"/>
  <node id="15" lat="48.085" lon="2.015"/>
  <node id="16" lat="48.045" lon="2.040"/>
  <node id="17" lat="48.055" lon="2.050"/>
  <node id="18" lat="48.045" lon="2.050"/>
  <node id="19" lat="48.055" lon="2.040"/>
  <way id="20">
    <nd ref="4"/><nd ref="5"/>
    <tag k="tourism" v="attraction"/><tag k="name" v="Promenade"/>
  </way>
  <way id="21">
    <nd ref="6"/><nd ref="7"/><nd ref="9"/><nd ref="8"/><nd ref="6"/>
    <tag k="historic" v="castle"/><tag k="ruins" v="yes"/>
  </way>
  <way id="22">
    <nd ref="16"/><nd ref="17"/><nd ref="18"/><nd ref="19"/><nd ref="16"/>
    <tag k="tourism" v="viewpoint"/>
  </way>
  <way id="23">
    <nd ref="4"/><nd ref="5"/><nd ref="7"/><nd ref="6"/><nd ref="4"/>
    <tag k="tourism" v="attraction"/><tag k="area" v="no"/>
  </way>
  <way id="30">
    <nd ref="8"/><nd ref="9"/><nd ref="10"/><nd ref="11"/><nd ref="8"/>
  </way>
  <way id="31">
    <nd ref="12"/><nd ref="13"/><nd ref="14"/><nd ref="15"/><nd ref="12"/>
  </way>
  <relation id="40">
    <member type="way" ref="30" role="outer"/>
    <member type="way" ref="31" role="inner"/>
    <tag k="type" v="multipolygon"/>
    <tag k="historic" v="archaeological_site"/>
  </relation>
</osm>
"""


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "tiny.osm"
    source.write_text(OSM_XML, encoding="utf-8")
    return source


def test_builder_selects_nodes_ways_relations_and_geometry(tmp_path: Path) -> None:
    source = _source(tmp_path)
    output = tmp_path / "nested" / "pois.json.gz"
    output.parent.mkdir()
    output.write_bytes(b"previous index")
    report = build_poi_index(source, output)
    with gzip.open(output, "rt", encoding="utf-8") as stream:
        document = PoiIndexDocument.model_validate(json.load(stream))

    assert report.feature_count == 7
    assert report.category_counts == {
        "archaeological_site": 1,
        "castle": 1,
        "drinking_water": 1,
        "fountain": 1,
        "tourism_attraction": 2,
        "viewpoint": 1,
    }
    assert report.potability_counts == {
        "not_applicable": 5,
        "unknown": 1,
        "verified": 1,
    }
    assert document.metadata.bounding_box == (2.0, 48.0, 2.1, 48.1)
    assert document.metadata.source_basename == "tiny.osm"
    assert document.metadata.source_size_bytes == source.stat().st_size
    assert tuple(feature.id for feature in document.features) == tuple(
        sorted(feature.id for feature in document.features)
    )
    by_id = {feature.id: feature for feature in document.features}
    assert by_id["node/1"].display_name == "Belvédère été"
    assert by_id["node/2"].potability == "verified"
    assert by_id["node/2"].access_status == "private"
    assert by_id["node/3"].potability == "unknown"
    assert by_id["way/20"].coordinate.lat == pytest.approx(48.04)
    assert by_id["way/20"].coordinate.lon == pytest.approx(2.02)
    assert by_id["way/21"].ruins
    castle_point = Point(
        by_id["way/21"].coordinate.lon,
        by_id["way/21"].coordinate.lat,
    )
    assert Polygon(
        ((2.01, 48.06), (2.03, 48.06), (2.03, 48.07), (2.01, 48.07))
    ).contains(castle_point)
    assert by_id["way/23"].coordinate.lon == pytest.approx(2.03)
    assert by_id["way/23"].coordinate.lat == pytest.approx(48.06)
    relation_point = Point(
        by_id["relation/40"].coordinate.lon,
        by_id["relation/40"].coordinate.lat,
    )
    outer = Polygon(((2.01, 48.07), (2.03, 48.07), (2.03, 48.09), (2.01, 48.09)))
    hole = Polygon(((2.015, 48.075), (2.025, 48.075), (2.025, 48.085), (2.015, 48.085)))
    assert outer.contains(relation_point)
    assert not hole.contains(relation_point)
    assert report.skipped_invalid_count == 1
    assert not tuple(output.parent.glob("*.tmp"))


def test_builder_output_is_byte_deterministic_and_path_independent(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    first = tmp_path / "one" / "pois.json.gz"
    second = tmp_path / "two" / "pois.json.gz"
    build_poi_index(source, first)
    build_poi_index(source, second)

    assert first.read_bytes() == second.read_bytes()
    assert str(tmp_path).encode() not in gzip.decompress(first.read_bytes())


def test_builder_rejects_missing_unsupported_and_invalid_positions(
    tmp_path: Path,
) -> None:
    with pytest.raises(PoiIndexBuildError):
        build_poi_index(tmp_path / "missing.osm", tmp_path / "out.json.gz")
    unsupported = tmp_path / "source.geojson"
    unsupported.write_text("{}", encoding="utf-8")
    with pytest.raises(PoiIndexBuildError):
        build_poi_index(unsupported, tmp_path / "out.json.gz")
    with pytest.raises(ValueError):
        _validated_position(181, 0)
    with pytest.raises(ValueError):
        _validated_position(0, float("nan"))


def test_polygon_approaches_keep_public_entrance_and_exclude_private(
    tmp_path: Path,
) -> None:
    source = tmp_path / "approaches.osm"
    source.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="test">
  <bounds minlat="48.0" minlon="2.0" maxlat="48.1" maxlon="2.1"/>
  <node id="1" lat="48.01" lon="2.01">
    <tag k="entrance" v="main"/><tag k="access" v="yes"/>
  </node>
  <node id="2" lat="48.01" lon="2.02">
    <tag k="entrance" v="yes"/><tag k="access" v="private"/>
  </node>
  <node id="3" lat="48.02" lon="2.02"/>
  <node id="4" lat="48.02" lon="2.01"/>
  <way id="10">
    <nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
    <tag k="historic" v="castle"/><tag k="name" v="Castle"/>
  </way>
</osm>
""",
        encoding="utf-8",
    )
    output = tmp_path / "approaches.json.gz"
    report = build_poi_index(source, output)
    with gzip.open(output, "rt", encoding="utf-8") as stream:
        document = PoiIndexDocument.model_validate(json.load(stream))

    castle = next(feature for feature in document.features if feature.id == "way/10")
    assert tuple(approach.kind for approach in castle.approach_candidates) == (
        "mapped_entrance",
    )
    assert castle.approach_candidates[0].osm_id == 1
    assert report.approach_counts == {"mapped_entrance": 1}


def test_private_polygon_never_inherits_a_public_approach(tmp_path: Path) -> None:
    source = tmp_path / "private-area.osm"
    source.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="test">
  <bounds minlat="48.0" minlon="2.0" maxlat="48.1" maxlon="2.1"/>
  <node id="1" lat="48.01" lon="2.01">
    <tag k="entrance" v="main"/><tag k="access" v="yes"/>
  </node>
  <node id="2" lat="48.01" lon="2.02"/>
  <node id="3" lat="48.02" lon="2.02"/>
  <node id="4" lat="48.02" lon="2.01"/>
  <way id="10">
    <nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
    <tag k="historic" v="castle"/><tag k="name" v="Private castle"/>
    <tag k="access" v="private"/>
  </way>
</osm>
""",
        encoding="utf-8",
    )
    output = tmp_path / "private-area.json.gz"
    report = build_poi_index(source, output)
    with gzip.open(output, "rt", encoding="utf-8") as stream:
        document = PoiIndexDocument.model_validate(json.load(stream))

    castle = next(feature for feature in document.features if feature.id == "way/10")
    assert castle.access_status == "private"
    assert castle.approach_candidates == ()
    assert report.approach_counts == {}


def test_polygon_gate_and_public_path_are_meaningful_bounded_approaches(
    tmp_path: Path,
) -> None:
    source = tmp_path / "gate-and-path.osm"
    source.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="test">
  <bounds minlat="48.0" minlon="2.0" maxlat="48.1" maxlon="2.1"/>
  <node id="1" lat="48.01" lon="2.01">
    <tag k="barrier" v="gate"/><tag k="access" v="yes"/>
  </node>
  <node id="2" lat="48.01" lon="2.02"/>
  <node id="3" lat="48.02" lon="2.02"/>
  <node id="4" lat="48.02" lon="2.01"/>
  <node id="5" lat="48.015" lon="2.005"/>
  <node id="6" lat="48.015" lon="2.025"/>
  <node id="10" lat="48.04" lon="2.04"/>
  <node id="11" lat="48.04" lon="2.05"/>
  <node id="12" lat="48.05" lon="2.05"/>
  <node id="13" lat="48.05" lon="2.04"/>
  <way id="20">
    <nd ref="4"/><nd ref="3"/><tag k="highway" v="footway"/>
    <tag k="access" v="yes"/>
  </way>
  <way id="30">
    <nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
    <tag k="historic" v="castle"/><tag k="name" v="Accessible castle"/>
  </way>
  <way id="31">
    <nd ref="10"/><nd ref="11"/><nd ref="12"/><nd ref="13"/><nd ref="10"/>
    <tag k="historic" v="castle"/><tag k="name" v="Castle without access"/>
  </way>
</osm>
""",
        encoding="utf-8",
    )
    output = tmp_path / "gate-and-path.json.gz"
    build_poi_index(source, output)
    with gzip.open(output, "rt", encoding="utf-8") as stream:
        document = PoiIndexDocument.model_validate(json.load(stream))

    by_id = {feature.id: feature for feature in document.features}
    approaches = by_id["way/30"].approach_candidates
    assert "mapped_gate" in {approach.kind for approach in approaches}
    assert sum(approach.kind == "public_path_boundary" for approach in approaches) == 2
    assert len(approaches) <= 8
    assert by_id["way/31"].approach_candidates == ()


def test_access_provenance_is_topological_cautious_and_truthful(
    tmp_path: Path,
) -> None:
    source = tmp_path / "provenance.osm"
    source.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="test">
  <bounds minlat="48.0" minlon="2.0" maxlat="48.1" maxlon="2.1"/>
  <node id="1" lat="48.010" lon="2.010">
    <tag k="entrance" v="main"/><tag k="access" v="yes"/>
  </node>
  <node id="2" lat="48.010" lon="2.020"/>
  <node id="3" lat="48.020" lon="2.020"/>
  <node id="4" lat="48.020" lon="2.010"/>
  <node id="5" lat="48.015" lon="2.00995">
    <tag k="entrance" v="yes"/><tag k="access" v="yes"/>
  </node>
  <node id="6" lat="48.016" lon="2.009995">
    <tag k="entrance" v="yes"/>
  </node>
  <node id="7" lat="48.030" lon="2.030"/>
  <way id="20"><nd ref="4"/><nd ref="3"/><tag k="highway" v="footway"/></way>
  <way id="21">
    <nd ref="1"/><nd ref="2"/><tag k="highway" v="footway"/>
    <tag k="bridge" v="yes"/><tag k="access" v="yes"/>
  </way>
  <way id="30">
    <nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
    <tag k="historic" v="castle"/><tag k="name" v="Castle"/>
  </way>
</osm>
""",
        encoding="utf-8",
    )
    output = tmp_path / "provenance.json.gz"
    build_poi_index(source, output)
    with gzip.open(output, "rt", encoding="utf-8") as stream:
        document = PoiIndexDocument.model_validate(json.load(stream))

    castle = next(feature for feature in document.features if feature.id == "way/30")
    by_osm = {approach.osm_id: approach for approach in castle.approach_candidates}

    assert by_osm[1].provenance == "way_boundary_node"
    assert 5 not in by_osm  # A nearby feature's entrance is not inherited.
    assert by_osm[6].access == "unknown"
    assert by_osm[6].provenance == "spatial_boundary_inferred"
    assert by_osm[6].warnings == ("spatial_boundary_association_unverified",)
    unknown_path = next(
        approach for approach in castle.approach_candidates if approach.osm_id == 20
    )
    assert unknown_path.access == "unknown"
    assert unknown_path.provenance == "shared_path_boundary_node"
    assert not any(approach.osm_id == 21 for approach in castle.approach_candidates)
