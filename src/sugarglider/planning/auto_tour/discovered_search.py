"""Bounded discovered-POI insertion search."""

# mypy: disable-error-code="attr-defined"

from sugarglider.planning.auto_tour.controls import (
    classify_route_direction,
)
from sugarglider.planning.auto_tour.decisions import (
    _comparison_rejection_reason,
    _record_rejection,
)
from sugarglider.planning.auto_tour.discovered_pois import (
    InsertedPoiRecord,
    PoiOpportunity,
    PoiShortlist,
    build_poi_visits,
    query_collectible_matches,
    shortlist_route_pois,
)
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
)
from sugarglider.planning.auto_tour.search_support import (
    _prune_insertion_beam,
)
from sugarglider.planning.auto_tour.state import (
    MAX_CANDIDATE_REJECTIONS,
    POI_EXPANSIONS_PER_STATE,
    _Draft,
    _InsertionState,
    _SearchState,
)
from sugarglider.planning.budget import SearchPhase
from sugarglider.planning.signatures import candidate_signature
from sugarglider.routing.errors import (
    RoutingUpstreamError,
)


class DiscoveredSearchMixin:
    async def _insert_pois(
        self,
        *,
        request: AutoTourSearchRequest,
        initial: _InsertionState,
        initial_shortlist: PoiShortlist,
        state: _SearchState,
    ) -> tuple[_InsertionState, ...]:
        if (
            self._poi_index is None
            or self._settings.max_inserted_pois == 0
            or request.requested_stops
        ):
            return (initial,)
        beam: tuple[_InsertionState, ...] = (initial,)
        retained: list[_InsertionState] = [initial]
        signatures = {(initial.candidate.signature, initial.selected_poi_ids)}
        for depth in range(self._settings.max_inserted_pois):
            expanded: list[_InsertionState] = []
            for parent in beam:
                shortlist = (
                    initial_shortlist
                    if depth == 0 and parent is initial
                    else shortlist_route_pois(
                        index=self._poi_index,
                        route_geometry=parent.draft.route.geometry,
                        routing_points=parent.draft.routing_points,
                        request=request,
                        settings=self._settings.poi,
                    )
                )
                candidates = tuple(
                    opportunity
                    for opportunity in shortlist.opportunities
                    if opportunity.match.feature.id not in parent.selected_poi_ids
                    and (
                        not parent.selected_progress
                        or opportunity.match.route_progress_share
                        >= parent.selected_progress[-1]
                    )
                )[:POI_EXPANSIONS_PER_STATE]
                for opportunity in candidates:
                    child = await self._evaluate_insertion(
                        request=request,
                        parent=parent,
                        opportunity=opportunity,
                        state=state,
                    )
                    if child is None:
                        continue
                    key = (child.candidate.signature, child.selected_poi_ids)
                    if key in signatures:
                        continue
                    signatures.add(key)
                    expanded.append(child)
                    retained.append(child)
            if not expanded:
                break
            beam = _prune_insertion_beam(tuple(expanded), self._settings.poi_beam_width)
            if (
                state.budget.used(SearchPhase.DISCOVERED_POI)
                >= self._settings.poi_route_evaluation_budget
            ):
                state.budget_exhausted = True
                break
        rejected = tuple(
            (
                *initial_shortlist.rejected,
                *state.rejected_by_skeleton.get(initial.draft.skeleton_id, ()),
            )
        )[:MAX_CANDIDATE_REJECTIONS]
        return tuple(
            value
            if value.candidate.rejected_poi_opportunities == rejected
            else _InsertionState(
                draft=value.draft,
                family_control=value.family_control,
                base_already_ids=value.base_already_ids,
                selected_poi_ids=value.selected_poi_ids,
                selected_progress=value.selected_progress,
                inserted_records=value.inserted_records,
                deliberately_routed_requested_indices=(
                    value.deliberately_routed_requested_indices
                ),
                candidate=value.candidate.model_copy(
                    update={"rejected_poi_opportunities": rejected}
                ),
            )
            for value in retained
        )

    async def _evaluate_insertion(
        self,
        *,
        request: AutoTourSearchRequest,
        parent: _InsertionState,
        opportunity: PoiOpportunity,
        state: _SearchState,
    ) -> _InsertionState | None:
        poi_index = self._poi_index
        if poi_index is None:
            return None
        if (
            state.budget.used(SearchPhase.DISCOVERED_POI)
            >= self._settings.poi_route_evaluation_budget
        ):
            state.budget_exhausted = True
            _record_rejection(
                state,
                parent.draft.skeleton_id,
                opportunity,
                "route_budget_exhausted",
            )
            return None
        points = (
            *parent.draft.routing_points[: opportunity.insertion_index],
            (
                opportunity.match.approach.coordinate
                if opportunity.match.approach is not None
                else opportunity.match.feature.coordinate
            ),
            *parent.draft.routing_points[opportunity.insertion_index :],
        )
        path = await self._route_points(
            points, request.profile, SearchPhase.DISCOVERED_POI, state
        )
        if path is None or not self._valid_complete_path(path, points):
            _record_rejection(
                state, parent.draft.skeleton_id, opportunity, "snap_too_far"
            )
            return None
        try:
            route = self._result_factory.create(
                name=request.name,
                path=path,
                input_point_count=len(points),
            )
        except RoutingUpstreamError:
            return None
        matches = query_collectible_matches(
            index=poi_index,
            route_geometry=route.geometry,
            request=request,
            settings=self._settings.poi,
        )
        inserted_match = next(
            (
                match
                for match in matches
                if match.feature.id == opportunity.match.feature.id
            ),
            None,
        )
        if (
            inserted_match is None
            or inserted_match.distance_m > opportunity.arrival_tolerance_m
        ):
            _record_rejection(
                state,
                parent.draft.skeleton_id,
                opportunity,
                "snap_too_far",
                nearest_distance_m=(
                    inserted_match.distance_m
                    if inserted_match is not None
                    else opportunity.match.distance_m
                ),
            )
            return None
        actual_delta = route.summary.distance_m - parent.draft.route.summary.distance_m
        records = dict(parent.inserted_records)
        records[opportunity.match.feature.id] = InsertedPoiRecord(
            estimated_detour_m=opportunity.estimated_detour_m,
            actual_distance_delta_m=actual_delta,
            marginal_utility=opportunity.marginal_utility,
        )
        visits = build_poi_visits(
            matches=matches,
            preferred_poi_ids=frozenset(request.preferred_poi_ids),
            base_already_ids=parent.base_already_ids,
            inserted_records=records,
        )
        direction = classify_route_direction(route.geometry)
        draft = _Draft(
            route=route,
            routed_path=path,
            routing_points=points,
            signature=candidate_signature(route),
            construction="poi_insertion",
            skeleton_id=parent.draft.skeleton_id,
            skeleton_method=parent.draft.skeleton_method,
            direction=direction.direction,
            direction_warnings=direction.warnings,
            hard_point_visits=self._hard_point_visits(
                request, points, path.snapped_points
            ),
            ellipse_bearing_degrees=parent.draft.ellipse_bearing_degrees,
            ellipse_aspect_ratio=parent.draft.ellipse_aspect_ratio,
            ellipse_perimeter_scale=parent.draft.ellipse_perimeter_scale,
            ellipse_containment_scale=parent.draft.ellipse_containment_scale,
        )
        candidate = self._search_candidate(
            request=request,
            draft=draft,
            visits=visits,
            rejected=(),
            family_control=parent.family_control,
            inserted=True,
            deliberately_routed_requested_indices=(
                parent.deliberately_routed_requested_indices
            ),
        )
        if not candidate.control_eligible:
            _record_rejection(
                state,
                parent.draft.skeleton_id,
                opportunity,
                _comparison_rejection_reason(candidate.control_comparison),
                nearest_distance_m=inserted_match.distance_m,
            )
        return _InsertionState(
            draft=draft,
            family_control=parent.family_control,
            base_already_ids=parent.base_already_ids,
            selected_poi_ids=(
                *parent.selected_poi_ids,
                opportunity.match.feature.id,
            ),
            selected_progress=(
                *parent.selected_progress,
                opportunity.match.route_progress_share,
            ),
            inserted_records=records,
            deliberately_routed_requested_indices=(
                parent.deliberately_routed_requested_indices
            ),
            candidate=candidate,
        )
