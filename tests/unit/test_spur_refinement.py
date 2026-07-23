"""Bounded synthetic tests for shared alternative-exit spur closure."""

from collections.abc import Mapping
from dataclasses import replace
from typing import cast
from xml.etree import ElementTree

import pytest

import sugarglider.planning.refinement.spur_closure as spur_closure_module
from sugarglider.analysis.spurs import detect_route_spurs
from sugarglider.domain.models import Coordinate, PathDetailSegment, RouteResult
from sugarglider.gpx.writer import write_plan_gpx
from sugarglider.planning.auto_tour.service import AutoTourPlanner, AutoTourService
from sugarglider.planning.budget import SearchBudget, SearchPhase
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.direction.models import ReversePlanRequest
from sugarglider.planning.direction.service import ReversePlanner
from sugarglider.planning.models import (
    PLAN_REQUEST_ADAPTER,
    AutoTourPlanRequest,
    WaypointPlanRequest,
)
from sugarglider.planning.refinement import (
    RepairAnchor,
    SpurClosureSettings,
    SpurRepairSource,
    refine_spur_closures,
)
from sugarglider.planning.refinement.rejoin import (
    generate_rejoin_candidates,
    locate_repair_anchors,
)
from sugarglider.planning.waypoint.service import WaypointPlanner
from sugarglider.routing.backend import AutoTourRoutingBackend, RoutedPath
from sugarglider.routing.errors import RoutingPointError
from sugarglider.routing.result import RouteResultFactory

A = Coordinate(lat=0.0, lon=0.000, name="A")
B = Coordinate(lat=0.0, lon=0.001, name="B")
C = Coordinate(lat=0.0, lon=0.002, name="C")
D = Coordinate(lat=0.0, lon=0.003, name="D")
E = Coordinate(lat=0.0, lon=0.004, name="E")
X = Coordinate(lat=0.001, lon=0.003, name="X")
Y = Coordinate(lat=0.001, lon=0.002, name="Y")
Z = Coordinate(lat=0.001, lon=0.001, name="Z")

type LegKey = tuple[float, float, float, float]


def _path(
    points: tuple[Coordinate, ...],
    edge_ids: tuple[int, ...],
    *,
    edge_distance_m: float = 100.0,
) -> RoutedPath:
    return RoutedPath(
        distance_m=edge_distance_m * len(edge_ids),
        duration_ms=len(edge_ids),
        ascend_m=None,
        descend_m=None,
        geometry=tuple((point.lon, point.lat) for point in points),
        snapped_points=tuple(
            (point.lon, point.lat) for point in (points[0], points[-1])
        ),
        details={
            "edge_id": tuple(
                PathDetailSegment(
                    from_index=index,
                    to_index=index + 1,
                    value=edge_id,
                )
                for index, edge_id in enumerate(edge_ids)
            )
        },
    )


def _source_route(*, edge_distance_m: float = 100.0) -> tuple[RouteResult, RoutedPath]:
    path = _path(
        (A, B, C, D, C, B, E),
        (10, 20, 30, 30, 20, 40),
        edge_distance_m=edge_distance_m,
    )
    route = RouteResultFactory().create(
        name="three-sided square",
        path=path,
        input_point_count=2,
        routing_profile="hike",
    )
    spurs = detect_route_spurs(route, topology="point_to_point")
    route = route.model_copy(
        update={"analysis": route.analysis.model_copy(update={"spurs": spurs})}
    )
    return route, path


class _Backend:
    def __init__(
        self,
        *,
        alternatives: tuple[RoutedPath, ...],
        routes: Mapping[LegKey, RoutedPath],
        fail_alternatives: bool = False,
        fail_routes: bool = False,
    ) -> None:
        self.alternatives = alternatives
        self.routes = dict(routes)
        self.calls: list[tuple[str, str]] = []
        self.fail_alternatives = fail_alternatives
        self.fail_routes = fail_routes

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        del pass_through
        self.calls.append(("route", profile))
        if self.fail_routes:
            raise RoutingPointError("synthetic reconstruction failure")
        key = (
            points[0].lat,
            points[0].lon,
            points[-1].lat,
            points[-1].lon,
        )
        return self.routes[key]

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
        del start, max_paths, max_weight_factor, max_share_factor
        self.calls.append(("alternatives", profile))
        if self.fail_alternatives:
            raise RoutingPointError("synthetic connector failure")
        return self.alternatives if (end.lat, end.lon) == (B.lat, B.lon) else ()


class _ReverseBackend:
    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        del profile, pass_through
        geometry = tuple((point.lon, point.lat) for point in points)
        return RoutedPath(
            distance_m=100.0 * (len(points) - 1),
            duration_ms=len(points),
            ascend_m=None,
            descend_m=None,
            geometry=geometry,
            snapped_points=geometry,
            details={
                "edge_id": tuple(
                    PathDetailSegment(
                        from_index=index,
                        to_index=index + 1,
                        value=1_000 + index,
                    )
                    for index in range(len(points) - 1)
                )
            },
        )


def _context(backend: _Backend, limit: int = 10) -> PlanningSearchContext:
    limits = {phase: 0 for phase in SearchPhase}
    limits[SearchPhase.SPUR_REPAIR] = limit
    return PlanningSearchContext.create(
        backend=cast(AutoTourRoutingBackend, backend),
        budget=SearchBudget(limits, total_limit=limit),
    )


def _source() -> SpurRepairSource:
    route, path = _source_route()
    return SpurRepairSource(
        source_candidate_id="source",
        route=route,
        routed_path=path,
        routing_points=(A, E),
        anchors=locate_repair_anchors(
            route,
            (A, E),
            exact_coordinates=frozenset(((A.lat, A.lon), (E.lat, E.lon))),
        ),
        topology="point_to_point",
        profile="hike",
    )


def test_rejoin_sampling_is_deterministic_bounded_and_respects_exact_boundary() -> None:
    route, _path_value = _source_route(edge_distance_m=1_000.0)
    spur = detect_route_spurs(route, topology="point_to_point").spurs[0]
    boundary = Coordinate(lat=0.0, lon=0.0035, name="Exact boundary")
    anchors = locate_repair_anchors(
        route,
        (A, boundary, E),
        exact_coordinates=frozenset(
            ((A.lat, A.lon), (boundary.lat, boundary.lon), (E.lat, E.lon))
        ),
    )

    first = generate_rejoin_candidates(
        route,
        spur,
        anchors,
        topology="point_to_point",
    )
    second = generate_rejoin_candidates(
        route,
        spur,
        anchors,
        topology="point_to_point",
    )

    assert first == second
    assert len(first) <= 8
    assert all(value.source_progress <= anchors[1].route_progress for value in first)
    assert any(value.source_kind == "deliberate_anchor" for value in first)
    assert len({value.stable_id for value in first}) == len(first)


def test_loop_rejoins_do_not_publish_the_duplicated_start_as_a_target() -> None:
    loop_path = _path(
        (A, B, C, D, C, B, E, A),
        (10, 20, 30, 30, 20, 40, 50),
        edge_distance_m=500.0,
    )
    loop_route = RouteResultFactory().create(
        name="loop spur",
        path=loop_path,
        input_point_count=2,
        routing_profile="hike",
    )
    spur = detect_route_spurs(loop_route, topology="loop").spurs[0]
    anchors = locate_repair_anchors(
        loop_route,
        (A, A),
        exact_coordinates=frozenset(((A.lat, A.lon),)),
    )

    rejoins = generate_rejoin_candidates(
        loop_route,
        spur,
        anchors,
        topology="loop",
    )

    assert rejoins
    assert all(value.source_progress < 1 for value in rejoins)
    assert all(value.coordinate != A for value in rejoins)


@pytest.mark.asyncio
async def test_same_corridor_is_rejected_then_clean_alternative_is_reconstructed() -> (
    None
):
    same_corridor = _path((D, C, B), (30, 20))
    clean_exit = _path((D, X, B), (50, 51))
    backend = _Backend(
        alternatives=(same_corridor, clean_exit),
        routes={
            (A.lat, A.lon, D.lat, D.lon): _path((A, B, C, D), (10, 20, 30)),
            (B.lat, B.lon, E.lat, E.lon): _path((B, E), (40,)),
        },
    )
    context = _context(backend)

    result = await refine_spur_closures(
        _source(),
        context=context,
        result_factory=RouteResultFactory(),
    )

    assert result.attempts == 2
    assert len(result.drafts) == 1
    repaired = result.drafts[0]
    assert repaired.path.geometry == (
        (A.lon, A.lat),
        (B.lon, B.lat),
        (C.lon, C.lat),
        (D.lon, D.lat),
        (X.lon, X.lat),
        (B.lon, B.lat),
        (E.lon, E.lat),
    )
    assert repaired.routing_points[0] == A
    assert repaired.routing_points[-1] == E
    assert repaired.diagnostics.inbound_overlap_share == 0
    assert repaired.diagnostics.repeated_distance_improvement_m >= 150
    aggregate = result.diagnostics
    assert aggregate.source_candidates_considered == 1
    assert aggregate.spurs_considered == 1
    assert aggregate.rejoin_candidates_generated == 2
    assert aggregate.connector_route_attempts == 2
    assert aggregate.connector_routes_succeeded == 2
    assert aggregate.rejected_inbound_overlap == 1
    assert aggregate.reconstruction_attempts == 1
    assert aggregate.accepted_repair_drafts == 1
    assert context.budget.used(SearchPhase.SPUR_REPAIR) == 4
    assert all(profile == "hike" for _operation, profile in backend.calls)


@pytest.mark.asyncio
async def test_budget_exhaustion_is_nonfatal_and_retains_no_partial_geometry() -> None:
    backend = _Backend(
        alternatives=(_path((D, X, B), (50, 51)),),
        routes={
            (A.lat, A.lon, D.lat, D.lon): _path((A, B, C, D), (10, 20, 30)),
            (B.lat, B.lon, E.lat, E.lon): _path((B, E), (40,)),
        },
    )
    context = _context(backend, limit=1)

    result = await refine_spur_closures(
        _source(),
        context=context,
        result_factory=RouteResultFactory(),
    )

    assert result.drafts == ()
    assert result.warnings == ("spur_repair_budget_exhausted",)
    assert result.diagnostics.budget_exhausted
    assert result.diagnostics.reconstruction_attempts == 1
    snapshot = context.routes.cache_snapshot()
    assert snapshot.lookup_count == snapshot.hit_count + snapshot.miss_count
    assert snapshot.backend_call_count == snapshot.miss_count


@pytest.mark.asyncio
async def test_trivial_spur_and_explicit_maximum_do_not_publish_repairs() -> None:
    small_route, small_path = _source_route(edge_distance_m=50.0)
    small = SpurRepairSource(
        source_candidate_id="small",
        route=small_route,
        routed_path=small_path,
        routing_points=(A, E),
        anchors=locate_repair_anchors(small_route, (A, E)),
        topology="point_to_point",
        profile="hike",
    )
    backend = _Backend(alternatives=(), routes={})
    small_result = await refine_spur_closures(
        small,
        context=_context(backend),
        result_factory=RouteResultFactory(),
    )
    assert small_result.attempts == 0
    assert small_result.drafts == ()
    assert small_result.diagnostics.source_candidates_considered == 1
    assert small_result.diagnostics.spurs_considered == 0
    assert small_result.diagnostics.rejoin_candidates_generated == 0

    clean_exit = _path((D, X, B), (50, 51))
    maximum_backend = _Backend(
        alternatives=(clean_exit,),
        routes={
            (A.lat, A.lon, D.lat, D.lon): _path((A, B, C, D), (10, 20, 30)),
            (B.lat, B.lon, E.lat, E.lon): _path((B, E), (40,)),
        },
    )
    maximum_result = await refine_spur_closures(
        replace(_source(), maximum_distance_m=550.0),
        context=_context(maximum_backend),
        result_factory=RouteResultFactory(),
    )
    assert maximum_result.attempts == 1
    assert maximum_result.drafts == ()
    assert maximum_result.diagnostics.rejected_explicit_maximum == 1


@pytest.mark.asyncio
async def test_repair_with_worse_total_repetition_is_rejected() -> None:
    repeating_connector = _path((D, X, Y, Z, C, B), (99, 98, 99, 98, 99))
    backend = _Backend(
        alternatives=(repeating_connector,),
        routes={
            (A.lat, A.lon, D.lat, D.lon): _path((A, B, C, D), (10, 20, 30)),
            (B.lat, B.lon, E.lat, E.lon): _path((B, E), (40,)),
        },
    )

    result = await refine_spur_closures(
        _source(),
        context=_context(backend),
        result_factory=RouteResultFactory(),
    )

    assert result.attempts == 1
    assert result.drafts == ()
    assert result.diagnostics.rejected_worse_total_repetition == 1


@pytest.mark.asyncio
async def test_connector_failure_and_reconstruction_failure_are_distinct() -> None:
    connector_failure = await refine_spur_closures(
        _source(),
        context=_context(_Backend(alternatives=(), routes={}, fail_alternatives=True)),
        result_factory=RouteResultFactory(),
    )
    assert connector_failure.diagnostics.connector_route_attempts == 2
    assert connector_failure.diagnostics.connector_route_failures == 2
    assert connector_failure.diagnostics.connector_routes_succeeded == 0
    assert connector_failure.diagnostics.reconstruction_attempts == 0

    reconstruction_failure = await refine_spur_closures(
        _source(),
        context=_context(
            _Backend(
                alternatives=(_path((D, X, B), (50, 51)),),
                routes={},
                fail_routes=True,
            )
        ),
        result_factory=RouteResultFactory(),
    )
    assert reconstruction_failure.diagnostics.connector_routes_succeeded == 1
    assert reconstruction_failure.diagnostics.reconstruction_attempts == 1
    assert reconstruction_failure.diagnostics.reconstruction_failures == 1
    assert reconstruction_failure.diagnostics.accepted_repair_drafts == 0


@pytest.mark.asyncio
async def test_exact_profile_and_trivial_rejections_have_separate_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    exact_inside_return = RepairAnchor(
        id="exact-return",
        coordinate=C,
        route_progress=0.50,
        kind="exact",
    )
    exact_result = await refine_spur_closures(
        replace(
            source,
            anchors=(
                source.anchors[0],
                exact_inside_return,
                source.anchors[-1],
            ),
        ),
        context=_context(_Backend(alternatives=(), routes={})),
        result_factory=RouteResultFactory(),
    )
    assert exact_result.diagnostics.rejected_exact_constraints == 1
    assert exact_result.diagnostics.spurs_considered == 0

    backend_routes = {
        (A.lat, A.lon, D.lat, D.lon): _path((A, B, C, D), (10, 20, 30)),
        (B.lat, B.lon, E.lat, E.lon): _path((B, E), (40,)),
    }
    trivial_result = await refine_spur_closures(
        source,
        context=_context(
            _Backend(
                alternatives=(
                    _path(
                        (D, X, D, B),
                        (50, 50, 51),
                        edge_distance_m=200.0,
                    ),
                ),
                routes=backend_routes,
            )
        ),
        result_factory=RouteResultFactory(),
    )
    assert trivial_result.diagnostics.rejected_trivial_improvement == 1
    assert trivial_result.diagnostics.accepted_repair_drafts == 0

    source_route = source.route

    def severe_only_for_repair(
        route: RouteResult,
    ) -> tuple[float, dict[str, float], bool]:
        return 0.0, {}, route is not source_route

    monkeypatch.setattr(
        spur_closure_module,
        "profile_quality_components",
        severe_only_for_repair,
    )
    profile_result = await refine_spur_closures(
        source,
        context=_context(
            _Backend(
                alternatives=(_path((D, X, B), (50, 51)),),
                routes=backend_routes,
            )
        ),
        result_factory=RouteResultFactory(),
    )
    assert profile_result.diagnostics.rejected_profile_incompatibility == 1
    assert profile_result.diagnostics.accepted_repair_drafts == 0


def test_settings_reject_unbounded_connector_search() -> None:
    with pytest.raises(ValueError, match="at most three"):
        SpurClosureSettings(maximum_connector_alternatives=4)


@pytest.mark.asyncio
async def test_auto_tour_planner_evaluates_repair_and_retains_source_candidate() -> (
    None
):
    _source_value, source_path = _source_route()
    backend = _Backend(
        alternatives=(
            _path((D, C, B), (30, 20)),
            _path((D, X, B), (50, 51)),
        ),
        routes={
            (A.lat, A.lon, E.lat, E.lon): source_path,
            (A.lat, A.lon, D.lat, D.lon): _path((A, B, C, D), (10, 20, 30)),
            (B.lat, B.lon, E.lat, E.lon): _path((B, E), (40,)),
        },
    )
    request = PLAN_REQUEST_ADAPTER.validate_python(
        {
            "schema_version": 1,
            "kind": "auto_tour",
            "name": "Auto spur integration",
            "topology": "point_to_point",
            "start": A.model_dump(),
            "end": E.model_dump(),
            "routing_profile": "hike",
            "candidate_count": 5,
            "seed": 1,
            "distance_objective": {
                "target_m": 1_000,
                "tolerance_m": 500,
                "maximum_m": None,
                "priority": "flexible",
            },
            "preferences": {
                "nature": "off",
                "path_selection": "shortest",
                "scenic": "off",
                "drinking_water": "off",
                "loop_geometry": "off",
                "direction": "any",
            },
            "hard_waypoints": [],
            "requested_stops": [],
            "preferred_discovered_poi_ids": [],
            "free_poi_spur_physical_m": 200,
        }
    )
    assert isinstance(request, AutoTourPlanRequest)

    result = await AutoTourPlanner(
        AutoTourService(
            cast(AutoTourRoutingBackend, backend),
            RouteResultFactory(),
        )
    ).generate(request)

    constructions = tuple(
        candidate.diagnostics.details["construction"] for candidate in result.candidates
    )
    assert "point_to_point_direct" in constructions
    assert "spur_closure_repair" in constructions
    assert result.candidates[0].diagnostics.repeated_distance_m == 0
    assert result.search_diagnostics.budget.phases["spur_repair"].used == 4
    repair_summary = result.search_diagnostics.details["spur_repair"]
    assert isinstance(repair_summary, dict)
    assert repair_summary["accepted_repair_drafts"] == 1
    assert repair_summary["repair_candidates_submitted_to_portfolio"] == 1
    assert repair_summary["published_repair_candidates"] == 1
    assert repair_summary["portfolio_excluded_repair_candidates"] == 0
    assert (
        result.search_diagnostics.cache.backend_call_count
        == result.search_diagnostics.cache.miss_count
    )


@pytest.mark.asyncio
async def test_waypoint_planner_evaluates_repair_and_retains_source_candidate() -> None:
    source_route, source_path = _source_route()
    del source_route
    source_path = RoutedPath(
        distance_m=source_path.distance_m,
        duration_ms=source_path.duration_ms,
        ascend_m=source_path.ascend_m,
        descend_m=source_path.descend_m,
        geometry=source_path.geometry,
        snapped_points=(
            (A.lon, A.lat),
            (D.lon, D.lat),
            (E.lon, E.lat),
        ),
        details=source_path.details,
    )
    same_corridor = _path((D, C, B), (30, 20))
    clean_exit = _path((D, X, B), (50, 51))
    backend = _Backend(
        alternatives=(same_corridor, clean_exit),
        routes={
            (A.lat, A.lon, E.lat, E.lon): source_path,
            (A.lat, A.lon, D.lat, D.lon): _path((A, B, C, D), (10, 20, 30)),
            (B.lat, B.lon, E.lat, E.lon): _path((B, E), (40,)),
        },
    )
    request = PLAN_REQUEST_ADAPTER.validate_python(
        {
            "schema_version": 1,
            "kind": "waypoint_route",
            "name": "Spur integration",
            "topology": "point_to_point",
            "start": A.model_dump(),
            "end": E.model_dump(),
            "routing_profile": "hike",
            "candidate_count": 5,
            "seed": 1,
            "distance_objective": {
                "target_m": 1_000,
                "tolerance_m": 500,
                "maximum_m": None,
                "priority": "flexible",
            },
            "preferences": {
                "nature": "off",
                "path_selection": "shortest",
                "loop_geometry": "off",
            },
            "waypoints": [
                {
                    "id": "turnaround",
                    "name": "Turnaround",
                    "coordinate": D.model_dump(),
                    "constraint_strength": "exact",
                }
            ],
            "waypoint_order": "fixed",
        }
    )
    assert isinstance(request, WaypointPlanRequest)

    result = await WaypointPlanner(
        cast(AutoTourRoutingBackend, backend),
        RouteResultFactory(),
        max_evaluations=1,
    ).generate(request)

    constructions = tuple(
        candidate.diagnostics.details["construction"] for candidate in result.candidates
    )
    assert "fixed_control" in constructions
    assert "spur_closure_repair" in constructions
    repaired = next(
        candidate
        for candidate in result.candidates
        if candidate.diagnostics.details["construction"] == "spur_closure_repair"
    )
    assert repaired.diagnostics.repeated_distance_m == 0
    assert repaired.diagnostics.details["source_candidate_id"]
    assert "inbound_edge_ids" not in repaired.diagnostics.details
    exact_anchors = tuple(
        anchor
        for anchor in repaired.traversal.anchors
        if anchor.kind == "exact_waypoint"
    )
    assert len(exact_anchors) == 1
    assert exact_anchors[0].routed_coordinate.lon == pytest.approx(D.lon)
    assert exact_anchors[0].routed_coordinate.lat == pytest.approx(D.lat)
    assert result.search_diagnostics.budget.phases["spur_repair"].used == 4
    repair_summary = result.search_diagnostics.details["spur_repair"]
    assert isinstance(repair_summary, dict)
    assert repair_summary["accepted_repair_drafts"] == 1
    assert repair_summary["repair_candidates_submitted_to_portfolio"] == 1
    assert repair_summary["published_repair_candidates"] == 1
    assert repair_summary["portfolio_excluded_repair_candidates"] == 0
    root = ElementTree.fromstring(write_plan_gpx(repaired))
    namespace = {"g": "http://www.topografix.com/GPX/1/1"}
    assert root.findall("g:rte", namespace) == []
    assert len(root.findall("g:trk/g:trkseg", namespace)) == 1
    assert root.findall("g:wpt", namespace) == []

    reversed_result = await ReversePlanner(
        cast(AutoTourRoutingBackend, _ReverseBackend()),
        RouteResultFactory(),
    ).reverse(
        ReversePlanRequest(
            schema_version=1,
            source_request=request,
            candidate=repaired,
        )
    )
    reversed_candidate = reversed_result.result.candidates[0]
    assert reversed_candidate.diagnostics.details["construction"] == "reversed_route"
    assert "targeted_spur_id" not in reversed_candidate.diagnostics.details
    assert reversed_candidate.route.geometry[0] == (E.lon, E.lat)
    assert reversed_candidate.route.geometry[-1] == (A.lon, A.lat)


@pytest.mark.asyncio
async def test_request_diagnostics_exist_when_no_repair_is_accepted() -> None:
    backend = _Backend(
        alternatives=(),
        routes={
            (A.lat, A.lon, E.lat, E.lon): _path((A, E), (40,)),
        },
    )
    request = PLAN_REQUEST_ADAPTER.validate_python(
        {
            "schema_version": 1,
            "kind": "waypoint_route",
            "name": "No spur",
            "topology": "point_to_point",
            "start": A.model_dump(),
            "end": E.model_dump(),
            "routing_profile": "hike",
            "candidate_count": 3,
            "seed": 1,
            "distance_objective": {
                "target_m": 1_000,
                "tolerance_m": 1_000,
                "maximum_m": None,
                "priority": "flexible",
            },
            "preferences": {
                "nature": "off",
                "path_selection": "shortest",
                "loop_geometry": "off",
            },
            "waypoints": [],
            "waypoint_order": "fixed",
        }
    )
    assert isinstance(request, WaypointPlanRequest)

    result = await WaypointPlanner(
        cast(AutoTourRoutingBackend, backend),
        RouteResultFactory(),
        max_evaluations=1,
    ).generate(request)

    repair_summary = result.search_diagnostics.details["spur_repair"]
    assert isinstance(repair_summary, dict)
    assert repair_summary["source_candidates_considered"] == 1
    assert repair_summary["spurs_considered"] == 0
    assert repair_summary["accepted_repair_drafts"] == 0
    assert repair_summary["repair_candidates_submitted_to_portfolio"] == 0
    assert repair_summary["published_repair_candidates"] == 0
