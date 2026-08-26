"""Native canonical Waypoint Route orchestration."""

from dataclasses import replace

from sugarglider.analysis.route import RouteAnalyzer
from sugarglider.nature.scoring import available_nature_score
from sugarglider.planning.budget import SearchBudget, SearchPhase
from sugarglider.planning.constraints.resolver import (
    ConstraintResolution,
    ConstraintResolver,
    mapped_approach_candidates,
)
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.diagnostics import PlanSearchDiagnostics
from sugarglider.planning.evaluator import CandidateEvaluator
from sugarglider.planning.models import WaypointPlanRequest
from sugarglider.planning.optimization import (
    GlobalOptimizationDiagnostics,
    GlobalOptimizationSettings,
    OptimizationDraft,
    SemanticOptimizationSource,
    SemanticRoutingAnchor,
    normalized_anchor_progress,
    optimization_source,
    optimize_tours,
    requested_outcomes_regress,
)
from sugarglider.planning.pipeline import evaluate_candidate_portfolio
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
from sugarglider.planning.waypoint.scoring import (
    WaypointCandidateScorer,
    waypoint_comparison_total,
)
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
        intent_request = request
        context = PlanningSearchContext.create(
            backend=self._backend,
            budget=_waypoint_budget(request, self._max_evaluations),
        )
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

        (
            optimization_diagnostics,
            optimization_warnings,
        ) = await self._evaluate_global_optimization(
            request=request,
            intent_request=intent_request,
            sources=tuple(routed),
            context=context,
            destination=candidates,
            constraint_resolutions=constraint_resolutions,
        )

        nature_comparable = all(
            available_nature_score(candidate.route.analysis.nature) is not None
            for candidate in candidates
        )
        portfolio = evaluate_candidate_portfolio(
            request,
            tuple(candidates),
            limit=request.candidate_count,
            ranking_key=lambda candidate: _waypoint_ranking_key(
                candidate, request, include_nature=nature_comparable
            ),
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
        optimization_diagnostics.published_candidates = sum(
            candidate.diagnostics.details.get("construction")
            == "edge_aware_global_optimization"
            for candidate in portfolio.candidates
        )
        for candidate in portfolio.candidates:
            final_target_ids = candidate.diagnostics.details.get(
                "targeted_spur_ids", ()
            )
            published_repairs = 0
            if isinstance(final_target_ids, (tuple, list)):
                published_repairs = optimization_diagnostics.record_published_spur_ids(
                    str(candidate.diagnostics.details.get("source_candidate_id", "")),
                    tuple(
                        spur_id
                        for spur_id in final_target_ids
                        if isinstance(spur_id, str)
                    ),
                )
            if published_repairs > 1:
                optimization_diagnostics.composition_states_published += 1
        warnings = tuple(
            sorted(
                {
                    *context.diagnostics.warnings,
                    *context.diagnostics.rejections,
                    *portfolio.rejection_reasons,
                    *optimization_warnings,
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
                "global_optimization": optimization_diagnostics.as_dict(),
                "best_excluded_refinement": portfolio.best_excluded_refinement,
                "best_excluded_structural_refinements": (
                    portfolio.best_excluded_structural_refinements
                ),
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
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> PlanCandidate:
        draft = waypoint_draft(
            request=request,
            proposal=proposal,
            path=path,
            result_factory=self._result_factory,
            constraint_resolutions=constraint_resolutions,
            metadata=metadata,
        )
        context.diagnostics.increment("candidate_drafts_created")
        candidate = self._evaluator.evaluate(
            request=request,
            draft=draft,
            scorer=self._scorer,
        )
        context.diagnostics.increment("candidates_evaluated")
        return candidate

    async def _evaluate_global_optimization(
        self,
        *,
        request: WaypointPlanRequest,
        intent_request: WaypointPlanRequest,
        sources: tuple[tuple[WaypointSequenceProposal, RoutedPath, PlanCandidate], ...],
        context: PlanningSearchContext,
        destination: list[PlanCandidate],
        constraint_resolutions: tuple[ConstraintResolution, ...],
    ) -> tuple[GlobalOptimizationDiagnostics, tuple[str, ...]]:
        settings = GlobalOptimizationSettings()
        diagnostics = GlobalOptimizationDiagnostics(
            graphhopper_call_limit=(settings.maximum_uncached_global_optimizer_calls),
            complete_evaluation_limit=settings.complete_evaluation_limit,
        )
        translated = []
        source_by_id: dict[str, tuple[WaypointSequenceProposal, PlanCandidate]] = {}
        for proposal, path, candidate in sources:
            anchor_source = _waypoint_optimization_source(
                request=request,
                intent_request=intent_request,
                proposal=proposal,
                path=path,
                candidate=candidate,
                resolutions=constraint_resolutions,
                poi_index=self._poi_index,
            )
            translated.append(optimization_source(anchor_source, candidate))
            source_by_id[candidate.id] = (proposal, candidate)
        result = await optimize_tours(
            tuple(translated),
            context=context,
            result_factory=self._structural_result_factory,
            seed=request.seed,
            settings=settings,
            diagnostics=diagnostics,
        )
        for optimized in result.drafts:
            if diagnostics.complete_evaluations >= settings.complete_evaluation_limit:
                break
            diagnostics.complete_evaluations += 1
            diagnostics.composition_states_evaluated += int(
                len(optimized.applied_spur_repairs) > 1
            )
            source_proposal, source_candidate = source_by_id[
                optimized.source_candidate_id
            ]
            try:
                optimized_proposal = _optimized_waypoint_proposal(
                    source_proposal, optimized
                )
                optimized_resolutions = _optimized_waypoint_resolutions(
                    constraint_resolutions, optimized
                )
                validate_waypoint_path(optimized_proposal, optimized.path)
                evaluated = self._evaluate_path(
                    request,
                    optimized_proposal,
                    optimized.path,
                    context,
                    optimized_resolutions,
                    metadata=optimized.metadata(),
                )
                if requested_outcomes_regress(source_candidate, evaluated):
                    diagnostics.states_pruned_coverage += 1
                    continue
                if not evaluated.diagnostics.safety_eligible:
                    diagnostics.states_pruned_profile += 1
                    continue
            except (CandidateEvaluationError, RoutingError, ValueError) as exc:
                diagnostics.states_pruned_infeasible += 1
                context.diagnostics.rejections.append(
                    f"edge_aware_global_optimization:{exc}"
                )
                context.diagnostics.increment("candidates_rejected")
                continue
            destination.append(evaluated)
            diagnostics.feasible_evaluated_candidates += 1
            context.diagnostics.increment("global_optimization_candidates")
        return diagnostics, result.warnings

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
    limits[SearchPhase.GLOBAL_OPTIMIZATION] = 64
    return SearchBudget(limits, total_limit=max_evaluations + 64)


def _waypoint_optimization_source(
    *,
    request: WaypointPlanRequest,
    intent_request: WaypointPlanRequest,
    proposal: WaypointSequenceProposal,
    path: RoutedPath,
    candidate: PlanCandidate,
    resolutions: tuple[ConstraintResolution, ...],
    poi_index: PoiIndex | None,
) -> SemanticOptimizationSource:
    resolution_by_coordinate = {
        (resolution.routed_coordinate.lat, resolution.routed_coordinate.lon): resolution
        for resolution in resolutions
        if resolution.routed_coordinate is not None
    }
    intent_by_id = {waypoint.id: waypoint for waypoint in intent_request.waypoints}
    exact_ids = dict(
        zip(
            proposal.exact_point_positions,
            proposal.exact_point_ids,
            strict=True,
        )
    )
    progress_by_id = {
        anchor.id.removeprefix("stop/"): anchor.route_progress
        for anchor in candidate.traversal.anchors
        if anchor.id.startswith("stop/")
    }
    anchors: list[SemanticRoutingAnchor] = []
    point_count = len(proposal.routing_points)
    for index, coordinate in enumerate(proposal.routing_points):
        route_progress = normalized_anchor_progress(index, point_count)
        if index in exact_ids:
            anchor_id = exact_ids[index] or f"exact/{index}"
            anchors.append(
                SemanticRoutingAnchor(
                    id=f"exact/{anchor_id}/{index}",
                    name=coordinate.name or str(anchor_id),
                    coordinate=coordinate,
                    semantic_coordinate=coordinate,
                    kind="exact",
                    route_progress=route_progress,
                )
            )
            continue
        resolution = resolution_by_coordinate.get((coordinate.lat, coordinate.lon))
        waypoint = (
            intent_by_id.get(resolution.constraint_id)
            if resolution is not None
            else None
        )
        eligible = (
            request.waypoint_order == "optimize"
            and resolution is not None
            and resolution.status in {"reached_approach", "approximated"}
            and resolution.approach is not None
            and waypoint is not None
            and waypoint.constraint_strength != "exact"
        )
        if not eligible:
            anchors.append(
                SemanticRoutingAnchor(
                    id=f"fixed/{index}",
                    name=coordinate.name or f"Routing point {index}",
                    coordinate=coordinate,
                    semantic_coordinate=coordinate,
                    kind="fixed",
                    route_progress=route_progress,
                )
            )
            continue
        assert resolution is not None
        assert resolution.approach is not None
        assert waypoint is not None
        _feature, mapped = mapped_approach_candidates(
            index=poi_index,
            coordinate=waypoint.coordinate,
            name=waypoint.name,
            osm_reference=None,
            radius_m=waypoint.access_search_radius_m,
        )
        approaches = tuple(
            {
                approach.id: approach for approach in (resolution.approach, *mapped)
            }.values()
        )
        anchors.append(
            SemanticRoutingAnchor(
                id=resolution.constraint_id,
                name=resolution.constraint_name,
                coordinate=coordinate,
                semantic_coordinate=resolution.semantic_coordinate,
                kind="soft",
                route_progress=progress_by_id.get(
                    resolution.constraint_id, route_progress
                ),
                constraint_strength=resolution.strength,
                outcome=(
                    "approximated" if resolution.status == "approximated" else "reached"
                ),
                current_approach=resolution.approach,
                approach_candidates=approaches,
                maximum_semantic_distance_m=(
                    resolution.approach.semantic_distance_m
                    if (
                        resolution.strength == "best_effort"
                        and resolution.approach.kind == "strict_graph_snap"
                    )
                    else (
                        waypoint.maximum_best_effort_distance_m
                        or waypoint.access_search_radius_m
                    )
                ),
            )
        )
    return SemanticOptimizationSource(
        source_candidate_id=candidate.id,
        route=candidate.route,
        routed_path=path,
        source_anchor_order=tuple(anchors),
        exact_boundary_indices=proposal.exact_point_positions,
        topology=request.topology,
        profile=request.routing_profile,
        target_distance_m=request.distance_objective.target_m,
        tolerance_m=request.distance_objective.tolerance_m,
        distance_priority=request.distance_objective.priority,
        maximum_distance_m=request.distance_objective.maximum_m,
    )


def _optimized_waypoint_proposal(
    source: WaypointSequenceProposal,
    optimized: OptimizationDraft,
) -> WaypointSequenceProposal:
    exact_positions = tuple(
        index
        for index, anchor in enumerate(optimized.anchors)
        if anchor.kind == "exact"
    )
    return WaypointSequenceProposal(
        routing_points=optimized.routing_points,
        exact_points=tuple(
            optimized.routing_points[index] for index in exact_positions
        ),
        exact_point_positions=exact_positions,
        original_indices=source.original_indices,
        exact_point_ids=source.exact_point_ids,
        topology=source.topology,
        construction="edge_aware_global_optimization",
        order_provenance="edge_aware_global_optimization",
        detour_provenance="edge_aware_global_optimization",
    )


def _optimized_waypoint_resolutions(
    resolutions: tuple[ConstraintResolution, ...],
    optimized: OptimizationDraft,
) -> tuple[ConstraintResolution, ...]:
    selected = dict(optimized.selected_approaches)
    values: list[ConstraintResolution] = []
    for resolution in resolutions:
        approach = selected.get(resolution.constraint_id)
        if approach is None:
            values.append(resolution)
            continue
        approximated = (
            resolution.strength == "best_effort"
            and approach.kind == "strict_graph_snap"
            and approach.semantic_distance_m > resolution.normal_tolerance_m
        )
        values.append(
            replace(
                resolution,
                status="approximated" if approximated else "reached_approach",
                routed_coordinate=approach.coordinate,
                approach=approach,
                distance_m=approach.semantic_distance_m,
                reason=(
                    "nearest_routeable_point_used"
                    if approximated
                    else "resolved_profile_compatible_approach"
                ),
                warnings=(("access_unknown",) if approach.access == "unknown" else ()),
            )
        )
    return tuple(values)


def _waypoint_ranking_key(
    candidate: PlanCandidate,
    request: WaypointPlanRequest,
    *,
    include_nature: bool = True,
) -> tuple[object, ...]:
    diagnostics = candidate.diagnostics
    return (
        0 if diagnostics.safety_eligible else 1,
        -diagnostics.requested_stop_count,
        diagnostics.approximated_stop_count,
        sum(stop.distance_m for stop in candidate.approximated_stops),
        diagnostics.dropped_stop_count,
        0 if diagnostics.within_tolerance else 1,
        {"strict": 0, "balanced": 1, "flexible": 2}[
            request.distance_objective.priority
        ],
        diagnostics.target_error_m,
        diagnostics.immediate_backtracking_m,
        diagnostics.repeated_distance_m,
        waypoint_comparison_total(
            candidate.score,
            include_nature=include_nature,
        ),
        candidate.id,
    )
