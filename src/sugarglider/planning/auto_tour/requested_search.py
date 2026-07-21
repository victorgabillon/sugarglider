"""Requested-stop routing and bounded subset search."""

# mypy: disable-error-code="attr-defined"

from typing import cast

from sugarglider.analysis.open_route import analyze_open_route
from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.models import Coordinate
from sugarglider.planning.auto_tour.controls import (
    classify_route_direction,
    routing_points_with_sampled_hard_anchors,
    sample_round_trip_routing_points,
)
from sugarglider.planning.auto_tour.decisions import (
    _approach_evaluation_points,
)
from sugarglider.planning.auto_tour.discovered_pois import (
    build_poi_visits,
    query_collectible_matches,
)
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
    RequestedPlaceFailureReason,
    RequestedTourPlace,
    poi_excursion_penalty_m,
)
from sugarglider.planning.auto_tour.requested_stops import (
    measure_requested_place_visits,
    requested_place_order_proposals,
)
from sugarglider.planning.auto_tour.search_support import (
    _maximum_distance,
)
from sugarglider.planning.auto_tour.selection import (
    _maximum_rejection_reason,
)
from sugarglider.planning.auto_tour.state import (
    _Draft,
    _InsertionState,
    _RequestedRouteOutcome,
    _SearchState,
)
from sugarglider.planning.budget import SearchPhase
from sugarglider.planning.cache import RouteCacheKey
from sugarglider.planning.signatures import candidate_signature
from sugarglider.routing.backend import (
    RoutedPath,
)
from sugarglider.routing.composition import (
    RouteCompositionError,
    compose_routed_segments,
)
from sugarglider.routing.errors import (
    RoutingUpstreamError,
)


class RequestedSearchMixin:
    async def _insert_requested_stops(
        self,
        *,
        request: AutoTourSearchRequest,
        initial: _InsertionState,
        state: _SearchState,
    ) -> tuple[_InsertionState, ...]:
        """Evaluate bounded complete requested-place families before discovered POIs."""
        request = await self._select_route_aware_approaches(
            request=request,
            initial=initial,
            state=state,
        )
        indexed_places = tuple(
            (index, request.requested_stops[index])
            for index in request.interior_requested_place_indices
            if request.requested_stops[index].chosen_approach is not None
        )
        if not indexed_places:
            return (initial,)
        for _index, place in indexed_places:
            if (
                place.chosen_approach is not None
                and place.chosen_approach.id not in state.considered_approach_ids
            ):
                state.considered_approach_ids.add(place.chosen_approach.id)
                state.approach_candidates_considered += 1
        deliberately_routed = frozenset(index for index, _place in indexed_places)
        coordinate_by_index = {
            index: place.routing_coordinate for index, place in indexed_places
        }
        orders = requested_place_order_proposals(
            start=request.effective_start,
            end=request.effective_end,
            indexed_places=indexed_places,
            topology=request.resolved_endpoints.topology,
            direct_geometry=(
                initial.family_control.route.geometry
                if request.resolved_endpoints.topology == "point_to_point"
                else ()
            ),
        )
        stable_points = (
            request.effective_start,
            *request.interior_hard_waypoints,
            request.effective_end,
        )
        control_anchors: tuple[Coordinate, ...] = ()
        if request.resolved_endpoints.topology == "loop" and len(indexed_places) <= 2:
            candidate_anchors = initial.draft.routing_points
            if len(candidate_anchors) < 4:
                sampled = sample_round_trip_routing_points(
                    start=request.effective_start,
                    geometry=initial.draft.route.geometry,
                    route_distance_m=initial.draft.route.summary.distance_m,
                )
                candidate_anchors = sampled or ()
            excluded = {
                (request.effective_start.lat, request.effective_start.lon),
                *((point.lat, point.lon) for point in coordinate_by_index.values()),
                *((point.lat, point.lon) for point in request.interior_hard_waypoints),
            }
            control_anchors = tuple(
                point
                for point in candidate_anchors
                if (point.lat, point.lon) not in excluded
            )
        proposals = tuple(
            routing_points_with_sampled_hard_anchors(
                (
                    request.effective_start,
                    *(coordinate_by_index[index] for index in order),
                    *control_anchors,
                    request.effective_end,
                ),
                request.interior_hard_waypoints,
            )
            for order in orders
        )
        children: list[_InsertionState] = []
        signatures: set[tuple[tuple[float, float], ...]] = set()
        requested_index_by_coordinate = {
            (coordinate.lat, coordinate.lon): index
            for index, coordinate in coordinate_by_index.items()
        }
        for proposal_index, points in enumerate(proposals):
            point_signature = tuple((point.lat, point.lon) for point in points)
            if point_signature in signatures:
                continue
            signatures.add(point_signature)
            state.full_set_route_attempted = True
            outcome = await self._route_requested_sequence(
                points,
                request.profile,
                state,
                requested_index_by_coordinate=requested_index_by_coordinate,
            )
            failure_reasons: dict[int, RequestedPlaceFailureReason] = {}
            if outcome is not None:
                complete = not outcome.removed_requested_indices
                if complete:
                    state.full_set_route_succeeded = True
                    state.full_set_distance_m = min(
                        outcome.path.distance_m,
                        state.full_set_distance_m or outcome.path.distance_m,
                    )
                    eligible = outcome.path.distance_m <= _maximum_distance(request)
                    if not eligible:
                        state.full_set_safety_eligible = False
                    if not eligible and state.full_set_rejection_reason is None:
                        state.full_set_rejection_reason = _maximum_rejection_reason(
                            request
                        )
                state.complete_set_candidate_distance_m = min(
                    outcome.path.distance_m,
                    state.complete_set_candidate_distance_m or outcome.path.distance_m,
                )
                failure_reasons.update(
                    {
                        index: "requested_place_graph_unreachable"
                        for index in outcome.removed_requested_indices
                    }
                )
                (
                    outcome,
                    ceiling_removed,
                ) = await self._repair_requested_distance_ceiling(
                    outcome,
                    profile=request.profile,
                    state=state,
                    requested_index_by_coordinate=requested_index_by_coordinate,
                    maximum_distance_m=_maximum_distance(request),
                )
                failure_reasons.update(
                    {
                        index: _maximum_rejection_reason(request)
                        for index in ceiling_removed
                    }
                )
            elif (
                not state.full_set_route_succeeded
                and state.full_set_rejection_reason is None
            ):
                state.full_set_rejection_reason = (
                    "requested_place_search_budget_exhausted"
                    if state.requested_place_budget_exhausted
                    else "requested_place_graph_unreachable"
                )
            if outcome is None or not self._valid_requested_path(
                outcome.path,
                outcome.points,
                stable_points=stable_points,
            ):
                continue
            path = outcome.path
            routed_points = outcome.points
            routed_requested = deliberately_routed.difference(failure_reasons)
            try:
                route = self._result_factory.create(
                    name=request.name,
                    path=path,
                    input_point_count=len(routed_points),
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
            visits = build_poi_visits(
                matches=matches,
                preferred_poi_ids=frozenset(request.preferred_poi_ids),
                base_already_ids=initial.base_already_ids,
                inserted_records={},
            )
            direction = classify_route_direction(route.geometry)
            draft = _Draft(
                route=route,
                routed_path=outcome.path,
                routing_points=routed_points,
                signature=candidate_signature(
                    route,
                    topology=request.resolved_endpoints.topology,
                ),
                construction="requested_place_family",
                skeleton_id=(f"{initial.draft.skeleton_id}-requested-{proposal_index}"),
                skeleton_method=initial.draft.skeleton_method,
                direction=direction.direction,
                direction_warnings=direction.warnings,
                hard_point_visits=self._hard_point_visits(
                    request, routed_points, path.snapped_points
                ),
                ellipse_bearing_degrees=initial.draft.ellipse_bearing_degrees,
                ellipse_aspect_ratio=initial.draft.ellipse_aspect_ratio,
                ellipse_perimeter_scale=initial.draft.ellipse_perimeter_scale,
                ellipse_containment_scale=initial.draft.ellipse_containment_scale,
            )
            candidate = self._search_candidate(
                request=request,
                draft=draft,
                visits=visits,
                rejected=(),
                family_control=initial.family_control,
                inserted=True,
                deliberately_routed_requested_indices=routed_requested,
                requested_failure_reasons=failure_reasons,
            )
            if not failure_reasons and len(routed_requested) == len(indexed_places):
                severe_backtracking = (
                    route.analysis.immediate_backtrack.distance_m > 1_000.0
                    and route.analysis.immediate_backtrack.share > 0.10
                )
                candidate_safe = (
                    route.summary.distance_m <= _maximum_distance(request)
                    and not severe_backtracking
                )
                state.full_set_safety_eligible = (
                    candidate_safe
                    if state.full_set_safety_eligible is None
                    else state.full_set_safety_eligible or candidate_safe
                )
                if candidate_safe:
                    state.full_set_rejection_reason = None
                elif (
                    route.summary.distance_m <= _maximum_distance(request)
                    and state.full_set_rejection_reason is None
                ):
                    state.full_set_rejection_reason = "requested_place_safety_rejected"
            children.append(
                _InsertionState(
                    draft=draft,
                    family_control=initial.family_control,
                    base_already_ids=initial.base_already_ids,
                    selected_poi_ids=(),
                    selected_progress=(),
                    inserted_records={},
                    deliberately_routed_requested_indices=routed_requested,
                    candidate=candidate,
                )
            )
        return (*children, initial)

    async def _select_route_aware_approaches(
        self,
        *,
        request: AutoTourSearchRequest,
        initial: _InsertionState,
        state: _SearchState,
    ) -> AutoTourSearchRequest:
        """Choose bounded requested approaches using complete routed sequences."""
        variable_indices = tuple(
            index
            for index in request.interior_requested_place_indices
            if len(request.requested_stops[index].approach_candidates) > 1
            and request.requested_stops[index].approach_override is None
        )
        if not variable_indices:
            return request
        beam: tuple[tuple[RequestedTourPlace, ...], ...] = (request.requested_stops,)
        for requested_index in variable_indices:
            expanded: list[
                tuple[tuple[object, ...], tuple[RequestedTourPlace, ...]]
            ] = []
            for places in beam:
                place = places[requested_index]
                for approach in place.approach_candidates[:4]:
                    if (
                        state.budget.used(SearchPhase.APPROACH)
                        >= self._settings.approach_route_evaluation_budget
                    ):
                        break
                    updated_places = list(places)
                    updated_places[requested_index] = place.model_copy(
                        update={"chosen_approach": approach}
                    )
                    candidate_places = tuple(updated_places)
                    evaluation_request = request.model_copy(
                        update={"requested_stops": candidate_places}
                    )
                    points = _approach_evaluation_points(
                        evaluation_request, initial.draft
                    )
                    path = await self._route_points(
                        points, request.profile, SearchPhase.APPROACH, state
                    )
                    if approach.id not in state.considered_approach_ids:
                        state.considered_approach_ids.add(approach.id)
                        state.approach_candidates_considered += 1
                    if path is None or not self._valid_requested_path(
                        path,
                        points,
                        stable_points=(
                            request.effective_start,
                            *request.interior_hard_waypoints,
                            request.effective_end,
                        ),
                    ):
                        continue
                    try:
                        route = self._result_factory.create(
                            name=request.name,
                            path=path,
                            input_point_count=len(points),
                        )
                    except RoutingUpstreamError:
                        continue
                    visits = measure_requested_place_visits(
                        route_geometry=route.geometry,
                        requested_stops=candidate_places,
                        deliberately_routed_indices=frozenset(
                            evaluation_request.interior_requested_place_indices
                        ),
                        routing_points=points,
                        snapped_routing_points=path.snapped_points,
                    )
                    invalid_arrivals = sum(
                        not visit.selected
                        for index, visit in enumerate(visits)
                        if index in evaluation_request.interior_requested_place_indices
                    )
                    if invalid_arrivals:
                        continue
                    loop_penalty = (
                        route.analysis.loop_geometry.penalty_breakdown.total
                        if route.analysis.loop_geometry is not None
                        else 0.0
                    )
                    reverse_progress = 0.0
                    if request.resolved_endpoints.topology == "point_to_point":
                        try:
                            reverse_progress = analyze_open_route(
                                geometry=route.geometry,
                                route_distance_m=route.summary.distance_m,
                                direct_geometry=initial.family_control.route.geometry,
                                direct_distance_m=(
                                    initial.family_control.route.summary.distance_m
                                ),
                            ).reverse_progress_distance_m
                        except ValueError:
                            reverse_progress = route.summary.distance_m
                    physical_spur_penalty = poi_excursion_penalty_m(
                        2.0 * route.analysis.immediate_backtrack.distance_m,
                        request.free_poi_spur_physical_m,
                    )
                    key: tuple[object, ...] = (
                        invalid_arrivals,
                        0
                        if route.summary.distance_m <= _maximum_distance(request)
                        else 1,
                        abs(route.summary.distance_m - request.target_distance_m),
                        route.analysis.immediate_backtrack.distance_m,
                        route.analysis.repetition.repeated_distance.distance_m,
                        reverse_progress,
                        loop_penalty,
                        physical_spur_penalty,
                        tuple(
                            value.chosen_approach.id
                            if value.chosen_approach is not None
                            else ""
                            for value in candidate_places
                        ),
                    )
                    expanded.append((key, candidate_places))
            if not expanded:
                break
            expanded.sort(key=lambda value: value[0])
            deduplicated: list[tuple[RequestedTourPlace, ...]] = []
            signatures: set[tuple[str, ...]] = set()
            for _key, places in expanded:
                signature = tuple(
                    place.chosen_approach.id
                    if place.chosen_approach is not None
                    else ""
                    for place in places
                )
                if signature in signatures:
                    continue
                signatures.add(signature)
                deduplicated.append(places)
                if len(deduplicated) >= self._settings.approach_beam_width:
                    break
            beam = tuple(deduplicated)
        return request.model_copy(update={"requested_stops": beam[0]})

    async def _repair_requested_distance_ceiling(
        self,
        outcome: _RequestedRouteOutcome,
        *,
        profile: str,
        state: _SearchState,
        requested_index_by_coordinate: dict[tuple[float, float], int],
        maximum_distance_m: float,
    ) -> tuple[_RequestedRouteOutcome | None, frozenset[int]]:
        """Greedily remove the fewest high-detour requested hooks within budget."""
        current = outcome
        removed: set[int] = set()
        while current.path.distance_m > maximum_distance_m:
            points = current.points
            removable: list[tuple[float, int, int]] = []
            for position in range(1, len(points) - 1):
                point = points[position]
                requested_index = requested_index_by_coordinate.get(
                    (point.lat, point.lon)
                )
                if requested_index is None:
                    continue
                left = points[position - 1]
                right = points[position + 1]
                if profile != "hike":
                    raise ValueError(f"unsupported routing profile {profile}")
                left_path = cast(
                    RoutedPath | None,
                    state.context.routes.peek(
                        RouteCacheKey.for_route(
                            profile_id="hike",
                            points=(left, point),
                            pass_through=True,
                        )
                    ),
                )
                right_path = cast(
                    RoutedPath | None,
                    state.context.routes.peek(
                        RouteCacheKey.for_route(
                            profile_id="hike",
                            points=(point, right),
                            pass_through=True,
                        )
                    ),
                )
                left_distance = (
                    left_path.distance_m
                    if left_path is not None
                    else haversine_distance_m(
                        (left.lon, left.lat), (point.lon, point.lat)
                    )
                )
                right_distance = (
                    right_path.distance_m
                    if right_path is not None
                    else haversine_distance_m(
                        (point.lon, point.lat), (right.lon, right.lat)
                    )
                )
                direct_lower_bound = haversine_distance_m(
                    (left.lon, left.lat), (right.lon, right.lat)
                )
                estimated_saving = left_distance + right_distance - direct_lower_bound
                removable.append((-estimated_saving, requested_index, position))
            if not removable:
                return None, frozenset(removed)
            _saving, requested_index, position = min(removable)
            reduced_points = (*points[:position], *points[position + 1 :])
            repaired = await self._route_requested_sequence(
                reduced_points,
                profile,
                state,
                requested_index_by_coordinate=requested_index_by_coordinate,
            )
            if repaired is None:
                return None, frozenset(removed)
            removed.add(requested_index)
            removed.update(repaired.removed_requested_indices)
            current = repaired
        return current, frozenset(removed)

    async def _route_requested_sequence(
        self,
        points: tuple[Coordinate, ...],
        profile: str,
        state: _SearchState,
        *,
        requested_index_by_coordinate: dict[tuple[float, float], int],
    ) -> _RequestedRouteOutcome | None:
        """Route one order, composing only exact routed legs on node-cap failure."""
        if len(points) <= 12:
            path = await self._route_points(
                points, profile, SearchPhase.REQUESTED_STOP, state
            )
            if path is not None:
                return _RequestedRouteOutcome(path=path, points=points)
        routed_points = list(points)
        removed: set[int] = set()
        while len(routed_points) >= 2:
            segments: list[RoutedPath] = []
            failed_pair: tuple[Coordinate, Coordinate] | None = None
            for left, right in zip(routed_points, routed_points[1:], strict=False):
                segment = await self._route_points(
                    (left, right), profile, SearchPhase.REQUESTED_STOP, state
                )
                if segment is None:
                    failed_pair = (left, right)
                    break
                segments.append(segment)
            if failed_pair is None:
                try:
                    return _RequestedRouteOutcome(
                        path=compose_routed_segments(tuple(segments)),
                        points=tuple(routed_points),
                        removed_requested_indices=frozenset(removed),
                    )
                except RouteCompositionError:
                    return None
            if state.requested_place_budget_exhausted:
                return None
            removable = next(
                (
                    point
                    for point in (failed_pair[1], failed_pair[0])
                    if (point.lat, point.lon) in requested_index_by_coordinate
                ),
                None,
            )
            if removable is None:
                return None
            removed.add(requested_index_by_coordinate[(removable.lat, removable.lon)])
            routed_points.remove(removable)
        return None
