"""Edge-supported downstream spur closure inside the shared optimizer."""

from __future__ import annotations

from dataclasses import dataclass, replace

from sugarglider.analysis.route import (
    haversine_distance_m,
    project_geometry_edges,
)
from sugarglider.analysis.spurs import (
    SpurTraversalAnchor,
    detect_route_spurs,
)
from sugarglider.domain.models import Coordinate, PathDetailSegment
from sugarglider.planning.optimization.corridor_avoidance import (
    corridor_avoidance_area,
    guide_candidates,
    inbound_corridor_evidence,
)
from sugarglider.planning.optimization.diagnostics import (
    GlobalOptimizationDiagnostics,
)
from sugarglider.planning.optimization.models import (
    AppliedSpurRepair,
    ConnectorGenerationStrategy,
    GlobalOptimizationSettings,
    InboundOverlapMeasurement,
    OptimizationAnchor,
    OptimizationSource,
    PathOption,
    RejoinPosition,
    SpurOptimizationTarget,
    StructuralRepairAction,
    TourOptimizationState,
)
from sugarglider.planning.optimization.path_pool import LazyPathPool
from sugarglider.planning.optimization.spur_splice import (
    LegSplice as _LegSplice,
)
from sugarglider.planning.optimization.spur_splice import (
    align_connector_endpoints as _align_connector_endpoints,
)
from sugarglider.planning.optimization.spur_splice import (
    leg_splice as _leg_splice,
)
from sugarglider.planning.optimization.spur_targets import (
    downstream_rejoins as downstream_rejoins,
)
from sugarglider.planning.optimization.spur_targets import (
    optimization_targets as optimization_targets,
)
from sugarglider.planning.optimization.state import state_from_selected_path_options
from sugarglider.routing.backend import CorridorAvoidanceArea, RoutedPath
from sugarglider.routing.composition import (
    RouteCompositionError,
    compose_routed_segments,
)
from sugarglider.routing.result import RouteResultFactory

_EPSILON = 1e-9


@dataclass(frozen=True)
class ConnectorStrategyResult:
    """Complete material-repair outcome for one connector strategy batch."""

    qualifying_actions: tuple[StructuralRepairAction, ...]
    connectors_considered: int
    rejected_profile: int
    rejected_overlap: int
    overlap_viable_connectors: int
    reconstructed_states: int
    reconstruction_failures: int
    hard_failures: int
    nonmaterial_improvements: int
    best_improvement_m: float
    best_distance_change_m: float

    @property
    def qualifying_states(self) -> tuple[TourOptimizationState, ...]:
        return tuple(
            action.resulting_single_state for action in self.qualifying_actions
        )


@dataclass(frozen=True)
class _GuidePlan:
    rejoin: RejoinPosition
    rejoin_splice: _LegSplice
    guides: tuple[tuple[ConnectorGenerationStrategy, Coordinate], ...]


async def structural_spur_actions(
    source: OptimizationSource,
    state: TourOptimizationState,
    *,
    path_pool: LazyPathPool,
    result_factory: RouteResultFactory,
    settings: GlobalOptimizationSettings,
    diagnostics: GlobalOptimizationDiagnostics,
) -> tuple[StructuralRepairAction, ...]:
    """Materialize reusable bounded important-spur repairs before ALNS."""
    retained: list[StructuralRepairAction] = []
    for target in optimization_targets(source, settings):
        rejoins = downstream_rejoins(source, target, settings)
        diagnostics.register_spur_target(target, rejoin_positions=len(rejoins))
        turnaround_splice = _leg_splice(
            state,
            target,
            anchor_id=f"{target.stable_id}/turnaround",
            coordinate=target.turnaround_coordinate,
            progress=target.turnaround_progress,
            maximum_distance_m=settings.maximum_source_splice_distance_m,
        )
        if turnaround_splice is None:
            diagnostics.set_spur_reason(target.stable_id, "reconstruction_failed")
            continue
        capabilities = path_pool.capabilities
        diagnostics.record_avoidance_capability(
            target.stable_id,
            capabilities.request_custom_model
            and capabilities.custom_model_areas
            and capabilities.alternative_route_with_custom_model,
        )
        evidence = inbound_corridor_evidence(target, settings)
        avoidance_requests = 0
        guide_attempts = 0
        target_has_qualifying_state = False
        unresolved: list[tuple[RejoinPosition, _LegSplice]] = []

        # Ordinary connectors are only successful when full reconstruction
        # produces a material targeted repair. Overlap viability is a prefilter.
        for rejoin in rejoins:
            rejoin_splice = _leg_splice(
                state,
                target,
                anchor_id=rejoin.stable_id,
                coordinate=rejoin.coordinate,
                progress=rejoin.source_progress,
                maximum_distance_m=settings.maximum_source_splice_distance_m,
            )
            if rejoin_splice is None:
                continue
            connectors = await _connector_options(
                turnaround_splice.anchor,
                rejoin_splice.anchor,
                path_pool=path_pool,
            )
            result = await evaluate_connectors(
                source,
                state,
                target,
                rejoin,
                turnaround_splice,
                rejoin_splice,
                connectors,
                "ordinary_alternative",
                path_pool=path_pool,
                result_factory=result_factory,
                settings=settings,
                diagnostics=diagnostics,
            )
            diagnostics.record_spur_connectors(
                target.stable_id,
                returned=len(connectors),
                rejected_overlap=result.rejected_overlap,
            )
            _record_strategy_result(diagnostics, target, result, "ordinary_alternative")
            if result.qualifying_states:
                retained.extend(result.qualifying_actions)
                target_has_qualifying_state = True
            else:
                unresolved.append((rejoin, rejoin_splice))

        avoidance_supported = (
            capabilities.request_custom_model
            and capabilities.custom_model_areas
            and capabilities.alternative_route_with_custom_model
        )
        guide_rejoins: list[
            tuple[RejoinPosition, _LegSplice, CorridorAvoidanceArea | None]
        ] = []
        for rejoin, rejoin_splice in unresolved:
            area = (
                corridor_avoidance_area(evidence, rejoin, settings)
                if evidence is not None
                else None
            )
            avoided: tuple[PathOption, ...] = ()
            request_avoidance = bool(
                avoidance_supported
                and area is not None
                and avoidance_requests < settings.maximum_avoidance_requests_per_target
            )
            if request_avoidance and area is not None:
                avoidance_requests += 1
                avoided = await path_pool.avoiding_options_for(
                    turnaround_splice.anchor,
                    rejoin_splice.anchor,
                    area,
                    priority_multiplier=settings.avoidance_priority_multiplier,
                )
            result = await evaluate_connectors(
                source,
                state,
                target,
                rejoin,
                turnaround_splice,
                rejoin_splice,
                avoided,
                "custom_model_corridor_avoidance",
                path_pool=path_pool,
                result_factory=result_factory,
                settings=settings,
                diagnostics=diagnostics,
            )
            diagnostics.record_avoidance(
                target.stable_id,
                supported=avoidance_supported,
                requested=request_avoidance,
                returned=len(avoided),
                rejected_overlap=result.rejected_overlap,
            )
            _record_strategy_result(
                diagnostics,
                target,
                result,
                "custom_model_corridor_avoidance",
            )
            if result.qualifying_states:
                retained.extend(result.qualifying_actions)
                target_has_qualifying_state = True
            else:
                guide_rejoins.append((rejoin, rejoin_splice, area))

        plans: list[_GuidePlan] = []
        for rejoin, rejoin_splice, area in guide_rejoins:
            guides = guide_candidates(target, rejoin, area, settings)
            diagnostics.record_guides(target.stable_id, generated=len(guides))
            if guides:
                plans.append(
                    _GuidePlan(
                        rejoin=rejoin,
                        rejoin_splice=rejoin_splice,
                        guides=guides,
                    )
                )

        # Allocate guide attempts in two-sided rounds across rejoins. An early
        # rejoin cannot consume the target's entire six-call allowance before a
        # later rejoin receives its first bounded opportunity.
        resolved_rejoins: set[str] = set()
        maximum_guides = max((len(plan.guides) for plan in plans), default=0)
        for pair_start in range(0, maximum_guides, 2):
            for plan in plans:
                if (
                    plan.rejoin.stable_id in resolved_rejoins
                    or guide_attempts
                    >= settings.maximum_guide_route_attempts_per_target
                ):
                    continue
                for guide_index in range(
                    pair_start, min(pair_start + 2, len(plan.guides))
                ):
                    if (
                        guide_attempts
                        >= settings.maximum_guide_route_attempts_per_target
                    ):
                        break
                    strategy, guide = plan.guides[guide_index]
                    guide_attempts += 1
                    option, rejected_snap = await path_pool.guide_option_for(
                        turnaround_splice.anchor,
                        plan.rejoin_splice.anchor,
                        guide,
                        strategy=strategy,
                        maximum_snap_distance_m=settings.maximum_guide_snap_distance_m,
                    )
                    returned = int(option is not None)
                    connectors = (
                        ()
                        if option is None
                        or _guide_detour_excessive(
                            source, target, plan.rejoin, option, settings
                        )
                        else (option,)
                    )
                    result = await evaluate_connectors(
                        source,
                        state,
                        target,
                        plan.rejoin,
                        turnaround_splice,
                        plan.rejoin_splice,
                        connectors,
                        strategy,
                        path_pool=path_pool,
                        result_factory=result_factory,
                        settings=settings,
                        diagnostics=diagnostics,
                    )
                    diagnostics.record_guides(
                        target.stable_id,
                        attempts=1,
                        returned=returned,
                        rejected_snap=int(rejected_snap),
                        rejected_overlap=result.rejected_overlap,
                    )
                    _record_strategy_result(diagnostics, target, result, strategy)
                    if result.qualifying_states:
                        retained.extend(result.qualifying_actions)
                        target_has_qualifying_state = True
                        resolved_rejoins.add(plan.rejoin.stable_id)
                        break
        if target_has_qualifying_state:
            diagnostics.set_spur_reason(target.stable_id, "archive_dominated")
    by_target: dict[str, list[StructuralRepairAction]] = {}
    for action in retained:
        by_target.setdefault(action.repair.target_stable_id, []).append(action)
    bounded = tuple(
        action
        for target_id in sorted(by_target)
        for action in sorted(
            by_target[target_id],
            key=_action_retention_key,
        )[: settings.maximum_actions_per_structural_target]
    )
    selected_actions = tuple(
        sorted(
            {value.stable_signature: value for value in bounded}.values(),
            key=_action_retention_key,
        )[: settings.maximum_structural_actions_per_source]
    )
    selected_option_ids = {action.replacement_option.id for action in selected_actions}
    for action in retained:
        if action.replacement_option.id not in selected_option_ids:
            path_pool.discard(action.replacement_option.id)
    return selected_actions


async def structural_spur_seeds(
    source: OptimizationSource,
    state: TourOptimizationState,
    *,
    path_pool: LazyPathPool,
    result_factory: RouteResultFactory,
    settings: GlobalOptimizationSettings,
    diagnostics: GlobalOptimizationDiagnostics,
) -> tuple[TourOptimizationState, ...]:
    """Compatibility facade returning the reusable actions' single states."""
    actions = await structural_spur_actions(
        source,
        state,
        path_pool=path_pool,
        result_factory=result_factory,
        settings=settings,
        diagnostics=diagnostics,
    )
    return tuple(action.resulting_single_state for action in actions)


async def evaluate_connectors(
    source: OptimizationSource,
    state: TourOptimizationState,
    target: SpurOptimizationTarget,
    rejoin: RejoinPosition,
    turnaround_splice: _LegSplice,
    rejoin_splice: _LegSplice,
    connectors: tuple[PathOption, ...],
    strategy: ConnectorGenerationStrategy,
    *,
    path_pool: LazyPathPool,
    result_factory: RouteResultFactory,
    settings: GlobalOptimizationSettings,
    diagnostics: GlobalOptimizationDiagnostics,
) -> ConnectorStrategyResult:
    """Reconstruct connectors and retain only material targeted repairs."""
    selected = connectors[: settings.maximum_connector_options_per_rejoin]
    rejected_profile = 0
    rejected_overlap = 0
    viable: list[PathOption] = []
    for connector in selected:
        if connector.severe_profile_incompatibility:
            rejected_profile += 1
            continue
        if (
            _inbound_overlap(connector, target, settings).overlap_share
            > settings.maximum_inbound_overlap_share
        ):
            rejected_overlap += 1
            continue
        viable.append(connector)

    qualifying: list[StructuralRepairAction] = []
    reconstructed = 0
    reconstruction_failures = 0
    hard_failures = 0
    nonmaterial = 0
    best_improvement = 0.0
    best_distance_change = 0.0
    for connector in viable:
        compound = _compound_option(
            source,
            state,
            target,
            rejoin,
            turnaround_splice,
            rejoin_splice,
            connector,
            path_pool=path_pool,
        )
        if compound is None:
            reconstruction_failures += 1
            continue
        selected_options = list(state.path_options)
        selected_options[target.containing_leg_start_index] = compound
        proposed = state_from_selected_path_options(
            source=source,
            anchors=state.anchors,
            options=tuple(selected_options),
            operator="spur_rejoin",
            applied_spur_repairs=(),
            analyzed_total_spur_repetition_m=None,
        )
        if proposed is None:
            path_pool.discard(compound.id)
            reconstruction_failures += 1
            continue
        reconstructed += 1
        diagnostics.states_reconstructed += 1
        if not proposed.objective_components.hard_feasible:
            hard_failures += 1
            reason = (
                "distance"
                if source.maximum_distance_m is not None
                and proposed.complete_path.distance_m > source.maximum_distance_m
                else (
                    "profile"
                    if any(
                        option.severe_profile_incompatibility
                        for option in proposed.path_options
                    )
                    else "infeasible"
                )
            )
            diagnostics.record_spur_rejection(target.stable_id, reason)
            path_pool.discard(compound.id)
            continue
        resulting, total_spur_repetition = _analyze_structural_state(
            source,
            proposed,
            target,
            result_factory,
        )
        improvement = max(0.0, target.repeated_distance_m - resulting)
        if improvement > best_improvement:
            best_improvement = improvement
            best_distance_change = (
                proposed.complete_path.distance_m - state.complete_path.distance_m
            )
        if improvement + _EPSILON < settings.minimum_structural_improvement_m:
            nonmaterial += 1
            path_pool.discard(compound.id)
            continue
        repair = AppliedSpurRepair(
            target_stable_id=target.stable_id,
            spur_id=target.spur_id,
            stop_ids=target.stop_ids,
            stop_names=target.stop_names,
            containing_leg_index=target.containing_leg_start_index,
            start_progress=target.start_progress,
            turnaround_progress=target.turnaround_progress,
            end_progress=target.end_progress,
            source_repeated_distance_m=target.repeated_distance_m,
            resulting_repeated_distance_m=resulting,
            improvement_m=improvement,
            generation_strategy=strategy,
            replacement_path_option_id=compound.id,
        )
        proposed = replace(
            proposed,
            objective_components=replace(
                proposed.objective_components,
                analyzed_total_spur_repetition_m=total_spur_repetition,
            ),
            applied_spur_repairs=(repair,),
        )
        qualifying.append(
            StructuralRepairAction(
                repair=repair,
                replacement_option=compound,
                resulting_single_state=proposed,
                stable_signature=f"{proposed.stable_signature}/{target.stable_id}",
            )
        )
    return ConnectorStrategyResult(
        qualifying_actions=tuple(qualifying),
        connectors_considered=len(selected),
        rejected_profile=rejected_profile,
        rejected_overlap=rejected_overlap,
        overlap_viable_connectors=len(viable),
        reconstructed_states=reconstructed,
        reconstruction_failures=reconstruction_failures,
        hard_failures=hard_failures,
        nonmaterial_improvements=nonmaterial,
        best_improvement_m=best_improvement,
        best_distance_change_m=best_distance_change,
    )


def _record_strategy_result(
    diagnostics: GlobalOptimizationDiagnostics,
    target: SpurOptimizationTarget,
    result: ConnectorStrategyResult,
    strategy: ConnectorGenerationStrategy,
) -> None:
    diagnostics.record_connector_strategy_evaluation(
        target.stable_id,
        strategy,
        overlap_viable=result.overlap_viable_connectors,
        reconstructed=result.reconstructed_states,
        nonmaterial=result.nonmaterial_improvements,
        qualifying=len(result.qualifying_states),
        best_improvement_m=result.best_improvement_m,
        best_distance_change_m=result.best_distance_change_m,
    )
    if result.reconstruction_failures and not result.qualifying_states:
        diagnostics.set_spur_reason(target.stable_id, "reconstruction_failed")


async def _connector_options(
    turnaround: OptimizationAnchor,
    downstream: OptimizationAnchor,
    *,
    path_pool: LazyPathPool,
) -> tuple[PathOption, ...]:
    return await path_pool.options_for(
        turnaround,
        downstream,
        source_kind="spur_connector",
        request_alternatives=True,
    )


def _compound_option(
    source: OptimizationSource,
    state: TourOptimizationState,
    target: SpurOptimizationTarget,
    rejoin: RejoinPosition,
    turnaround_splice: _LegSplice,
    rejoin_splice: _LegSplice,
    connector: PathOption,
    *,
    path_pool: LazyPathPool,
) -> PathOption | None:
    leg_index = target.containing_leg_start_index
    source_option = state.path_options[leg_index]
    left = state.anchors[leg_index]
    right = state.anchors[leg_index + 1]
    turnaround_index = turnaround_splice.geometry_index
    rejoin_index = rejoin_splice.geometry_index
    if rejoin_index <= turnaround_index:
        return None
    prefix = _slice_path(source_option.routed_path, 0, turnaround_index)
    suffix = _slice_path(
        source_option.routed_path,
        rejoin_index,
        len(source_option.routed_path.geometry) - 1,
    )
    connector_path = _align_connector_endpoints(
        connector.routed_path,
        source_option.routed_path.geometry[turnaround_index],
        source_option.routed_path.geometry[rejoin_index],
    )
    if connector_path is None:
        return None
    segments = tuple(
        value for value in (prefix, connector_path, suffix) if value is not None
    )
    try:
        compound = compose_routed_segments(segments)
    except RouteCompositionError:
        return None
    compound = RoutedPath(
        distance_m=compound.distance_m,
        duration_ms=compound.duration_ms,
        ascend_m=compound.ascend_m,
        descend_m=compound.descend_m,
        geometry=compound.geometry,
        snapped_points=(compound.geometry[0], compound.geometry[-1]),
        details=compound.details,
    )
    return path_pool.insert(
        from_anchor=left,
        to_anchor=right,
        profile=source.routing_profile,
        path=compound,
        source_kind="spur_connector",
    )


def _analyze_structural_state(
    source: OptimizationSource,
    state: TourOptimizationState,
    target: SpurOptimizationTarget,
    result_factory: RouteResultFactory,
) -> tuple[float, float]:
    route = result_factory.create(
        name=source.route.name,
        path=state.complete_path,
        input_point_count=max(2, len(state.anchors)),
        routing_profile=source.routing_profile,
    )
    cumulative = 0.0
    anchors: list[SpurTraversalAnchor] = []
    for index, anchor in enumerate(state.anchors):
        progress = (
            cumulative / state.complete_path.distance_m
            if state.complete_path.distance_m > 0
            else 0.0
        )
        if anchor.kind == "soft":
            anchors.append(
                SpurTraversalAnchor(
                    id=anchor.id, name=anchor.name, route_progress=progress
                )
            )
        if index < len(state.path_options):
            cumulative += state.path_options[index].distance_m
    resulting = detect_route_spurs(route, tuple(anchors), topology=source.topology)
    matches = tuple(
        spur
        for spur in resulting.spurs
        if (
            (
                not target.stop_ids
                or bool(
                    _normalized_stop_ids(target.stop_ids)
                    & _normalized_stop_ids(spur.deliberate_stop_ids)
                )
                or bool(set(target.stop_names) & set(spur.deliberate_stop_names))
            )
            and haversine_distance_m(
                spur.turnaround_coordinate,
                (
                    target.turnaround_coordinate.lon,
                    target.turnaround_coordinate.lat,
                ),
            )
            <= 200.0
        )
    )
    return (
        max((spur.repeated_distance_m for spur in matches), default=0.0),
        resulting.total_repeated_distance_m,
    )


def _action_retention_key(
    action: StructuralRepairAction,
) -> tuple[object, ...]:
    state = action.resulting_single_state
    return (
        -action.repair.improvement_m,
        state.objective_components.lexicographic_key(),
        action.stable_signature,
    )


def _inbound_overlap(
    connector: PathOption,
    target: SpurOptimizationTarget,
    settings: GlobalOptimizationSettings,
) -> InboundOverlapMeasurement:
    raw = sum(
        edge.distance_m
        for edge in connector.directed_edges
        if edge.physical_edge_key in target.inbound_edge_keys
    )
    allowed = min(
        settings.maximum_shared_distance_near_turnaround_m,
        target.inbound_distance_m,
    )
    charged = max(0.0, raw - allowed)
    return InboundOverlapMeasurement(
        inbound_distance_m=target.inbound_distance_m,
        raw_overlap_m=raw,
        allowed_stem_m=allowed,
        charged_overlap_m=charged,
        overlap_share=charged / target.inbound_distance_m,
    )


def _guide_detour_excessive(
    source: OptimizationSource,
    target: SpurOptimizationTarget,
    rejoin: RejoinPosition,
    connector: PathOption,
    settings: GlobalOptimizationSettings,
) -> bool:
    source_interval_m = (
        rejoin.source_progress - target.turnaround_progress
    ) * source.route.summary.distance_m
    return connector.distance_m > (
        source_interval_m * settings.maximum_guide_connector_detour_factor
        + settings.maximum_extra_distance_m
    )


def _private_anchor(
    anchor_id: str, coordinate: Coordinate, progress: float
) -> OptimizationAnchor:
    return OptimizationAnchor(
        id=anchor_id,
        name="Structural routing position",
        coordinate=coordinate,
        semantic_coordinate=coordinate,
        kind="fixed",
        source_progress=progress,
        exact_window=0,
    )


def _slice_path(path: RoutedPath, start: int, end: int) -> RoutedPath | None:
    if end <= start:
        return None
    projection = project_geometry_edges(
        geometry=path.geometry,
        route_distance_m=path.distance_m,
        path_details=path.details,
    )
    distance = sum(projection.edges[index].distance_m for index in range(start, end))
    duration = (
        round(path.duration_ms * distance / path.distance_m)
        if path.distance_m > 0
        else 0
    )
    details: dict[str, tuple[PathDetailSegment, ...]] = {}
    for name, values in path.details.items():
        sliced: list[PathDetailSegment] = []
        for value in values:
            left = max(start, value.from_index)
            right = min(end, value.to_index)
            if left < right:
                sliced.append(
                    PathDetailSegment(
                        from_index=left - start,
                        to_index=right - start,
                        value=value.value,
                    )
                )
        details[name] = tuple(sliced)
    geometry = path.geometry[start : end + 1]
    return RoutedPath(
        distance_m=distance,
        duration_ms=duration,
        ascend_m=None,
        descend_m=None,
        geometry=geometry,
        snapped_points=(geometry[0], geometry[-1]),
        details=details,
    )


def _normalized_stop_ids(values: tuple[str, ...]) -> frozenset[str]:
    return frozenset(value.removeprefix("stop/") for value in values)
