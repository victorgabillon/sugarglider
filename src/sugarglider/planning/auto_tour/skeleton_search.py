"""Routed Auto Tour skeleton and control search."""

# mypy: disable-error-code="attr-defined"

from sugarglider.planning.auto_tour.controls import (
    LoopSkeleton,
    classify_route_direction,
    routing_points_with_hard_anchors,
    routing_points_with_sampled_hard_anchors,
    sample_round_trip_routing_points,
)
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
)
from sugarglider.planning.auto_tour.search_support import (
    _valid_closed_geometry,
)
from sugarglider.planning.auto_tour.state import (
    ROUND_TRIP_CONTROL_HEADINGS,
    _Draft,
    _SearchState,
)
from sugarglider.planning.budget import SearchPhase
from sugarglider.planning.routing_gateway import SearchBudgetExhaustedError
from sugarglider.planning.signatures import candidate_signature
from sugarglider.routing.backend import (
    IsochroneResult,
)
from sugarglider.routing.errors import (
    RoutingError,
    RoutingTimeoutError,
    RoutingUnavailableError,
    RoutingUpstreamError,
)


class SkeletonSearchMixin:
    async def _load_isochrone(
        self,
        request: AutoTourSearchRequest,
        state: _SearchState,
        warnings: set[str],
    ) -> IsochroneResult | None:
        state.isochrone_proposals_generated += 1
        try:
            result = await state.context.routes.isochrone(
                request.effective_start,
                request.profile,
                distance_limit_m=request.target_distance_m / 2,
                buckets=1,
                reverse_flow=False,
                phase=SearchPhase.CONTROL,
            )
        except SearchBudgetExhaustedError:
            state.budget_exhausted = True
            return None
        except (RoutingTimeoutError, RoutingUnavailableError):
            raise
        except RoutingError:
            warnings.add("auto_tour_isochrone_unavailable")
            return None
        if result.geometry_was_repaired:
            warnings.add("auto_tour_isochrone_geometry_repaired")
        return result

    async def _route_skeleton(
        self,
        request: AutoTourSearchRequest,
        skeleton: LoopSkeleton,
        state: _SearchState,
    ) -> _Draft | None:
        points = routing_points_with_hard_anchors(
            skeleton, request.interior_hard_waypoints
        )
        path = await self._route_points(
            points, request.profile, SearchPhase.SKELETON, state
        )
        if path is None or not self._valid_complete_path(path, points):
            return None
        try:
            route = self._result_factory.create(
                name=request.name,
                path=path,
                input_point_count=len(points),
            )
        except RoutingUpstreamError:
            return None
        direction = classify_route_direction(route.geometry)
        hard_visits = self._hard_point_visits(request, points, path.snapped_points)
        state.skeleton_candidates += 1
        return _Draft(
            route=route,
            routed_path=path,
            routing_points=points,
            signature=candidate_signature(route),
            construction="isochrone_ellipse",
            skeleton_id=skeleton.skeleton_id,
            skeleton_method="isochrone_ellipse",
            direction=direction.direction,
            direction_warnings=direction.warnings,
            hard_point_visits=hard_visits,
            ellipse_bearing_degrees=skeleton.bearing_degrees,
            ellipse_aspect_ratio=skeleton.aspect_ratio,
            ellipse_perimeter_scale=skeleton.perimeter_scale,
            ellipse_containment_scale=skeleton.containment_scale,
        )

    async def _round_trip_controls(
        self,
        request: AutoTourSearchRequest,
        state: _SearchState,
        *,
        sample_fallback: bool,
    ) -> tuple[_Draft, ...]:
        drafts: list[_Draft] = []
        for index, heading in enumerate(
            ROUND_TRIP_CONTROL_HEADINGS[: self._settings.round_trip_control_budget]
        ):
            path = await self._round_trip(
                request=request,
                heading=heading,
                derived_seed=request.seed + index * 104_729,
                state=state,
            )
            if path is None or not _valid_closed_geometry(path):
                continue
            try:
                route = self._result_factory.create(
                    name=request.name,
                    path=path,
                    input_point_count=2,
                )
            except RoutingUpstreamError:
                continue
            direction = classify_route_direction(route.geometry)
            raw = _Draft(
                route=route,
                routed_path=path,
                routing_points=(request.effective_start,),
                signature=candidate_signature(route),
                construction="graphhopper_round_trip",
                skeleton_id=f"round-trip-h{heading:g}",
                skeleton_method="graphhopper_round_trip",
                direction=direction.direction,
                direction_warnings=direction.warnings,
                hard_point_visits=self._hard_point_visits(
                    request, (request.effective_start,), None
                ),
            )
            drafts.append(raw)
            if not sample_fallback:
                continue
            sampled = sample_round_trip_routing_points(
                start=request.effective_start,
                geometry=path.geometry,
                route_distance_m=path.distance_m,
            )
            if sampled is None:
                continue
            points = routing_points_with_sampled_hard_anchors(
                sampled, request.interior_hard_waypoints
            )
            sampled_path = await self._route_points(
                points, request.profile, SearchPhase.SKELETON, state
            )
            if sampled_path is None or not self._valid_complete_path(
                sampled_path, points
            ):
                continue
            try:
                sampled_route = self._result_factory.create(
                    name=request.name,
                    path=sampled_path,
                    input_point_count=len(points),
                )
            except RoutingUpstreamError:
                continue
            sampled_direction = classify_route_direction(sampled_route.geometry)
            state.skeleton_candidates += 1
            state.sampled_fallback_skeletons += 1
            drafts.append(
                _Draft(
                    route=sampled_route,
                    routed_path=sampled_path,
                    routing_points=points,
                    signature=candidate_signature(sampled_route),
                    construction="graphhopper_round_trip_sampled",
                    skeleton_id=f"round-trip-sampled-h{heading:g}",
                    skeleton_method="graphhopper_round_trip_sampled",
                    direction=sampled_direction.direction,
                    direction_warnings=sampled_direction.warnings,
                    hard_point_visits=self._hard_point_visits(
                        request, points, sampled_path.snapped_points
                    ),
                )
            )
        return tuple(drafts)
