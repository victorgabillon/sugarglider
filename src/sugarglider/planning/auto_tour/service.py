"""Canonical Auto Tour candidate production and publication."""

from sugarglider.nature.scoring import available_nature_score
from sugarglider.planning.alternative_legs import LowOverlapSettings
from sugarglider.planning.auto_tour.candidate_models import (
    AutoTourCandidate,
)
from sugarglider.planning.auto_tour.discovered_pois import shortlist_route_pois
from sugarglider.planning.auto_tour.discovered_search import DiscoveredSearchMixin
from sugarglider.planning.auto_tour.loop_search import LoopSearchMixin
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
    DroppedPoiStop,
    RequestedTourPlace,
    SelectedPoiStop,
)
from sugarglider.planning.auto_tour.open_search import OpenSearchMixin
from sugarglider.planning.auto_tour.optimization_adapter import (
    auto_tour_optimization_source,
)
from sugarglider.planning.auto_tour.quality import AutoTourQualityMixin
from sugarglider.planning.auto_tour.ranking import (
    canonical_auto_tour_key,
    score_route,
)
from sugarglider.planning.auto_tour.repairs import RepairSearchMixin
from sugarglider.planning.auto_tour.requested_search import RequestedSearchMixin
from sugarglider.planning.auto_tour.skeleton_search import SkeletonSearchMixin
from sugarglider.planning.auto_tour.state import AutoTourSettings, _Draft
from sugarglider.planning.auto_tour.through_routes import ThroughRouteSearchMixin
from sugarglider.planning.direction.analysis import analyze_route_direction
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.evaluator import CandidateEvaluator
from sugarglider.planning.models import AutoTourPlanRequest, PlanRequestBase
from sugarglider.planning.optimization import (
    GlobalOptimizationDiagnostics,
    GlobalOptimizationSettings,
    OptimizationDraft,
    optimization_source,
    optimize_tours,
    requested_outcomes_regress,
)
from sugarglider.planning.pipeline import evaluate_candidate_portfolio
from sugarglider.planning.profile_quality import profile_aware_drop_reason
from sugarglider.planning.result import (
    ApproximatedPlanStop,
    DroppedPlanStop,
    PlanCompromise,
    PlanResult,
    PlanScore,
    ReachedPlanStop,
    SelectionMethod,
    SelectionOrigin,
)
from sugarglider.planning.signatures import candidate_signature
from sugarglider.planning.validation import CandidateEvaluationError
from sugarglider.pois.index import PoiIndex
from sugarglider.routing.backend import AutoTourRoutingBackend
from sugarglider.routing.errors import RoutingError
from sugarglider.routing.result import RouteResultFactory


class AutoTourService(
    LoopSearchMixin,
    OpenSearchMixin,
    SkeletonSearchMixin,
    RequestedSearchMixin,
    DiscoveredSearchMixin,
    RepairSearchMixin,
    ThroughRouteSearchMixin,
    AutoTourQualityMixin,
):
    """Own dependencies while focused modules implement bounded search phases."""

    def __init__(
        self,
        backend: AutoTourRoutingBackend,
        result_factory: RouteResultFactory,
        *,
        poi_index: PoiIndex | None = None,
        settings: AutoTourSettings | None = None,
        nature_index_available: bool = False,
        structural_result_factory: RouteResultFactory | None = None,
        low_overlap_settings: LowOverlapSettings | None = None,
    ) -> None:
        self._backend = backend
        self._final_result_factory = result_factory
        self._poi_index = poi_index
        self._settings = settings or AutoTourSettings()
        self._nature_index_available = nature_index_available
        self._structural_result_factory = (
            structural_result_factory
            if structural_result_factory is not None
            else RouteResultFactory()
        )
        self._result_factory = self._structural_result_factory
        self._low_overlap_settings = low_overlap_settings or LowOverlapSettings()

    @property
    def final_result_factory(self) -> RouteResultFactory:
        return self._final_result_factory

    @property
    def structural_result_factory(self) -> RouteResultFactory:
        return self._structural_result_factory

    @property
    def poi_index(self) -> PoiIndex | None:
        return self._poi_index

    @property
    def global_optimization_route_request_budget(self) -> int:
        return self._settings.global_optimization_route_request_budget

    def rebuild_optimized_candidate(
        self,
        *,
        request: AutoTourSearchRequest,
        source: AutoTourCandidate,
        optimized: OptimizationDraft,
    ) -> AutoTourCandidate:
        """Rebuild Auto Tour semantics once for a global-archive state."""
        resolved_request = _optimized_auto_tour_request(request, optimized)
        direction_value = analyze_route_direction(
            optimized.route.geometry,
            resolved_request.resolved_endpoints.topology,
        )
        direction = (
            direction_value
            if direction_value in {"clockwise", "counterclockwise"}
            else "mixed"
        )
        draft = _Draft(
            route=optimized.route,
            routed_path=optimized.path,
            routing_points=optimized.routing_points,
            signature=candidate_signature(
                optimized.route,
                topology=resolved_request.resolved_endpoints.topology,
                routing_profile=resolved_request.profile,
            ),
            construction="edge_aware_global_optimization",
            skeleton_id=source.skeleton_id,
            skeleton_method=source.skeleton_method,
            direction=direction,
            direction_warnings=(),
            hard_point_visits=self._hard_point_visits(
                resolved_request,
                optimized.routing_points,
                optimized.path.snapped_points,
            ),
        )
        source_draft = _Draft(
            route=source.route,
            routed_path=source.routed_path or optimized.path,
            routing_points=source.routing_points,
            signature=source.signature,
            construction=source.construction,
            skeleton_id=source.skeleton_id,
            skeleton_method=source.skeleton_method,
            direction=source.direction,
            direction_warnings=(),
            hard_point_visits=source.hard_point_visits,
        )
        shortlist = shortlist_route_pois(
            index=self._poi_index,
            route_geometry=optimized.route.geometry,
            routing_points=optimized.routing_points,
            request=resolved_request,
            settings=self._settings.poi,
        )
        deliberate_requested = frozenset(
            visit.requested_place.original_index
            for visit in source.requested_place_visits
            if visit.deliberately_routed
            and visit.requested_place.original_index is not None
        )
        candidate = self._search_candidate(
            request=resolved_request,
            draft=draft,
            visits=shortlist.already_collected,
            rejected=shortlist.rejected,
            family_control=source_draft,
            inserted=True,
            deliberately_routed_requested_indices=deliberate_requested,
        )
        comparison = candidate.control_comparison
        rejection_reasons = tuple(
            reason
            for reason in comparison.rejection_reasons
            if reason != "no_positive_soft_objective"
        )
        comparison = comparison.model_copy(
            update={
                "eligible": not rejection_reasons,
                "rejection_reasons": rejection_reasons,
            }
        )
        return candidate.model_copy(
            update={
                "control_eligible": comparison.eligible,
                "control_comparison": comparison,
                "repair_metadata": optimized.metadata(),
            }
        )


class AutoTourCandidateScorer:
    """Compute the final score from immutable mode-specific quality inputs."""

    def score(self, *, request: PlanRequestBase, draft: CandidateDraft) -> PlanScore:
        if not isinstance(request, AutoTourPlanRequest):
            raise TypeError("Auto Tour scorer requires an Auto Tour request")
        route_score = score_route(draft.route, request.distance_objective.target_m)
        return PlanScore(
            total=route_score.total,
            components={
                "distance_error_ratio": route_score.distance_error_ratio,
                "repetition_penalty": route_score.repetition_penalty,
                "major_road_penalty": route_score.major_road_penalty,
                "paved_penalty": route_score.paved_penalty,
                "unknown_surface_penalty": route_score.unknown_surface_penalty,
                "trail_like_reward": route_score.trail_like_reward,
                "hiking_network_reward": route_score.hiking_network_reward,
                "profile_quality_penalty": route_score.profile_quality_penalty,
                "poi_reward": dict(draft.quality_inputs).get("poi_reward", 0.0),
            },
        )


class AutoTourPlanner:
    """Produce Auto Tour routes and publish only canonical planning models."""

    def __init__(self, search: AutoTourService) -> None:
        self._search = search
        self._evaluator = CandidateEvaluator(search.final_result_factory)
        self._scorer = AutoTourCandidateScorer()

    async def generate(self, request: AutoTourPlanRequest) -> PlanResult:
        result = await self._search.generate(_search_request(request))
        original_candidates = tuple(
            self._evaluator.evaluate(
                request=request,
                draft=_candidate_draft(candidate, request),
                scorer=self._scorer,
            )
            for candidate in result.candidates
        )
        candidates = [*original_candidates]
        optimization_settings = GlobalOptimizationSettings(
            maximum_uncached_global_optimizer_calls=(
                self._search.global_optimization_route_request_budget
            )
        )
        optimization_diagnostics = GlobalOptimizationDiagnostics(
            graphhopper_call_limit=(
                optimization_settings.maximum_uncached_global_optimizer_calls
            ),
            complete_evaluation_limit=(optimization_settings.complete_evaluation_limit),
        )
        optimization_sources = []
        internal_by_id: dict[str, AutoTourCandidate] = {}
        evaluated_by_id = {candidate.id: candidate for candidate in original_candidates}
        for source, evaluated_source in zip(
            result.candidates,
            original_candidates,
            strict=True,
        ):
            if source.routed_path is None:
                continue
            local_source = auto_tour_optimization_source(
                request=request,
                resolved_request=result.resolved_request,
                source=source,
                evaluated=evaluated_source,
                poi_index=self._search.poi_index,
            )
            optimization_sources.append(
                optimization_source(local_source, evaluated_source)
            )
            internal_by_id[evaluated_source.id] = source
        optimized = await optimize_tours(
            tuple(optimization_sources),
            context=result.search_context,
            result_factory=self._search.structural_result_factory,
            seed=request.seed,
            settings=optimization_settings,
            diagnostics=optimization_diagnostics,
        )
        for optimized_draft in optimized.drafts:
            if (
                optimization_diagnostics.complete_evaluations
                >= optimization_settings.complete_evaluation_limit
            ):
                break
            optimization_diagnostics.complete_evaluations += 1
            optimization_diagnostics.composition_states_evaluated += int(
                len(optimized_draft.applied_spur_repairs) > 1
            )
            source = internal_by_id[optimized_draft.source_candidate_id]
            evaluated_source = evaluated_by_id[optimized_draft.source_candidate_id]
            try:
                rebuilt = self._search.rebuild_optimized_candidate(
                    request=result.resolved_request,
                    source=source,
                    optimized=optimized_draft,
                )
                if not rebuilt.control_eligible:
                    optimization_diagnostics.states_pruned_infeasible += 1
                    continue
                evaluated_optimized = self._evaluator.evaluate(
                    request=request,
                    draft=_candidate_draft(rebuilt, request),
                    scorer=self._scorer,
                )
                if requested_outcomes_regress(evaluated_source, evaluated_optimized):
                    optimization_diagnostics.states_pruned_coverage += 1
                    continue
                if not evaluated_optimized.diagnostics.safety_eligible:
                    optimization_diagnostics.states_pruned_profile += 1
                    continue
            except (CandidateEvaluationError, RoutingError, ValueError):
                optimization_diagnostics.states_pruned_infeasible += 1
                continue
            candidates.append(evaluated_optimized)
            optimization_diagnostics.feasible_evaluated_candidates += 1
        evaluated = evaluate_candidate_portfolio(
            request,
            tuple(candidates),
            limit=request.candidate_count,
            ranking_key=lambda candidate: canonical_auto_tour_key(
                candidate,
                request.distance_objective.priority,
                include_nature=all(
                    available_nature_score(value.route.analysis.nature) is not None
                    for value in candidates
                ),
            ),
        )
        optimization_diagnostics.published_candidates = sum(
            candidate.diagnostics.details.get("construction")
            == "edge_aware_global_optimization"
            for candidate in evaluated.candidates
        )
        for candidate in evaluated.candidates:
            final_target_ids = candidate.diagnostics.details.get(
                "targeted_spur_ids", ()
            )
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
        diagnostic_details = {
            **result.diagnostics.details,
            "global_optimization": optimization_diagnostics.as_dict(),
            "best_excluded_refinement": evaluated.best_excluded_refinement,
            "best_excluded_structural_refinements": (
                evaluated.best_excluded_structural_refinements
            ),
        }
        return PlanResult(
            kind=request.kind,
            topology=request.topology,
            routing_profile=request.routing_profile,
            effective_start=request.start,
            effective_end=request.effective_end,
            candidates=evaluated.candidates,
            search_diagnostics=evaluated.attach_rejections(
                result.diagnostics.model_copy(
                    update={
                        "budget": result.search_context.budget.snapshot(),
                        "cache": result.search_context.routes.cache_snapshot(),
                        "warnings": tuple(
                            sorted(
                                {
                                    *result.diagnostics.warnings,
                                    *optimized.warnings,
                                }
                            )
                        ),
                        "details": diagnostic_details,
                    }
                )
            ),
        )


def _optimized_auto_tour_request(
    request: AutoTourSearchRequest,
    optimized: OptimizationDraft,
) -> AutoTourSearchRequest:
    selected = dict(optimized.selected_approaches)
    places: list[RequestedTourPlace] = []
    for place in request.requested_stops:
        approach = selected.get(place.id or "")
        if approach is None:
            places.append(place)
            continue
        candidates = {
            candidate.id: candidate for candidate in place.approach_candidates
        }
        candidates[approach.id] = approach
        places.append(
            place.model_copy(
                update={
                    "approach_candidates": tuple(candidates.values()),
                    "chosen_approach": approach,
                }
            )
        )
    return request.model_copy(update={"requested_stops": tuple(places)})


def _search_request(request: AutoTourPlanRequest) -> AutoTourSearchRequest:
    objective = request.distance_objective
    preferences = request.preferences
    return AutoTourSearchRequest(
        name=request.name,
        start=request.start,
        end=request.end,
        topology=request.topology,
        target_distance_m=objective.target_m,
        tolerance_m=objective.tolerance_m,
        maximum_distance_m=objective.maximum_m,
        candidate_count=request.candidate_count,
        seed=request.seed,
        profile=request.routing_profile,
        direction_preference=preferences.direction,
        hard_waypoints=tuple(
            waypoint.coordinate.model_copy(update={"name": waypoint.name})
            for waypoint in request.hard_waypoints
        ),
        requested_stops=tuple(
            RequestedTourPlace(
                id=stop.id,
                name=stop.name,
                coordinate=stop.semantic_coordinate,
                access_search_radius_m=stop.access_search_radius_m,
                importance=stop.importance,
                constraint_strength=stop.constraint_strength,
                osm_reference=stop.osm_reference,
                approach_override=stop.approach_override,
                maximum_best_effort_distance_m=(stop.maximum_best_effort_distance_m),
                original_index=index,
            )
            for index, stop in enumerate(request.requested_stops)
        ),
        preferred_poi_ids=request.preferred_discovered_poi_ids,
        distance_priority=objective.priority,
        scenic_preference=preferences.scenic,
        drinking_water_preference=preferences.drinking_water,
        nature_preference=preferences.nature,
        loop_geometry_preference=preferences.loop_geometry,
        path_selection_mode=preferences.path_selection,
        free_poi_spur_physical_m=request.free_poi_spur_physical_m,
    )


def _candidate_draft(
    candidate: AutoTourCandidate, request: AutoTourPlanRequest
) -> CandidateDraft:
    reached = tuple(_reached_stop(stop, request) for stop in candidate.selected_stops)
    approximated = _approximated_stops(candidate, request)
    approximated_ids = {stop.id for stop in approximated}
    dropped = tuple(
        _dropped_stop(stop, request)
        for stop in candidate.dropped_stops
        if stop.semantic_poi.id not in approximated_ids
    )
    return CandidateDraft(
        route=candidate.route,
        routed_path=candidate.routed_path,
        routing_points=candidate.routing_points,
        topology=request.topology,
        construction=candidate.construction,
        search_family="auto_tour",
        reached_stops=reached,
        approximated_stops=approximated,
        dropped_stops=dropped,
        compromises=tuple(
            _approximation_compromise(stop, request) for stop in approximated
        ),
        quality_inputs=(("poi_reward", candidate.total_poi_reward),),
        maximum_distance_m=request.distance_objective.maximum_m,
        structural_safety_eligible=all(
            visit.selected for visit in candidate.hard_point_visits
        ),
        metadata=(
            ("direction", candidate.direction),
            ("producer_control_eligible", str(candidate.control_eligible)),
            ("selected_scenic_count", str(candidate.selected_scenic_count)),
            (
                "selected_verified_water_count",
                str(candidate.selected_verified_water_count),
            ),
            *candidate.repair_metadata,
        ),
    )


def _reached_stop(
    stop: SelectedPoiStop, request: AutoTourPlanRequest
) -> ReachedPlanStop:
    semantic = stop.semantic_poi
    return ReachedPlanStop(
        id=semantic.id,
        name=semantic.name,
        semantic_coordinate=semantic.coordinate,
        category=semantic.category,
        importance=semantic.importance,
        selection_origin=_origin(semantic.origin, semantic.id, request),
        selection_method=_method(stop),
        resolved_approach=stop.chosen_approach,
        route_progress=stop.route_progress_share,
        route_to_approach_m=stop.measured_route_to_approach_m,
    )


def _dropped_stop(
    stop: DroppedPoiStop, request: AutoTourPlanRequest
) -> DroppedPlanStop:
    semantic = stop.semantic_poi
    reason = profile_aware_drop_reason(request.routing_profile, stop.drop_reason)
    return DroppedPlanStop(
        id=semantic.id,
        name=semantic.name,
        semantic_coordinate=semantic.coordinate,
        category=semantic.category,
        importance=semantic.importance,
        selection_origin=_origin(semantic.origin, semantic.id, request),
        reason=reason,
        considered_approaches=stop.approach_candidates_considered,
    )


def _approximated_stops(
    candidate: AutoTourCandidate, request: AutoTourPlanRequest
) -> tuple[ApproximatedPlanStop, ...]:
    values: list[ApproximatedPlanStop] = []
    snapped = candidate.snapped_routing_points
    if snapped is None:
        return ()
    for visit in candidate.requested_place_visits:
        place = visit.requested_place
        approach = visit.chosen_approach
        if (
            visit.decision != "dropped"
            or place.constraint_strength != "best_effort"
            or not visit.deliberately_routed
            or approach is None
            or visit.graph_snap_distance_m is None
        ):
            continue
        maximum = place.maximum_best_effort_distance_m or place.access_search_radius_m
        if visit.graph_snap_distance_m > maximum:
            continue
        point_index = next(
            (
                index
                for index, point in enumerate(candidate.routing_points)
                if (point.lat, point.lon)
                == (approach.coordinate.lat, approach.coordinate.lon)
            ),
            None,
        )
        if point_index is None or point_index >= len(snapped):
            continue
        routed_lon, routed_lat = snapped[point_index]
        routed = approach.coordinate.model_copy(
            update={"lat": routed_lat, "lon": routed_lon}
        )
        resolved_approach = approach.model_copy(
            update={
                "coordinate": routed,
                "kind": "strict_graph_snap",
                "semantic_distance_m": visit.graph_snap_distance_m,
                "provenance": "profile_snap_fallback",
            }
        )
        public = next(stop for stop in request.requested_stops if stop.id == place.id)
        values.append(
            ApproximatedPlanStop(
                id=public.id,
                name=public.name,
                semantic_coordinate=public.semantic_coordinate,
                category="requested_place",
                importance=public.importance,
                selection_origin="requested",
                resolved_approach=resolved_approach,
                route_progress=visit.route_progress_share,
                distance_m=visit.graph_snap_distance_m,
                normal_tolerance_m=visit.arrival_tolerance_m,
                configured_maximum_m=maximum,
                reason="nearest_routeable_point_used",
            )
        )
    return tuple(values)


def _approximation_compromise(
    stop: ApproximatedPlanStop, request: AutoTourPlanRequest
) -> PlanCompromise:
    return PlanCompromise(
        code="stop_approximated",
        severity="warning",
        constraint_id=stop.id,
        constraint_name=stop.name,
        semantic_coordinate=stop.semantic_coordinate,
        routed_coordinate=stop.resolved_approach.coordinate,
        distance_m=stop.distance_m,
        normal_tolerance_m=stop.normal_tolerance_m,
        configured_maximum_m=stop.configured_maximum_m,
        reason=stop.reason,
        profile=request.routing_profile,
        suggestion="Review the fallback, make the stop exact, or remove it.",
    )


def _origin(origin: str, poi_id: str, request: AutoTourPlanRequest) -> SelectionOrigin:
    if origin == "requested":
        return "requested"
    if poi_id in request.preferred_discovered_poi_ids:
        return "user_preferred"
    return "discovered"


def _method(stop: SelectedPoiStop) -> SelectionMethod:
    if stop.selection_reason == "already_on_route":
        return "already_reached"
    if stop.selection_reason == "corridor_continuation":
        return "corridor_continuation"
    if stop.selection_reason == "shared_excursion":
        return "shared_excursion"
    if stop.excursion_id is not None:
        return "short_excursion"
    return "deliberate_insertion"
