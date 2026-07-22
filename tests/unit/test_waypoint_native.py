"""Behavioral parity fixtures for the native canonical Waypoint pipeline."""

from math import hypot
from typing import cast
from xml.etree import ElementTree

import pytest

from sugarglider.domain.models import Coordinate
from sugarglider.gpx.writer import write_plan_gpx
from sugarglider.planning.models import PLAN_REQUEST_ADAPTER, WaypointPlanRequest
from sugarglider.planning.result import PlanCandidate, PlanGpxRequest, PlanResult
from sugarglider.planning.validation import ExactWaypointNotReachedError
from sugarglider.planning.waypoint.service import WaypointPlanner
from sugarglider.routing.backend import AutoTourRoutingBackend, RoutedPath
from sugarglider.routing.profiles import RoutingProfileId
from sugarglider.routing.result import RouteResultFactory

START = Coordinate(lat=48.8700, lon=2.0900)
END = Coordinate(lat=48.8800, lon=2.1400)
FIRST = Coordinate(lat=48.8900, lon=2.1100)
SECOND = Coordinate(lat=48.8750, lon=2.1250)


class _NativeBackend:
    def __init__(self, *, bad_snap: bool = False) -> None:
        self.bad_snap = bad_snap
        self.route_calls = 0
        self.round_trip_calls = 0
        self.alternative_calls = 0
        self.profiles: list[str] = []

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        del pass_through
        self.profiles.append(profile)
        self.route_calls += 1
        geometry = tuple((point.lon, point.lat) for point in points)
        snapped = list(geometry)
        if self.bad_snap and len(snapped) > 2:
            lon, lat = snapped[1]
            snapped[1] = (lon + 0.02, lat + 0.02)
        return _path(geometry, tuple(snapped))

    async def round_trip(
        self,
        start: Coordinate,
        distance_m: float,
        seed: int,
        profile: str = "hike",
        *,
        heading_degrees: float | None = None,
    ) -> RoutedPath:
        del distance_m, seed, heading_degrees
        self.profiles.append(profile)
        self.round_trip_calls += 1
        geometry = (
            (start.lon, start.lat),
            (start.lon + 0.035, start.lat + 0.015),
            (start.lon + 0.010, start.lat + 0.040),
            (start.lon - 0.025, start.lat + 0.015),
            (start.lon, start.lat),
        )
        return _path(geometry, (geometry[0], geometry[-1]))

    async def alternative_routes(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: str = "hike",
        *,
        max_paths: int = 3,
        max_weight_factor: float = 1.6,
        max_share_factor: float = 0.5,
    ) -> tuple[RoutedPath, ...]:
        del max_weight_factor, max_share_factor
        self.profiles.append(profile)
        self.alternative_calls += 1
        direct_geometry = ((start.lon, start.lat), (end.lon, end.lat))
        midpoint = (
            (start.lon + end.lon) / 2 + 0.018,
            (start.lat + end.lat) / 2 + 0.012,
        )
        alternative_geometry = (direct_geometry[0], midpoint, direct_geometry[-1])
        values = (
            _path(direct_geometry, direct_geometry),
            _path(alternative_geometry, direct_geometry),
        )
        return values[:max_paths]


def _path(
    geometry: tuple[tuple[float, float], ...],
    snapped: tuple[tuple[float, float], ...],
) -> RoutedPath:
    distance_m = sum(
        hypot((right[0] - left[0]) * 73_000, (right[1] - left[1]) * 111_000)
        for left, right in zip(geometry, geometry[1:], strict=False)
    )
    return RoutedPath(
        distance_m=distance_m,
        duration_ms=round(distance_m * 700),
        ascend_m=None,
        descend_m=None,
        geometry=geometry,
        snapped_points=snapped,
        details={},
    )


def _request(
    *,
    topology: str,
    waypoints: tuple[Coordinate, ...],
    order: str = "fixed",
    target_m: float = 8_000,
    tolerance_m: float = 1_500,
    path_selection: str = "shortest",
    profile: RoutingProfileId = "hike",
) -> WaypointPlanRequest:
    document = {
        "schema_version": 1,
        "kind": "waypoint_route",
        "name": "Native parity",
        "topology": topology,
        "start": START.model_dump(),
        "end": END.model_dump() if topology == "point_to_point" else None,
        "routing_profile": profile,
        "candidate_count": 5,
        "seed": 41,
        "distance_objective": {
            "target_m": target_m,
            "tolerance_m": tolerance_m,
            "maximum_m": None,
            "priority": "flexible",
        },
        "preferences": {
            "nature": "off",
            "path_selection": path_selection,
            "loop_geometry": "off",
        },
        "waypoints": [
            {
                "id": f"waypoint-{index}",
                "name": point.name or f"Waypoint {index}",
                "coordinate": point.model_dump(),
                "constraint_strength": "exact",
            }
            for index, point in enumerate(waypoints, start=1)
        ],
        "waypoint_order": order,
    }
    request = PLAN_REQUEST_ADAPTER.validate_python(document)
    assert isinstance(request, WaypointPlanRequest)
    return request


async def _generate(
    request: WaypointPlanRequest, backend: _NativeBackend | None = None
) -> tuple[_NativeBackend, PlanResult]:
    resolved = backend or _NativeBackend()
    result = await WaypointPlanner(
        cast(AutoTourRoutingBackend, resolved),
        RouteResultFactory(),
        max_evaluations=48,
    ).generate(request)
    return resolved, result


def _assert_cache_invariants(result: PlanResult) -> None:
    diagnostics = result.search_diagnostics.cache
    assert diagnostics.lookup_count == diagnostics.hit_count + diagnostics.miss_count
    assert diagnostics.entry_count == (
        diagnostics.successful_entry_count + diagnostics.failed_entry_count
    )
    assert diagnostics.backend_call_count == diagnostics.miss_count


def _assert_gpx(candidate: PlanCandidate) -> None:
    request = PlanGpxRequest(schema_version=1, candidate=candidate)
    root = ElementTree.fromstring(write_plan_gpx(request.candidate))
    namespace = {"g": "http://www.topografix.com/GPX/1/1"}
    assert len(root.findall("g:trk", namespace)) == 1
    assert len(root.findall("g:trk/g:trkseg", namespace)) == 1
    assert root.findall("g:rte", namespace) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile",
    (
        "trail_run",
        "hike",
        "city_bike",
        "gravel_bike",
        "mountain_bike",
        "road_bike",
    ),
)
async def test_every_public_profile_propagates_through_waypoint_route(
    profile: RoutingProfileId,
) -> None:
    request = _request(
        topology="point_to_point",
        waypoints=(),
        target_m=3_000,
        tolerance_m=2_000,
        profile=profile,
    )
    backend, result = await _generate(request)
    assert backend.profiles == [profile]
    assert result.routing_profile == profile
    assert all(candidate.routing_profile == profile for candidate in result.candidates)
    assert all(
        candidate.route.routing_profile == profile for candidate in result.candidates
    )


@pytest.mark.asyncio
async def test_fixed_loop_control_parity() -> None:
    request = _request(topology="loop", waypoints=(FIRST, SECOND), target_m=6_000)
    _, result = await _generate(request)
    assert result.candidates
    assert result.topology == "loop"
    assert (
        result.candidates[0].route.geometry[0]
        == result.candidates[0].route.geometry[-1]
    )
    assert any(
        candidate.diagnostics.details["construction"] == "fixed_control"
        for candidate in result.candidates
    )
    _assert_cache_invariants(result)
    _assert_gpx(result.candidates[0])


@pytest.mark.asyncio
async def test_optimized_loop_keeps_start_fixed() -> None:
    request = _request(
        topology="loop", waypoints=(FIRST, SECOND), order="optimize", target_m=6_000
    )
    _, result = await _generate(request)
    assert result.candidates
    assert result.search_diagnostics.details["order_proposals_generated"] > 0
    assert all(
        candidate.route.geometry[0] == (START.lon, START.lat)
        for candidate in result.candidates
    )
    assert all(
        candidate.route.geometry[-1] == (START.lon, START.lat)
        for candidate in result.candidates
    )


@pytest.mark.asyncio
async def test_direct_open_zero_waypoint_control_uses_one_call() -> None:
    request = _request(
        topology="point_to_point", waypoints=(), target_m=3_000, tolerance_m=2_000
    )
    backend, result = await _generate(request)
    assert result.candidates
    assert backend.route_calls == 1
    assert result.search_diagnostics.budget.total_used == 1
    assert (
        result.candidates[0].route.geometry[0]
        != result.candidates[0].route.geometry[-1]
    )
    _assert_gpx(result.candidates[0])


@pytest.mark.asyncio
async def test_fixed_open_interior_waypoints_are_reached() -> None:
    request = _request(
        topology="point_to_point", waypoints=(FIRST, SECOND), target_m=8_000
    )
    _, result = await _generate(request)
    geometry = result.candidates[0].route.geometry
    assert (FIRST.lon, FIRST.lat) in geometry
    assert (SECOND.lon, SECOND.lat) in geometry
    assert geometry[0] == (START.lon, START.lat)
    assert geometry[-1] == (END.lon, END.lat)


@pytest.mark.asyncio
async def test_optimized_open_preserves_endpoints() -> None:
    request = _request(
        topology="point_to_point",
        waypoints=(FIRST, SECOND),
        order="optimize",
        target_m=8_000,
    )
    _, result = await _generate(request)
    assert result.search_diagnostics.details["order_proposals_generated"] > 0
    assert all(
        route.route.geometry[0] == (START.lon, START.lat) for route in result.candidates
    )
    assert all(
        route.route.geometry[-1] == (END.lon, END.lat) for route in result.candidates
    )


@pytest.mark.asyncio
async def test_long_target_produces_graph_derived_detour() -> None:
    request = _request(topology="loop", waypoints=(FIRST,), target_m=15_000)
    backend, result = await _generate(request)
    constructions = {
        candidate.diagnostics.details["construction"] for candidate in result.candidates
    }
    assert backend.round_trip_calls == 3
    assert "round_trip_detour" in constructions
    distances = [candidate.route.summary.distance_m for candidate in result.candidates]
    assert max(distances) > min(distances)


@pytest.mark.asyncio
async def test_low_overlap_uses_gateway_alternatives_and_retains_control() -> None:
    request = _request(
        topology="point_to_point",
        waypoints=(FIRST,),
        target_m=8_000,
        path_selection="low_overlap",
    )
    backend, result = await _generate(request)
    constructions = {
        candidate.diagnostics.details["construction"] for candidate in result.candidates
    }
    assert backend.alternative_calls > 0
    assert "fixed_control" in constructions
    assert result.search_diagnostics.budget.phases["alternative_leg"].used > 0
    _assert_cache_invariants(result)


@pytest.mark.asyncio
async def test_target_below_control_is_best_effort_with_warning() -> None:
    request = _request(
        topology="point_to_point", waypoints=(FIRST,), target_m=1_000, tolerance_m=100
    )
    _, result = await _generate(request)
    assert result.candidates
    assert "target_below_mandatory_lower_bound" in result.search_diagnostics.warnings
    assert not result.candidates[0].diagnostics.within_tolerance


@pytest.mark.asyncio
async def test_badly_snapped_exact_waypoint_is_rejected() -> None:
    named = FIRST.model_copy(update={"name": "Cliff gate"})
    request = _request(topology="point_to_point", waypoints=(named,), target_m=8_000)
    with pytest.raises(ExactWaypointNotReachedError) as caught:
        await _generate(request, _NativeBackend(bad_snap=True))
    assert caught.value.point_index == 1
    assert caught.value.point_name == "Cliff gate"
    assert caught.value.snap_distance_m > 300
    assert caught.value.maximum_snap_distance_m == 300
