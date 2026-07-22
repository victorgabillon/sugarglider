"""Canonical models, profiles, budgets, cache, evaluation, and portfolio."""

from typing import cast

import pytest
from pydantic import ValidationError

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.planning.auto_tour.ranking import canonical_auto_tour_key
from sugarglider.planning.budget import SearchBudget, SearchPhase
from sugarglider.planning.cache import RouteCacheKey, RouteCallCache
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.evaluator import CandidateEvaluator
from sugarglider.planning.models import (
    PLAN_REQUEST_ADAPTER,
    PlanRequestBase,
    WaypointPlanRequest,
)
from sugarglider.planning.portfolio import build_portfolio
from sugarglider.planning.profiles import RoutingProfileId, routing_profile
from sugarglider.planning.result import (
    DroppedPlanStop,
    PlanCandidate,
    PlanCandidateDiagnostics,
    PlanScore,
    SelectedPlanStop,
)
from sugarglider.planning.routing_gateway import CachedRoutingGateway
from sugarglider.planning.validation import (
    CandidateEvaluationError,
    validate_search_candidate,
)
from sugarglider.planning.waypoint.service import WaypointPlanner
from sugarglider.pois.models import PoiApproachCandidate
from sugarglider.routing.backend import AutoTourRoutingBackend, RoutedPath
from sugarglider.routing.result import RouteResultFactory


class _CountingResultFactory(RouteResultFactory):
    def __init__(self, route: RouteResult) -> None:
        super().__init__()
        self.route = route
        self.calls = 0

    def create(
        self,
        *,
        name: str,
        path: RoutedPath,
        input_point_count: int,
        routing_profile: RoutingProfileId,
    ) -> RouteResult:
        del name, path, input_point_count, routing_profile
        self.calls += 1
        return self.route


class _DraftScorer:
    def score(self, *, request: PlanRequestBase, draft: CandidateDraft) -> PlanScore:
        del request, draft
        return PlanScore(total=0)


class _GatewayBackend:
    def __init__(self, path: RoutedPath, *, fail: bool = False) -> None:
        self.path = path
        self.fail = fail
        self.route_calls = 0
        self.alternative_calls = 0
        self.round_trip_calls = 0

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        del points, profile, pass_through
        self.route_calls += 1
        if self.fail:
            raise ValueError("deterministic failure")
        return self.path

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
        del start, end, profile, max_paths, max_weight_factor, max_share_factor
        self.alternative_calls += 1
        return (self.path,)

    async def round_trip(
        self,
        start: Coordinate,
        distance_m: float,
        seed: int,
        profile: str = "hike",
        *,
        heading_degrees: float | None = None,
    ) -> RoutedPath:
        del start, distance_m, seed, profile, heading_degrees
        self.round_trip_calls += 1
        return self.path


def _routed_path(route: RouteResult) -> RoutedPath:
    return RoutedPath(
        distance_m=route.summary.distance_m,
        duration_ms=route.summary.duration_ms,
        ascend_m=route.summary.ascend_m,
        descend_m=route.summary.descend_m,
        geometry=route.geometry,
        snapped_points=route.snapped_points,
        details=route.path_details,
    )


def _common() -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "Plan",
        "topology": "loop",
        "start": {"lat": 48.87, "lon": 2.09},
        "end": None,
        "routing_profile": "hike",
        "candidate_count": 3,
        "seed": 7,
        "distance_objective": {
            "target_m": 10_000,
            "tolerance_m": 1_000,
            "maximum_m": None,
            "priority": "flexible",
        },
    }


def _auto_preferences() -> dict[str, str]:
    return {
        "scenic": "prefer",
        "drinking_water": "prefer",
        "nature": "prefer",
        "loop_geometry": "prefer",
        "direction": "any",
        "path_selection": "low_overlap",
    }


def _waypoint_preferences() -> dict[str, str]:
    return {
        "nature": "prefer",
        "loop_geometry": "off",
        "path_selection": "low_overlap",
    }


def test_discriminated_models_round_trip_and_forbid_obsolete_fields() -> None:
    document = {
        **_common(),
        "kind": "auto_tour",
        "preferences": _auto_preferences(),
        "hard_waypoints": [],
        "requested_stops": [],
        "preferred_discovered_poi_ids": [],
        "free_poi_spur_physical_m": 200,
    }
    request = PLAN_REQUEST_ADAPTER.validate_python(document)
    assert (
        PLAN_REQUEST_ADAPTER.validate_python(request.model_dump(mode="json")) == request
    )
    document["requested_places"] = []
    with pytest.raises(ValidationError, match="requested_places"):
        PLAN_REQUEST_ADAPTER.validate_python(document)


@pytest.mark.parametrize(
    ("topology", "end"),
    [("loop", {"lat": 48.88, "lon": 2.1}), ("point_to_point", None)],
)
def test_endpoint_rules_are_explicit(topology: str, end: object) -> None:
    document = {
        **_common(),
        "kind": "waypoint_route",
        "topology": topology,
        "end": end,
        "preferences": _waypoint_preferences(),
        "waypoints": [{"lat": 48.89, "lon": 2.11}],
        "waypoint_order": "fixed",
    }
    with pytest.raises(ValidationError):
        PLAN_REQUEST_ADAPTER.validate_python(document)


def test_point_to_point_waypoint_route_allows_no_interior_waypoints() -> None:
    request = PLAN_REQUEST_ADAPTER.validate_python(
        {
            **_common(),
            "kind": "waypoint_route",
            "topology": "point_to_point",
            "end": {"lat": 48.88, "lon": 2.10},
            "preferences": {
                **_waypoint_preferences(),
                "path_selection": "shortest",
            },
            "waypoints": [],
            "waypoint_order": "fixed",
            "distance_objective": {
                "target_m": 2_000,
                "tolerance_m": 1_000,
                "maximum_m": None,
                "priority": "flexible",
            },
        }
    )
    assert isinstance(request, WaypointPlanRequest)
    assert request.waypoints == ()


def test_loop_waypoint_route_still_requires_an_interior_waypoint() -> None:
    with pytest.raises(ValidationError, match="interior waypoint"):
        PLAN_REQUEST_ADAPTER.validate_python(
            {
                **_common(),
                "kind": "waypoint_route",
                "preferences": _waypoint_preferences(),
                "waypoints": [],
                "waypoint_order": "fixed",
            }
        )


def test_waypoint_route_rejects_auto_tour_preferences() -> None:
    with pytest.raises(ValidationError, match="scenic"):
        PLAN_REQUEST_ADAPTER.validate_python(
            {
                **_common(),
                "kind": "waypoint_route",
                "preferences": {**_waypoint_preferences(), "scenic": "prefer"},
                "waypoints": [{"lat": 48.89, "lon": 2.11}],
                "waypoint_order": "fixed",
            }
        )


def test_profile_is_the_only_graphhopper_mapping() -> None:
    profile = routing_profile("hike")
    assert profile.id == "hike"
    assert profile.graphhopper_profile == "hike"
    assert profile.activity_kind == "walking"
    assert "nature" in profile.allowed_quality_metrics


def test_typed_budget_has_exact_phase_and_global_accounting() -> None:
    limits = {phase: 0 for phase in SearchPhase}
    limits[SearchPhase.SKELETON] = 2
    limits[SearchPhase.REPAIR] = 1
    budget = SearchBudget(limits, total_limit=2)
    assert budget.reserve(SearchPhase.SKELETON)
    assert budget.reserve(SearchPhase.REPAIR)
    assert not budget.reserve(SearchPhase.SKELETON)
    assert budget.used(SearchPhase.REPAIR) == 1
    assert budget.global_exhausted
    assert budget.diagnostics().total_used == 2


def test_unified_cache_counts_hits_misses_and_cached_failures() -> None:
    key = RouteCacheKey.for_route(
        profile_id="hike",
        points=(),
        pass_through=True,
    )
    cache: RouteCallCache[str] = RouteCallCache()
    assert cache.lookup(key) == (False, None)
    cache.record_backend_call()
    cache.store(key, None)
    assert cache.peek(key) is None
    assert cache.lookup(key) == (True, None)
    assert cache.diagnostics().model_dump() == {
        "lookup_count": 2,
        "hit_count": 1,
        "miss_count": 1,
        "entry_count": 1,
        "successful_entry_count": 0,
        "failed_entry_count": 1,
        "backend_call_count": 1,
        "pre_backend_rejection_count": 0,
    }


@pytest.mark.asyncio
async def test_gateway_cache_hit_does_not_consume_budget(
    route_result: RouteResult,
) -> None:
    limits = {phase: 0 for phase in SearchPhase}
    limits[SearchPhase.CONTROL] = 2
    budget = SearchBudget(limits, total_limit=2)
    backend = _GatewayBackend(_routed_path(route_result))
    gateway = CachedRoutingGateway(cast(AutoTourRoutingBackend, backend), budget)
    points = (Coordinate(lat=48.87, lon=2.09), Coordinate(lat=48.88, lon=2.1))
    assert await gateway.route(points, "hike") is backend.path
    assert await gateway.route(points, "hike") is backend.path
    assert budget.total_used == 1
    assert backend.route_calls == 1
    assert gateway.cache_snapshot().model_dump() == {
        "lookup_count": 2,
        "hit_count": 1,
        "miss_count": 1,
        "entry_count": 1,
        "successful_entry_count": 1,
        "failed_entry_count": 0,
        "backend_call_count": 1,
        "pre_backend_rejection_count": 0,
    }


@pytest.mark.asyncio
async def test_gateway_caches_deterministic_failures(route_result: RouteResult) -> None:
    limits = {phase: 0 for phase in SearchPhase}
    limits[SearchPhase.CONTROL] = 2
    budget = SearchBudget(limits, total_limit=2)
    backend = _GatewayBackend(_routed_path(route_result), fail=True)
    context = PlanningSearchContext.create(
        backend=cast(AutoTourRoutingBackend, backend), budget=budget
    )
    points = (Coordinate(lat=48.87, lon=2.09), Coordinate(lat=48.88, lon=2.1))
    with pytest.raises(ValueError, match="deterministic failure"):
        await context.routes.route(points, "hike")
    with pytest.raises(ValueError, match="deterministic failure"):
        await context.routes.route(points, "hike")
    assert budget.total_used == 1
    assert backend.route_calls == 1
    snapshot = context.routes.cache_snapshot()
    assert snapshot.failed_entry_count == 1
    assert snapshot.backend_call_count == snapshot.miss_count == 1


@pytest.mark.asyncio
async def test_gateway_caches_alternatives_and_round_trip_detours(
    route_result: RouteResult,
) -> None:
    limits = {phase: 0 for phase in SearchPhase}
    limits[SearchPhase.ALTERNATIVE_LEG] = 2
    limits[SearchPhase.SKELETON] = 2
    budget = SearchBudget(limits, total_limit=4)
    backend = _GatewayBackend(_routed_path(route_result))
    gateway = CachedRoutingGateway(cast(AutoTourRoutingBackend, backend), budget)
    start = Coordinate(lat=48.87, lon=2.09)
    end = Coordinate(lat=48.88, lon=2.1)
    first = await gateway.alternative_routes(start, end, "hike")
    second = await gateway.alternative_routes(start, end, "hike")
    assert first == second
    first_detour = await gateway.round_trip(
        start, 5_000, 7, "hike", phase=SearchPhase.SKELETON
    )
    second_detour = await gateway.round_trip(
        start, 5_000, 7, "hike", phase=SearchPhase.SKELETON
    )
    assert first_detour == second_detour
    assert backend.alternative_calls == backend.round_trip_calls == 1
    assert budget.total_used == 2
    snapshot = gateway.cache_snapshot()
    assert snapshot.hit_count == snapshot.miss_count == 2
    assert snapshot.entry_count == snapshot.backend_call_count == 2


@pytest.mark.asyncio
async def test_route_cache_key_distinguishes_behavior_options(
    route_result: RouteResult,
) -> None:
    limits = {phase: 0 for phase in SearchPhase}
    limits[SearchPhase.CONTROL] = 4
    budget = SearchBudget(limits, total_limit=4)
    backend = _GatewayBackend(_routed_path(route_result))
    gateway = CachedRoutingGateway(cast(AutoTourRoutingBackend, backend), budget)
    points = (Coordinate(lat=48.87, lon=2.09), Coordinate(lat=48.88, lon=2.1))
    await gateway.route(points, "hike", pass_through=False)
    await gateway.route(points, "hike", pass_through=True)
    await gateway.route(points, "hike", custom_options=(("avoid", "steps"),))
    await gateway.route(
        points,
        "hike",
        topology_options=(("topology", "point_to_point"),),
    )
    assert backend.route_calls == 4
    snapshot = gateway.cache_snapshot()
    assert snapshot.miss_count == snapshot.entry_count == 4


@pytest.mark.asyncio
async def test_native_waypoint_direct_route_has_truthful_diagnostics(
    route_result: RouteResult,
) -> None:
    request = PLAN_REQUEST_ADAPTER.validate_python(
        {
            **_common(),
            "kind": "waypoint_route",
            "name": "Direct route",
            "topology": "point_to_point",
            "start": {"lat": 48.871389, "lon": 2.096667},
            "end": {"lat": 48.871454, "lon": 2.124421},
            "preferences": {
                **_waypoint_preferences(),
                "path_selection": "shortest",
            },
            "waypoints": [],
            "waypoint_order": "fixed",
            "distance_objective": {
                "target_m": 2_000,
                "tolerance_m": 1_000,
                "maximum_m": None,
                "priority": "flexible",
            },
        }
    )
    assert isinstance(request, WaypointPlanRequest)
    backend = _GatewayBackend(_routed_path(route_result))
    result = await WaypointPlanner(
        cast(AutoTourRoutingBackend, backend), RouteResultFactory()
    ).generate(request)
    assert len(result.candidates) == 1
    assert result.search_diagnostics.budget.total_used == 1
    cache = result.search_diagnostics.cache
    assert cache.entry_count == cache.miss_count == cache.backend_call_count == 1
    assert cache.lookup_count == 1
    details = result.search_diagnostics.details
    assert details["order_proposals_generated"] == 0
    assert details["candidate_drafts_created"] == 1
    assert details["candidates_evaluated"] == 1
    assert details["portfolio_count"] == 1


def _candidate(
    route: RouteResult,
    candidate_id: str,
    *,
    error: float,
    stops: int,
    backtracking: float,
) -> PlanCandidate:
    return PlanCandidate(
        id=candidate_id,
        routing_profile=route.routing_profile,
        rank=1,
        roles=(),
        route=route,
        score=PlanScore(total=error),
        diagnostics=PlanCandidateDiagnostics(
            safety_eligible=True,
            target_error_m=error,
            within_tolerance=error < 500,
            requested_stop_count=stops,
            immediate_backtracking_m=backtracking,
            repeated_distance_m=backtracking,
        ),
    )


def test_shared_portfolio_assigns_distinct_multi_roles(
    route_result: RouteResult,
) -> None:
    candidates = (
        _candidate(route_result, "balanced", error=300, stops=1, backtracking=100),
        _candidate(route_result, "coverage", error=700, stops=4, backtracking=200),
        _candidate(route_result, "smooth", error=600, stops=2, backtracking=0),
        _candidate(route_result, "distance", error=50, stops=0, backtracking=300),
    )
    portfolio = build_portfolio(candidates, limit=4)
    roles = {role: candidate.id for candidate in portfolio for role in candidate.roles}
    assert roles == {
        "harmonious": "distance",
        "maximum_requested_coverage": "coverage",
        "smooth_low_detour": "smooth",
        "distance_focused": "distance",
    }
    assert tuple(candidate.rank for candidate in portfolio) == (1, 2, 3, 4)


def test_flexible_auto_tour_publication_preserves_requested_coverage(
    route_result: RouteResult,
) -> None:
    direct = _candidate(route_result, "direct", error=50, stops=0, backtracking=0)
    coverage = _candidate(
        route_result, "coverage", error=1_500, stops=12, backtracking=100
    )
    portfolio = build_portfolio(
        (direct, coverage),
        limit=2,
        ranking_key=lambda candidate: canonical_auto_tour_key(candidate, "flexible"),
    )
    assert portfolio[0].id == "coverage"
    assert "harmonious" in portfolio[0].roles


def _offset_from_route_start(route: RouteResult, x_m: float, y_m: float) -> Coordinate:
    start_lon, start_lat = route.geometry[0]
    projection = LocalMetricProjection(start_lat)
    origin = projection.project_position((start_lon, start_lat))
    lon, lat = projection.unproject_position((origin[0] + x_m, origin[1] + y_m))
    return Coordinate(lat=lat, lon=lon)


def test_hard_waypoint_566_m_from_route_is_rejected(
    route_result: RouteResult,
) -> None:
    waypoint = _offset_from_route_start(route_result, -566, 0)
    request = PLAN_REQUEST_ADAPTER.validate_python(
        {
            **_common(),
            "kind": "waypoint_route",
            "topology": "point_to_point",
            "start": {
                "lat": route_result.geometry[0][1],
                "lon": route_result.geometry[0][0],
            },
            "end": {
                "lat": route_result.geometry[-1][1],
                "lon": route_result.geometry[-1][0],
            },
            "preferences": _waypoint_preferences(),
            "waypoints": [waypoint.model_dump(mode="json")],
            "waypoint_order": "fixed",
        }
    )
    candidate = _candidate(
        route_result, "missed-waypoint", error=0, stops=0, backtracking=0
    )
    with pytest.raises(CandidateEvaluationError, match="required waypoint"):
        validate_search_candidate(request, candidate)


def test_inaccessible_semantic_stop_can_be_dropped_or_use_an_override(
    route_result: RouteResult,
) -> None:
    semantic = _offset_from_route_start(route_result, -566, 0)
    request = PLAN_REQUEST_ADAPTER.validate_python(
        {
            **_common(),
            "kind": "auto_tour",
            "topology": "point_to_point",
            "start": {
                "lat": route_result.geometry[0][1],
                "lon": route_result.geometry[0][0],
            },
            "end": {
                "lat": route_result.geometry[-1][1],
                "lon": route_result.geometry[-1][0],
            },
            "preferences": {**_auto_preferences(), "loop_geometry": "off"},
            "hard_waypoints": [],
            "requested_stops": [
                {
                    "id": "castle",
                    "name": "Castle",
                    "semantic_coordinate": semantic.model_dump(mode="json"),
                    "importance": "must_visit",
                }
            ],
        }
    )
    base = _candidate(route_result, "semantic-stop", error=0, stops=0, backtracking=0)
    dropped = base.model_copy(
        update={
            "dropped_stops": (
                DroppedPlanStop(
                    id="castle",
                    name="Castle",
                    semantic_coordinate=semantic,
                    category="castle",
                    importance="must_visit",
                    selection_origin="requested",
                    reason="no_accessible_approach",
                ),
            )
        }
    )
    assert validate_search_candidate(request, dropped) == dropped

    route_start = Coordinate(
        lat=route_result.geometry[0][1], lon=route_result.geometry[0][0]
    )
    approach = PoiApproachCandidate(
        id="castle/user-override",
        coordinate=route_start,
        kind="user_override",
        source="user_override",
        access="unknown",
        semantic_distance_m=566,
        arrival_tolerance_m=20,
    )
    selected = base.model_copy(
        update={
            "selected_stops": (
                SelectedPlanStop(
                    id="castle",
                    name="Castle",
                    semantic_coordinate=semantic,
                    category="castle",
                    importance="must_visit",
                    selection_origin="requested",
                    selection_method="deliberate_insertion",
                    resolved_approach=approach,
                    route_progress=0,
                    route_to_approach_m=0,
                ),
            ),
            "diagnostics": base.diagnostics.model_copy(
                update={"requested_stop_count": 1}
            ),
        }
    )
    assert validate_search_candidate(request, selected) == selected


def test_shared_evaluator_enriches_each_complete_draft_once(
    route_result: RouteResult,
) -> None:
    request = PLAN_REQUEST_ADAPTER.validate_python(
        {
            **_common(),
            "kind": "auto_tour",
            "topology": "point_to_point",
            "start": {
                "lat": route_result.geometry[0][1],
                "lon": route_result.geometry[0][0],
            },
            "end": {
                "lat": route_result.geometry[-1][1],
                "lon": route_result.geometry[-1][0],
            },
            "preferences": {**_auto_preferences(), "loop_geometry": "off"},
            "hard_waypoints": [],
            "requested_stops": [],
        }
    )
    routed_path = _routed_path(route_result)
    draft = CandidateDraft(
        route=route_result,
        routed_path=routed_path,
        routing_points=(request.start, request.effective_end),
        topology="point_to_point",
        construction="test_control",
        search_family="auto_tour",
    )
    factory = _CountingResultFactory(route_result)

    CandidateEvaluator(factory).evaluate(
        request=request,
        draft=draft,
        scorer=_DraftScorer(),
    )

    assert factory.calls == 1
