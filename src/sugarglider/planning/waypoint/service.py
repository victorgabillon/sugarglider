"""Native canonical Waypoint Route orchestration."""

from sugarglider.analysis.route import RouteAnalyzer
from sugarglider.planning.budget import SearchBudget, SearchPhase
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.diagnostics import PlanSearchDiagnostics
from sugarglider.planning.evaluator import CandidateEvaluator
from sugarglider.planning.models import WaypointPlanRequest
from sugarglider.planning.pipeline import evaluate_candidate_portfolio
from sugarglider.planning.result import PlanCandidate, PlanResult
from sugarglider.planning.validation import (
    CandidateEvaluationError,
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
    ) -> None:
        if max_evaluations < 1:
            raise ValueError("Waypoint search budget must be positive")
        self._backend = backend
        self._result_factory = result_factory
        self._structural_result_factory = (
            structural_result_factory or RouteResultFactory(RouteAnalyzer())
        )
        self._max_evaluations = max_evaluations
        self._evaluator = CandidateEvaluator()
        self._scorer = WaypointCandidateScorer()

    async def generate(self, request: WaypointPlanRequest) -> PlanResult:
        context = PlanningSearchContext.create(
            backend=self._backend,
            budget=_waypoint_budget(request, self._max_evaluations),
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
        for proposal in base_proposals:
            evaluated = await self._route_and_evaluate(
                request=request,
                proposal=proposal,
                context=context,
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
            )

        portfolio = evaluate_candidate_portfolio(
            request,
            tuple(candidates),
            limit=request.candidate_count,
            ranking_key=lambda candidate: _waypoint_ranking_key(candidate, request),
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
            },
        )
        return PlanResult(
            kind=request.kind,
            topology=request.topology,
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
        phase: SearchPhase | None = None,
    ) -> tuple[RoutedPath, PlanCandidate] | None:
        try:
            path = await route_proposal(
                request=request,
                proposal=proposal,
                context=context,
                phase=phase,
            )
            return path, self._evaluate_path(request, proposal, path, context)
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
    ) -> PlanCandidate:
        draft = waypoint_draft(
            request=request,
            proposal=proposal,
            path=path,
            result_factory=self._result_factory,
        )
        context.diagnostics.increment("candidate_drafts_created")
        candidate = self._evaluator.evaluate(
            request=request,
            draft=draft,
            scorer=self._scorer,
        )
        context.diagnostics.increment("candidates_evaluated")
        return candidate

    async def _evaluate_low_overlap(
        self,
        *,
        request: WaypointPlanRequest,
        sources: tuple[tuple[WaypointSequenceProposal, RoutedPath, PlanCandidate], ...],
        context: PlanningSearchContext,
        destination: list[PlanCandidate],
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
                        request, value.proposal, value.path, context
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


def _waypoint_budget(
    request: WaypointPlanRequest, max_evaluations: int
) -> SearchBudget:
    limits = {phase: 0 for phase in SearchPhase}
    limits[SearchPhase.CONTROL] = 1
    remaining = max_evaluations - 1
    alternative = (
        min(16, remaining) if request.preferences.path_selection == "low_overlap" else 0
    )
    limits[SearchPhase.ALTERNATIVE_LEG] = alternative
    limits[SearchPhase.SKELETON] = remaining - alternative
    return SearchBudget(limits, total_limit=max_evaluations)


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
        0 if diagnostics.within_tolerance else 1,
        priority_weight,
        diagnostics.target_error_m,
        diagnostics.immediate_backtracking_m,
        diagnostics.repeated_distance_m,
        candidate.score.total,
        candidate.id,
    )
