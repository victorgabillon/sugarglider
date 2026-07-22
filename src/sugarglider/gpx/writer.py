"""Generate a single clean GPX 1.1 track from routed GeoJSON geometry."""

import re
import unicodedata
from typing import cast
from xml.etree import ElementTree

from shapely.geometry import Point

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.domain.models import RouteResult
from sugarglider.planning.profiles import routing_profile
from sugarglider.planning.result import (
    ApproximatedPlanStop,
    PlanCandidate,
    ReachedPlanStop,
)

GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
UNSAFE_FILENAME_CHARACTERS = re.compile(r"[<>:\"/\\|?*\x00-\x1f\x7f]+")
MAX_REPORTED_STOP_DISTANCE_DIFFERENCE_M = 2.0

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
    """Serialize exactly one GraphHopper track and no analysis extensions."""
    profile = routing_profile(route.routing_profile)
    route_name = f"{route.name} — {profile.display_name}"
    root = ElementTree.Element(
        _tag("gpx"),
        {"version": "1.1", "creator": "Sugarglider"},
    )
    metadata = ElementTree.SubElement(root, _tag("metadata"))
    ElementTree.SubElement(metadata, _tag("name")).text = clean_xml_text(route_name)
    ElementTree.SubElement(metadata, _tag("desc")).text = (
        "Route preference based on mapped OpenStreetMap data; conditions, access "
        "and suitability must be checked locally."
    )
    track = ElementTree.SubElement(root, _tag("trk"))
    ElementTree.SubElement(track, _tag("name")).text = clean_xml_text(route_name)
    ElementTree.SubElement(track, _tag("type")).text = {
        "walking": "hiking",
        "running": "running",
        "cycling": "cycling",
    }[profile.activity_kind]
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


def write_plan_gpx(candidate: PlanCandidate) -> bytes:
    """Export one immutable canonical candidate without any routing call."""
    stops: tuple[ReachedPlanStop | ApproximatedPlanStop, ...] = (
        *candidate.reached_stops,
        *candidate.approximated_stops,
    )
    validate_plan_stops(candidate.route, stops)
    root = ElementTree.fromstring(write_gpx(candidate.route))
    metadata = root.find(_tag("metadata"))
    insertion_index = list(root).index(metadata) + 1 if metadata is not None else 0
    for order, stop in enumerate(stops, start=1):
        approach = stop.resolved_approach
        waypoint = ElementTree.Element(
            _tag("wpt"),
            {
                "lat": format(approach.coordinate.lat, ".8f"),
                "lon": format(approach.coordinate.lon, ".8f"),
            },
        )
        ElementTree.SubElement(waypoint, _tag("name")).text = clean_xml_text(
            f"{order}. {stop.name}"
            + (" — approximate" if isinstance(stop, ApproximatedPlanStop) else "")
        )
        ElementTree.SubElement(waypoint, _tag("desc")).text = clean_xml_text(
            f"Visit {order}; {stop.category}; approach {approach.kind}."
        )
        ElementTree.SubElement(waypoint, _tag("type")).text = clean_xml_text(
            stop.category
        )
        root.insert(insertion_index + order - 1, waypoint)
    return cast(
        bytes, ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
    )


def validate_plan_stops(
    route: RouteResult,
    stops: tuple[ReachedPlanStop | ApproximatedPlanStop, ...],
) -> tuple[float, ...]:
    """Recompute canonical stop arrivals at the GPX trust boundary."""
    if not stops:
        return ()
    if len(route.geometry) < 2:
        raise SelectedStopNotReachedError
    projection = LocalMetricProjection(route.geometry[0][1])
    line = projection.project_line(route.geometry)
    if line.is_empty or not line.is_valid or line.length <= 0:
        raise SelectedStopNotReachedError
    measured: list[float] = []
    for stop in stops:
        approach = stop.resolved_approach
        distance = float(
            line.distance(
                Point(
                    projection.project_position(
                        (approach.coordinate.lon, approach.coordinate.lat)
                    )
                )
            )
        )
        if distance > approach.arrival_tolerance_m or (
            isinstance(stop, ReachedPlanStop)
            and abs(distance - stop.route_to_approach_m)
            > MAX_REPORTED_STOP_DISTANCE_DIFFERENCE_M
        ):
            raise SelectedStopNotReachedError
        measured.append(distance)
    return tuple(measured)


def validate_plan_selected_stops(
    route: RouteResult, selected_stops: tuple[ReachedPlanStop, ...]
) -> tuple[float, ...]:
    """Retained function name for internal callers; public stops are reached."""
    return validate_plan_stops(route, selected_stops)


class SelectedStopNotReachedError(ValueError):
    """A client-posted selected stop is not truthfully reached by its track."""
