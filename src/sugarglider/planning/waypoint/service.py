"""Native canonical Waypoint Route orchestration."""

from sugarglider.analysis.route import RouteAnalyzer
from sugarglider.planning.budget import SearchBudget, SearchPhase
from sugarglider.planning.constraints.resolver import (
    ConstraintResolution,
    ConstraintResolver,
)
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.diagnostics import PlanSearchDiagnostics
from sugarglider.planning.evaluator import CandidateEvaluator
from sugarglider.planning.models import WaypointPlanRequest
from sugarglider.planning.pipeline import evaluate_candidate_portfolio
from sugarglider.planning.refinement import (
    SpurClosureSettings,
    SpurRepairDiagnosticAccumulator,
    SpurRepairSource,
    refine_spur_closures,
)
from sugarglider.planning.refinement.models import SpurClosureDraft
from sugarglider.planning.refinement.rejoin import locate_repair_anchors
from sugarglider.planning.result import PlanCandidate, PlanResult
from sugarglider.planning.routing_gateway import SearchBudgetExhaustedError
from sugarglider.planning.validation import (
    CandidateEvaluationError,
    ExactWaypointNotReachedError,
    validate_waypoint_path,
)
from sugarglider.planning.waypoint.controls import control_proposal
from sugarglider.planning.waypoint.detours import target_detour_proposals
from sugarglider.planning.waypoint.drafts import waypoint_draft
from sugarglider.planning.waypoint.low_overlap import refine_low_overlap
from sugarglider.planning.waypoint.models import WaypointSequenceProposal
from sugarglider.planning.waypoint.ordering import ordering_proposals
from sugarglider.planning.waypoint.routing import route_proposal
from sugarglider.planning.waypoint.scoring import WaypointCandidateScorer
from sugarglider.pois.index import PoiIndex
from sugarglider.routing.backend import AutoTourRoutingBackend, RoutedPath
from sugarglider.routing.errors import RoutingError
from sugarglider.routing.result import RouteResultFactory


class WaypointPlanner:
    """Orchestrate proposals, shared routing/evaluation, and shared publication."""

    def __init__(
        self,
        backend: AutoTourRoutingBackend,
        result_factory: RouteResultFactory,
        *,
        max_evaluations: int = 48,
        structural_result_factory: RouteResultFactory | None = None,
        poi_index: PoiIndex | None = None,
    ) -> None:
        if max_evaluations < 1:
            raise ValueError("Waypoint search budget must be positive")
        self._backend = backend
        self._result_factory = result_factory
        self._structural_result_factory = (
            structural_result_factory or RouteResultFactory(RouteAnalyzer())
        )
        self._max_evaluations = max_evaluations
        self._poi_index = poi_index
        self._evaluator = CandidateEvaluator()
        self._scorer = WaypointCandidateScorer()

    async def generate(self, request: WaypointPlanRequest) -> PlanResult:
        context = PlanningSearchContext.create(
            backend=self._backend,
            budget=_waypoint_budget(request, self._max_evaluations),
        )
        repair_diagnostics = SpurRepairDiagnosticAccumulator()
        request, constraint_resolutions = await self._resolve_constraints(
            request, context
        )
        ordered, ordering_stats = ordering_proposals(
            request, limit=min(16, self._max_evaluations)
        )
        base_proposals = (control_proposal(request), *ordered)
        context.diagnostics.increment(
            "order_proposals_generated", ordering_stats.generated
        )
        context.diagnostics.increment(
            "order_proposals_deduplicated", ordering_stats.deduplicated
        )
        context.diagnostics.increment(
            "order_proposals_rejected_before_routing",
            ordering_stats.rejected_before_routing,
        )

        candidates: list[PlanCandidate] = []
        routed: list[tuple[WaypointSequenceProposal, RoutedPath, PlanCandidate]] = []
        exact_waypoint_failures: list[ExactWaypointNotReachedError] = []
        for proposal in base_proposals:
            evaluated = await self._route_and_evaluate(
                request=request,
                proposal=proposal,
                context=context,
                exact_waypoint_failures=exact_waypoint_failures,
                constraint_resolutions=constraint_resolutions,
            )
            if evaluated is not None:
                path, candidate = evaluated
                routed.append((proposal, path, candidate))
                candidates.append(candidate)

        control = next(
            (value for value in routed if value[0].construction == "fixed_control"),
            None,
        )
        if control is not None and (
            control[1].distance_m > request.distance_objective.target_m
        ):
            context.diagnostics.warnings.add("target_below_mandatory_lower_bound")

        detours, detour_stats = await target_detour_proposals(
            request=request,
            sources=tuple((proposal, path) for proposal, path, _ in routed[:3]),
            context=context,
        )
        context.diagnostics.increment(
            "detour_graph_proposals_requested",
            detour_stats.graph_proposals_requested,
        )
        context.diagnostics.increment(
            "detour_proposals_created", detour_stats.proposals_created
        )
        context.diagnostics.increment(
            "detour_proposals_rejected_before_routing",
            detour_stats.proposals_rejected_before_routing,
        )
        for proposal in detours:
            evaluated = await self._route_and_evaluate(
                request=request,
                proposal=proposal,
                context=context,
                phase=SearchPhase.SKELETON,
                exact_waypoint_failures=exact_waypoint_failures,
                constraint_resolutions=constraint_resolutions,
            )
            if evaluated is not None:
                path, candidate = evaluated
                routed.append((proposal, path, candidate))
                candidates.append(candidate)

        if request.preferences.path_selection == "low_overlap":
            await self._evaluate_low_overlap(
                request=request,
                sources=tuple(routed),
                context=context,
                destination=candidates,
                constraint_resolutions=constraint_resolutions,
            )

        await self._evaluate_spur_repairs(
            request=request,
            sources=tuple(routed),
            context=context,
            destination=candidates,
            constraint_resolutions=constraint_resolutions,
            diagnostics=repair_diagnostics,
        )

        portfolio = evaluate_candidate_portfolio(
            request,
            tuple(candidates),
            limit=request.candidate_count,
            ranking_key=lambda candidate: _waypoint_ranking_key(candidate, request),
        )
        if not portfolio.candidates and exact_waypoint_failures:
            raise min(
                exact_waypoint_failures,
                key=lambda error: (
                    error.point_index,
                    error.snap_distance_m,
                    error.point_name or "",
                ),
            )
        repair_diagnostics.published_repair_candidates += sum(
            candidate.diagnostics.details.get("construction") == "spur_closure_repair"
            for candidate in portfolio.candidates
        )
        repair_diagnostics.portfolio_excluded_repair_candidates += max(
            0,
            repair_diagnostics.repair_candidates_submitted_to_portfolio
            - repair_diagnostics.published_repair_candidates,
        )
        warnings = tuple(
            sorted(
                {
                    *context.diagnostics.warnings,
                    *context.diagnostics.rejections,
                    *portfolio.rejection_reasons,
                }
            )
        )
        diagnostics = PlanSearchDiagnostics(
            budget=context.budget.snapshot(),
            cache=context.routes.cache_snapshot(),
            warnings=warnings,
            details={
                **context.diagnostics.counters,
                "portfolio_count": len(portfolio.candidates),
                "spur_repair": repair_diagnostics.snapshot().as_dict(),
            },
        )
        return PlanResult(
            kind=request.kind,
            topology=request.topology,
            routing_profile=request.routing_profile,
            effective_start=request.start,
            effective_end=request.effective_end,
            candidates=portfolio.candidates,
            search_diagnostics=diagnostics,
        )

    async def _route_and_evaluate(
        self,
        *,
        request: WaypointPlanRequest,
        proposal: WaypointSequenceProposal,
        context: PlanningSearchContext,
        exact_waypoint_failures: list[ExactWaypointNotReachedError],
        constraint_resolutions: tuple[ConstraintResolution, ...],
        phase: SearchPhase | None = None,
    ) -> tuple[RoutedPath, PlanCandidate] | None:
        try:
            path = await route_proposal(
                request=request,
                proposal=proposal,
                context=context,
                phase=phase,
            )
            return path, self._evaluate_path(
                request, proposal, path, context, constraint_resolutions
            )
        except ExactWaypointNotReachedError as exc:
            exc.profile = request.routing_profile
            exact_waypoint_failures.append(exc)
            context.diagnostics.rejections.append(f"{proposal.construction}:{exc}")
            context.diagnostics.increment("candidates_rejected")
            return None
        except SearchBudgetExhaustedError as exc:
            context.diagnostics.warnings.add("route_budget_exhausted")
            context.diagnostics.rejections.append(f"{proposal.construction}:{exc}")
            context.diagnostics.increment("candidates_rejected")
            return None
        except (CandidateEvaluationError, RoutingError) as exc:
            context.diagnostics.rejections.append(f"{proposal.construction}:{exc}")
            context.diagnostics.increment("candidates_rejected")
            return None

    def _evaluate_path(
        self,
        request: WaypointPlanRequest,
        proposal: WaypointSequenceProposal,
        path: RoutedPath,
        context: PlanningSearchContext,
        constraint_resolutions: tuple[ConstraintResolution, ...],
        repair: SpurClosureDraft | None = None,
    ) -> PlanCandidate:
        draft = waypoint_draft(
            request=request,
            proposal=proposal,
            path=path,
            result_factory=self._result_factory,
            constraint_resolutions=constraint_resolutions,
            metadata=repair.diagnostics.metadata() if repair is not None else (),
        )
        context.diagnostics.increment("candidate_drafts_created")
        candidate = self._evaluator.evaluate(
            request=request,
            draft=draft,
            scorer=self._scorer,
        )
        context.diagnostics.increment("candidates_evaluated")
        return candidate

    async def _evaluate_spur_repairs(
        self,
        *,
        request: WaypointPlanRequest,
        sources: tuple[tuple[WaypointSequenceProposal, RoutedPath, PlanCandidate], ...],
        context: PlanningSearchContext,
        destination: list[PlanCandidate],
        constraint_resolutions: tuple[ConstraintResolution, ...],
        diagnostics: SpurRepairDiagnosticAccumulator,
    ) -> None:
        settings = SpurClosureSettings()
        ordered = sorted(
            sources,
            key=lambda value: (
                -value[2].diagnostics.spur_repeated_distance_m,
                value[2].diagnostics.immediate_backtracking_m,
                value[2].id,
            ),
        )[: settings.maximum_source_candidates]
        for proposal, path, candidate in ordered:
            deliberate = frozenset(
                (
                    anchor.routed_coordinate.lat,
                    anchor.routed_coordinate.lon,
                )
                for anchor in candidate.traversal.anchors
            )
            exact = frozenset((point.lat, point.lon) for point in proposal.exact_points)
            source = SpurRepairSource(
                source_candidate_id=candidate.id,
                route=candidate.route,
                routed_path=path,
                routing_points=proposal.routing_points,
                anchors=locate_repair_anchors(
                    candidate.route,
                    proposal.routing_points,
                    exact_coordinates=exact,
                    deliberate_coordinates=deliberate,
                ),
                topology=request.topology,
                profile=request.routing_profile,
                maximum_distance_m=request.distance_objective.maximum_m,
            )
            refined = await refine_spur_closures(
                source,
                context=context,
                result_factory=self._structural_result_factory,
                settings=settings,
                diagnostics=diagnostics,
            )
            context.diagnostics.warnings.update(refined.warnings)
            context.diagnostics.increment("spur_repair_attempts", refined.attempts)
            for repaired in refined.drafts:
                try:
                    repaired_proposal = _repaired_waypoint_proposal(proposal, repaired)
                    validate_waypoint_path(repaired_proposal, repaired.path)
                    evaluated = self._evaluate_path(
                        request,
                        repaired_proposal,
                        repaired.path,
                        context,
                        constraint_resolutions,
                        repair=repaired,
                    )
                except (CandidateEvaluationError, RoutingError, ValueError) as exc:
                    diagnostics.repair_drafts_rejected_after_acceptance += 1
                    if isinstance(exc, ValueError) and "exact waypoint" in str(exc):
                        diagnostics.reject("exact_constraints")
                    context.diagnostics.rejections.append(f"spur_closure_repair:{exc}")
                    context.diagnostics.increment("candidates_rejected")
                    continue
                destination.append(evaluated)
                diagnostics.repair_candidates_submitted_to_portfolio += 1
                context.diagnostics.increment("spur_repair_candidates")

    async def _evaluate_low_overlap(
        self,
        *,
        request: WaypointPlanRequest,
        sources: tuple[tuple[WaypointSequenceProposal, RoutedPath, PlanCandidate], ...],
        context: PlanningSearchContext,
        destination: list[PlanCandidate],
        constraint_resolutions: tuple[ConstraintResolution, ...],
    ) -> None:
        source_order = sorted(
            sources,
            key=lambda value: (
                value[2].diagnostics.target_error_m,
                value[2].id,
            ),
        )[:2]
        for proposal, _path, standard in source_order:
            refined = await refine_low_overlap(
                request=request,
                source=proposal,
                context=context,
                structural_result_factory=self._structural_result_factory,
            )
            context.diagnostics.increment("low_overlap_complete_paths", len(refined))
            for value in refined:
                try:
                    validate_waypoint_path(value.proposal, value.path)
                    candidate = self._evaluate_path(
                        request,
                        value.proposal,
                        value.path,
                        context,
                        constraint_resolutions,
                    )
                except (CandidateEvaluationError, RoutingError) as exc:
                    context.diagnostics.rejections.append(f"low_overlap_beam:{exc}")
                    context.diagnostics.increment("candidates_rejected")
                    continue
                if (
                    candidate.diagnostics.immediate_backtracking_m
                    > standard.diagnostics.immediate_backtracking_m + 1e-6
                ):
                    context.diagnostics.increment("low_overlap_backtracking_rejected")
                    continue
                destination.append(candidate)

    async def _resolve_constraints(
        self,
        request: WaypointPlanRequest,
        context: PlanningSearchContext,
    ) -> tuple[WaypointPlanRequest, tuple[ConstraintResolution, ...]]:
        resolver = ConstraintResolver(routes=context.routes, poi_index=self._poi_index)
        resolved_waypoints = []
        resolutions = []
        anchor = request.start
        for waypoint in request.waypoints:
            resolution = await resolver.resolve(
                constraint_id=waypoint.id,
                constraint_name=waypoint.name,
                semantic_coordinate=waypoint.coordinate,
                strength=waypoint.constraint_strength,
                anchor=anchor,
                profile=request.routing_profile,
                access_search_radius_m=waypoint.access_search_radius_m,
                maximum_best_effort_distance_m=(
                    waypoint.maximum_best_effort_distance_m
                ),
                approach_override=waypoint.approach_override,
            )
            resolutions.append(resolution)
            if resolution.routed_coordinate is not None:
                resolved_waypoints.append(
                    waypoint.model_copy(
                        update={"coordinate": resolution.routed_coordinate}
                    )
                )
                anchor = resolution.routed_coordinate
        return (
            request.model_copy(update={"waypoints": tuple(resolved_waypoints)}),
            tuple(resolutions),
        )


def _waypoint_budget(
    request: WaypointPlanRequest, max_evaluations: int
) -> SearchBudget:
    limits = {phase: 0 for phase in SearchPhase}
    approach = min(
        sum(waypoint.constraint_strength != "exact" for waypoint in request.waypoints),
        max_evaluations - 1,
    )
    limits[SearchPhase.APPROACH] = approach
    limits[SearchPhase.CONTROL] = 1
    remaining = max_evaluations - 1 - approach
    alternative = (
        min(16, remaining) if request.preferences.path_selection == "low_overlap" else 0
    )
    limits[SearchPhase.ALTERNATIVE_LEG] = alternative
    limits[SearchPhase.SKELETON] = remaining - alternative
    limits[SearchPhase.SPUR_REPAIR] = 48
    return SearchBudget(limits, total_limit=max_evaluations + 48)


def _repaired_waypoint_proposal(
    source: WaypointSequenceProposal,
    repaired: SpurClosureDraft,
) -> WaypointSequenceProposal:
    positions: list[int] = []
    cursor = 0
    for exact in source.exact_points:
        position = next(
            (
                index
                for index in range(cursor, len(repaired.routing_points))
                if repaired.routing_points[index] == exact
            ),
            None,
        )
        if position is None:
            raise ValueError("spur repair lost an exact waypoint")
        positions.append(position)
        cursor = position + 1
    return WaypointSequenceProposal(
        routing_points=repaired.routing_points,
        exact_points=source.exact_points,
        exact_point_positions=tuple(positions),
        original_indices=source.original_indices,
        exact_point_ids=source.exact_point_ids,
        topology=source.topology,
        construction="spur_closure_repair",
        order_provenance=source.order_provenance,
        detour_provenance="spur_closure_repair",
    )


def _waypoint_ranking_key(
    candidate: PlanCandidate, request: WaypointPlanRequest
) -> tuple[object, ...]:
    priority_weight = {
        "strict": 0,
        "balanced": 1,
        "flexible": 2,
    }[request.distance_objective.priority]
    diagnostics = candidate.diagnostics
    return (
        0 if diagnostics.safety_eligible else 1,
        -diagnostics.requested_stop_count,
        diagnostics.approximated_stop_count,
        sum(stop.distance_m for stop in candidate.approximated_stops),
        diagnostics.dropped_stop_count,
        0 if diagnostics.within_tolerance else 1,
        priority_weight,
        diagnostics.target_error_m,
        diagnostics.immediate_backtracking_m,
        diagnostics.repeated_distance_m,
        candidate.score.total,
        candidate.id,
    )
