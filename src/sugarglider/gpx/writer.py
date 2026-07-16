"""Generate a single clean GPX 1.1 track from routed GeoJSON geometry."""

import re
import unicodedata
from typing import cast
from xml.etree import ElementTree

from sugarglider.domain.models import RouteResult

GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
UNSAFE_FILENAME_CHARACTERS = re.compile(r"[<>:\"/\\|?*\x00-\x1f\x7f]+")

ElementTree.register_namespace("", GPX_NAMESPACE)


def _tag(name: str) -> str:
    return f"{{{GPX_NAMESPACE}}}{name}"


def clean_xml_text(value: str) -> str:
    """Remove characters XML 1.0 cannot represent while preserving Unicode."""
    return "".join(
        character
        for character in value
        if unicodedata.category(character) not in {"Cc", "Cs"}
        and character not in {"\ufffe", "\uffff"}
    )


def gpx_filename(name: str) -> str:
    """Create a safe, useful attachment filename from a route name."""
    cleaned = (
        unicodedata.normalize("NFKD", clean_xml_text(name))
        .encode("ascii", "ignore")
        .decode("ascii")
        .strip()
    )
    cleaned = UNSAFE_FILENAME_CHARACTERS.sub("-", cleaned)
    cleaned = re.sub(r"\s+", "-", cleaned)
    cleaned = re.sub(r"-+", "-", cleaned).strip(" .-_")
    return f"{(cleaned or 'sugarglider-route')[:100]}.gpx"


def write_gpx(route: RouteResult) -> bytes:
    """Serialize exactly one track containing only GraphHopper route coordinates."""
    root = ElementTree.Element(
        _tag("gpx"),
        {"version": "1.1", "creator": "Sugarglider"},
    )
    metadata = ElementTree.SubElement(root, _tag("metadata"))
    ElementTree.SubElement(metadata, _tag("name")).text = clean_xml_text(route.name)
    ElementTree.SubElement(
        metadata, _tag("desc")
    ).text = "Trail route snapped to OpenStreetMap paths by GraphHopper."
    track = ElementTree.SubElement(root, _tag("trk"))
    ElementTree.SubElement(track, _tag("name")).text = clean_xml_text(route.name)
    segment = ElementTree.SubElement(track, _tag("trkseg"))
    for lon, lat in route.geometry:
        ElementTree.SubElement(
            segment,
            _tag("trkpt"),
            {"lat": format(lat, ".8f"), "lon": format(lon, ".8f")},
        )
    return cast(
        bytes, ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
    )
