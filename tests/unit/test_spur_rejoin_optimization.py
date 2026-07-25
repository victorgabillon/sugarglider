"""Synthetic downstream-spur closure coverage for the unified optimizer."""

from __future__ import annotations

from typing import cast

import pytest

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.spurs import detect_route_spurs
from sugarglider.domain.models import Coordinate, PathDetailSegment
from sugarglider.planning.budget import SearchBudget, SearchPhase
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.optimization.corridor_avoidance import (
    corridor_avoidance_area,
    guide_candidates,
    inbound_corridor_evidence,
)
from sugarglider.planning.optimization.diagnostics import (
    GlobalOptimizationDiagnostics,
)
from sugarglider.planning.optimization.models import (
    GlobalOptimizationSettings,
    OptimizationAnchor,
    OptimizationSource,
    SpurOptimizationTarget,
    TourOptimizationState,
)
from sugarglider.planning.optimization.optimizer import optimize_tours
from sugarglider.planning.optimization.path_pool import LazyPathPool
from sugarglider.planning.optimization.spur_rejoin import (
    _inbound_overlap,
    downstream_rejoins,
    optimization_targets,
    structural_spur_seeds,
)
from sugarglider.planning.optimization.state import initial_state
from sugarglider.routing.backend import (
    AutoTourRoutingBackend,
    CorridorAvoidanceArea,
    GraphHopperRoutingCapabilities,
    RoutedPath,
)
from sugarglider.routing.errors import RoutingPointError
from sugarglider.routing.result import RouteResultFactory

A = Coordinate(lat=0.0, lon=0.000, name="A")
B = Coordinate(lat=0.0, lon=0.001, name="B")
C = Coordinate(lat=0.0, lon=0.002, name="C")
D = Coordinate(lat=0.0, lon=0.003, name="D")
P = Coordinate(lat=0.001, lon=0.001, name="P")
Q = Coordinate(lat=0.001, lon=0.002, name="Q")
E = Coordinate(lat=0.001, lon=0.003, name="E")
X = Coordinate(lat=0.002, lon=0.003, name="X")


def _path(
    points: tuple[Coordinate, ...],
    edge_ids: tuple[int, ...],
    *,
    snapped: tuple[Coordinate, ...] | None = None,
    edge_distance_m: float = 600.0,
) -> RoutedPath:
    geometry = tuple((point.lon, point.lat) for point in points)
    return RoutedPath(
        distance_m=edge_distance_m * len(edge_ids),
        duration_ms=1_000 * len(edge_ids),
        ascend_m=None,
        descend_m=None,
        geometry=geometry,
        snapped_points=tuple(
            (point.lon, point.lat) for point in (snapped or (points[0], points[-1]))
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


def _anchor(
    anchor_id: str, coordinate: Coordinate, progress: float, *, window: int = 0
) -> OptimizationAnchor:
    return OptimizationAnchor(
        id=anchor_id,
        name=coordinate.name or anchor_id,
        coordinate=coordinate,
        semantic_coordinate=coordinate,
        kind="exact",
        source_progress=progress,
        exact_window=window,
    )


def _source(
    *,
    anchors: tuple[OptimizationAnchor, ...] | None = None,
) -> OptimizationSource:
    path = _path(
        (A, B, C, D, C, B, P, Q, E),
        (10, 20, 30, 30, 20, 40, 41, 42),
        snapped=(A, E),
    )
    route = RouteResultFactory().create(
        name="Synthetic excursion",
        path=path,
        input_point_count=2,
        routing_profile="hike",
    )
    spurs = detect_route_spurs(route, topology="point_to_point")
    route = route.model_copy(
        update={"analysis": route.analysis.model_copy(update={"spurs": spurs})}
    )
    source_anchors = anchors or (
        _anchor("start", A, 0.0),
        _anchor("end", E, 1.0, window=1),
    )
    return OptimizationSource(
        source_candidate_id="source",
        route=route,
        routed_path=path,
        anchors=source_anchors,
        topology="point_to_point",
        routing_profile="hike",
        target_distance_m=path.distance_m,
        tolerance_m=10_000,
        distance_priority="flexible",
        maximum_distance_m=None,
        reached_requested_ids=frozenset(),
        approximated_requested_ids=frozenset(),
        dropped_requested_ids=frozenset(),
    )


class _ConnectorBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[float, float]] = []

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
        del profile, max_paths, max_weight_factor, max_share_factor
        self.calls.append((end.lat, end.lon))
        if (start.lat, start.lon) != (D.lat, D.lon):
            return ()
        if (end.lat, end.lon) == (P.lat, P.lon):
            return (_path((D, C, B, P), (30, 20, 40)),)
        if (end.lat, end.lon) == (Q.lat, Q.lon):
            return (_path((D, X, Q), (80, 81)),)
        return ()


class _AvoidanceBackend(_ConnectorBackend):
    def __init__(self) -> None:
        super().__init__()
        self.avoidance_areas: list[CorridorAvoidanceArea] = []

    @property
    def routing_capabilities(self) -> GraphHopperRoutingCapabilities:
        return GraphHopperRoutingCapabilities(True, True, True, False)

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
        del profile, max_paths, max_weight_factor, max_share_factor
        self.calls.append((end.lat, end.lon))
        if (start.lat, start.lon) != (D.lat, D.lon):
            return ()
        if (end.lat, end.lon) == (P.lat, P.lon):
            return (_path((D, C, B, P), (30, 20, 40)),)
        if (end.lat, end.lon) == (Q.lat, Q.lon):
            return (_path((D, C, B, P, Q), (30, 20, 40, 41)),)
        return ()

    async def alternative_routes_avoiding_corridor(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: str,
        area: CorridorAvoidanceArea,
        *,
        priority_multiplier: float,
        max_paths: int,
        max_weight_factor: float,
        max_share_factor: float,
    ) -> tuple[RoutedPath, ...]:
        del (
            profile,
            priority_multiplier,
            max_paths,
            max_weight_factor,
            max_share_factor,
        )
        self.avoidance_areas.append(area)
        if (start.lat, start.lon) != (D.lat, D.lon):
            return ()
        return (_path((D, X, end), (80, 81)),)


class _GuideBackend(_AvoidanceBackend):
    def __init__(self) -> None:
        super().__init__()
        self.guide_calls = 0

    @property
    def routing_capabilities(self) -> GraphHopperRoutingCapabilities:
        return GraphHopperRoutingCapabilities(False, False, False, True)

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        del profile
        assert pass_through and len(points) == 3
        self.guide_calls += 1
        if self.guide_calls == 1:
            raise RoutingPointError("synthetic guide side is unreachable")
        return _path(points, (80, 81), snapped=points)


class _FailingAvoidanceBackend(_AvoidanceBackend):
    async def alternative_routes_avoiding_corridor(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: str,
        area: CorridorAvoidanceArea,
        *,
        priority_multiplier: float,
        max_paths: int,
        max_weight_factor: float,
        max_share_factor: float,
    ) -> tuple[RoutedPath, ...]:
        del (
            start,
            end,
            profile,
            area,
            priority_multiplier,
            max_paths,
            max_weight_factor,
            max_share_factor,
        )
        raise RoutingPointError("synthetic custom-model failure")


class _FarSnapGuideBackend(_GuideBackend):
    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        del profile
        assert pass_through and len(points) == 3
        self.guide_calls += 1
        far = points[1].model_copy(update={"lat": points[1].lat + 0.01})
        return _path(points, (80, 81), snapped=(points[0], far, points[2]))


class _EscalationBackend(_AvoidanceBackend):
    def __init__(self) -> None:
        super().__init__()
        self.guide_calls = 0

    @property
    def routing_capabilities(self) -> GraphHopperRoutingCapabilities:
        return GraphHopperRoutingCapabilities(True, True, True, True)

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
        del profile, max_paths, max_weight_factor, max_share_factor
        self.calls.append((end.lat, end.lon))
        return (_path((start, X, end), (80, 81)),)

    async def alternative_routes_avoiding_corridor(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: str,
        area: CorridorAvoidanceArea,
        *,
        priority_multiplier: float,
        max_paths: int,
        max_weight_factor: float,
        max_share_factor: float,
    ) -> tuple[RoutedPath, ...]:
        del (
            profile,
            priority_multiplier,
            max_paths,
            max_weight_factor,
            max_share_factor,
        )
        self.avoidance_areas.append(area)
        return (_path((start, X, end), (82, 83)),)

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        del profile
        assert pass_through and len(points) == 3
        self.guide_calls += 1
        return _path(points, (84, 85), snapped=points)


class _UnrouteableGuideBackend(_GuideBackend):
    def __init__(self) -> None:
        super().__init__()
        self.guide_rejoins: list[tuple[float, float]] = []

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        del profile
        assert pass_through and len(points) == 3
        self.guide_calls += 1
        self.guide_rejoins.append((points[-1].lat, points[-1].lon))
        raise RoutingPointError("synthetic guide is unreachable")


def _context(backend: _ConnectorBackend) -> PlanningSearchContext:
    limits = {phase: 0 for phase in SearchPhase}
    limits[SearchPhase.GLOBAL_OPTIMIZATION] = 64
    return PlanningSearchContext.create(
        backend=cast(AutoTourRoutingBackend, backend),
        budget=SearchBudget(limits, total_limit=64),
    )


def _settings() -> GlobalOptimizationSettings:
    return GlobalOptimizationSettings(
        maximum_iterations=10,
        maximum_no_improvement_iterations=10,
        optimizer_cpu_time_limit_s=2,
        optimizer_total_wall_time_limit_s=2,
    )


def test_downstream_rejoins_are_bounded_deterministic_and_stop_at_exact_boundary() -> (
    None
):
    source = _source()
    target = optimization_targets(source, _settings())[0]

    first = downstream_rejoins(source, target, _settings())
    second = downstream_rejoins(source, target, _settings())

    assert first == second
    assert len(first) >= 3
    assert len(first) <= 8
    assert all(value.source_progress > target.end_progress for value in first)
    assert first[-1].coordinate == E

    bounded = _source(
        anchors=(
            _anchor("start", A, 0.0),
            _anchor("boundary", Q, 7 / 8, window=1),
            _anchor("end", E, 1.0, window=2),
        )
    )
    bounded_target = optimization_targets(bounded, _settings())[0]
    bounded_rejoins = downstream_rejoins(bounded, bounded_target, _settings())
    assert bounded_rejoins
    assert all(value.source_progress <= 7 / 8 for value in bounded_rejoins)
    assert all(value.coordinate != E for value in bounded_rejoins)


def test_corridor_excludes_allowed_stem_and_bounds_area_and_guides() -> None:
    source = _source()
    settings = _settings()
    target = optimization_targets(source, settings)[0]
    rejoin = downstream_rejoins(source, target, settings)[0]

    evidence = inbound_corridor_evidence(target, settings)
    assert evidence is not None
    assert evidence.allowed_stem_distance_m == 100
    assert evidence.avoid_distance_m == pytest.approx(target.inbound_distance_m - 100)
    assert evidence.avoid_geometry[-1] != (
        target.turnaround_coordinate.lon,
        target.turnaround_coordinate.lat,
    )
    area = corridor_avoidance_area(evidence, rejoin, settings)
    assert area is not None
    assert area.source_distance_m == pytest.approx(evidence.avoid_distance_m)
    assert area.vertex_count <= 80
    guides = guide_candidates(target, rejoin, area, settings)
    assert 1 <= len(guides) <= 4
    assert {strategy for strategy, _coordinate in guides} <= {
        "guide_point_left",
        "guide_point_right",
    }


def test_balanced_guide_fan_retains_both_sides_and_outer_scale() -> None:
    source = _source()
    settings = _settings()
    target = optimization_targets(source, settings)[0]
    rejoin = downstream_rejoins(source, target, settings)[0]

    guides = guide_candidates(target, rejoin, None, settings)

    assert tuple(strategy for strategy, _ in guides) == (
        "guide_point_left",
        "guide_point_right",
        "guide_point_left",
        "guide_point_right",
    )
    projection = LocalMetricProjection(target.turnaround_coordinate.lat)
    start = projection.project_position(
        (target.turnaround_coordinate.lon, target.turnaround_coordinate.lat)
    )
    end = projection.project_position((rejoin.coordinate.lon, rejoin.coordinate.lat))
    delta = (end[0] - start[0], end[1] - start[1])
    length = (delta[0] ** 2 + delta[1] ** 2) ** 0.5
    lateral_offsets = tuple(
        abs(
            delta[0]
            * (projection.project_position((guide.lon, guide.lat))[1] - start[1])
            - delta[1]
            * (projection.project_position((guide.lon, guide.lat))[0] - start[0])
        )
        / length
        for _, guide in guides
    )
    assert lateral_offsets == pytest.approx((150, 150, 600, 600))


def test_first_hundred_metres_of_inbound_overlap_is_not_charged() -> None:
    source = _source()
    settings = _settings()
    target = optimization_targets(source, settings)[0]
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    pool = LazyPathPool(
        context=_context(_ConnectorBackend()),
        profile="hike",
        result_factory=RouteResultFactory(),
        settings=settings,
        diagnostics=diagnostics,
    )
    connector = pool.insert(
        from_anchor=_anchor("turnaround", D, target.turnaround_progress),
        to_anchor=_anchor("rejoin", P, 0.75),
        profile="hike",
        path=_path((D, P), (30,), edge_distance_m=100),
        source_kind="spur_connector",
    )

    overlap = _inbound_overlap(connector, target, settings)

    assert overlap.raw_overlap_m == pytest.approx(100)
    assert overlap.allowed_stem_m == 100
    assert overlap.charged_overlap_m == 0
    assert overlap.overlap_share == 0


@pytest.mark.asyncio
async def test_later_clean_rejoin_replaces_return_interval_and_preserves_anchors() -> (
    None
):
    source = _source()
    backend = _ConnectorBackend()
    context = _context(backend)
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    pool = LazyPathPool(
        context=context,
        profile="hike",
        result_factory=RouteResultFactory(),
        settings=_settings(),
        diagnostics=diagnostics,
    )
    state = await initial_state(source, pool)
    assert state is not None

    seeds = await structural_spur_seeds(
        source,
        state,
        path_pool=pool,
        result_factory=RouteResultFactory(),
        settings=_settings(),
        diagnostics=diagnostics,
    )

    assert seeds, diagnostics.as_dict()["targeted_spurs"][0]
    repaired = seeds[0]
    assert repaired.ordered_anchor_ids == ("start", "end")
    assert repaired.complete_path.geometry == (
        (A.lon, A.lat),
        (B.lon, B.lat),
        (C.lon, C.lat),
        (D.lon, D.lat),
        (X.lon, X.lat),
        (Q.lon, Q.lat),
        (E.lon, E.lat),
    )
    assert len(repaired.applied_spur_repairs) == 1
    assert repaired.applied_spur_repairs[0].source_repeated_distance_m == pytest.approx(
        1_200
    )
    assert repaired.applied_spur_repairs[0].resulting_repeated_distance_m == 0
    assert repaired.applied_spur_repairs[0].improvement_m == pytest.approx(1_200)
    targeted = diagnostics.as_dict()["targeted_spurs"]
    assert targeted[0]["rejoin_positions_generated"] >= 3
    assert targeted[0]["connector_requests"] >= 2
    assert targeted[0]["rejected_inbound_overlap"] == 1
    assert targeted[0]["states_reconstructed"] >= 1
    assert targeted[0]["states_targeted_improvement"] >= 1
    assert "edge_id" not in repr(targeted)


@pytest.mark.asyncio
async def test_custom_model_avoidance_generates_viable_connector_before_guides() -> (
    None
):
    source = _source()
    backend = _AvoidanceBackend()
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    pool = LazyPathPool(
        context=_context(backend),
        profile="hike",
        result_factory=RouteResultFactory(),
        settings=_settings(),
        diagnostics=diagnostics,
    )
    state = await initial_state(source, pool)
    assert state is not None

    seeds = await structural_spur_seeds(
        source,
        state,
        path_pool=pool,
        result_factory=RouteResultFactory(),
        settings=_settings(),
        diagnostics=diagnostics,
    )

    assert seeds, diagnostics.as_dict()
    assert backend.avoidance_areas
    repaired = seeds[0]
    assert repaired.ordered_anchor_ids == ("start", "end")
    assert repaired.applied_spur_repairs[0].improvement_m == pytest.approx(1_200)
    targeted = diagnostics.as_dict()["targeted_spurs"][0]
    assert targeted["ordinary_rejected_overlap"] >= 1
    assert targeted["avoidance_supported"] is True
    assert targeted["avoidance_requests"] >= 1
    assert targeted["avoidance_paths_returned"] >= 1
    assert targeted["viable_connectors"] >= 1
    assert targeted["guide_route_attempts"] == 0


@pytest.mark.asyncio
async def test_nonmaterial_ordinary_and_avoidance_escalate_to_guides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    backend = _EscalationBackend()
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    pool = LazyPathPool(
        context=_context(backend),
        profile="hike",
        result_factory=RouteResultFactory(),
        settings=_settings(),
        diagnostics=diagnostics,
    )
    state = await initial_state(source, pool)
    assert state is not None

    def resulting_repetition(
        source_value: object,
        proposed_value: object,
        target_value: object,
        result_factory_value: object,
    ) -> tuple[float, float]:
        del source_value, result_factory_value
        proposed = cast(TourOptimizationState, proposed_value)
        target = cast(SpurOptimizationTarget, target_value)
        edge_ids = {
            segment.value
            for segment in proposed.complete_path.details.get("edge_id", ())
        }
        if 84 in edge_ids:
            return 0.0, 0.0
        if 82 in edge_ids:
            return target.repeated_distance_m - 200.0, 1_000.0
        return target.repeated_distance_m - 100.0, 1_100.0

    monkeypatch.setattr(
        "sugarglider.planning.optimization.spur_rejoin._analyze_structural_state",
        resulting_repetition,
    )

    seeds = await structural_spur_seeds(
        source,
        state,
        path_pool=pool,
        result_factory=RouteResultFactory(),
        settings=_settings(),
        diagnostics=diagnostics,
    )

    assert backend.avoidance_areas
    assert backend.guide_calls >= 1
    targeted = diagnostics.as_dict()["targeted_spurs"][0]
    assert targeted["ordinary_overlap_viable_connectors"] >= 1
    assert targeted["ordinary_nonmaterial_states"] >= 1
    assert targeted["ordinary_qualifying_states"] == 0
    assert targeted["ordinary_best_improvement_m"] == pytest.approx(100)
    assert targeted["avoidance_overlap_viable_connectors"] >= 1
    assert targeted["avoidance_nonmaterial_states"] >= 1
    assert targeted["avoidance_qualifying_states"] == 0
    assert targeted["avoidance_best_improvement_m"] == pytest.approx(200)
    assert targeted["guide_qualifying_states"] >= 1
    assert seeds


@pytest.mark.asyncio
async def test_material_ordinary_repair_skips_avoidance_and_guides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    backend = _EscalationBackend()
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    pool = LazyPathPool(
        context=_context(backend),
        profile="hike",
        result_factory=RouteResultFactory(),
        settings=_settings(),
        diagnostics=diagnostics,
    )
    state = await initial_state(source, pool)
    assert state is not None

    def resulting_repetition(
        source_value: object,
        proposed_value: object,
        target_value: object,
        result_factory_value: object,
    ) -> tuple[float, float]:
        del source_value, proposed_value, result_factory_value
        target = cast(SpurOptimizationTarget, target_value)
        return target.repeated_distance_m - 700.0, 500.0

    monkeypatch.setattr(
        "sugarglider.planning.optimization.spur_rejoin._analyze_structural_state",
        resulting_repetition,
    )

    seeds = await structural_spur_seeds(
        source,
        state,
        path_pool=pool,
        result_factory=RouteResultFactory(),
        settings=_settings(),
        diagnostics=diagnostics,
    )

    assert seeds
    assert backend.avoidance_areas == []
    assert backend.guide_calls == 0
    targeted = diagnostics.as_dict()["targeted_spurs"][0]
    assert targeted["ordinary_qualifying_states"] >= 1
    assert targeted["avoidance_requests"] == 0
    assert targeted["guide_route_attempts"] == 0


@pytest.mark.asyncio
async def test_exhausted_nonmaterial_strategies_report_truthfully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    backend = _EscalationBackend()
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    pool = LazyPathPool(
        context=_context(backend),
        profile="hike",
        result_factory=RouteResultFactory(),
        settings=_settings(),
        diagnostics=diagnostics,
    )
    state = await initial_state(source, pool)
    assert state is not None

    def resulting_repetition(
        source_value: object,
        proposed_value: object,
        target_value: object,
        result_factory_value: object,
    ) -> tuple[float, float]:
        del source_value, proposed_value, result_factory_value
        target = cast(SpurOptimizationTarget, target_value)
        return target.repeated_distance_m - 100.0, 1_100.0

    monkeypatch.setattr(
        "sugarglider.planning.optimization.spur_rejoin._analyze_structural_state",
        resulting_repetition,
    )

    seeds = await structural_spur_seeds(
        source,
        state,
        path_pool=pool,
        result_factory=RouteResultFactory(),
        settings=_settings(),
        diagnostics=diagnostics,
    )

    assert seeds == ()
    targeted = diagnostics.as_dict()["targeted_spurs"][0]
    assert targeted["guide_route_attempts"] == 6
    assert targeted["guide_nonmaterial_states"] == 6
    assert targeted["guide_qualifying_states"] == 0
    assert targeted["final_reason"] == "guide_no_material_repair"


@pytest.mark.asyncio
async def test_private_guide_fallback_is_bounded_and_not_a_semantic_anchor() -> None:
    source = _source()
    backend = _GuideBackend()
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    pool = LazyPathPool(
        context=_context(backend),
        profile="hike",
        result_factory=RouteResultFactory(),
        settings=_settings(),
        diagnostics=diagnostics,
    )
    state = await initial_state(source, pool)
    assert state is not None

    seeds = await structural_spur_seeds(
        source,
        state,
        path_pool=pool,
        result_factory=RouteResultFactory(),
        settings=_settings(),
        diagnostics=diagnostics,
    )

    assert seeds
    repaired = seeds[0]
    assert repaired.ordered_anchor_ids == ("start", "end")
    assert tuple(anchor.coordinate for anchor in repaired.anchors) == (A, E)
    assert len(repaired.complete_path.geometry) > len(repaired.anchors)
    targeted = diagnostics.as_dict()["targeted_spurs"][0]
    assert targeted["avoidance_supported"] is False
    assert 1 <= targeted["guide_candidates_generated"]
    assert 2 <= targeted["guide_route_attempts"] <= 6
    assert targeted["guide_paths_returned"] >= 1
    assert targeted["viable_connectors"] >= 1
    assert "edge_id" not in repr(targeted)


@pytest.mark.asyncio
async def test_guide_attempts_are_fair_across_rejoins_and_remain_bounded() -> None:
    source = _source()
    backend = _UnrouteableGuideBackend()
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    pool = LazyPathPool(
        context=_context(backend),
        profile="hike",
        result_factory=RouteResultFactory(),
        settings=_settings(),
        diagnostics=diagnostics,
    )
    state = await initial_state(source, pool)
    assert state is not None

    seeds = await structural_spur_seeds(
        source,
        state,
        path_pool=pool,
        result_factory=RouteResultFactory(),
        settings=_settings(),
        diagnostics=diagnostics,
    )

    assert seeds == ()
    assert backend.guide_calls == 6
    assert len(set(backend.guide_rejoins)) >= 2
    targeted = diagnostics.as_dict()["targeted_spurs"][0]
    assert targeted["guide_route_attempts"] == 6


@pytest.mark.asyncio
async def test_avoidance_failure_and_far_guide_snaps_are_nonfatal() -> None:
    source = _source()
    for backend in (_FailingAvoidanceBackend(), _FarSnapGuideBackend()):
        diagnostics = GlobalOptimizationDiagnostics(64, 24)
        pool = LazyPathPool(
            context=_context(backend),
            profile="hike",
            result_factory=RouteResultFactory(),
            settings=_settings(),
            diagnostics=diagnostics,
        )
        state = await initial_state(source, pool)
        assert state is not None

        seeds = await structural_spur_seeds(
            source,
            state,
            path_pool=pool,
            result_factory=RouteResultFactory(),
            settings=_settings(),
            diagnostics=diagnostics,
        )

        assert seeds == ()
        targeted = diagnostics.as_dict()["targeted_spurs"][0]
        assert targeted["states_reconstructed"] == 0
        assert targeted["final_reason"] in {
            "no_viable_connector",
            "avoidance_no_path",
            "guide_points_unrouteable",
        }
        if isinstance(backend, _FarSnapGuideBackend):
            assert 1 <= targeted["guide_rejected_snap"] <= 6


@pytest.mark.asyncio
async def test_structural_seeding_runs_before_alns_and_publishes_targeted_draft() -> (
    None
):
    source = _source()
    backend = _ConnectorBackend()
    diagnostics = GlobalOptimizationDiagnostics(64, 24)

    result = await optimize_tours(
        (source,),
        context=_context(backend),
        result_factory=RouteResultFactory(),
        seed=17,
        settings=GlobalOptimizationSettings(
            maximum_iterations=1,
            maximum_no_improvement_iterations=1,
            optimizer_cpu_time_limit_s=2,
            optimizer_total_wall_time_limit_s=2,
        ),
        diagnostics=diagnostics,
    )

    assert result.drafts
    assert tuple(
        repair.spur_id for repair in result.drafts[0].applied_spur_repairs
    ) == (source.route.analysis.spurs.spurs[0].id,)
    assert result.drafts[0].applied_spur_repairs[0].improvement_m == pytest.approx(
        1_200
    )
    assert diagnostics.iterations == 1
    assert (
        diagnostics.as_dict()["targeted_spurs"][0]["states_targeted_improvement"] >= 1
    )
