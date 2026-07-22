"""Canonical track-only GPX generation and strict stop validation."""

from xml.etree import ElementTree

import pytest

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.gpx.writer import (
    GPX_NAMESPACE,
    SelectedStopNotReachedError,
    gpx_filename,
    validate_plan_selected_stops,
    write_gpx,
    write_plan_gpx,
)
from sugarglider.planning.result import (
    ApproximatedPlanStop,
    PlanCandidate,
    PlanCandidateDiagnostics,
    PlanScore,
    ReachedPlanStop,
)
from sugarglider.pois.models import PoiApproachCandidate


def _candidate(
    route: RouteResult,
    selected: tuple[ReachedPlanStop, ...] = (),
    approximated: tuple[ApproximatedPlanStop, ...] = (),
) -> PlanCandidate:
    return PlanCandidate(
        id="candidate",
        routing_profile=route.routing_profile,
        rank=1,
        roles=("harmonious",),
        route=route,
        score=PlanScore(total=0),
        reached_stops=selected,
        approximated_stops=approximated,
        diagnostics=PlanCandidateDiagnostics(
            safety_eligible=True,
            target_error_m=0,
            within_tolerance=True,
            requested_stop_count=len(selected),
            immediate_backtracking_m=0,
            repeated_distance_m=0,
        ),
    )


def _stop(route: RouteResult, *, offset_m: float = 0) -> ReachedPlanStop:
    projection = LocalMetricProjection(route.geometry[0][1])
    line = projection.project_line(route.geometry)
    midpoint = line.interpolate(line.length / 2)
    lon, lat = projection.unproject_position((midpoint.x, midpoint.y + offset_m))
    approach = PoiApproachCandidate(
        id="requested/1/approach",
        coordinate=Coordinate(lat=lat, lon=lon),
        kind="strict_graph_snap",
        source="imported_coordinate",
        access="unknown",
        semantic_distance_m=0,
        arrival_tolerance_m=25,
        provenance="imported_coordinate",
    )
    return ReachedPlanStop(
        id="requested/1",
        name="Étape & source",
        semantic_coordinate=approach.coordinate,
        category="requested_stop",
        importance="must_visit",
        selection_origin="requested",
        selection_method="deliberate_insertion",
        resolved_approach=approach,
        route_progress=0.5,
        route_to_approach_m=offset_m,
    )


def test_gpx_contains_one_track_and_exact_geometry(route_result: RouteResult) -> None:
    root = ElementTree.fromstring(write_gpx(route_result))
    namespace = {"g": GPX_NAMESPACE}
    assert len(root.findall("g:trk", namespace)) == 1
    assert len(root.findall("g:trk/g:trkseg", namespace)) == 1
    points = root.findall("g:trk/g:trkseg/g:trkpt", namespace)
    assert len(points) == len(route_result.geometry)
    assert points[0].attrib == {"lat": "48.87138900", "lon": "2.09666700"}
    assert root.findall("g:rte", namespace) == []
    assert root.findall("g:wpt", namespace) == []


def test_gpx_uses_public_profile_metadata_without_extensions(
    route_result: RouteResult,
) -> None:
    road_route = route_result.model_copy(update={"routing_profile": "road_bike"})
    root = ElementTree.fromstring(write_gpx(road_route))
    namespace = {"g": GPX_NAMESPACE}
    assert root.findtext("g:trk/g:type", namespaces=namespace) == "cycling"
    assert "Road bike" in (root.findtext("g:trk/g:name", namespaces=namespace) or "")
    assert root.findall(".//g:extensions", namespace) == []


def test_plan_gpx_contains_only_selected_stops(route_result: RouteResult) -> None:
    root = ElementTree.fromstring(
        write_plan_gpx(_candidate(route_result, (_stop(route_result),)))
    )
    namespace = {"g": GPX_NAMESPACE}
    waypoints = root.findall("g:wpt", namespace)
    assert len(waypoints) == 1
    assert waypoints[0].findtext("g:name", namespaces=namespace) == "1. Étape & source"
    assert waypoints[0].findtext("g:type", namespaces=namespace) == "requested_stop"
    assert len(root.findall("g:trk", namespace)) == 1
    assert root.findall("g:rte", namespace) == []


def test_plan_gpx_truthfully_exports_and_revalidates_approximation(
    route_result: RouteResult,
) -> None:
    reached = _stop(route_result)
    routed = reached.resolved_approach.coordinate
    semantic = routed.model_copy(update={"lat": routed.lat + 0.001})
    remaining = haversine_distance_m(
        (semantic.lon, semantic.lat), (routed.lon, routed.lat)
    )
    approximated = ApproximatedPlanStop(
        id="approximate-1",
        name="Woodland viewpoint",
        semantic_coordinate=semantic,
        category="requested_stop",
        importance="must_visit",
        selection_origin="requested",
        resolved_approach=reached.resolved_approach,
        route_progress=reached.route_progress,
        distance_m=remaining,
        normal_tolerance_m=25,
        configured_maximum_m=500,
        reason="nearest_routeable_point_used",
    )
    root = ElementTree.fromstring(
        write_plan_gpx(_candidate(route_result, approximated=(approximated,)))
    )
    namespace = {"g": GPX_NAMESPACE}
    assert root.findall("g:rte", namespace) == []
    assert len(root.findall("g:trk/g:trkseg", namespace)) == 1
    assert root.findtext("g:wpt/g:name", namespaces=namespace) == (
        "1. Woodland viewpoint — approximate"
    )

    forged = approximated.model_copy(
        update={
            "resolved_approach": approximated.resolved_approach.model_copy(
                update={
                    "coordinate": semantic.model_copy(update={"lat": semantic.lat + 1})
                }
            )
        }
    )
    with pytest.raises(SelectedStopNotReachedError):
        write_plan_gpx(_candidate(route_result, approximated=(forged,)))


def test_plan_export_rejects_forged_stop_measurement(route_result: RouteResult) -> None:
    valid = _stop(route_result)
    projection = LocalMetricProjection(route_result.geometry[0][1])
    line = projection.project_line(route_result.geometry)
    midpoint = line.interpolate(line.length / 2)
    lon, lat = projection.unproject_position((midpoint.x, midpoint.y + 40))
    forged = valid.model_copy(
        update={
            "resolved_approach": valid.resolved_approach.model_copy(
                update={"coordinate": Coordinate(lat=lat, lon=lon)}
            ),
            "route_to_approach_m": 0,
        }
    )
    with pytest.raises(SelectedStopNotReachedError):
        validate_plan_selected_stops(route_result, (forged,))


def test_filename_is_safe_and_http_header_compatible() -> None:
    assert gpx_filename(' Désert: de / Retz? "été" ') == "Desert-de-Retz-ete.gpx"
    assert gpx_filename("\x00 / ") == "sugarglider-route.gpx"
