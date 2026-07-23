"""Loop Auto Tour orchestration."""

# mypy: disable-error-code="attr-defined"

from time import perf_counter
from typing import cast

from sugarglider.domain.endpoints import validated_endpoint_visits
from sugarglider.planning.auto_tour.approaches import (
    choose_route_dependent_approaches,
    resolve_requested_stops,
)
from sugarglider.planning.auto_tour.candidate_models import (
    AutoTourCandidate,
)
from sugarglider.planning.auto_tour.controls import (
    generate_isochrone_skeletons,
)
from sugarglider.planning.auto_tour.decisions import (
    _apply_requested_search_failure_context,
    _discovered_decision_count,
    _dropped_discovered_count,
    _mark_cross_candidate_requested_routing,
    _selected_discovered_count,
)
from sugarglider.planning.auto_tour.diagnostics import (
    AutoTourSearchResult,
    AutoTourSearchSummary,
    AutoTourTimings,
)
from sugarglider.planning.auto_tour.discovered_pois import (
    PoiShortlist,
    shortlist_route_pois,
)
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
)
from sugarglider.planning.auto_tour.ranking import (
    auto_tour_ranking_key,
)
from sugarglider.planning.auto_tour.search_support import (
    _control_key,
    _deduplicate_candidates,
    _deduplicate_drafts,
    _hard_waypoints_selected,
    _maximum_distance,
    _retain_diverse_controls,
)
from sugarglider.planning.auto_tour.state import (
    AutoTourNoCandidateError,
    _Draft,
    _InsertionState,
    _public_search_diagnostics,
    _search_budget,
    _SearchState,
)
from sugarglider.planning.budget import SearchPhase
from sugarglider.planning.context import PlanningSearchContext


class LoopSearchMixin:
    async def generate(self, request: AutoTourSearchRequest) -> AutoTourSearchResult:
        """Return a retained no-POI control and conservative ranked candidates."""
        request = request.model_copy(
            update={
                "requested_stops": resolve_requested_stops(
                    request.requested_stops, self._poi_index
                )
            }
        )
        if request.resolved_endpoints.topology == "point_to_point":
            return cast(AutoTourSearchResult, await self._generate_open_tour(request))
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

        isochrone_started = perf_counter()
        envelope = await self._load_isochrone(request, state, warnings)
        isochrone_seconds = perf_counter() - isochrone_started

        skeleton_started = perf_counter()
        skeletons = (
            generate_isochrone_skeletons(
                start=request.effective_start,
                target_distance_m=request.target_distance_m,
                envelope=envelope.geometry,
                direction_preference=request.direction_preference,
            )
            if envelope is not None
            else ()
        )
        skeleton_construction_seconds = perf_counter() - skeleton_started

        controls: list[_Draft] = []
        for skeleton in skeletons:
            if (
                state.budget.used(SearchPhase.SKELETON)
                >= self._settings.skeleton_route_budget
            ):
                state.budget_exhausted = True
                break
            draft = await self._route_skeleton(request, skeleton, state)
            if draft is not None:
                controls.append(draft)

        controls.extend(
            await self._round_trip_controls(
                request,
                state,
                sample_fallback=envelope is None,
            )
        )
        controls = list(_deduplicate_drafts(tuple(controls)))
        controls = [draft for draft in controls if _hard_waypoints_selected(draft)]
        if request.direction_preference != "any":
            controls = [
                draft
                for draft in controls
                if draft.direction == request.direction_preference
            ]
        if not controls:
            raise AutoTourNoCandidateError

        global_control_draft = min(
            controls, key=lambda draft: _control_key(draft, request)
        )
        request = request.model_copy(
            update={
                "requested_stops": choose_route_dependent_approaches(
                    request.requested_stops, global_control_draft.route.geometry
                )
            }
        )
        retained = _retain_diverse_controls(
            tuple(controls), self._settings.retained_skeleton_limit, request
        )

        poi_query_seconds = 0.0
        insertion_started = perf_counter()
        base_candidates: dict[str, AutoTourCandidate] = {}
        all_insertions: list[_InsertionState] = []
        initial_families: list[tuple[_InsertionState, PoiShortlist]] = []
        for control in retained:
            query_started = perf_counter()
            shortlist = shortlist_route_pois(
                index=self._poi_index,
                route_geometry=control.route.geometry,
                routing_points=control.routing_points,
                request=request,
                settings=self._settings.poi,
            )
            if len(control.routing_points) < 2 and shortlist.opportunities:
                shortlist = PoiShortlist(
                    matches=shortlist.matches,
                    already_collected=shortlist.already_collected,
                    opportunities=(),
                    rejected=shortlist.rejected,
                )
            poi_query_seconds += perf_counter() - query_started
            state.poi_index_candidate_count += len(shortlist.matches)
            state.already_collected_count += len(shortlist.already_collected)
            base_candidate = self._search_candidate(
                request=request,
                draft=control,
                visits=shortlist.already_collected,
                rejected=shortlist.rejected,
                family_control=control,
                inserted=False,
            )
            base_candidates[control.signature] = base_candidate
            base_ids = frozenset(visit.poi.id for visit in shortlist.already_collected)
            start_state = _InsertionState(
                draft=control,
                family_control=control,
                base_already_ids=base_ids,
                selected_poi_ids=(),
                selected_progress=(),
                inserted_records={},
                deliberately_routed_requested_indices=frozenset(),
                candidate=base_candidate,
            )
            initial_families.append((start_state, shortlist))

        requested_families: list[
            tuple[_InsertionState, PoiShortlist, _InsertionState]
        ] = []
        for start_state, shortlist in initial_families:
            requested_states = await self._insert_requested_stops(
                request=request,
                initial=start_state,
                state=state,
            )
            for requested_state in requested_states:
                if request.requested_stops and requested_state is start_state:
                    continue
                requested_families.append((requested_state, shortlist, start_state))

        for requested_state, shortlist, start_state in requested_families:
            if requested_state.draft.route.summary.distance_m > _maximum_distance(
                request
            ):
                all_insertions.append(requested_state)
                continue
            state_shortlist = (
                shortlist
                if requested_state is start_state
                else shortlist_route_pois(
                    index=self._poi_index,
                    route_geometry=requested_state.draft.route.geometry,
                    routing_points=requested_state.draft.routing_points,
                    request=request,
                    settings=self._settings.poi,
                )
            )
            family_states = await self._insert_pois(
                request=request,
                initial=requested_state,
                initial_shortlist=state_shortlist,
                state=state,
            )
            all_insertions.extend(
                family_state
                for family_state in family_states
                if family_state.selected_poi_ids
                or family_state.deliberately_routed_requested_indices
            )
        poi_insertion_seconds = perf_counter() - insertion_started

        local_repair_started = perf_counter()
        repaired = await self._local_repair(
            request=request,
            states=tuple(all_insertions),
            state=state,
        )
        local_repair_seconds = perf_counter() - local_repair_started
        all_insertions.extend(repaired)

        global_control = base_candidates.get(global_control_draft.signature)
        if global_control is None:
            shortlist = shortlist_route_pois(
                index=self._poi_index,
                route_geometry=global_control_draft.route.geometry,
                routing_points=global_control_draft.routing_points,
                request=request,
                settings=self._settings.poi,
            )
            global_control = self._search_candidate(
                request=request,
                draft=global_control_draft,
                visits=shortlist.already_collected,
                rejected=shortlist.rejected,
                family_control=global_control_draft,
                inserted=False,
            )

        eligible = [
            insertion.candidate
            for insertion in all_insertions
            if insertion.candidate.control_eligible
        ]
        maximum_distance = _maximum_distance(request)
        recommendation_pool = _deduplicate_candidates(
            (
                *base_candidates.values(),
                global_control,
                *(
                    insertion.candidate
                    for insertion in all_insertions
                    if insertion.candidate.route.summary.distance_m <= maximum_distance
                    and all(
                        visit.selected
                        for visit in insertion.candidate.hard_point_visits
                    )
                ),
            )
        )
        selected = sorted(recommendation_pool, key=auto_tour_ranking_key)[
            : request.candidate_count
        ]
        requested_representative = min(
            (
                candidate
                for candidate in recommendation_pool
                if candidate.signature != selected[0].signature
                if any(
                    visit.deliberately_routed
                    for visit in candidate.requested_place_visits
                )
            ),
            key=lambda candidate: (
                -candidate.selected_must_visit_count,
                -candidate.selected_preferred_place_count,
                auto_tour_ranking_key(candidate),
            ),
            default=None,
        )
        if (
            request.candidate_count > 1
            and requested_representative is not None
            and requested_representative.signature
            not in {candidate.signature for candidate in selected}
        ):
            selected[-1] = requested_representative
            selected.sort(key=auto_tour_ranking_key)
        selected = list(
            _mark_cross_candidate_requested_routing(
                _apply_requested_search_failure_context(tuple(selected), state)
            )
        )
        ranked = tuple(
            candidate.model_copy(update={"rank": rank})
            for rank, candidate in enumerate(selected, start=1)
        )
        control_ranked = global_control.model_copy(update={"rank": 1})

        if (
            self._poi_index is not None
            and not request.requested_stops
            and request.scenic_preference == "prefer"
            and not any(candidate.discovered_poi_reward > 0 for candidate in eligible)
        ):
            warnings.add("auto_tour_no_safe_poi_improvement")
        if (
            self._poi_index is not None
            and not request.requested_stops
            and request.drinking_water_preference == "prefer"
            and not any(
                visit.poi.category == "drinking_water"
                and visit.poi.potability == "verified"
                for candidate in (global_control, *eligible)
                if candidate.control_eligible
                for visit in candidate.poi_visits
            )
        ):
            warnings.add("auto_tour_no_safe_water_insertion")
        if state.budget_exhausted:
            warnings.add("auto_tour_route_budget_exhausted")
        if (
            state.complete_set_candidate_distance_m is not None
            and state.complete_set_candidate_distance_m > _maximum_distance(request)
        ):
            warnings.add("auto_tour_requested_complete_set_exceeds_safety_ceiling")
        warnings.update(
            warning
            for candidate in ranked
            for warning in candidate.warnings
            if warning.startswith("auto_tour_")
        )

        recommended = ranked[0]
        total_seconds = perf_counter() - started
        timings = AutoTourTimings(
            isochrone_seconds=isochrone_seconds,
            skeleton_construction_seconds=skeleton_construction_seconds,
            route_call_seconds=state.route_call_seconds,
            poi_corridor_query_seconds=poi_query_seconds,
            poi_insertion_search_seconds=poi_insertion_seconds,
            local_repair_seconds=local_repair_seconds,
            total_seconds=total_seconds,
        )
        summary = AutoTourSearchSummary(
            isochrone_request_count=state.isochrone_proposals_generated,
            round_trip_control_request_count=max(
                0,
                state.budget.used(SearchPhase.CONTROL)
                - state.isochrone_proposals_generated,
            ),
            sampled_fallback_skeleton_count=state.sampled_fallback_skeletons,
            skeleton_route_request_count=state.budget.used(SearchPhase.SKELETON),
            skeleton_candidate_count=state.skeleton_candidates,
            retained_skeleton_count=len(retained),
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
            local_repair_evaluation_count=state.budget.used(SearchPhase.REPAIR),
            corridor_repair_evaluation_count=state.budget.used(SearchPhase.REPAIR),
            alternative_leg_request_count=state.budget.used(
                SearchPhase.ALTERNATIVE_LEG
            ),
            total_route_request_budget=state.budget.total_limit,
            total_route_request_count=state.budget.total_used,
            budget_exhausted=state.budget_exhausted,
            control_signature=control_ranked.signature,
            recommended_signature=recommended.signature,
            control_retained=True,
            selected_scenic_count=recommended.selected_scenic_count,
            selected_verified_water_count=(recommended.selected_verified_water_count),
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
        visits, endpoint_warnings = validated_endpoint_visits(
            request.resolved_endpoints,
            recommended.route.snapped_points,
            maximum_snap_distance_m=self._settings.max_snap_displacement_m,
        )
        return AutoTourSearchResult(
            control=control_ranked,
            candidates=ranked,
            search=summary,
            diagnostics=_public_search_diagnostics(state, summary),
            topology="loop",
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
