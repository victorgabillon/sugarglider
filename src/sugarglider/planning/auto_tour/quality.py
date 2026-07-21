"""Auto Tour complete-candidate evaluation inputs."""

# mypy: disable-error-code="attr-defined"

from time import perf_counter

from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.models import Coordinate
from sugarglider.planning.auto_tour.approaches import (
    approach_candidates_for_feature,
)
from sugarglider.planning.auto_tour.candidate_models import (
    AutoTourCandidate,
)
from sugarglider.planning.auto_tour.decisions import (
    _bounded_discovered_visits,
    _poi_drop_reason,
    _requested_semantic_id,
    _same_coordinate,
)
from sugarglider.planning.auto_tour.excursions import analyze_poi_excursions
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
    DiscoveredPoiVisit,
    DroppedPoiStop,
    HardWaypointVisit,
    RejectedPoiOpportunity,
    RequestedPlaceFailureReason,
    RequestedTourPlaceVisit,
    SelectedPoiStop,
    SemanticPoi,
    TourControlComparison,
    TourRepairExplanation,
)
from sugarglider.planning.auto_tour.ranking import (
    compare_with_control,
    control_comparison,
    score_route,
    soft_distance_penalty,
)
from sugarglider.planning.auto_tour.requested_stops import (
    measure_requested_place_visits,
)
from sugarglider.planning.auto_tour.search_support import (
    _hard_waypoints_selected,
    _maximum_distance,
    _valid_closed_geometry,
    _without_loop_geometry,
)
from sugarglider.planning.auto_tour.state import (
    MAX_CANDIDATE_REJECTIONS,
    _Draft,
    _SearchState,
)
from sugarglider.planning.budget import SearchPhase
from sugarglider.planning.routing_gateway import SearchBudgetExhaustedError
from sugarglider.routing.backend import (
    RoutedPath,
)
from sugarglider.routing.errors import (
    RoutingPointError,
)


class AutoTourQualityMixin:
    def _search_candidate(
        self,
        *,
        request: AutoTourSearchRequest,
        draft: _Draft,
        visits: tuple[DiscoveredPoiVisit, ...],
        rejected: tuple[RejectedPoiOpportunity, ...],
        family_control: _Draft,
        inserted: bool,
        deliberately_routed_requested_indices: frozenset[int] = frozenset(),
        requested_failure_reasons: dict[int, RequestedPlaceFailureReason] | None = None,
        repair: TourRepairExplanation | None = None,
    ) -> AutoTourCandidate:
        public_route = (
            _without_loop_geometry(draft.route)
            if request.resolved_endpoints.topology == "point_to_point"
            else draft.route
        )
        control_route = (
            _without_loop_geometry(family_control.route)
            if request.resolved_endpoints.topology == "point_to_point"
            else family_control.route
        )
        target_error = abs(public_route.summary.distance_m - request.target_distance_m)
        within = target_error <= request.tolerance_m
        requested_visits = measure_requested_place_visits(
            route_geometry=draft.route.geometry,
            requested_stops=request.requested_stops,
            deliberately_routed_indices=deliberately_routed_requested_indices,
            routing_points=draft.routing_points,
            snapped_routing_points=draft.route.snapped_points,
            failure_reasons=requested_failure_reasons,
        )
        requested_osm_references = {
            visit.requested_place.osm_reference
            for visit in requested_visits
            if visit.requested_place.osm_reference is not None
        }
        visits = tuple(
            visit for visit in visits if visit.poi.id not in requested_osm_references
        )
        total_reward = sum(visit.reward for visit in visits)
        inserted_reward = sum(visit.reward for visit in visits if visit.inserted)
        family_requested_visits = measure_requested_place_visits(
            route_geometry=family_control.route.geometry,
            requested_stops=request.requested_stops,
        )
        requested_gain = sum(visit.selected for visit in requested_visits) - sum(
            visit.selected for visit in family_requested_visits
        )
        maximum_distance = _maximum_distance(request)
        comparison: TourControlComparison
        if inserted:
            comparison = compare_with_control(
                route=public_route,
                within_tolerance=within,
                hard_waypoints_selected=_hard_waypoints_selected(draft),
                discovered_poi_reward=inserted_reward,
                control=control_route,
                control_within_tolerance=(
                    abs(control_route.summary.distance_m - request.target_distance_m)
                    <= request.tolerance_m
                ),
                control_signature=family_control.signature,
                requested_place_gain=requested_gain,
                distance_priority=request.distance_priority,
                maximum_distance_m=maximum_distance,
            )
            if (
                request.resolved_endpoints.topology == "loop"
                and request.direction_preference != "any"
                and draft.direction != request.direction_preference
            ):
                comparison = comparison.model_copy(
                    update={
                        "eligible": False,
                        "rejection_reasons": tuple(
                            sorted(
                                {
                                    *comparison.rejection_reasons,
                                    "direction_preference",
                                }
                            )
                        ),
                    }
                )
        else:
            comparison = control_comparison(public_route, draft.signature)
        scenic_count = sum(visit.poi.group == "scenic" for visit in visits)
        water_count = sum(
            visit.poi.category == "drinking_water"
            and visit.poi.potability == "verified"
            for visit in visits
        )
        selected_stops, dropped_stops = self._stop_decisions(
            request=request,
            requested_visits=requested_visits,
            poi_visits=visits,
            rejected=rejected,
        )
        excursion_analysis = analyze_poi_excursions(
            public_route,
            selected_stops,
            free_physical_spur_allowance_m=request.free_poi_spur_physical_m,
        )
        excursions = excursion_analysis.excursions
        return AutoTourCandidate(
            rank=1,
            route=public_route,
            routed_path=draft.routed_path,
            signature=draft.signature,
            construction=draft.construction,
            direction=draft.direction,
            skeleton_id=draft.skeleton_id,
            skeleton_method=draft.skeleton_method,
            ellipse_bearing_degrees=draft.ellipse_bearing_degrees,
            ellipse_aspect_ratio=draft.ellipse_aspect_ratio,
            ellipse_perimeter_scale=draft.ellipse_perimeter_scale,
            ellipse_containment_scale=draft.ellipse_containment_scale,
            routing_points=draft.routing_points,
            snapped_routing_points=public_route.snapped_points,
            hard_point_visits=draft.hard_point_visits,
            poi_visits=visits,
            requested_place_visits=requested_visits,
            selected_stops=excursion_analysis.selected_stops,
            dropped_stops=dropped_stops,
            poi_excursions=excursions,
            poi_excursion_physical_distance_m=sum(
                excursion.physical_spur_distance_m for excursion in excursions
            ),
            poi_excursion_returning_backtracking_m=sum(
                excursion.returning_backtrack_distance_m for excursion in excursions
            ),
            poi_excursion_repeated_distance_m=sum(
                excursion.physical_spur_distance_m for excursion in excursions
            ),
            poi_excursion_penalty_m_equivalent=sum(
                excursion.penalty_m_equivalent for excursion in excursions
            ),
            poi_attributed_backtracking_m=(
                excursion_analysis.attributed_immediate_backtracking_m
            ),
            non_poi_backtracking_m=excursion_analysis.non_poi_backtracking_m,
            rejected_poi_opportunities=rejected[:MAX_CANDIDATE_REJECTIONS],
            target_error_m=target_error,
            within_tolerance=within,
            distance_priority=request.distance_priority,
            soft_distance_penalty=soft_distance_penalty(
                distance_m=public_route.summary.distance_m,
                target_distance_m=request.target_distance_m,
                tolerance_m=request.tolerance_m,
                priority=request.distance_priority,
            ),
            maximum_distance_m=maximum_distance,
            control_eligible=comparison.eligible,
            control_comparison=comparison,
            total_poi_reward=total_reward,
            discovered_poi_reward=inserted_reward,
            selected_scenic_count=scenic_count,
            selected_verified_water_count=water_count,
            selected_must_visit_count=sum(
                visit.selected and visit.requested_place.importance == "must_visit"
                for visit in requested_visits
            ),
            selected_preferred_place_count=sum(
                visit.selected and visit.requested_place.importance == "prefer"
                for visit in requested_visits
            ),
            route_score=score_route(public_route, request.target_distance_m),
            repair=repair,
            warnings=tuple(
                sorted(
                    {
                        *draft.direction_warnings,
                        *(
                            warning
                            for excursion in excursions
                            for warning in excursion.warnings
                        ),
                    }
                )
            ),
        )

    def _stop_decisions(
        self,
        *,
        request: AutoTourSearchRequest,
        requested_visits: tuple[RequestedTourPlaceVisit, ...],
        poi_visits: tuple[DiscoveredPoiVisit, ...],
        rejected: tuple[RejectedPoiOpportunity, ...],
    ) -> tuple[tuple[SelectedPoiStop, ...], tuple[DroppedPoiStop, ...]]:
        selected: list[SelectedPoiStop] = []
        dropped: list[DroppedPoiStop] = []
        for raw_visit in requested_visits:
            place = raw_visit.requested_place
            semantic = SemanticPoi(
                id=_requested_semantic_id(place),
                name=place.name,
                coordinate=place.coordinate,
                category="requested_place",
                origin="requested",
                importance=place.importance,
                osm_reference=place.osm_reference,
            )
            if raw_visit.decision == "selected":
                if (
                    raw_visit.chosen_approach is None
                    or raw_visit.selection_reason is None
                ):
                    raise ValueError("selected requested stop has no valid approach")
                selected.append(
                    SelectedPoiStop(
                        semantic_poi=semantic,
                        chosen_approach=raw_visit.chosen_approach,
                        route_progress_share=raw_visit.route_progress_share,
                        measured_route_to_approach_m=raw_visit.measured_distance_m,
                        selection_reason=raw_visit.selection_reason,
                        deliberately_inserted=raw_visit.deliberately_routed,
                    )
                )
            else:
                if raw_visit.drop_reason is None:
                    raise ValueError("dropped requested stop has no reason")
                dropped.append(
                    DroppedPoiStop(
                        semantic_poi=semantic,
                        approach_candidates_considered=place.approach_candidates,
                        best_graph_snap_distance_m=raw_visit.graph_snap_distance_m,
                        drop_reason=raw_visit.drop_reason,
                    )
                )
        preferred_ids = frozenset(request.preferred_poi_ids)
        selected_osm_references = {
            stop.semantic_poi.osm_reference
            for stop in selected
            if stop.semantic_poi.osm_reference is not None
        }
        for visit in _bounded_discovered_visits(poi_visits, preferred_ids):
            feature = visit.poi
            if feature.id in selected_osm_references:
                continue
            selected.append(
                SelectedPoiStop(
                    semantic_poi=SemanticPoi(
                        id=feature.id,
                        name=feature.display_name,
                        coordinate=feature.coordinate,
                        category=feature.category,
                        origin=(
                            "discovered_water"
                            if feature.group == "hydration"
                            else "discovered_scenic"
                        ),
                        osm_reference=feature.id,
                    ),
                    chosen_approach=visit.chosen_approach,
                    route_progress_share=visit.route_progress_share,
                    measured_route_to_approach_m=visit.visit_distance_m,
                    selection_reason=(
                        "preferred_by_user"
                        if feature.id in preferred_ids
                        else "low_cost_insertion"
                        if visit.inserted
                        else "already_on_route"
                    ),
                    deliberately_inserted=visit.inserted,
                )
            )
        decided_ids = {stop.semantic_poi.id for stop in selected} | {
            stop.semantic_poi.id for stop in dropped
        }
        for rejection in rejected:
            if rejection.poi_id in decided_ids or self._poi_index is None:
                continue
            rejected_feature = self._poi_index.get_feature(rejection.poi_id)
            if rejected_feature is None:
                continue
            dropped.append(
                DroppedPoiStop(
                    semantic_poi=SemanticPoi(
                        id=rejected_feature.id,
                        name=rejected_feature.display_name,
                        coordinate=rejected_feature.coordinate,
                        category=rejected_feature.category,
                        origin=(
                            "discovered_water"
                            if rejected_feature.group == "hydration"
                            else "discovered_scenic"
                        ),
                        osm_reference=rejected_feature.id,
                    ),
                    approach_candidates_considered=approach_candidates_for_feature(
                        rejected_feature
                    ),
                    drop_reason=_poi_drop_reason(rejection.reason_code),
                    estimated_marginal_route_cost_m=rejection.estimated_detour_m,
                )
            )
            decided_ids.add(rejection.poi_id)
        return (
            tuple(
                sorted(
                    selected,
                    key=lambda stop: (
                        stop.route_progress_share,
                        stop.semantic_poi.id,
                    ),
                )
            ),
            tuple(sorted(dropped, key=lambda stop: stop.semantic_poi.id)),
        )

    async def _route_points(
        self,
        points: tuple[Coordinate, ...],
        profile: str,
        phase: SearchPhase,
        state: _SearchState,
    ) -> RoutedPath | None:
        if profile != "hike":
            raise ValueError(f"unsupported routing profile {profile}")
        started = perf_counter()
        try:
            path = await state.context.routes.route(
                points,
                "hike",
                pass_through=True,
                phase=phase,
            )
        except SearchBudgetExhaustedError:
            state.budget_exhausted = True
            if phase is SearchPhase.REQUESTED_STOP:
                state.requested_place_budget_exhausted = True
            elif phase is SearchPhase.DISCOVERED_POI:
                state.discovered_poi_budget_exhausted = True
            return None
        except RoutingPointError:
            return None
        finally:
            state.route_call_seconds += perf_counter() - started
        return path

    async def _round_trip(
        self,
        *,
        request: AutoTourSearchRequest,
        heading: float,
        derived_seed: int,
        state: _SearchState,
    ) -> RoutedPath | None:
        started = perf_counter()
        try:
            path = await state.context.routes.round_trip(
                request.effective_start,
                request.target_distance_m,
                derived_seed,
                request.profile,
                heading_degrees=heading,
                phase=SearchPhase.CONTROL,
            )
        except SearchBudgetExhaustedError:
            state.budget_exhausted = True
            return None
        except RoutingPointError:
            return None
        finally:
            state.route_call_seconds += perf_counter() - started
        return path

    def _valid_complete_path(
        self, path: RoutedPath, points: tuple[Coordinate, ...]
    ) -> bool:
        if path.snapped_points is None or len(path.snapped_points) != len(points):
            return False
        expects_loop = _same_coordinate(points[0], points[-1])
        if expects_loop != _valid_closed_geometry(path):
            return False
        return all(
            haversine_distance_m(
                (point.lon, point.lat),
                snapped,
            )
            <= self._settings.max_snap_displacement_m
            for point, snapped in zip(points, path.snapped_points, strict=True)
        )

    def _valid_requested_path(
        self,
        path: RoutedPath,
        points: tuple[Coordinate, ...],
        *,
        stable_points: tuple[Coordinate, ...],
    ) -> bool:
        """Validate full accounting while allowing soft places to miss their radius."""
        if path.snapped_points is None or len(path.snapped_points) != len(points):
            return False
        expects_loop = _same_coordinate(points[0], points[-1])
        if expects_loop != _valid_closed_geometry(path):
            return False
        stable_keys = {(point.lat, point.lon) for point in stable_points}
        return all(
            haversine_distance_m((point.lon, point.lat), snapped)
            <= self._settings.max_snap_displacement_m
            for point, snapped in zip(points, path.snapped_points, strict=True)
            if (point.lat, point.lon) in stable_keys
        )

    def _hard_point_visits(
        self,
        request: AutoTourSearchRequest,
        points: tuple[Coordinate, ...],
        snapped: tuple[tuple[float, float], ...] | None,
    ) -> tuple[HardWaypointVisit, ...]:
        visits: list[HardWaypointVisit] = []
        for original_index, hard_point in enumerate(request.hard_waypoints):
            point_index = next(
                (
                    index
                    for index, point in enumerate(points)
                    if _same_coordinate(point, hard_point)
                ),
                None,
            )
            snapped_point = (
                snapped[point_index]
                if snapped is not None
                and point_index is not None
                and point_index < len(snapped)
                else None
            )
            distance = (
                haversine_distance_m((hard_point.lon, hard_point.lat), snapped_point)
                if snapped_point is not None
                else None
            )
            visits.append(
                HardWaypointVisit(
                    original_index=original_index,
                    coordinate=hard_point,
                    snapped_coordinate=snapped_point,
                    snap_distance_m=distance,
                    selected=(
                        distance is not None
                        and distance <= self._settings.max_snap_displacement_m
                    ),
                )
            )
        return tuple(visits)
