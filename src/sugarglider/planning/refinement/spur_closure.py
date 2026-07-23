"""Bounded graph-valid alternative exits for detected route spurs."""

from dataclasses import replace

from sugarglider.analysis.route import known_edge_id, project_geometry_edges
from sugarglider.analysis.spurs import (
    SpurTraversalAnchor,
    detect_route_spurs,
    spur_repair_priority,
)
from sugarglider.domain.analysis import RouteSpur, RouteSpurAnalysis
from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.planning.budget import SearchPhase
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.profile_quality import profile_quality_components
from sugarglider.planning.refinement.models import (
    RejoinCandidate,
    SpurClosureDiagnostics,
    SpurClosureDraft,
    SpurClosureResult,
    SpurClosureSettings,
    SpurRepairDiagnosticAccumulator,
    SpurRepairRejection,
    SpurRepairSource,
    _SupportedSpur,
)
from sugarglider.planning.refinement.rejoin import generate_rejoin_candidates
from sugarglider.planning.routing_gateway import SearchBudgetExhaustedError
from sugarglider.routing.backend import RoutedPath
from sugarglider.routing.composition import (
    RouteCompositionError,
    compose_routed_segments,
)
from sugarglider.routing.errors import RoutingError
from sugarglider.routing.result import RouteResultFactory


async def refine_spur_closures(
    source: SpurRepairSource,
    *,
    context: PlanningSearchContext,
    result_factory: RouteResultFactory,
    settings: SpurClosureSettings | None = None,
    diagnostics: SpurRepairDiagnosticAccumulator | None = None,
) -> SpurClosureResult:
    """Return accepted complete paths; optional failures never reject the source."""
    resolved = settings or SpurClosureSettings()
    accumulator = diagnostics or SpurRepairDiagnosticAccumulator()
    accumulator.source_candidates_considered += 1
    spur_analysis = _source_spurs(source)
    supported = _supported_spurs(source, spur_analysis, resolved, accumulator)
    considered = supported[: resolved.maximum_spurs_per_candidate]
    accumulator.spurs_considered += len(considered)
    drafts: list[SpurClosureDraft] = []
    warnings: set[str] = set()
    attempts = 0
    for evidence in considered:
        rejoins = generate_rejoin_candidates(
            source.route,
            evidence.spur,
            source.anchors,
            topology=source.topology,
            settings=resolved,
        )
        accumulator.rejoin_candidates_generated += len(rejoins)
        for rejoin in rejoins:
            if attempts >= resolved.maximum_attempts_per_candidate:
                break
            try:
                accumulator.connector_route_attempts += 1
                connectors = await context.routes.alternative_routes(
                    _coordinate(evidence.spur.turnaround_coordinate),
                    rejoin.coordinate,
                    source.profile,
                    max_paths=resolved.maximum_connector_alternatives,
                    max_weight_factor=1.8,
                    max_share_factor=0.7,
                    phase=SearchPhase.SPUR_REPAIR,
                )
            except SearchBudgetExhaustedError:
                warnings.add("spur_repair_budget_exhausted")
                accumulator.budget_exhausted = True
                return _final_result(drafts, attempts, warnings, accumulator)
            except RoutingError:
                accumulator.connector_route_failures += 1
                continue
            accumulator.connector_routes_succeeded += len(connectors)
            for connector in _ordered_connectors(connectors):
                if attempts >= resolved.maximum_attempts_per_candidate:
                    break
                attempts += 1
                overlap_m, overlap_share = _inbound_overlap(
                    connector, evidence, resolved
                )
                if overlap_share > resolved.maximum_inbound_overlap_share:
                    accumulator.rejected_inbound_overlap += 1
                    continue
                accumulator.reconstruction_attempts += 1
                try:
                    complete, points = await _reconstruct(
                        source, evidence.spur, rejoin, connector, context
                    )
                    if not _preserves_exact_constraints(source, points):
                        accumulator.reject("exact_constraints")
                        continue
                    route = result_factory.create(
                        name=source.route.name,
                        path=complete,
                        input_point_count=len(points),
                        routing_profile=source.profile,
                    )
                except SearchBudgetExhaustedError:
                    warnings.add("spur_repair_budget_exhausted")
                    accumulator.budget_exhausted = True
                    return _final_result(drafts, attempts, warnings, accumulator)
                except (RoutingError, RouteCompositionError, ValueError):
                    accumulator.reconstruction_failures += 1
                    continue
                repair_diagnostics, rejection = _improvement(
                    source,
                    evidence.spur,
                    rejoin,
                    connector,
                    route,
                    overlap_m,
                    overlap_share,
                    attempts,
                    resolved,
                )
                if rejection is not None:
                    accumulator.reject(rejection)
                    continue
                if repair_diagnostics is None:
                    continue
                drafts.append(
                    SpurClosureDraft(
                        path=complete,
                        route=route,
                        routing_points=points,
                        diagnostics=repair_diagnostics,
                    )
                )
    return _final_result(drafts, attempts, warnings, accumulator)


def _final_result(
    drafts: list[SpurClosureDraft],
    attempts: int,
    warnings: set[str],
    diagnostics: SpurRepairDiagnosticAccumulator,
) -> SpurClosureResult:
    completed = tuple(
        replace(
            value,
            diagnostics=replace(
                value.diagnostics,
                repair_attempt_count=attempts,
            ),
        )
        for value in drafts
    )
    unique = {
        (
            tuple(value.path.geometry),
            value.diagnostics.targeted_spur_id,
        ): value
        for value in completed
    }
    diagnostics.accepted_repair_drafts += len(unique)
    return SpurClosureResult(
        drafts=tuple(
            sorted(
                unique.values(),
                key=lambda value: (
                    -value.diagnostics.repeated_distance_improvement_m,
                    -value.diagnostics.immediate_backtracking_improvement_m,
                    value.diagnostics.targeted_spur_id,
                    value.diagnostics.rejoin_progress,
                    tuple(value.path.geometry),
                ),
            )
        ),
        attempts=attempts,
        warnings=tuple(sorted(warnings)),
        diagnostics=diagnostics.snapshot(),
    )


def _source_spurs(source: SpurRepairSource) -> RouteSpurAnalysis:
    deliberate = tuple(
        SpurTraversalAnchor(
            id=anchor.id,
            name=anchor.coordinate.name or anchor.id,
            route_progress=anchor.route_progress,
        )
        for anchor in source.anchors
        if anchor.mandatory and anchor.route_progress not in {0.0, 1.0}
    )
    return detect_route_spurs(source.route, deliberate, topology=source.topology)


def _supported_spurs(
    source: SpurRepairSource,
    analysis: RouteSpurAnalysis,
    settings: SpurClosureSettings,
    diagnostics: SpurRepairDiagnosticAccumulator,
) -> tuple[_SupportedSpur, ...]:
    projection = project_geometry_edges(
        geometry=source.route.geometry,
        route_distance_m=source.route.summary.distance_m,
        path_details=source.route.path_details,
    )
    prefix = 0.0
    intervals: list[tuple[float, float, int, float]] = []
    for edge in projection.edges:
        edge_id = known_edge_id(edge)
        intervals.append(
            (
                prefix,
                prefix + edge.distance_m,
                edge_id if edge_id is not None else -1,
                edge.distance_m,
            )
        )
        prefix += edge.distance_m
    supported: list[_SupportedSpur] = []
    for spur in sorted(analysis.spurs, key=spur_repair_priority):
        exact_anchor_bypassed = any(
            anchor.kind == "exact"
            and spur.turnaround_progress + 1e-9
            < anchor.route_progress
            < spur.end_progress - 1e-9
            for anchor in source.anchors
        )
        if exact_anchor_bypassed:
            diagnostics.reject("exact_constraints")
            continue
        if (
            spur.confidence == "low"
            or spur.repeated_distance_m
            < settings.minimum_repeated_distance_improvement_m
            or "near_route_endpoint" in spur.reason_codes
            or any(
                anchor.mandatory
                and spur.turnaround_progress + 1e-9
                < anchor.route_progress
                < spur.end_progress - 1e-9
                for anchor in source.anchors
            )
        ):
            continue
        start_m = spur.start_progress * source.route.summary.distance_m
        turnaround_m = spur.turnaround_progress * source.route.summary.distance_m
        inbound = tuple(
            value
            for value in intervals
            if value[0] < turnaround_m and value[1] > start_m
        )
        edge_ids = frozenset(value[2] for value in inbound if value[2] >= 0)
        distance_m = sum(value[3] for value in inbound if value[2] >= 0)
        if not edge_ids or distance_m <= 0:
            continue
        supported.append(_SupportedSpur(spur, edge_ids, distance_m))
    return tuple(supported)


def _ordered_connectors(paths: tuple[RoutedPath, ...]) -> tuple[RoutedPath, ...]:
    return tuple(
        sorted(
            paths,
            key=lambda path: (
                path.distance_m,
                tuple(path.geometry),
            ),
        )
    )


def _inbound_overlap(
    connector: RoutedPath,
    evidence: _SupportedSpur,
    settings: SpurClosureSettings,
) -> tuple[float, float]:
    projected = project_geometry_edges(
        geometry=connector.geometry,
        route_distance_m=connector.distance_m,
        path_details=connector.details,
    )
    raw = sum(
        edge.distance_m
        for edge in projected.edges
        if known_edge_id(edge) in evidence.inbound_edge_ids
    )
    charged = max(0.0, raw - settings.maximum_shared_distance_near_turnaround_m)
    return charged, charged / evidence.inbound_distance_m


async def _reconstruct(
    source: SpurRepairSource,
    spur: RouteSpur,
    rejoin: RejoinCandidate,
    connector: RoutedPath,
    context: PlanningSearchContext,
) -> tuple[RoutedPath, tuple[Coordinate, ...]]:
    turnaround = _coordinate(spur.turnaround_coordinate)
    prefix = tuple(
        anchor.coordinate
        for anchor in source.anchors
        if anchor.route_progress <= spur.turnaround_progress + 1e-9
    )
    suffix = tuple(
        anchor.coordinate
        for anchor in source.anchors
        if anchor.route_progress > rejoin.source_progress + 1e-9
    )
    points = _deduplicate_adjacent((*prefix, turnaround, rejoin.coordinate, *suffix))
    if len(points) < 2:
        raise RouteCompositionError("spur reconstruction has too few routing points")
    connector_index = next(
        index
        for index, (left, right) in enumerate(zip(points, points[1:], strict=False))
        if _same_coordinate(left, turnaround)
        and _same_coordinate(right, rejoin.coordinate)
    )
    segments: list[RoutedPath] = []
    for index, (left, right) in enumerate(zip(points, points[1:], strict=False)):
        if index == connector_index:
            segments.append(connector)
            continue
        segments.append(
            await context.routes.route(
                (left, right),
                source.profile,
                pass_through=True,
                phase=SearchPhase.SPUR_REPAIR,
            )
        )
    return compose_routed_segments(tuple(segments)), points


def _improvement(
    source: SpurRepairSource,
    spur: RouteSpur,
    rejoin: RejoinCandidate,
    connector: RoutedPath,
    result: RouteResult,
    overlap_m: float,
    overlap_share: float,
    attempts: int,
    settings: SpurClosureSettings,
) -> tuple[SpurClosureDiagnostics | None, SpurRepairRejection | None]:
    if (
        source.maximum_distance_m is not None
        and result.summary.distance_m > source.maximum_distance_m
    ):
        return None, "explicit_maximum"
    _penalty, _components, severe = profile_quality_components(result)
    _source_penalty, _source_components, source_severe = profile_quality_components(
        source.route
    )
    if severe and not source_severe:
        return None, "profile_incompatibility"
    resulting = detect_route_spurs(result, topology=source.topology)
    source_repetition = source.route.analysis.repetition.repeated_distance.distance_m
    result_repetition = result.analysis.repetition.repeated_distance.distance_m
    if result_repetition > source_repetition + 1e-6:
        return None, "worse_total_repetition"
    spur_improvement = max(
        0.0,
        source.route.analysis.spurs.total_repeated_distance_m
        - resulting.total_repeated_distance_m,
    )
    backtrack_improvement = max(
        0.0,
        source.route.analysis.immediate_backtrack.distance_m
        - result.analysis.immediate_backtrack.distance_m,
    )
    if max(spur_improvement, backtrack_improvement) < (
        settings.minimum_repeated_distance_improvement_m
    ):
        return None, "trivial_improvement"
    matching = tuple(
        value
        for value in resulting.spurs
        if abs(value.turnaround_progress - spur.turnaround_progress) <= 0.10
    )
    resulting_target = max(
        (value.repeated_distance_m for value in matching), default=0.0
    )
    return (
        SpurClosureDiagnostics(
            source_candidate_id=source.source_candidate_id,
            targeted_spur_id=spur.id,
            rejoin_source=rejoin.source_kind,
            rejoin_progress=rejoin.source_progress,
            connector_distance_m=connector.distance_m,
            inbound_overlap_m=overlap_m,
            inbound_overlap_share=overlap_share,
            source_spur_repeated_distance_m=spur.repeated_distance_m,
            resulting_spur_repeated_distance_m=resulting_target,
            repeated_distance_improvement_m=spur_improvement,
            immediate_backtracking_improvement_m=backtrack_improvement,
            repair_attempt_count=attempts,
            targeted_spur_still_present=resulting_target > 0,
        ),
        None,
    )


def _preserves_exact_constraints(
    source: SpurRepairSource,
    points: tuple[Coordinate, ...],
) -> bool:
    expected = tuple(
        (anchor.coordinate.lat, anchor.coordinate.lon)
        for anchor in source.anchors
        if anchor.kind == "exact"
    )
    routed = tuple((point.lat, point.lon) for point in points)
    cursor = 0
    for key in expected:
        position = next(
            (index for index in range(cursor, len(routed)) if routed[index] == key),
            None,
        )
        if position is None:
            return False
        cursor = position + 1
    return True


def _coordinate(position: tuple[float, float]) -> Coordinate:
    return Coordinate(lon=position[0], lat=position[1])


def _deduplicate_adjacent(
    points: tuple[Coordinate, ...],
) -> tuple[Coordinate, ...]:
    retained: list[Coordinate] = []
    for point in points:
        if retained and _same_coordinate(retained[-1], point):
            continue
        retained.append(point)
    return tuple(retained)


def _same_coordinate(left: Coordinate, right: Coordinate) -> bool:
    return (left.lat, left.lon) == (right.lat, right.lon)
