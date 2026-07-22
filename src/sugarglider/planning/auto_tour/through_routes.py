"""Corridor continuation and through-route search."""

# mypy: disable-error-code="attr-defined"

from sugarglider.domain.models import Coordinate
from sugarglider.planning.auto_tour.approaches import (
    approach_candidates_for_feature,
)
from sugarglider.planning.auto_tour.controls import (
    classify_route_direction,
)
from sugarglider.planning.auto_tour.decisions import (
    _records_without_final_deltas,
)
from sugarglider.planning.auto_tour.discovered_pois import (
    InsertedPoiRecord,
    build_poi_visits,
    query_collectible_matches,
    shortlist_route_pois,
)
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
    TourRepairExplanation,
)
from sugarglider.planning.auto_tour.requested_stops import (
    insert_coordinate_after,
    measure_requested_place_visits,
    requested_place_opportunities,
)
from sugarglider.planning.auto_tour.state import (
    _ContinuationOption,
    _Draft,
    _InsertionState,
    _SearchState,
)
from sugarglider.planning.budget import SearchPhase
from sugarglider.planning.signatures import candidate_signature
from sugarglider.routing.errors import (
    RoutingUpstreamError,
)


class ThroughRouteSearchMixin:
    async def _corridor_continuation_repairs(
        self,
        *,
        request: AutoTourSearchRequest,
        states: tuple[_InsertionState, ...],
        state: _SearchState,
    ) -> tuple[_InsertionState, ...]:
        """Try a bounded P→Q through-route even when singleton P was ineligible."""
        poi_index = self._poi_index
        if poi_index is None:
            return ()
        sources = sorted(
            (
                source
                for source in states
                if source.selected_poi_ids
                or source.deliberately_routed_requested_indices
            ),
            key=lambda source: (
                -source.draft.route.analysis.immediate_backtrack.distance_m,
                -(
                    source.draft.route.analysis.loop_geometry.outbound_return_proximity.share
                    if source.draft.route.analysis.loop_geometry is not None
                    else 0.0
                ),
                source.candidate.signature,
            ),
        )[:3]
        repaired: list[_InsertionState] = []
        for source in sources:
            geometry = source.draft.route.analysis.loop_geometry
            if source.draft.route.analysis.immediate_backtrack.distance_m <= 300.0 and (
                geometry is None or geometry.outbound_return_proximity.share < 0.25
            ):
                continue
            if (
                state.budget.used(SearchPhase.REPAIR)
                >= self._settings.local_repair_route_evaluation_budget
            ):
                break
            pivot = self._continuation_pivot(source)
            if pivot is None:
                continue
            pivot_coordinate, pivot_progress = pivot
            shortlist = shortlist_route_pois(
                index=poi_index,
                route_geometry=source.draft.route.geometry,
                routing_points=source.draft.routing_points,
                request=request,
                settings=self._settings.poi,
            )
            poi_continuations = tuple(
                _ContinuationOption(
                    coordinate=(
                        opportunity.match.approach.coordinate
                        if opportunity.match.approach is not None
                        else opportunity.match.feature.coordinate
                    ),
                    route_progress_share=opportunity.match.route_progress_share,
                    poi_opportunity=opportunity,
                )
                for opportunity in shortlist.opportunities
                if opportunity.match.feature.id not in source.selected_poi_ids
                and opportunity.match.route_progress_share >= pivot_progress
            )
            requested_continuations = tuple(
                _ContinuationOption(
                    coordinate=opportunity.place.routing_coordinate,
                    route_progress_share=opportunity.route_progress_share,
                    requested_index=opportunity.original_index,
                )
                for opportunity in requested_place_opportunities(
                    route_geometry=source.draft.route.geometry,
                    routing_points=source.draft.routing_points,
                    requested_stops=request.requested_stops,
                )
                if opportunity.route_progress_share >= pivot_progress
                and opportunity.place.routing_coordinate != pivot_coordinate
            )
            continuations = tuple(
                sorted(
                    (*requested_continuations, *poi_continuations),
                    key=lambda option: (
                        0 if option.requested_index is not None else 1,
                        option.route_progress_share,
                        option.requested_index
                        if option.requested_index is not None
                        else option.poi_opportunity.match.feature.id
                        if option.poi_opportunity is not None
                        else "",
                    ),
                )[:1]
            )
            for continuation in continuations:
                points = insert_coordinate_after(
                    source.draft.routing_points,
                    after=pivot_coordinate,
                    coordinate=continuation.coordinate,
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
                route_geometry = route.analysis.loop_geometry
                backtracking_improved = (
                    route.analysis.immediate_backtrack.distance_m
                    < source.draft.route.analysis.immediate_backtrack.distance_m
                )
                proximity_improved = (
                    geometry is not None
                    and route_geometry is not None
                    and route_geometry.outbound_return_proximity.share
                    < geometry.outbound_return_proximity.share
                )
                if not backtracking_improved and not proximity_improved:
                    continue
                matches = query_collectible_matches(
                    index=poi_index,
                    route_geometry=route.geometry,
                    request=request,
                    settings=self._settings.poi,
                )
                opportunity = continuation.poi_opportunity
                if opportunity is not None:
                    continuation_match = next(
                        (
                            match
                            for match in matches
                            if match.feature.id == opportunity.match.feature.id
                        ),
                        None,
                    )
                    if (
                        continuation_match is None
                        or continuation_match.distance_m
                        > opportunity.arrival_tolerance_m
                    ):
                        continue
                deliberately_routed = source.deliberately_routed_requested_indices
                if continuation.requested_index is not None:
                    requested_visit = measure_requested_place_visits(
                        route_geometry=route.geometry,
                        requested_stops=(
                            request.requested_stops[continuation.requested_index],
                        ),
                        deliberately_routed_indices=frozenset({0}),
                    )[0]
                    if not requested_visit.selected:
                        continue
                    deliberately_routed = frozenset(
                        {
                            *deliberately_routed,
                            continuation.requested_index,
                        }
                    )
                records = _records_without_final_deltas(source.inserted_records)
                if opportunity is not None:
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
                    construction="corridor_continuation",
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
                provisional = self._search_candidate(
                    request=request,
                    draft=draft,
                    visits=visits,
                    rejected=(),
                    family_control=source.family_control,
                    inserted=True,
                    deliberately_routed_requested_indices=(deliberately_routed),
                )
                explanation = TourRepairExplanation(
                    reason="corridor_continuation",
                    repeated_distance_removed_m=max(
                        0.0,
                        source.draft.route.analysis.repetition.repeated_distance.distance_m
                        - route.analysis.repetition.repeated_distance.distance_m,
                    ),
                    immediate_backtracking_removed_m=max(
                        0.0,
                        source.draft.route.analysis.immediate_backtrack.distance_m
                        - route.analysis.immediate_backtrack.distance_m,
                    ),
                    additional_route_distance_m=(
                        route.summary.distance_m - source.draft.route.summary.distance_m
                    ),
                    requested_stops_selected=max(
                        0,
                        provisional.selected_must_visit_count
                        + provisional.selected_preferred_place_count
                        - source.candidate.selected_must_visit_count
                        - source.candidate.selected_preferred_place_count,
                    ),
                    added_scenic_pois=max(
                        0,
                        provisional.selected_scenic_count
                        - source.candidate.selected_scenic_count,
                    ),
                    added_verified_water_pois=max(
                        0,
                        provisional.selected_verified_water_count
                        - source.candidate.selected_verified_water_count,
                    ),
                    geometry_changed=(draft.signature != source.draft.signature),
                )
                candidate = provisional.model_copy(update={"repair": explanation})
                repaired.append(
                    _InsertionState(
                        draft=draft,
                        family_control=source.family_control,
                        base_already_ids=source.base_already_ids,
                        selected_poi_ids=source.selected_poi_ids
                        if opportunity is None
                        else (
                            *source.selected_poi_ids,
                            opportunity.match.feature.id,
                        ),
                        selected_progress=source.selected_progress
                        if opportunity is None
                        else (
                            *source.selected_progress,
                            opportunity.match.route_progress_share,
                        ),
                        inserted_records=records,
                        deliberately_routed_requested_indices=(deliberately_routed),
                        candidate=candidate,
                    )
                )
        return tuple(repaired)

    def _continuation_pivot(
        self, source: _InsertionState
    ) -> tuple[Coordinate, float] | None:
        poi_index = self._poi_index
        if source.selected_poi_ids and poi_index is not None:
            feature = poi_index.get_feature(source.selected_poi_ids[-1])
            if feature is not None:
                progress = (
                    source.selected_progress[-1] if source.selected_progress else 0.0
                )
                approaches = approach_candidates_for_feature(feature)
                return (
                    approaches[0].coordinate if approaches else feature.coordinate,
                    progress,
                )
        routed = sorted(source.deliberately_routed_requested_indices)
        if not routed:
            return None
        index = routed[-1]
        if index >= len(source.candidate.requested_place_visits):
            return None
        visit = source.candidate.requested_place_visits[index]
        return visit.requested_place.routing_coordinate, visit.route_progress_share
