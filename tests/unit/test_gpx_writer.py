"""Tests for clean, track-only GPX generation."""

from xml.etree import ElementTree

from sugarglider.domain.models import RouteResult
from sugarglider.gpx.writer import GPX_NAMESPACE, gpx_filename, write_gpx


def test_gpx_contains_one_track_and_exact_geometry(route_result: RouteResult) -> None:
    xml = write_gpx(route_result)
    root = ElementTree.fromstring(xml)
    namespace = {"g": GPX_NAMESPACE}

    assert root.tag == f"{{{GPX_NAMESPACE}}}gpx"
    assert len(root.findall("g:trk", namespace)) == 1
    assert len(root.findall("g:trk/g:trkseg", namespace)) == 1
    points = root.findall("g:trk/g:trkseg/g:trkpt", namespace)
    assert len(points) == len(route_result.geometry)
    assert points[0].attrib == {"lat": "48.87138900", "lon": "2.09666700"}
    assert points[-1].attrib == {"lat": "48.87145400", "lon": "2.12442100"}
    assert points[-1].attrib != points[0].attrib
    assert root.findall("g:rte", namespace) == []
    assert root.findall(".//g:ele", namespace) == []


def test_gpx_escapes_route_name(route_result: RouteResult) -> None:
    special = route_result.model_copy(update={"name": "Forêt & <Marly>\x01"})
    xml = write_gpx(special)
    assert b"For\xc3\xaat &amp; &lt;Marly&gt;" in xml
    root = ElementTree.fromstring(xml)
    assert root.findtext(f"{{{GPX_NAMESPACE}}}metadata/{{{GPX_NAMESPACE}}}name") == (
        "Forêt & <Marly>"
    )


def test_filename_is_safe_and_http_header_compatible() -> None:
    assert gpx_filename(' Désert: de / Retz? "été" ') == "Desert-de-Retz-ete.gpx"
    assert gpx_filename("\x00 / ") == "sugarglider-route.gpx"
