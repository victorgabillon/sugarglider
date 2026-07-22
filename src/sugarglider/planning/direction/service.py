"""Focused graph-valid reverse planning through the shared routing boundary."""

from dataclasses import dataclass
from time import perf_counter

from shapely.geometry import Point

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.domain.models import Coordinate
from sugarglider.planning.auto_tour.service import AutoTourCandidateScorer
from sugarglider.planning.budget import SearchBudget, SearchPhase
from sugarglider.planning.constraints.outcomes import constraint_outcomes
from sugarglider.planning.constraints.resolver import (
    ConstraintResolution,
    ConstraintResolver,
)
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.diagnostics import PlanSearchDiagnostics
from sugarglider.planning.direction.anchors import sample_shape_anchors
from sugarglider.planning.direction.models import (
    ReversePlanRequest,
    ReversePlanResponse,
    ReverseRouteVariant,
)
from sugarglider.planning.direction.transform import transform_reverse_request
from sugarglider.planning.direction.validation import validate_reverse_source
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.evaluator import CandidateEvaluator, CandidateScorer
from sugarglider.planning.models import (
    AutoTourPlanRequest,
    ExactWaypoint,
    PlanRequest,
    RequestedStop,
    RouteWaypoint,
)
from sugarglider.planning.pipeline import evaluate_candidate_portfolio
from sugarglider.planning.result import PlanCandidate, PlanResult, ReachedPlanStop
from sugarglider.planning.routing_gateway import SearchBudgetExhaustedError
from sugarglider.planning.validation import (
    CandidateEvaluationError,
    ExactWaypointNotReachedError,
    validate_waypoint_path,
)
from sugarglider.planning.waypoint.models import WaypointSequenceProposal
from sugarglider.planning.waypoint.scoring import WaypointCandidateScorer
from sugarglider.pois.index import PoiIndex
from sugarglider.routing.backend import AutoTourRoutingBackend, RoutedPath
from sugarglider.routing.errors import RoutingError
from sugarglider.routing.result import RouteResultFactory

MAX_REVERSE_ROUTE_CALLS = 3


@dataclass(frozen=True)
class _IntentAnchor:
    id: str
    coordinate: Coordinate
    target_progress: float
    exact: bool
    point_index: int


class ReversePlanner:
    """Reroute opposite traversal intent without launching a global mode search."""

    def __init__(
        self,
        backend: AutoTourRoutingBackend,
        result_factory: RouteResultFactory,
        *,
        poi_index: PoiIndex | None = None,
    ) -> None:
        self._backend = backend
        self._result_factory = result_factory
        self._poi_index = poi_index
        self._evaluator = CandidateEvaluator()
        self._waypoint_scorer = WaypointCandidateScorer()
        self._auto_tour_scorer = AutoTourCandidateScorer()

    async def reverse(self, posted: ReversePlanRequest) -> ReversePlanResponse:
        started = perf_counter()
        source = posted.source_request
        validate_reverse_source(source, posted.candidate)
        transformed = transform_reverse_request(
            source, posted.candidate, candidate_count=posted.candidate_count
        )
        soft_count = _soft_count(transformed)
        context = PlanningSearchContext.create(
            backend=self._backend,
            budget=_reverse_budget(soft_count, posted.candidate_count),
        )
        resolutions = await self._resolve_soft_constraints(transformed, context)
        variants = _reverse_variants(
            transformed,
            posted.candidate,
            resolutions,
            posted.candidate_count,
        )
        candidates: list[PlanCandidate] = []
        exact_failures: list[ExactWaypointNotReachedError] = []
        for variant_index, variant in enumerate(variants):
            try:
                path = await context.routes.route(
                    variant.points,
                    transformed.routing_profile,
                    pass_through=transformed.topology == "point_to_point",
                    phase=SearchPhase.REVERSE,
                    topology_options=(
                        ("topology", transformed.topology),
                        ("operation", "reverse"),
                        ("variant", str(variant_index)),
                    ),
                )
                _validate_exact_path(transformed, variant, path)
                candidates.append(
                    self._evaluate(
                        transformed,
                        posted.candidate,
                        variant,
                        path,
                        resolutions,
                    )
                )
                if len(candidates) >= posted.candidate_count:
                    break
            except ExactWaypointNotReachedError as exc:
                exc.profile = transformed.routing_profile
                exact_failures.append(exc)
                context.diagnostics.rejections.append(f"reversed_route:{exc}")
            except (CandidateEvaluationError, RoutingError) as exc:
                context.diagnostics.rejections.append(f"reversed_route:{exc}")
            except SearchBudgetExhaustedError:
                context.diagnostics.warnings.add("reverse_route_budget_exhausted")
                break
        if not candidates and exact_failures:
            raise min(exact_failures, key=lambda error: error.point_index)
        portfolio = evaluate_candidate_portfolio(
            transformed,
            tuple(candidates),
            limit=posted.candidate_count,
        )
        if not portfolio.candidates:
            raise ReverseRouteUnavailableError
        selected = portfolio.candidates[0]
        elapsed = perf_counter() - started
        warnings = {
            *context.diagnostics.warnings,
            *context.diagnostics.rejections,
            *portfolio.rejection_reasons,
        }
        distance_change = abs(
            selected.route.summary.distance_m
            - posted.candidate.route.summary.distance_m
        )
        if distance_change > max(
            100.0, posted.candidate.route.summary.distance_m * 0.01
        ):
            warnings.add("opposite_direction_uses_different_roads")
        details = {
            "source_candidate_id": posted.candidate.id,
            "source_direction": posted.candidate.traversal.direction,
            "resulting_direction": selected.traversal.direction,
            "deliberate_anchor_count": _deliberate_count(selected),
            "internal_shape_anchor_count": int(
                selected.diagnostics.details.get("internal_shape_anchor_count", 0)
            ),
            "internal_shape_anchors_removed": int(
                selected.diagnostics.details.get("internal_shape_anchors_removed", 0)
            ),
            "reverse_route_calls": context.budget.used(SearchPhase.REVERSE),
            "reverse_elapsed_seconds": round(elapsed, 6),
            "portfolio_count": len(portfolio.candidates),
        }
        result = PlanResult(
            kind=transformed.kind,
            topology=transformed.topology,
            routing_profile=transformed.routing_profile,
            effective_start=transformed.start,
            effective_end=transformed.effective_end,
            candidates=portfolio.candidates,
            search_diagnostics=PlanSearchDiagnostics(
                budget=context.budget.snapshot(),
                cache=context.routes.cache_snapshot(),
                warnings=tuple(sorted(warnings)),
                details=details,
            ),
        )
        return ReversePlanResponse(
            transformed_request=transformed,
            result=result,
            source_candidate_id=posted.candidate.id,
        )

    async def _resolve_soft_constraints(
        self, request: PlanRequest, context: PlanningSearchContext
    ) -> tuple[ConstraintResolution, ...]:
        resolver = ConstraintResolver(routes=context.routes, poi_index=self._poi_index)
        resolutions: list[ConstraintResolution] = []
        anchor = request.start
        for value in _soft_constraints(request):
            coordinate = (
                value.semantic_coordinate
                if isinstance(value, RequestedStop)
                else value.coordinate
            )
            resolution = await resolver.resolve(
                constraint_id=value.id,
                constraint_name=value.name,
                semantic_coordinate=coordinate,
                strength=value.constraint_strength,
                anchor=anchor,
                profile=request.routing_profile,
                access_search_radius_m=value.access_search_radius_m,
                maximum_best_effort_distance_m=(value.maximum_best_effort_distance_m),
                osm_reference=(
                    value.osm_reference if isinstance(value, RequestedStop) else None
                ),
                approach_override=value.approach_override,
            )
            resolutions.append(resolution)
            if resolution.routed_coordinate is not None:
                anchor = resolution.routed_coordinate
        return tuple(resolutions)

    def _evaluate(
        self,
        request: PlanRequest,
        source: PlanCandidate,
        variant: ReverseRouteVariant,
        path: RoutedPath,
        resolutions: tuple[ConstraintResolution, ...],
    ) -> PlanCandidate:
        route = self._result_factory.create(
            name=request.name,
            path=path,
            input_point_count=len(variant.points),
            routing_profile=request.routing_profile,
        )
        reached, approximated, dropped, compromises = constraint_outcomes(
            route.geometry, request.routing_profile, resolutions
        )
        discovered = _revalidated_discovered(source, route.geometry)
        draft = CandidateDraft(
            route=route,
            routed_path=path,
            routing_points=variant.points,
            topology=request.topology,
            construction="reversed_route",
            search_family="reverse",
            reached_stops=(*reached, *discovered),
            approximated_stops=approximated,
            dropped_stops=dropped,
            compromises=compromises,
            metadata=(
                ("source_candidate_id", source.id),
                ("source_direction", source.traversal.direction),
                ("internal_shape_anchor_count", str(variant.shape_anchor_count)),
                (
                    "internal_shape_anchors_removed",
                    str(variant.shape_anchors_removed),
                ),
            ),
            maximum_distance_m=request.distance_objective.maximum_m,
        )
        return self._evaluator.evaluate(
            request=request,
            draft=draft,
            scorer=_scorer(request, self._auto_tour_scorer, self._waypoint_scorer),
        )


class ReverseRouteUnavailableError(ValueError):
    """No bounded graph-valid opposite route could be published."""


def _reverse_budget(soft_count: int, candidate_count: int) -> SearchBudget:
    limits = {phase: 0 for phase in SearchPhase}
    limits[SearchPhase.APPROACH] = soft_count
    # The fixed cap permits a primary route plus deterministic shape-hint
    # reduction, while remaining independent of the full mode-search budgets.
    limits[SearchPhase.REVERSE] = MAX_REVERSE_ROUTE_CALLS
    return SearchBudget(limits)


def _soft_count(request: PlanRequest) -> int:
    return len(_soft_constraints(request))


def _soft_constraints(
    request: PlanRequest,
) -> tuple[RequestedStop | RouteWaypoint, ...]:
    if isinstance(request, AutoTourPlanRequest):
        return request.requested_stops
    return tuple(
        waypoint
        for waypoint in request.waypoints
        if waypoint.constraint_strength != "exact"
    )


def _scorer(
    request: PlanRequest,
    auto: AutoTourCandidateScorer,
    waypoint: WaypointCandidateScorer,
) -> CandidateScorer:
    return auto if isinstance(request, AutoTourPlanRequest) else waypoint


def _reverse_variants(
    request: PlanRequest,
    source: PlanCandidate,
    resolutions: tuple[ConstraintResolution, ...],
    candidate_count: int,
) -> tuple[ReverseRouteVariant, ...]:
    progress = {
        anchor.id: 1.0 - anchor.route_progress
        for anchor in source.traversal.anchors
        if anchor.kind not in {"start", "end"}
    }
    resolved = {
        resolution.constraint_id: resolution.routed_coordinate
        for resolution in resolutions
        if resolution.routed_coordinate is not None
    }
    intent: list[_IntentAnchor] = []
    exact_values: tuple[ExactWaypoint | RouteWaypoint, ...]
    if isinstance(request, AutoTourPlanRequest):
        exact_values = request.hard_waypoints
        ordered_values: tuple[ExactWaypoint | RequestedStop | RouteWaypoint, ...] = (
            *request.hard_waypoints,
            *request.requested_stops,
        )
    else:
        exact_values = tuple(
            waypoint
            for waypoint in request.waypoints
            if waypoint.constraint_strength == "exact"
        )
        # Waypoint Route has one ordered intent sequence. Keep exact and soft
        # constraints interleaved exactly as the transformed request specifies.
        ordered_values = request.waypoints
    exact_ids = {value.id for value in exact_values}
    for index, value in enumerate(ordered_values, start=1):
        exact = value.id in exact_ids
        if not exact and value.id not in resolved:
            # A dropped soft stop is accounting, not a routing coordinate. Never
            # silently route through its semantic position after resolution failed.
            continue
        coordinate = (
            value.semantic_coordinate
            if isinstance(value, RequestedStop)
            else value.coordinate
        )
        coordinate = resolved.get(value.id, coordinate)
        intent.append(
            _IntentAnchor(
                id=value.id,
                coordinate=coordinate,
                target_progress=progress.get(
                    ("exact/" if exact else "stop/") + value.id,
                    index / (len(ordered_values) + 1),
                ),
                exact=exact,
                point_index=index,
            )
        )
    source_discovered = [
        anchor
        for anchor in source.traversal.anchors
        if anchor.kind == "deliberate_discovered_stop"
    ]
    for source_anchor in source_discovered:
        intent.append(
            _IntentAnchor(
                id=source_anchor.id,
                coordinate=source_anchor.routed_coordinate,
                target_progress=1.0 - source_anchor.route_progress,
                exact=False,
                point_index=0,
            )
        )
    useful = len(intent)
    shapes = (
        sample_shape_anchors(source.route.geometry)
        if request.topology == "loop" and useful < 3
        else ()
    )
    shape_sets = [shapes]
    if shapes and candidate_count > 1:
        shape_sets.append(shapes[::2])
    if shapes:
        shape_sets.append(())
    variants: list[ReverseRouteVariant] = []
    seen: set[tuple[tuple[float, float], ...]] = set()
    for retained in shape_sets[: max(1, candidate_count + 2)]:
        combined: list[tuple[float, _IntentAnchor | None, Coordinate]] = [
            (intent_anchor.target_progress, intent_anchor, intent_anchor.coordinate)
            for intent_anchor in intent
        ]
        combined.extend(
            (1.0 - shape.source_progress, None, shape.coordinate) for shape in retained
        )
        combined.sort(
            key=lambda value: (
                value[0],
                "" if value[1] is None else value[1].id,
            )
        )
        interior = tuple(value[2] for value in combined)
        end = request.start if request.topology == "loop" else request.effective_end
        points = _deduplicate_points((request.start, *interior, end))
        key = tuple((point.lat, point.lon) for point in points)
        if key in seen:
            continue
        seen.add(key)
        exact_values_with_positions: list[tuple[int, str, Coordinate]] = [
            (0, "start", request.start)
        ]
        for intent_anchor in intent:
            if not intent_anchor.exact:
                continue
            position = points.index(intent_anchor.coordinate)
            exact_values_with_positions.append(
                (position, intent_anchor.id, intent_anchor.coordinate)
            )
        exact_values_with_positions.append(
            (
                len(points) - 1,
                "start" if request.topology == "loop" else "end",
                end,
            )
        )
        exact_values_with_positions.sort(key=lambda value: value[0])
        variants.append(
            ReverseRouteVariant(
                points=points,
                exact_points=tuple(value[2] for value in exact_values_with_positions),
                exact_positions=tuple(
                    value[0] for value in exact_values_with_positions
                ),
                exact_ids=tuple(value[1] for value in exact_values_with_positions),
                shape_anchor_count=len(retained),
                shape_anchors_removed=len(shapes) - len(retained),
            )
        )
    return tuple(variants)


def _deduplicate_points(points: tuple[Coordinate, ...]) -> tuple[Coordinate, ...]:
    values: list[Coordinate] = []
    for point in points:
        if not values or point != values[-1]:
            values.append(point)
    return tuple(values)


def _validate_exact_path(
    request: PlanRequest, variant: ReverseRouteVariant, path: RoutedPath
) -> None:
    proposal = WaypointSequenceProposal(
        routing_points=variant.points,
        exact_points=variant.exact_points,
        exact_point_positions=variant.exact_positions,
        original_indices=variant.exact_positions,
        exact_point_ids=variant.exact_ids,
        topology=request.topology,
        construction="reversed_route",
        order_provenance="reversed_traversal",
    )
    validate_waypoint_path(proposal, path)


def _revalidated_discovered(
    source: PlanCandidate, geometry: tuple[tuple[float, float], ...]
) -> tuple[ReachedPlanStop, ...]:
    projection = LocalMetricProjection(geometry[0][1])
    line = projection.project_line(geometry)
    values: list[ReachedPlanStop] = []
    deliberate_ids = {
        anchor.id.split("/", 1)[1]
        for anchor in source.traversal.anchors
        if anchor.kind == "deliberate_discovered_stop"
    }
    for stop in source.reached_stops:
        if stop.id not in deliberate_ids:
            continue
        point = Point(
            projection.project_position(
                (
                    stop.resolved_approach.coordinate.lon,
                    stop.resolved_approach.coordinate.lat,
                )
            )
        )
        distance = float(line.distance(point))
        if distance > stop.resolved_approach.arrival_tolerance_m:
            continue
        values.append(
            stop.model_copy(
                update={
                    "route_progress": (
                        float(line.project(point) / line.length)
                        if line.length > 0
                        else 0.0
                    ),
                    "route_to_approach_m": distance,
                }
            )
        )
    return tuple(values)


def _deliberate_count(candidate: PlanCandidate) -> int:
    return sum(
        anchor.kind not in {"start", "end"} for anchor in candidate.traversal.anchors
    )
