"""Bounded local and approach repair search."""

# mypy: disable-error-code="attr-defined"

from typing import cast

from sugarglider.planning.alternative_legs import (
    LowOverlapBeamSearch,
)
from sugarglider.planning.auto_tour.approaches import (
    approach_candidates_for_feature,
)
from sugarglider.planning.auto_tour.controls import (
    classify_route_direction,
)
from sugarglider.planning.auto_tour.decisions import (
    _force_trade_off,
    _records_without_final_deltas,
    _remove_coordinate,
    _replace_coordinate,
)
from sugarglider.planning.auto_tour.discovered_pois import (
    InsertedPoiRecord,
    build_poi_visits,
    query_collectible_matches,
    shortlist_route_pois,
)
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
)
from sugarglider.planning.auto_tour.ranking import (
    auto_tour_ranking_key,
    compare_with_control,
)
from sugarglider.planning.auto_tour.search_support import (
    _hard_waypoints_selected,
    _maximum_distance,
)
from sugarglider.planning.auto_tour.state import (
    _Draft,
    _InsertionState,
    _SearchState,
)
from sugarglider.planning.budget import SearchPhase
from sugarglider.planning.signatures import candidate_signature
from sugarglider.routing.backend import (
    RoutingBackend,
)
from sugarglider.routing.errors import (
    RoutingUpstreamError,
)


class RepairSearchMixin:
    async def _local_repair(
        self,
        *,
        request: AutoTourSearchRequest,
        states: tuple[_InsertionState, ...],
        state: _SearchState,
    ) -> tuple[_InsertionState, ...]:
        """Try bounded deterministic removal of the lowest-utility inserted POI."""
        requested_repairs = await self._remove_dropped_requested_place_hooks(
            request=request,
            states=states,
            state=state,
        )
        poi_index = self._poi_index
        if poi_index is None:
            return requested_repairs
        corridor_repairs = await self._corridor_continuation_repairs(
            request=request,
            states=states,
            state=state,
        )
        eligible = sorted(
            (value for value in states if value.candidate.control_eligible),
            key=lambda value: auto_tour_ranking_key(value.candidate),
        )[:2]
        repaired: list[_InsertionState] = [
            *requested_repairs,
            *corridor_repairs,
        ]
        for source in eligible:
            if (
                len(source.selected_poi_ids) < 2
                or state.budget.used(SearchPhase.REPAIR)
                >= self._settings.local_repair_route_evaluation_budget
            ):
                continue
            remove_id = min(
                source.selected_poi_ids,
                key=lambda poi_id: (
                    source.inserted_records[poi_id].marginal_utility,
                    poi_id,
                ),
            )
            remove_index = source.selected_poi_ids.index(remove_id)
            feature = poi_index.get_feature(remove_id)
            if feature is None:
                continue
            points = next(
                (
                    removed
                    for approach in approach_candidates_for_feature(feature)
                    if (
                        removed := _remove_coordinate(
                            source.draft.routing_points, approach.coordinate
                        )
                    )
                    is not None
                ),
                None,
            )
            if points is None:
                continue
            path = await self._route_points(
                points, request.profile, SearchPhase.REPAIR, state
            )
            if path is None or not self._valid_complete_path(path, points):
                continue
            try:
                route = self._result_factory.create(
                    name=request.name,
                    path=path,
                    input_point_count=len(points),
                    routing_profile=request.profile,
                )
            except RoutingUpstreamError:
                continue
            matches = query_collectible_matches(
                index=poi_index,
                route_geometry=route.geometry,
                request=request,
                settings=self._settings.poi,
            )
            records = _records_without_final_deltas(
                {
                    poi_id: record
                    for poi_id, record in source.inserted_records.items()
                    if poi_id != remove_id
                }
            )
            visits = build_poi_visits(
                matches=matches,
                preferred_poi_ids=frozenset(request.preferred_poi_ids),
                base_already_ids=source.base_already_ids,
                inserted_records=records,
            )
            direction = classify_route_direction(route.geometry)
            draft = _Draft(
                route=route,
                routed_path=path,
                routing_points=points,
                signature=candidate_signature(route),
                construction="local_repair",
                skeleton_id=source.draft.skeleton_id,
                skeleton_method=source.draft.skeleton_method,
                direction=direction.direction,
                direction_warnings=direction.warnings,
                hard_point_visits=self._hard_point_visits(
                    request, points, path.snapped_points
                ),
                ellipse_bearing_degrees=source.draft.ellipse_bearing_degrees,
                ellipse_aspect_ratio=source.draft.ellipse_aspect_ratio,
                ellipse_perimeter_scale=source.draft.ellipse_perimeter_scale,
                ellipse_containment_scale=source.draft.ellipse_containment_scale,
            )
            candidate = self._search_candidate(
                request=request,
                draft=draft,
                visits=visits,
                rejected=(),
                family_control=source.family_control,
                inserted=True,
                deliberately_routed_requested_indices=(
                    source.deliberately_routed_requested_indices
                ),
            )
            repaired.append(
                _InsertionState(
                    draft=draft,
                    family_control=source.family_control,
                    base_already_ids=source.base_already_ids,
                    selected_poi_ids=tuple(
                        poi_id
                        for poi_id in source.selected_poi_ids
                        if poi_id != remove_id
                    ),
                    selected_progress=tuple(
                        progress
                        for index, progress in enumerate(source.selected_progress)
                        if index != remove_index
                    ),
                    inserted_records=records,
                    deliberately_routed_requested_indices=(
                        source.deliberately_routed_requested_indices
                    ),
                    candidate=candidate,
                )
            )
        for source in eligible:
            replacement = await self._replace_scenic_poi(
                request=request,
                source=source,
                state=state,
            )
            if replacement is not None:
                repaired.append(replacement)
        if (
            request.path_selection_mode == "low_overlap"
            and self._settings.alternative_leg_request_budget > 0
        ):
            requested_repair_sources = sorted(
                (
                    value
                    for value in states
                    if value.deliberately_routed_requested_indices
                ),
                key=lambda value: (
                    -value.candidate.selected_must_visit_count,
                    -value.candidate.selected_preferred_place_count,
                    auto_tour_ranking_key(value.candidate),
                ),
            )[:1]
            alternative_sources = tuple(
                {
                    value.candidate.signature: value
                    for value in (*requested_repair_sources, *eligible)
                }.values()
            )[:2]
            search = LowOverlapBeamSearch(
                cast(RoutingBackend, state.context.routes),
                self._structural_result_factory,
                self._low_overlap_settings,
            )
            for source in alternative_sources:
                if len(source.draft.routing_points) < 2:
                    continue
                result = await search.assemble(
                    name=request.name,
                    routing_points=source.draft.routing_points,
                    profile=request.profile,
                    target_distance_m=request.target_distance_m,
                    input_point_count=len(source.draft.routing_points),
                    closed=request.resolved_endpoints.topology == "loop",
                )
                for beam_state in result.states:
                    try:
                        route = self._result_factory.create(
                            name=request.name,
                            path=beam_state.composed_path,
                            input_point_count=len(source.draft.routing_points),
                            routing_profile=request.profile,
                        )
                    except RoutingUpstreamError:
                        continue
                    matches = query_collectible_matches(
                        index=poi_index,
                        route_geometry=route.geometry,
                        request=request,
                        settings=self._settings.poi,
                    )
                    alternative_records = _records_without_final_deltas(
                        source.inserted_records
                    )
                    visits = build_poi_visits(
                        matches=matches,
                        preferred_poi_ids=frozenset(request.preferred_poi_ids),
                        base_already_ids=source.base_already_ids,
                        inserted_records=alternative_records,
                    )
                    direction = classify_route_direction(route.geometry)
                    draft = _Draft(
                        route=route,
                        routed_path=beam_state.composed_path,
                        routing_points=source.draft.routing_points,
                        signature=candidate_signature(route),
                        construction="alternative_leg_repair",
                        skeleton_id=source.draft.skeleton_id,
                        skeleton_method=source.draft.skeleton_method,
                        direction=direction.direction,
                        direction_warnings=direction.warnings,
                        hard_point_visits=self._hard_point_visits(
                            request,
                            source.draft.routing_points,
                            beam_state.composed_path.snapped_points,
                        ),
                        ellipse_bearing_degrees=source.draft.ellipse_bearing_degrees,
                        ellipse_aspect_ratio=source.draft.ellipse_aspect_ratio,
                        ellipse_perimeter_scale=(source.draft.ellipse_perimeter_scale),
                        ellipse_containment_scale=(
                            source.draft.ellipse_containment_scale
                        ),
                    )
                    candidate = self._search_candidate(
                        request=request,
                        draft=draft,
                        visits=visits,
                        rejected=(),
                        family_control=source.family_control,
                        inserted=True,
                        deliberately_routed_requested_indices=(
                            source.deliberately_routed_requested_indices
                        ),
                    )
                    natural_improvement = (
                        route.analysis.repetition.repeated_distance.share
                        < source.draft.route.analysis.repetition.repeated_distance.share
                        - 1e-12
                        and route.analysis.immediate_backtrack.share
                        <= source.draft.route.analysis.immediate_backtrack.share + 1e-12
                    )
                    if not natural_improvement:
                        candidate = _force_trade_off(
                            candidate, "low_overlap_not_natural_improvement"
                        )
                    repaired.append(
                        _InsertionState(
                            draft=draft,
                            family_control=source.family_control,
                            base_already_ids=source.base_already_ids,
                            selected_poi_ids=source.selected_poi_ids,
                            selected_progress=source.selected_progress,
                            inserted_records=alternative_records,
                            deliberately_routed_requested_indices=(
                                source.deliberately_routed_requested_indices
                            ),
                            candidate=candidate,
                        )
                    )
                if "low_overlap_leg_budget_exhausted" in result.warnings:
                    state.budget_exhausted = True
                    break
        return tuple(repaired)

    async def _remove_dropped_requested_place_hooks(
        self,
        *,
        request: AutoTourSearchRequest,
        states: tuple[_InsertionState, ...],
        state: _SearchState,
    ) -> tuple[_InsertionState, ...]:
        """Stop forcing soft coordinates that snapped outside their visit radius."""
        ordered_sources = sorted(
            (
                source
                for source in states
                if source.deliberately_routed_requested_indices
                and source.draft.route.analysis.immediate_backtrack.distance_m > 300.0
                and source.draft.route.summary.distance_m <= _maximum_distance(request)
            ),
            key=lambda source: (
                -source.candidate.selected_must_visit_count,
                -source.candidate.selected_preferred_place_count,
                auto_tour_ranking_key(source.candidate),
            ),
        )
        sources_by_skeleton: dict[str, _InsertionState] = {}
        for source in ordered_sources:
            sources_by_skeleton.setdefault(source.draft.skeleton_id, source)
        sources = tuple(sources_by_skeleton.values())[:6]
        repaired: list[_InsertionState] = []
        for source in sources:
            dropped_indices = tuple(
                index
                for index, visit in enumerate(source.candidate.requested_place_visits)
                if index in source.deliberately_routed_requested_indices
                and not visit.selected
            )[:1]
            for requested_index in dropped_indices:
                if (
                    state.budget.used(SearchPhase.REPAIR)
                    >= self._settings.local_repair_route_evaluation_budget
                ):
                    return tuple(repaired)
                place = request.requested_stops[requested_index]
                points = _remove_coordinate(
                    source.draft.routing_points, place.routing_coordinate
                )
                if points is None:
                    continue
                path = await self._route_points(
                    points, request.profile, SearchPhase.REPAIR, state
                )
                if path is None or not self._valid_requested_path(
                    path,
                    points,
                    stable_points=source.family_control.routing_points,
                ):
                    continue
                try:
                    route = self._result_factory.create(
                        name=request.name,
                        path=path,
                        input_point_count=len(points),
                        routing_profile=request.profile,
                    )
                except RoutingUpstreamError:
                    continue
                matches = (
                    query_collectible_matches(
                        index=self._poi_index,
                        route_geometry=route.geometry,
                        request=request,
                        settings=self._settings.poi,
                    )
                    if self._poi_index is not None
                    else ()
                )
                records = _records_without_final_deltas(source.inserted_records)
                visits = build_poi_visits(
                    matches=matches,
                    preferred_poi_ids=frozenset(request.preferred_poi_ids),
                    base_already_ids=source.base_already_ids,
                    inserted_records=records,
                )
                direction = classify_route_direction(route.geometry)
                draft = _Draft(
                    route=route,
                    routed_path=path,
                    routing_points=points,
                    signature=candidate_signature(route),
                    construction="local_repair",
                    skeleton_id=source.draft.skeleton_id,
                    skeleton_method=source.draft.skeleton_method,
                    direction=direction.direction,
                    direction_warnings=direction.warnings,
                    hard_point_visits=self._hard_point_visits(
                        request, points, path.snapped_points
                    ),
                    ellipse_bearing_degrees=source.draft.ellipse_bearing_degrees,
                    ellipse_aspect_ratio=source.draft.ellipse_aspect_ratio,
                    ellipse_perimeter_scale=source.draft.ellipse_perimeter_scale,
                    ellipse_containment_scale=(source.draft.ellipse_containment_scale),
                )
                deliberately_routed = frozenset(
                    index
                    for index in source.deliberately_routed_requested_indices
                    if index != requested_index
                )
                candidate = self._search_candidate(
                    request=request,
                    draft=draft,
                    visits=visits,
                    rejected=(),
                    family_control=source.family_control,
                    inserted=True,
                    deliberately_routed_requested_indices=deliberately_routed,
                )
                repaired.append(
                    _InsertionState(
                        draft=draft,
                        family_control=source.family_control,
                        base_already_ids=source.base_already_ids,
                        selected_poi_ids=source.selected_poi_ids,
                        selected_progress=source.selected_progress,
                        inserted_records=records,
                        deliberately_routed_requested_indices=deliberately_routed,
                        candidate=candidate,
                    )
                )
        return tuple(repaired)

    async def _replace_scenic_poi(
        self,
        *,
        request: AutoTourSearchRequest,
        source: _InsertionState,
        state: _SearchState,
    ) -> _InsertionState | None:
        """Replace one low-utility scenic insertion without regressing its route."""
        poi_index = self._poi_index
        if (
            poi_index is None
            or state.budget.used(SearchPhase.REPAIR)
            >= self._settings.local_repair_route_evaluation_budget
        ):
            return None
        scenic_ids = tuple(
            poi_id
            for poi_id in source.selected_poi_ids
            if (feature := poi_index.get_feature(poi_id)) is not None
            and feature.group == "scenic"
        )
        if not scenic_ids:
            return None
        replaced_id = min(
            scenic_ids,
            key=lambda poi_id: (
                source.inserted_records[poi_id].marginal_utility,
                poi_id,
            ),
        )
        replaced_feature = poi_index.get_feature(replaced_id)
        if replaced_feature is None:
            return None
        selected_index = source.selected_poi_ids.index(replaced_id)
        minimum_progress = (
            source.selected_progress[selected_index - 1] if selected_index > 0 else 0.0
        )
        maximum_progress = (
            source.selected_progress[selected_index + 1]
            if selected_index + 1 < len(source.selected_progress)
            else 1.0
        )
        shortlist = shortlist_route_pois(
            index=poi_index,
            route_geometry=source.draft.route.geometry,
            routing_points=source.draft.routing_points,
            request=request,
            settings=self._settings.poi,
        )
        opportunity = next(
            (
                value
                for value in shortlist.opportunities
                if value.match.feature.group == "scenic"
                and value.match.feature.id not in source.selected_poi_ids
                and minimum_progress
                <= value.match.route_progress_share
                <= maximum_progress
                and value.marginal_utility
                > source.inserted_records[replaced_id].marginal_utility
            ),
            None,
        )
        if opportunity is None:
            return None
        points = _replace_coordinate(
            source.draft.routing_points,
            (
                approach_candidates_for_feature(replaced_feature)[0].coordinate
                if approach_candidates_for_feature(replaced_feature)
                else replaced_feature.coordinate
            ),
            (
                opportunity.match.approach.coordinate
                if opportunity.match.approach is not None
                else opportunity.match.feature.coordinate
            ),
        )
        if points is None:
            return None
        path = await self._route_points(
            points, request.profile, SearchPhase.REPAIR, state
        )
        if path is None or not self._valid_complete_path(path, points):
            return None
        try:
            route = self._result_factory.create(
                name=request.name,
                path=path,
                input_point_count=len(points),
                routing_profile=request.profile,
            )
        except RoutingUpstreamError:
            return None
        matches = query_collectible_matches(
            index=poi_index,
            route_geometry=route.geometry,
            request=request,
            settings=self._settings.poi,
        )
        replacement_match = next(
            (
                match
                for match in matches
                if match.feature.id == opportunity.match.feature.id
            ),
            None,
        )
        if (
            replacement_match is None
            or replacement_match.distance_m > opportunity.arrival_tolerance_m
        ):
            return None
        records = _records_without_final_deltas(
            {
                poi_id: record
                for poi_id, record in source.inserted_records.items()
                if poi_id != replaced_id
            }
        )
        records[opportunity.match.feature.id] = InsertedPoiRecord(
            estimated_detour_m=opportunity.estimated_detour_m,
            actual_distance_delta_m=None,
            marginal_utility=opportunity.marginal_utility,
        )
        visits = build_poi_visits(
            matches=matches,
            preferred_poi_ids=frozenset(request.preferred_poi_ids),
            base_already_ids=source.base_already_ids,
            inserted_records=records,
        )
        direction = classify_route_direction(route.geometry)
        draft = _Draft(
            route=route,
            routed_path=path,
            routing_points=points,
            signature=candidate_signature(route),
            construction="local_repair",
            skeleton_id=source.draft.skeleton_id,
            skeleton_method=source.draft.skeleton_method,
            direction=direction.direction,
            direction_warnings=direction.warnings,
            hard_point_visits=self._hard_point_visits(
                request, points, path.snapped_points
            ),
            ellipse_bearing_degrees=source.draft.ellipse_bearing_degrees,
            ellipse_aspect_ratio=source.draft.ellipse_aspect_ratio,
            ellipse_perimeter_scale=source.draft.ellipse_perimeter_scale,
            ellipse_containment_scale=source.draft.ellipse_containment_scale,
        )
        candidate = self._search_candidate(
            request=request,
            draft=draft,
            visits=visits,
            rejected=(),
            family_control=source.family_control,
            inserted=True,
            deliberately_routed_requested_indices=(
                source.deliberately_routed_requested_indices
            ),
        )
        source_comparison = compare_with_control(
            route=route,
            within_tolerance=candidate.within_tolerance,
            hard_waypoints_selected=_hard_waypoints_selected(draft),
            discovered_poi_reward=candidate.discovered_poi_reward,
            control=source.draft.route,
            control_within_tolerance=source.candidate.within_tolerance,
            control_signature=source.candidate.signature,
            requested_place_gain=(
                candidate.selected_must_visit_count
                + candidate.selected_preferred_place_count
                - source.candidate.selected_must_visit_count
                - source.candidate.selected_preferred_place_count
            ),
            distance_priority=request.distance_priority,
            maximum_distance_m=_maximum_distance(request),
        )
        if (
            not candidate.control_eligible
            or not source_comparison.eligible
            or candidate.total_poi_reward <= source.candidate.total_poi_reward + 1e-12
        ):
            return None
        selected_ids = list(source.selected_poi_ids)
        selected_ids[selected_index] = opportunity.match.feature.id
        selected_progress = list(source.selected_progress)
        selected_progress[selected_index] = opportunity.match.route_progress_share
        return _InsertionState(
            draft=draft,
            family_control=source.family_control,
            base_already_ids=source.base_already_ids,
            selected_poi_ids=tuple(selected_ids),
            selected_progress=tuple(selected_progress),
            inserted_records=records,
            deliberately_routed_requested_indices=(
                source.deliberately_routed_requested_indices
            ),
            candidate=candidate,
        )
