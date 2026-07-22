"""Canonical Auto Tour candidate production and publication."""

from sugarglider.planning.alternative_legs import LowOverlapSettings
from sugarglider.planning.auto_tour.candidate_models import (
    AutoTourCandidate,
)
from sugarglider.planning.auto_tour.discovered_search import DiscoveredSearchMixin
from sugarglider.planning.auto_tour.loop_search import LoopSearchMixin
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
    DroppedPoiStop,
    RequestedTourPlace,
    SelectedPoiStop,
)
from sugarglider.planning.auto_tour.open_search import OpenSearchMixin
from sugarglider.planning.auto_tour.quality import AutoTourQualityMixin
from sugarglider.planning.auto_tour.ranking import (
    canonical_auto_tour_key,
    score_route,
)
from sugarglider.planning.auto_tour.repairs import RepairSearchMixin
from sugarglider.planning.auto_tour.requested_search import RequestedSearchMixin
from sugarglider.planning.auto_tour.skeleton_search import SkeletonSearchMixin
from sugarglider.planning.auto_tour.state import AutoTourSettings
from sugarglider.planning.auto_tour.through_routes import ThroughRouteSearchMixin
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.evaluator import CandidateEvaluator
from sugarglider.planning.models import AutoTourPlanRequest, PlanRequestBase
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
from sugarglider.pois.index import PoiIndex
from sugarglider.routing.backend import AutoTourRoutingBackend
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
        candidates = tuple(
            self._evaluator.evaluate(
                request=request,
                draft=_candidate_draft(candidate, request),
                scorer=self._scorer,
            )
            for candidate in result.candidates
        )
        evaluated = evaluate_candidate_portfolio(
            request,
            candidates,
            limit=request.candidate_count,
            ranking_key=lambda candidate: canonical_auto_tour_key(
                candidate, request.distance_objective.priority
            ),
        )
        return PlanResult(
            kind=request.kind,
            topology=request.topology,
            routing_profile=request.routing_profile,
            effective_start=request.start,
            effective_end=request.effective_end,
            candidates=evaluated.candidates,
            search_diagnostics=evaluated.attach_rejections(result.diagnostics),
        )


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
