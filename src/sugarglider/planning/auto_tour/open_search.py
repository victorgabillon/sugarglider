"""Open Auto Tour orchestration."""

# mypy: disable-error-code="attr-defined"

from dataclasses import replace
from time import perf_counter

from sugarglider.domain.endpoints import validated_endpoint_visits
from sugarglider.planning.auto_tour.approaches import (
    choose_route_dependent_approaches,
)
from sugarglider.planning.auto_tour.candidate_models import (
    AutoTourCandidate,
)
from sugarglider.planning.auto_tour.decisions import (
    _apply_requested_search_failure_context,
    _discovered_decision_count,
    _dropped_discovered_count,
    _mark_cross_candidate_requested_routing,
    _selected_discovered_count,
    _with_requested_coverage_warning,
)
from sugarglider.planning.auto_tour.diagnostics import (
    AutoTourSearchResult,
    AutoTourSearchSummary,
    AutoTourTimings,
)
from sugarglider.planning.auto_tour.discovered_pois import (
    shortlist_route_pois,
)
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
)
from sugarglider.planning.auto_tour.search_support import (
    _deduplicate_candidates,
    _deduplicate_drafts,
    _hard_waypoints_by_direct_progress,
    _maximum_distance,
    _with_open_metrics,
)
from sugarglider.planning.auto_tour.selection import (
    _open_candidate_portfolio,
)
from sugarglider.planning.auto_tour.state import (
    AutoTourMaximumBelowDirectLowerBoundError,
    AutoTourNoCandidateError,
    _Draft,
    _InsertionState,
    _public_search_diagnostics,
    _search_budget,
    _SearchState,
)
from sugarglider.planning.budget import SearchPhase
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.signatures import candidate_signature
from sugarglider.routing.errors import (
    RoutingPointError,
)


class OpenSearchMixin:
    async def _generate_open_tour(
        self, request: AutoTourSearchRequest
    ) -> AutoTourSearchResult:
        """Run the bounded endpoint-fixed Auto Tour lane without round trips."""
        started = perf_counter()
        context = PlanningSearchContext.create(
            backend=self._backend, budget=_search_budget(self._settings)
        )
        state = _SearchState(budget=context.budget, context=context)
        warnings: set[str] = set()
        if self._poi_index is None:
            warnings.add("auto_tour_poi_index_unavailable")
        if request.nature_preference == "prefer" and not self._nature_index_available:
            warnings.add("auto_tour_nature_index_unavailable")

        direct_points = (request.effective_start, request.effective_end)
        direct_path = await self._route_points(
            direct_points, request.profile, SearchPhase.SKELETON, state
        )
        if direct_path is None or not self._valid_complete_path(
            direct_path, direct_points
        ):
            raise AutoTourNoCandidateError
        direct_route = self._result_factory.create(
            name=request.name,
            path=direct_path,
            input_point_count=2,
            routing_profile=request.profile,
        )
        if (
            request.maximum_distance_m is not None
            and request.maximum_distance_m < direct_route.summary.distance_m
        ):
            raise AutoTourMaximumBelowDirectLowerBoundError
        request = request.model_copy(
            update={
                "requested_stops": choose_route_dependent_approaches(
                    request.requested_stops, direct_route.geometry
                )
            }
        )
        direct_draft = _Draft(
            route=direct_route,
            routed_path=direct_path,
            routing_points=direct_points,
            signature=candidate_signature(direct_route, topology="point_to_point"),
            construction="point_to_point_direct",
            skeleton_id="point-to-point-direct",
            skeleton_method="point_to_point_direct",
            direction="mixed",
            direction_warnings=(),
            hard_point_visits=self._hard_point_visits(
                request, direct_points, direct_path.snapped_points
            ),
        )
        state.skeleton_candidates += 1
        if request.target_distance_m < direct_route.summary.distance_m:
            warnings.add("target_below_point_to_point_lower_bound")

        control_drafts: list[_Draft] = [direct_draft]
        exact_points = (
            request.effective_start,
            *_hard_waypoints_by_direct_progress(
                request.interior_hard_waypoints, direct_route.geometry
            ),
            request.effective_end,
        )
        primary_draft = direct_draft
        if exact_points != direct_points:
            exact_path = await self._route_points(
                exact_points, request.profile, SearchPhase.SKELETON, state
            )
            if exact_path is None or not self._valid_complete_path(
                exact_path, exact_points
            ):
                raise AutoTourNoCandidateError
            exact_route = self._result_factory.create(
                name=request.name,
                path=exact_path,
                input_point_count=len(exact_points),
                routing_profile=request.profile,
            )
            primary_draft = _Draft(
                route=exact_route,
                routed_path=exact_path,
                routing_points=exact_points,
                signature=candidate_signature(exact_route, topology="point_to_point"),
                construction="point_to_point_hard_waypoints",
                skeleton_id="point-to-point-hard-points",
                skeleton_method="point_to_point_hard_waypoints",
                direction="mixed",
                direction_warnings=(),
                hard_point_visits=self._hard_point_visits(
                    request, exact_points, exact_path.snapped_points
                ),
            )
            state.skeleton_candidates += 1
            control_drafts.append(primary_draft)

        original_hard_waypoints = (
            request.effective_start,
            *request.interior_hard_waypoints,
            request.effective_end,
        )
        if (
            len(request.interior_hard_waypoints) > 1
            and original_hard_waypoints != exact_points
        ):
            original_path = await self._route_points(
                original_hard_waypoints, request.profile, SearchPhase.SKELETON, state
            )
            if original_path is not None and self._valid_complete_path(
                original_path, original_hard_waypoints
            ):
                original_route = self._result_factory.create(
                    name=request.name,
                    path=original_path,
                    input_point_count=len(original_hard_waypoints),
                    routing_profile=request.profile,
                )
                control_drafts.append(
                    _Draft(
                        route=original_route,
                        routed_path=original_path,
                        routing_points=original_hard_waypoints,
                        signature=candidate_signature(
                            original_route, topology="point_to_point"
                        ),
                        construction="point_to_point_hard_waypoints",
                        skeleton_id="point-to-point-hard-points-original-order",
                        skeleton_method="point_to_point_hard_waypoints",
                        direction="mixed",
                        direction_warnings=(),
                        hard_point_visits=self._hard_point_visits(
                            request,
                            original_hard_waypoints,
                            original_path.snapped_points,
                        ),
                    )
                )
                state.skeleton_candidates += 1

        if (
            not request.interior_hard_waypoints
            and self._settings.alternative_leg_request_budget
            and not state.budget.exhausted(SearchPhase.ALTERNATIVE_LEG)
        ):
            alternative_started = perf_counter()
            try:
                alternatives = await state.context.routes.alternative_routes(
                    request.effective_start,
                    request.effective_end,
                    request.profile,
                    max_paths=self._low_overlap_settings.max_paths,
                    max_weight_factor=self._low_overlap_settings.max_weight_factor,
                    max_share_factor=self._low_overlap_settings.max_share_factor,
                )
            except RoutingPointError:
                alternatives = ()
            finally:
                state.route_call_seconds += perf_counter() - alternative_started
            for index, path in enumerate(alternatives):
                if not self._valid_complete_path(path, direct_points):
                    continue
                route = self._result_factory.create(
                    name=request.name,
                    path=path,
                    input_point_count=2,
                    routing_profile=request.profile,
                )
                control_drafts.append(
                    _Draft(
                        route=route,
                        routed_path=path,
                        routing_points=direct_points,
                        signature=candidate_signature(route, topology="point_to_point"),
                        construction="point_to_point_alternative",
                        skeleton_id=f"point-to-point-alternative-{index}",
                        skeleton_method="point_to_point_alternative",
                        direction="mixed",
                        direction_warnings=(),
                        hard_point_visits=self._hard_point_visits(
                            request, direct_points, path.snapped_points
                        ),
                    )
                )

        control_drafts = list(_deduplicate_drafts(tuple(control_drafts)))
        base_candidates: list[AutoTourCandidate] = []
        insertion_states: list[_InsertionState] = []
        poi_query_seconds = 0.0
        insertion_started = perf_counter()
        for draft in control_drafts:
            query_started = perf_counter()
            shortlist = shortlist_route_pois(
                index=self._poi_index,
                route_geometry=draft.route.geometry,
                routing_points=draft.routing_points,
                request=request,
                settings=self._settings.poi,
            )
            poi_query_seconds += perf_counter() - query_started
            state.poi_index_candidate_count += len(shortlist.matches)
            state.already_collected_count += len(shortlist.already_collected)
            candidate = self._search_candidate(
                request=request,
                draft=draft,
                visits=shortlist.already_collected,
                rejected=shortlist.rejected,
                family_control=draft,
                inserted=False,
            )
            candidate = _with_open_metrics(candidate, direct_route)
            base_candidates.append(candidate)
            initial = _InsertionState(
                draft=draft,
                family_control=draft,
                base_already_ids=frozenset(
                    visit.poi.id for visit in shortlist.already_collected
                ),
                selected_poi_ids=(),
                selected_progress=(),
                inserted_records={},
                deliberately_routed_requested_indices=frozenset(),
                candidate=candidate,
            )
            requested_states = await self._insert_requested_stops(
                request=request,
                initial=initial,
                state=state,
            )
            for requested_state in requested_states:
                normalized_requested = replace(
                    requested_state,
                    candidate=_with_open_metrics(
                        requested_state.candidate, direct_route
                    ),
                )
                insertion_states.append(normalized_requested)
                routed_shortlist = shortlist_route_pois(
                    index=self._poi_index,
                    route_geometry=normalized_requested.draft.route.geometry,
                    routing_points=normalized_requested.draft.routing_points,
                    request=request,
                    settings=self._settings.poi,
                )
                poi_states = await self._insert_pois(
                    request=request,
                    initial=normalized_requested,
                    initial_shortlist=routed_shortlist,
                    state=state,
                )
                insertion_states.extend(
                    replace(
                        value,
                        candidate=_with_open_metrics(value.candidate, direct_route),
                    )
                    for value in poi_states
                )
        poi_insertion_seconds = perf_counter() - insertion_started

        public_control = next(
            candidate
            for candidate in base_candidates
            if candidate.signature == direct_draft.signature
        ).model_copy(update={"rank": 1})
        pool = _deduplicate_candidates(
            (
                *base_candidates,
                *(value.candidate for value in insertion_states),
            )
        )
        hard_valid = tuple(
            candidate
            for candidate in pool
            if all(visit.selected for visit in candidate.hard_point_visits)
        )
        selected = _open_candidate_portfolio(
            hard_valid or pool,
            request=request,
            control=public_control,
        )
        selected = tuple(
            _with_requested_coverage_warning(candidate, request, public_control)
            for candidate in selected
        )
        selected = _apply_requested_search_failure_context(selected, state)
        selected = _mark_cross_candidate_requested_routing(selected)
        ranked = tuple(
            candidate.model_copy(update={"rank": rank})
            for rank, candidate in enumerate(selected, start=1)
        )
        if not ranked:
            raise AutoTourNoCandidateError
        recommended = ranked[0]
        if state.budget_exhausted:
            warnings.add("auto_tour_route_budget_exhausted")
        if any(
            "target_distance_exceeded_for_requested_coverage" in candidate.warnings
            for candidate in ranked
        ):
            warnings.add("target_distance_exceeded_for_requested_coverage")
        if (
            state.complete_set_candidate_distance_m is not None
            and state.complete_set_candidate_distance_m > _maximum_distance(request)
        ):
            warnings.add("auto_tour_requested_complete_set_exceeds_safety_ceiling")
        visits, endpoint_warnings = validated_endpoint_visits(
            request.resolved_endpoints,
            recommended.route.snapped_points,
            maximum_snap_distance_m=self._settings.max_snap_displacement_m,
        )
        warnings.update(endpoint_warnings)
        total_seconds = perf_counter() - started
        timings = AutoTourTimings(
            isochrone_seconds=0.0,
            skeleton_construction_seconds=0.0,
            route_call_seconds=state.route_call_seconds,
            poi_corridor_query_seconds=poi_query_seconds,
            poi_insertion_search_seconds=poi_insertion_seconds,
            local_repair_seconds=0.0,
            total_seconds=total_seconds,
        )
        summary = AutoTourSearchSummary(
            isochrone_request_count=0,
            round_trip_control_request_count=0,
            sampled_fallback_skeleton_count=0,
            skeleton_route_request_count=state.budget.used(SearchPhase.SKELETON),
            skeleton_candidate_count=state.skeleton_candidates,
            retained_skeleton_count=len(control_drafts),
            poi_index_candidate_count=state.poi_index_candidate_count,
            already_collected_poi_count=state.already_collected_count,
            poi_route_evaluation_count=(
                state.budget.used(SearchPhase.REQUESTED_STOP)
                + state.budget.used(SearchPhase.DISCOVERED_POI)
            ),
            requested_place_route_evaluations=state.budget.used(
                SearchPhase.REQUESTED_STOP
            ),
            discovered_poi_route_evaluations=state.budget.used(
                SearchPhase.DISCOVERED_POI
            ),
            requested_place_budget_exhausted=(state.requested_place_budget_exhausted),
            discovered_poi_budget_exhausted=state.discovered_poi_budget_exhausted,
            local_repair_evaluation_count=0,
            corridor_repair_evaluation_count=0,
            alternative_leg_request_count=state.budget.used(
                SearchPhase.ALTERNATIVE_LEG
            ),
            total_route_request_budget=state.budget.total_limit,
            total_route_request_count=state.budget.total_used,
            budget_exhausted=state.budget_exhausted,
            control_signature=public_control.signature,
            recommended_signature=recommended.signature,
            control_retained=True,
            selected_scenic_count=recommended.selected_scenic_count,
            selected_verified_water_count=recommended.selected_verified_water_count,
            requested_place_selected_count=sum(
                visit.selected for visit in recommended.requested_place_visits
            ),
            requested_place_dropped_count=sum(
                not visit.selected for visit in recommended.requested_place_visits
            ),
            complete_set_candidate_distance_m=(state.complete_set_candidate_distance_m),
            full_set_route_attempted=state.full_set_route_attempted,
            full_set_route_succeeded=state.full_set_route_succeeded,
            full_set_distance_m=state.full_set_distance_m,
            full_set_safety_eligible=state.full_set_safety_eligible,
            full_set_rejection_reason=state.full_set_rejection_reason,
            maximum_distance_m=_maximum_distance(request),
            route_cache_hit_count=state.context.routes.cache_snapshot().hit_count,
            approach_candidates_considered=state.approach_candidates_considered,
            approach_route_evaluation_count=state.budget.used(SearchPhase.APPROACH),
            through_route_evaluation_count=state.budget.used(SearchPhase.THROUGH_ROUTE),
            spur_route_evaluation_count=state.budget.used(SearchPhase.EXCURSION),
            corridor_continuation_evaluation_count=state.budget.used(
                SearchPhase.REPAIR
            ),
            selected_excursion_count=len(recommended.poi_excursions),
            spatial_query_candidate_count=state.poi_index_candidate_count,
            considered_discovered_poi_count=_discovered_decision_count(recommended),
            selected_discovered_poi_count=_selected_discovered_count(recommended),
            dropped_discovered_poi_count=_dropped_discovered_count(recommended),
            selected_stop_count=len(recommended.selected_stops),
            dropped_stop_count=len(recommended.dropped_stops),
            gpx_stop_count=len(recommended.selected_stops),
            timings=timings,
            warnings=tuple(sorted(warnings)),
        )
        return AutoTourSearchResult(
            control=public_control,
            candidates=ranked,
            search=summary,
            diagnostics=_public_search_diagnostics(state, summary),
            topology="point_to_point",
            effective_start=request.effective_start,
            effective_end=request.effective_end,
            endpoint_visits=visits,
            endpoint_warnings=endpoint_warnings,
            import_warnings=tuple(
                sorted(
                    {
                        warning
                        for place in request.requested_stops
                        for warning in place.import_warnings
                    }
                )
            ),
            search_context=context,
            resolved_request=request,
        )
