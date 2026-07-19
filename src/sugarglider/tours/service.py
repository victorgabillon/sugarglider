"""Bounded skeleton-first Auto Tour generation and conservative POI insertion."""

from dataclasses import dataclass, field, replace
from time import perf_counter

from shapely.geometry import Point

from sugarglider.analysis.open_route import analyze_open_route
from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.endpoints import validated_endpoint_visits
from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.generation.low_overlap import LowOverlapBeamSearch, LowOverlapSettings
from sugarglider.generation.scoring import score_route
from sugarglider.generation.signatures import candidate_signature
from sugarglider.pois.index import PoiIndex
from sugarglider.routing.backend import (
    AutoTourRoutingBackend,
    IsochroneResult,
    RoutedPath,
)
from sugarglider.routing.composition import (
    RouteCompositionError,
    compose_routed_segments,
)
from sugarglider.routing.errors import (
    RoutingError,
    RoutingPointError,
    RoutingTimeoutError,
    RoutingUnavailableError,
    RoutingUpstreamError,
)
from sugarglider.routing.result import RouteResultFactory
from sugarglider.tours.models import (
    AutoTourCandidate,
    AutoTourRequest,
    AutoTourResult,
    AutoTourSearchSummary,
    AutoTourTimings,
    PoiRejectionReason,
    RejectedPoiOpportunity,
    RequestedPlaceFailureReason,
    SkeletonMethod,
    TourConstruction,
    TourControlComparison,
    TourDirection,
    TourHardPointVisit,
    TourPoiVisit,
    TourRepairExplanation,
)
from sugarglider.tours.poi_selection import (
    InsertedPoiRecord,
    PoiOpportunity,
    PoiShortlist,
    TourPoiSettings,
    build_poi_visits,
    query_collectible_matches,
    shortlist_route_pois,
)
from sugarglider.tours.requested_places import (
    insert_coordinate_after,
    measure_requested_place_visits,
    requested_place_opportunities,
    requested_place_order_proposals,
)
from sugarglider.tours.scoring import (
    auto_tour_ranking_key,
    compare_with_control,
    control_comparison,
    maximum_auto_tour_distance_m,
    soft_distance_penalty,
)
from sugarglider.tours.skeletons import (
    LoopSkeleton,
    classify_route_direction,
    generate_isochrone_skeletons,
    routing_points_with_hard_anchors,
    routing_points_with_sampled_hard_anchors,
    sample_round_trip_routing_points,
)

ISOCHRONE_REQUEST_BUDGET = 1
ROUND_TRIP_CONTROL_HEADINGS = (0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0)
ROUND_TRIP_CONTROL_REQUEST_BUDGET = 8
SKELETON_ROUTE_REQUEST_BUDGET = 24
RETAINED_SKELETON_LIMIT = 6
MAX_INSERTED_POIS = 4
POI_BEAM_WIDTH = 6
POI_ROUTE_EVALUATION_BUDGET = 24
REQUESTED_PLACE_ROUTE_EVALUATION_BUDGET = 60
POI_EXPANSIONS_PER_STATE = 4
LOCAL_REPAIR_ROUTE_EVALUATION_BUDGET = 12
ALTERNATIVE_LEG_REQUEST_BUDGET = 24
MAX_SNAP_DISPLACEMENT_M = 300.0
ROUTE_CLOSURE_TOLERANCE_M = 25.0
MAX_CANDIDATE_REJECTIONS = 12

type RouteCacheKey = tuple[str, tuple[tuple[float, float], ...], bool]
type RoundTripCacheKey = tuple[float, float, float, int, str, float | None]


class AutoTourNoCandidateError(ValueError):
    """No graph-valid control survived the bounded Auto Tour search."""


class AutoTourMaximumBelowDirectLowerBoundError(ValueError):
    """A user maximum cannot contain the graph-valid endpoint control."""


@dataclass(frozen=True)
class AutoTourSettings:
    """Strict named request budgets and server-controlled POI behavior."""

    round_trip_control_budget: int = ROUND_TRIP_CONTROL_REQUEST_BUDGET
    skeleton_route_budget: int = SKELETON_ROUTE_REQUEST_BUDGET
    retained_skeleton_limit: int = RETAINED_SKELETON_LIMIT
    max_inserted_pois: int = MAX_INSERTED_POIS
    poi_beam_width: int = POI_BEAM_WIDTH
    poi_route_evaluation_budget: int = POI_ROUTE_EVALUATION_BUDGET
    requested_place_route_evaluation_budget: int = (
        REQUESTED_PLACE_ROUTE_EVALUATION_BUDGET
    )
    local_repair_route_evaluation_budget: int = LOCAL_REPAIR_ROUTE_EVALUATION_BUDGET
    alternative_leg_request_budget: int = ALTERNATIVE_LEG_REQUEST_BUDGET
    max_snap_displacement_m: float = MAX_SNAP_DISPLACEMENT_M
    poi: TourPoiSettings = TourPoiSettings()

    def __post_init__(self) -> None:
        if not 1 <= self.round_trip_control_budget <= 8:
            raise ValueError("round-trip control budget must be between 1 and 8")
        if not 1 <= self.skeleton_route_budget <= 24:
            raise ValueError("skeleton route budget must be between 1 and 24")
        if not 1 <= self.retained_skeleton_limit <= 6:
            raise ValueError("retained skeleton limit must be between 1 and 6")
        if not 0 <= self.max_inserted_pois <= 4:
            raise ValueError("maximum inserted POIs must be between 0 and 4")
        if not 1 <= self.poi_beam_width <= 6:
            raise ValueError("POI beam width must be between 1 and 6")
        if not 0 <= self.poi_route_evaluation_budget <= 24:
            raise ValueError("POI route budget must be between 0 and 24")
        if not 0 <= self.requested_place_route_evaluation_budget <= 60:
            raise ValueError("requested-place route budget must be between 0 and 60")
        if not 0 <= self.local_repair_route_evaluation_budget <= 12:
            raise ValueError("local repair route budget must be between 0 and 12")
        if not 0 <= self.alternative_leg_request_budget <= 24:
            raise ValueError("alternative-leg budget must be between 0 and 24")
        if self.max_snap_displacement_m < 0:
            raise ValueError("snap displacement must be non-negative")

    @property
    def total_route_request_budget(self) -> int:
        return (
            self.round_trip_control_budget
            + self.skeleton_route_budget
            + self.poi_route_evaluation_budget
            + self.requested_place_route_evaluation_budget
            + self.local_repair_route_evaluation_budget
            + self.alternative_leg_request_budget
        )


@dataclass
class _SearchState:
    route_cache: dict[RouteCacheKey, RoutedPath | None] = field(default_factory=dict)
    round_trip_cache: dict[RoundTripCacheKey, RoutedPath | None] = field(
        default_factory=dict
    )
    isochrone_requests: int = 0
    round_trip_requests: int = 0
    skeleton_requests: int = 0
    skeleton_candidates: int = 0
    poi_requests: int = 0
    requested_place_requests: int = 0
    repair_requests: int = 0
    alternative_requests: int = 0
    sampled_fallback_skeletons: int = 0
    corridor_repair_requests: int = 0
    route_cache_hits: int = 0
    budget_exhausted: bool = False
    requested_place_budget_exhausted: bool = False
    discovered_poi_budget_exhausted: bool = False
    route_call_seconds: float = 0.0
    poi_index_candidate_count: int = 0
    already_collected_count: int = 0
    complete_set_candidate_distance_m: float | None = None
    full_set_route_attempted: bool = False
    full_set_route_succeeded: bool = False
    full_set_distance_m: float | None = None
    full_set_safety_eligible: bool | None = None
    full_set_rejection_reason: str | None = None
    rejected_by_skeleton: dict[str, list[RejectedPoiOpportunity]] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class _Draft:
    route: RouteResult
    routing_points: tuple[Coordinate, ...]
    signature: str
    construction: TourConstruction
    skeleton_id: str
    skeleton_method: SkeletonMethod
    direction: TourDirection
    direction_warnings: tuple[str, ...]
    hard_point_visits: tuple[TourHardPointVisit, ...]
    ellipse_bearing_degrees: float | None = None
    ellipse_aspect_ratio: float | None = None
    ellipse_perimeter_scale: float | None = None
    ellipse_containment_scale: float | None = None


@dataclass(frozen=True)
class _InsertionState:
    draft: _Draft
    family_control: _Draft
    base_already_ids: frozenset[str]
    selected_poi_ids: tuple[str, ...]
    selected_progress: tuple[float, ...]
    inserted_records: dict[str, InsertedPoiRecord]
    deliberately_routed_requested_indices: frozenset[int]
    candidate: AutoTourCandidate


@dataclass(frozen=True)
class _ContinuationOption:
    coordinate: Coordinate
    route_progress_share: float
    poi_opportunity: PoiOpportunity | None = None
    requested_index: int | None = None


@dataclass(frozen=True)
class _RequestedRouteOutcome:
    path: RoutedPath
    points: tuple[Coordinate, ...]
    removed_requested_indices: frozenset[int] = frozenset()


class AutoTourService:
    """Build loop controls first, then softly collect bounded local POIs."""

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
        self._result_factory = result_factory
        self._poi_index = poi_index
        self._settings = settings or AutoTourSettings()
        self._nature_index_available = nature_index_available
        self._structural_result_factory = (
            structural_result_factory
            if structural_result_factory is not None
            else RouteResultFactory()
        )
        configured_low_overlap = low_overlap_settings or LowOverlapSettings()
        self._low_overlap_settings = LowOverlapSettings(
            max_paths=configured_low_overlap.max_paths,
            max_weight_factor=configured_low_overlap.max_weight_factor,
            max_share_factor=configured_low_overlap.max_share_factor,
            beam_width=configured_low_overlap.beam_width,
            max_leg_requests=max(
                1,
                min(
                    configured_low_overlap.max_leg_requests,
                    self._settings.alternative_leg_request_budget or 1,
                ),
            ),
            source_count=min(2, configured_low_overlap.source_count),
        )

    async def generate(self, request: AutoTourRequest) -> AutoTourResult:
        """Return a retained no-POI control and conservative ranked candidates."""
        if request.resolved_endpoints.topology == "point_to_point":
            return await self._generate_open_tour(request)
        started = perf_counter()
        state = _SearchState()
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
            if state.skeleton_requests >= self._settings.skeleton_route_budget:
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
        controls = [draft for draft in controls if _hard_points_satisfied(draft)]
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
            base_candidate = self._public_candidate(
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
            requested_states = await self._insert_requested_places(
                request=request,
                initial=start_state,
                state=state,
            )
            for requested_state in requested_states:
                if request.requested_places and requested_state is start_state:
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
            global_control = self._public_candidate(
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
                        visit.satisfied
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
                if any(
                    visit.deliberately_routed
                    for visit in candidate.requested_place_visits
                )
            ),
            key=lambda candidate: (
                -candidate.satisfied_must_visit_count,
                -candidate.satisfied_preferred_place_count,
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
            and not request.requested_places
            and request.scenic_preference == "prefer"
            and not any(candidate.inserted_poi_reward > 0 for candidate in eligible)
        ):
            warnings.add("auto_tour_no_safe_poi_improvement")
        if (
            self._poi_index is not None
            and not request.requested_places
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
            isochrone_request_count=state.isochrone_requests,
            round_trip_control_request_count=state.round_trip_requests,
            sampled_fallback_skeleton_count=state.sampled_fallback_skeletons,
            skeleton_route_request_count=state.skeleton_requests,
            skeleton_candidate_count=state.skeleton_candidates,
            retained_skeleton_count=len(retained),
            poi_index_candidate_count=state.poi_index_candidate_count,
            already_collected_poi_count=state.already_collected_count,
            poi_route_evaluation_count=(
                state.requested_place_requests + state.poi_requests
            ),
            requested_place_route_evaluations=state.requested_place_requests,
            discovered_poi_route_evaluations=state.poi_requests,
            requested_place_budget_exhausted=(state.requested_place_budget_exhausted),
            discovered_poi_budget_exhausted=state.discovered_poi_budget_exhausted,
            local_repair_evaluation_count=state.repair_requests,
            corridor_repair_evaluation_count=state.corridor_repair_requests,
            alternative_leg_request_count=state.alternative_requests,
            total_route_request_budget=self._settings.total_route_request_budget,
            total_route_request_count=(
                state.round_trip_requests
                + state.skeleton_requests
                + state.requested_place_requests
                + state.poi_requests
                + state.repair_requests
                + state.alternative_requests
            ),
            budget_exhausted=state.budget_exhausted,
            control_signature=control_ranked.signature,
            recommended_signature=recommended.signature,
            control_retained=True,
            selected_scenic_count=recommended.selected_scenic_count,
            selected_verified_water_count=(recommended.selected_verified_water_count),
            requested_place_satisfied_count=sum(
                visit.satisfied for visit in recommended.requested_place_visits
            ),
            requested_place_missed_count=sum(
                not visit.satisfied for visit in recommended.requested_place_visits
            ),
            complete_set_candidate_distance_m=(state.complete_set_candidate_distance_m),
            full_set_route_attempted=state.full_set_route_attempted,
            full_set_route_succeeded=state.full_set_route_succeeded,
            full_set_distance_m=state.full_set_distance_m,
            full_set_safety_eligible=state.full_set_safety_eligible,
            full_set_rejection_reason=state.full_set_rejection_reason,
            maximum_distance_m=_maximum_distance(request),
            route_cache_hit_count=state.route_cache_hits,
            timings=timings,
            warnings=tuple(sorted(warnings)),
        )
        visits, endpoint_warnings = validated_endpoint_visits(
            request.resolved_endpoints,
            recommended.route.snapped_points,
            maximum_snap_distance_m=self._settings.max_snap_displacement_m,
        )
        return AutoTourResult(
            control=control_ranked,
            candidates=ranked,
            search=summary,
            topology="loop",
            effective_start=request.effective_start,
            effective_end=request.effective_end,
            endpoint_visits=visits,
            endpoint_warnings=endpoint_warnings,
        )

    async def _generate_open_tour(self, request: AutoTourRequest) -> AutoTourResult:
        """Run the bounded endpoint-fixed Auto Tour lane without round trips."""
        started = perf_counter()
        state = _SearchState()
        warnings: set[str] = set()
        if self._poi_index is None:
            warnings.add("auto_tour_poi_index_unavailable")
        if request.nature_preference == "prefer" and not self._nature_index_available:
            warnings.add("auto_tour_nature_index_unavailable")

        direct_points = (request.effective_start, request.effective_end)
        direct_path = await self._route_points(
            direct_points, request.profile, "skeleton", state
        )
        if direct_path is None or not self._valid_complete_path(
            direct_path, direct_points
        ):
            raise AutoTourNoCandidateError
        direct_route = self._result_factory.create(
            name=request.name,
            path=direct_path,
            input_point_count=2,
        )
        if (
            request.maximum_distance_m is not None
            and request.maximum_distance_m < direct_route.summary.distance_m
        ):
            raise AutoTourMaximumBelowDirectLowerBoundError
        direct_draft = _Draft(
            route=direct_route,
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
            *_hard_points_by_direct_progress(
                request.interior_hard_points, direct_route.geometry
            ),
            request.effective_end,
        )
        primary_draft = direct_draft
        if exact_points != direct_points:
            exact_path = await self._route_points(
                exact_points, request.profile, "skeleton", state
            )
            if exact_path is None or not self._valid_complete_path(
                exact_path, exact_points
            ):
                raise AutoTourNoCandidateError
            exact_route = self._result_factory.create(
                name=request.name,
                path=exact_path,
                input_point_count=len(exact_points),
            )
            primary_draft = _Draft(
                route=exact_route,
                routing_points=exact_points,
                signature=candidate_signature(exact_route, topology="point_to_point"),
                construction="point_to_point_hard_points",
                skeleton_id="point-to-point-hard-points",
                skeleton_method="point_to_point_hard_points",
                direction="mixed",
                direction_warnings=(),
                hard_point_visits=self._hard_point_visits(
                    request, exact_points, exact_path.snapped_points
                ),
            )
            state.skeleton_candidates += 1
            control_drafts.append(primary_draft)

        original_hard_points = (
            request.effective_start,
            *request.interior_hard_points,
            request.effective_end,
        )
        if (
            len(request.interior_hard_points) > 1
            and original_hard_points != exact_points
        ):
            original_path = await self._route_points(
                original_hard_points, request.profile, "skeleton", state
            )
            if original_path is not None and self._valid_complete_path(
                original_path, original_hard_points
            ):
                original_route = self._result_factory.create(
                    name=request.name,
                    path=original_path,
                    input_point_count=len(original_hard_points),
                )
                control_drafts.append(
                    _Draft(
                        route=original_route,
                        routing_points=original_hard_points,
                        signature=candidate_signature(
                            original_route, topology="point_to_point"
                        ),
                        construction="point_to_point_hard_points",
                        skeleton_id="point-to-point-hard-points-original-order",
                        skeleton_method="point_to_point_hard_points",
                        direction="mixed",
                        direction_warnings=(),
                        hard_point_visits=self._hard_point_visits(
                            request,
                            original_hard_points,
                            original_path.snapped_points,
                        ),
                    )
                )
                state.skeleton_candidates += 1

        if (
            not request.interior_hard_points
            and self._settings.alternative_leg_request_budget
        ):
            alternative_started = perf_counter()
            state.alternative_requests += 1
            try:
                alternatives = await self._backend.alternative_routes(
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
                )
                control_drafts.append(
                    _Draft(
                        route=route,
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
            candidate = self._public_candidate(
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
            requested_states = await self._insert_requested_places(
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
            if all(visit.satisfied for visit in candidate.hard_point_visits)
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
            skeleton_route_request_count=state.skeleton_requests,
            skeleton_candidate_count=state.skeleton_candidates,
            retained_skeleton_count=len(control_drafts),
            poi_index_candidate_count=state.poi_index_candidate_count,
            already_collected_poi_count=state.already_collected_count,
            poi_route_evaluation_count=(
                state.requested_place_requests + state.poi_requests
            ),
            requested_place_route_evaluations=state.requested_place_requests,
            discovered_poi_route_evaluations=state.poi_requests,
            requested_place_budget_exhausted=(state.requested_place_budget_exhausted),
            discovered_poi_budget_exhausted=state.discovered_poi_budget_exhausted,
            local_repair_evaluation_count=0,
            corridor_repair_evaluation_count=0,
            alternative_leg_request_count=state.alternative_requests,
            total_route_request_budget=self._settings.total_route_request_budget,
            total_route_request_count=(
                state.skeleton_requests
                + state.requested_place_requests
                + state.poi_requests
                + state.alternative_requests
            ),
            budget_exhausted=state.budget_exhausted,
            control_signature=public_control.signature,
            recommended_signature=recommended.signature,
            control_retained=True,
            selected_scenic_count=recommended.selected_scenic_count,
            selected_verified_water_count=recommended.selected_verified_water_count,
            requested_place_satisfied_count=sum(
                visit.satisfied for visit in recommended.requested_place_visits
            ),
            requested_place_missed_count=sum(
                not visit.satisfied for visit in recommended.requested_place_visits
            ),
            complete_set_candidate_distance_m=(state.complete_set_candidate_distance_m),
            full_set_route_attempted=state.full_set_route_attempted,
            full_set_route_succeeded=state.full_set_route_succeeded,
            full_set_distance_m=state.full_set_distance_m,
            full_set_safety_eligible=state.full_set_safety_eligible,
            full_set_rejection_reason=state.full_set_rejection_reason,
            maximum_distance_m=_maximum_distance(request),
            route_cache_hit_count=state.route_cache_hits,
            timings=timings,
            warnings=tuple(sorted(warnings)),
        )
        return AutoTourResult(
            control=public_control,
            candidates=ranked,
            search=summary,
            topology="point_to_point",
            effective_start=request.effective_start,
            effective_end=request.effective_end,
            endpoint_visits=visits,
            endpoint_warnings=endpoint_warnings,
        )

    async def _load_isochrone(
        self,
        request: AutoTourRequest,
        state: _SearchState,
        warnings: set[str],
    ) -> IsochroneResult | None:
        state.isochrone_requests += 1
        try:
            result = await self._backend.isochrone(
                request.effective_start,
                request.profile,
                distance_limit_m=request.target_distance_m / 2,
                buckets=1,
                reverse_flow=False,
            )
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
        request: AutoTourRequest,
        skeleton: LoopSkeleton,
        state: _SearchState,
    ) -> _Draft | None:
        points = routing_points_with_hard_anchors(
            skeleton, request.interior_hard_points
        )
        path = await self._route_points(points, request.profile, "skeleton", state)
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
        request: AutoTourRequest,
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
                sampled, request.interior_hard_points
            )
            sampled_path = await self._route_points(
                points, request.profile, "skeleton", state
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

    async def _insert_requested_places(
        self,
        *,
        request: AutoTourRequest,
        initial: _InsertionState,
        state: _SearchState,
    ) -> tuple[_InsertionState, ...]:
        """Evaluate bounded complete requested-place families before discovered POIs."""
        indexed_places = tuple(
            (index, request.requested_places[index])
            for index in request.interior_requested_place_indices
        )
        if not indexed_places:
            return (initial,)
        deliberately_routed = frozenset(index for index, _place in indexed_places)
        coordinate_by_index = {
            index: place.coordinate for index, place in indexed_places
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
            *request.interior_hard_points,
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
                *((point.lat, point.lon) for point in request.interior_hard_points),
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
                request.interior_hard_points,
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
            candidate = self._public_candidate(
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
                left_path = state.route_cache.get(
                    (
                        profile,
                        ((left.lat, left.lon), (point.lat, point.lon)),
                        True,
                    )
                )
                right_path = state.route_cache.get(
                    (
                        profile,
                        ((point.lat, point.lon), (right.lat, right.lon)),
                        True,
                    )
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
            path = await self._route_points(points, profile, "requested", state)
            if path is not None:
                return _RequestedRouteOutcome(path=path, points=points)
        routed_points = list(points)
        removed: set[int] = set()
        while len(routed_points) >= 2:
            segments: list[RoutedPath] = []
            failed_pair: tuple[Coordinate, Coordinate] | None = None
            for left, right in zip(routed_points, routed_points[1:], strict=False):
                segment = await self._route_points(
                    (left, right), profile, "requested", state
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

    async def _insert_pois(
        self,
        *,
        request: AutoTourRequest,
        initial: _InsertionState,
        initial_shortlist: PoiShortlist,
        state: _SearchState,
    ) -> tuple[_InsertionState, ...]:
        if (
            self._poi_index is None
            or self._settings.max_inserted_pois == 0
            or request.requested_places
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
            if state.poi_requests >= self._settings.poi_route_evaluation_budget:
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
        request: AutoTourRequest,
        parent: _InsertionState,
        opportunity: PoiOpportunity,
        state: _SearchState,
    ) -> _InsertionState | None:
        poi_index = self._poi_index
        if poi_index is None:
            return None
        if state.poi_requests >= self._settings.poi_route_evaluation_budget:
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
            opportunity.match.feature.coordinate,
            *parent.draft.routing_points[opportunity.insertion_index :],
        )
        path = await self._route_points(points, request.profile, "poi", state)
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
            or inserted_match.distance_m > opportunity.visit_radius_m
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
        candidate = self._public_candidate(
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

    async def _local_repair(
        self,
        *,
        request: AutoTourRequest,
        states: tuple[_InsertionState, ...],
        state: _SearchState,
    ) -> tuple[_InsertionState, ...]:
        """Try bounded deterministic removal of the lowest-utility inserted POI."""
        requested_repairs = await self._remove_missed_requested_place_hooks(
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
                or state.repair_requests
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
            points = _remove_coordinate(source.draft.routing_points, feature.coordinate)
            if points is None:
                continue
            path = await self._route_points(points, request.profile, "repair", state)
            if path is None or not self._valid_complete_path(path, points):
                continue
            try:
                route = self._result_factory.create(
                    name=request.name,
                    path=path,
                    input_point_count=len(points),
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
            candidate = self._public_candidate(
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
                    -value.candidate.satisfied_must_visit_count,
                    -value.candidate.satisfied_preferred_place_count,
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
                self._backend,
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
                    close_loop=request.resolved_endpoints.topology == "loop",
                )
                for beam_state in result.states:
                    try:
                        route = self._result_factory.create(
                            name=request.name,
                            path=beam_state.composed_path,
                            input_point_count=len(source.draft.routing_points),
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
                    candidate = self._public_candidate(
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
                if search.budget_exhausted:
                    state.budget_exhausted = True
                    break
            state.alternative_requests = search.request_count
            state.route_cache_hits += search.cache_hit_count
        return tuple(repaired)

    async def _remove_missed_requested_place_hooks(
        self,
        *,
        request: AutoTourRequest,
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
                -source.candidate.satisfied_must_visit_count,
                -source.candidate.satisfied_preferred_place_count,
                auto_tour_ranking_key(source.candidate),
            ),
        )
        sources_by_skeleton: dict[str, _InsertionState] = {}
        for source in ordered_sources:
            sources_by_skeleton.setdefault(source.draft.skeleton_id, source)
        sources = tuple(sources_by_skeleton.values())[:6]
        repaired: list[_InsertionState] = []
        for source in sources:
            missed_indices = tuple(
                index
                for index, visit in enumerate(source.candidate.requested_place_visits)
                if index in source.deliberately_routed_requested_indices
                and not visit.satisfied
            )[:1]
            for requested_index in missed_indices:
                if (
                    state.repair_requests
                    >= self._settings.local_repair_route_evaluation_budget
                ):
                    return tuple(repaired)
                place = request.requested_places[requested_index]
                points = _remove_coordinate(
                    source.draft.routing_points, place.coordinate
                )
                if points is None:
                    continue
                path = await self._route_points(
                    points, request.profile, "repair", state
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
                candidate = self._public_candidate(
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

    async def _corridor_continuation_repairs(
        self,
        *,
        request: AutoTourRequest,
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
                state.repair_requests
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
                    coordinate=opportunity.match.feature.coordinate,
                    route_progress_share=opportunity.match.route_progress_share,
                    poi_opportunity=opportunity,
                )
                for opportunity in shortlist.opportunities
                if opportunity.match.feature.id not in source.selected_poi_ids
                and opportunity.match.route_progress_share >= pivot_progress
            )
            requested_continuations = tuple(
                _ContinuationOption(
                    coordinate=opportunity.place.coordinate,
                    route_progress_share=opportunity.route_progress_share,
                    requested_index=opportunity.original_index,
                )
                for opportunity in requested_place_opportunities(
                    route_geometry=source.draft.route.geometry,
                    routing_points=source.draft.routing_points,
                    requested_places=request.requested_places,
                )
                if opportunity.route_progress_share >= pivot_progress
                and opportunity.place.coordinate != pivot_coordinate
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
                previous_repairs = state.repair_requests
                path = await self._route_points(
                    points, request.profile, "repair", state
                )
                state.corridor_repair_requests += (
                    state.repair_requests - previous_repairs
                )
                if path is None or not self._valid_complete_path(path, points):
                    continue
                try:
                    route = self._result_factory.create(
                        name=request.name,
                        path=path,
                        input_point_count=len(points),
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
                        or continuation_match.distance_m > opportunity.visit_radius_m
                    ):
                        continue
                deliberately_routed = source.deliberately_routed_requested_indices
                if continuation.requested_index is not None:
                    requested_visit = measure_requested_place_visits(
                        route_geometry=route.geometry,
                        requested_places=(
                            request.requested_places[continuation.requested_index],
                        ),
                        deliberately_routed_indices=frozenset({0}),
                    )[0]
                    if not requested_visit.satisfied:
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
                provisional = self._public_candidate(
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
                    requested_places_satisfied=max(
                        0,
                        provisional.satisfied_must_visit_count
                        + provisional.satisfied_preferred_place_count
                        - source.candidate.satisfied_must_visit_count
                        - source.candidate.satisfied_preferred_place_count,
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
                return feature.coordinate, progress
        routed = sorted(source.deliberately_routed_requested_indices)
        if not routed:
            return None
        index = routed[-1]
        if index >= len(source.candidate.requested_place_visits):
            return None
        visit = source.candidate.requested_place_visits[index]
        return visit.requested_place.coordinate, visit.route_progress_share

    async def _replace_scenic_poi(
        self,
        *,
        request: AutoTourRequest,
        source: _InsertionState,
        state: _SearchState,
    ) -> _InsertionState | None:
        """Replace one low-utility scenic insertion without regressing its route."""
        poi_index = self._poi_index
        if (
            poi_index is None
            or state.repair_requests
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
            replaced_feature.coordinate,
            opportunity.match.feature.coordinate,
        )
        if points is None:
            return None
        path = await self._route_points(points, request.profile, "repair", state)
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
            or replacement_match.distance_m > opportunity.visit_radius_m
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
        candidate = self._public_candidate(
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
            hard_points_satisfied=_hard_points_satisfied(draft),
            inserted_poi_reward=candidate.inserted_poi_reward,
            control=source.draft.route,
            control_within_tolerance=source.candidate.within_tolerance,
            control_signature=source.candidate.signature,
            requested_place_gain=(
                candidate.satisfied_must_visit_count
                + candidate.satisfied_preferred_place_count
                - source.candidate.satisfied_must_visit_count
                - source.candidate.satisfied_preferred_place_count
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

    def _public_candidate(
        self,
        *,
        request: AutoTourRequest,
        draft: _Draft,
        visits: tuple[TourPoiVisit, ...],
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
        total_reward = sum(visit.reward for visit in visits)
        inserted_reward = sum(visit.reward for visit in visits if visit.inserted)
        requested_visits = measure_requested_place_visits(
            route_geometry=draft.route.geometry,
            requested_places=request.requested_places,
            deliberately_routed_indices=deliberately_routed_requested_indices,
            routing_points=draft.routing_points,
            snapped_routing_points=draft.route.snapped_points,
            failure_reasons=requested_failure_reasons,
        )
        family_requested_visits = measure_requested_place_visits(
            route_geometry=family_control.route.geometry,
            requested_places=request.requested_places,
        )
        requested_gain = sum(visit.satisfied for visit in requested_visits) - sum(
            visit.satisfied for visit in family_requested_visits
        )
        maximum_distance = _maximum_distance(request)
        comparison: TourControlComparison
        if inserted:
            comparison = compare_with_control(
                route=public_route,
                within_tolerance=within,
                hard_points_satisfied=_hard_points_satisfied(draft),
                inserted_poi_reward=inserted_reward,
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
        return AutoTourCandidate(
            rank=1,
            route=public_route,
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
            inserted_poi_reward=inserted_reward,
            selected_scenic_count=scenic_count,
            selected_verified_water_count=water_count,
            satisfied_must_visit_count=sum(
                visit.satisfied and visit.requested_place.importance == "must_visit"
                for visit in requested_visits
            ),
            satisfied_preferred_place_count=sum(
                visit.satisfied and visit.requested_place.importance == "prefer"
                for visit in requested_visits
            ),
            route_score=score_route(public_route, request.target_distance_m),
            repair=repair,
            warnings=tuple(sorted(set(draft.direction_warnings))),
        )

    async def _route_points(
        self,
        points: tuple[Coordinate, ...],
        profile: str,
        phase: str,
        state: _SearchState,
    ) -> RoutedPath | None:
        key: RouteCacheKey = (
            profile,
            tuple((point.lat, point.lon) for point in points),
            True,
        )
        if key in state.route_cache:
            state.route_cache_hits += 1
            return state.route_cache[key]
        current, maximum = _phase_budget(phase, state, self._settings)
        if current >= maximum:
            state.budget_exhausted = True
            if phase == "requested":
                state.requested_place_budget_exhausted = True
            elif phase == "poi":
                state.discovered_poi_budget_exhausted = True
            return None
        _increment_phase(phase, state)
        started = perf_counter()
        try:
            path = await self._backend.route(points, profile, pass_through=True)
        except RoutingPointError:
            path = None
        finally:
            state.route_call_seconds += perf_counter() - started
        state.route_cache[key] = path
        return path

    async def _round_trip(
        self,
        *,
        request: AutoTourRequest,
        heading: float,
        derived_seed: int,
        state: _SearchState,
    ) -> RoutedPath | None:
        key: RoundTripCacheKey = (
            request.effective_start.lat,
            request.effective_start.lon,
            request.target_distance_m,
            derived_seed,
            request.profile,
            heading,
        )
        if key in state.round_trip_cache:
            state.route_cache_hits += 1
            return state.round_trip_cache[key]
        if state.round_trip_requests >= self._settings.round_trip_control_budget:
            state.budget_exhausted = True
            return None
        state.round_trip_requests += 1
        started = perf_counter()
        try:
            path = await self._backend.round_trip(
                request.effective_start,
                request.target_distance_m,
                derived_seed,
                request.profile,
                heading_degrees=heading,
            )
        except RoutingPointError:
            path = None
        finally:
            state.route_call_seconds += perf_counter() - started
        state.round_trip_cache[key] = path
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
        request: AutoTourRequest,
        points: tuple[Coordinate, ...],
        snapped: tuple[tuple[float, float], ...] | None,
    ) -> tuple[TourHardPointVisit, ...]:
        visits: list[TourHardPointVisit] = []
        for original_index, hard_point in enumerate(request.hard_points):
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
                TourHardPointVisit(
                    original_index=original_index,
                    coordinate=hard_point,
                    snapped_coordinate=snapped_point,
                    snap_distance_m=distance,
                    satisfied=(
                        distance is not None
                        and distance <= self._settings.max_snap_displacement_m
                    ),
                )
            )
        return tuple(visits)


def _phase_budget(
    phase: str, state: _SearchState, settings: AutoTourSettings
) -> tuple[int, int]:
    if phase == "skeleton":
        return state.skeleton_requests, settings.skeleton_route_budget
    if phase == "poi":
        return state.poi_requests, settings.poi_route_evaluation_budget
    if phase == "requested":
        return (
            state.requested_place_requests,
            settings.requested_place_route_evaluation_budget,
        )
    if phase == "repair":
        return state.repair_requests, settings.local_repair_route_evaluation_budget
    raise ValueError(f"unknown Auto Tour route phase {phase}")


def _increment_phase(phase: str, state: _SearchState) -> None:
    if phase == "skeleton":
        state.skeleton_requests += 1
    elif phase == "poi":
        state.poi_requests += 1
    elif phase == "requested":
        state.requested_place_requests += 1
    elif phase == "repair":
        state.repair_requests += 1
    else:
        raise ValueError(f"unknown Auto Tour route phase {phase}")


def _valid_closed_geometry(path: RoutedPath) -> bool:
    return (
        len(path.geometry) >= 4
        and haversine_distance_m(path.geometry[0], path.geometry[-1])
        <= ROUTE_CLOSURE_TOLERANCE_M
    )


def _hard_points_satisfied(draft: _Draft) -> bool:
    return all(visit.satisfied for visit in draft.hard_point_visits)


def _control_key(draft: _Draft, request: AutoTourRequest) -> tuple[object, ...]:
    route = draft.route
    error = abs(route.summary.distance_m - request.target_distance_m)
    within = error <= request.tolerance_m
    geometry = route.analysis.loop_geometry
    nature = route.analysis.nature
    common = (
        0 if _hard_points_satisfied(draft) else 1,
        route.analysis.immediate_backtrack.share,
        route.analysis.repetition.repeated_distance.share,
        (0, geometry.penalty_breakdown.total) if geometry is not None else (1, 0.0),
        (
            (0, -nature.nature_score)
            if request.nature_preference == "prefer" and nature is not None
            else (1, 0.0)
            if request.nature_preference == "prefer"
            else (0, 0.0)
        ),
        score_route(route, request.target_distance_m).total,
        draft.signature,
    )
    if request.distance_priority == "strict":
        return (
            common[0],
            0 if within else 1,
            0.0 if within else error,
            *common[1:],
        )
    highly_mixed = (
        draft.direction == "mixed"
        and "auto_tour_direction_highly_mixed" in draft.direction_warnings
    )
    return (
        common[0],
        1 if highly_mixed else 0,
        common[1],
        geometry.outbound_return_proximity.share if geometry is not None else 1.0,
        common[2],
        common[3],
        soft_distance_penalty(
            distance_m=route.summary.distance_m,
            target_distance_m=request.target_distance_m,
            tolerance_m=request.tolerance_m,
            priority=request.distance_priority,
        ),
        *common[4:],
    )


def _retain_diverse_controls(
    controls: tuple[_Draft, ...], limit: int, request: AutoTourRequest
) -> tuple[_Draft, ...]:
    retained: list[_Draft] = []

    def retain(candidate: _Draft | None) -> None:
        if (
            candidate is not None
            and len(retained) < limit
            and candidate.signature not in {value.signature for value in retained}
        ):
            retained.append(candidate)

    retain(min(controls, key=lambda value: _control_key(value, request)))
    sampled_controls = tuple(
        value
        for value in controls
        if value.skeleton_method == "graphhopper_round_trip_sampled"
    )
    retain(
        min(
            sampled_controls,
            key=lambda value: _control_key(value, request),
            default=None,
        )
    )
    retain(
        min(
            controls,
            key=lambda value: (
                value.route.analysis.immediate_backtrack.share,
                value.route.analysis.repetition.repeated_distance.share,
                value.signature,
            ),
        )
    )
    retain(
        min(
            controls,
            key=lambda value: (
                value.route.analysis.repetition.repeated_distance.share,
                value.route.analysis.immediate_backtrack.share,
                value.signature,
            ),
        )
    )
    geometry_controls = tuple(
        value for value in controls if value.route.analysis.loop_geometry is not None
    )
    retain(
        min(
            geometry_controls,
            key=lambda value: (
                value.route.analysis.loop_geometry.penalty_breakdown.total  # type: ignore[union-attr]
            ),
            default=None,
        )
    )
    for direction in ("clockwise", "counterclockwise"):
        matching = tuple(value for value in controls if value.direction == direction)
        retain(
            min(matching, key=lambda value: _control_key(value, request), default=None)
        )
    for candidate in sorted(controls, key=lambda value: _control_key(value, request)):
        retain(candidate)
    return tuple(retained)


def _prune_insertion_beam(
    states: tuple[_InsertionState, ...], width: int
) -> tuple[_InsertionState, ...]:
    retained: list[_InsertionState] = []

    def retain(value: _InsertionState | None) -> None:
        if (
            value is not None
            and len(retained) < width
            and value.candidate.signature
            not in {state.candidate.signature for state in retained}
        ):
            retained.append(value)

    retain(min(states, key=lambda value: auto_tour_ranking_key(value.candidate)))
    retain(
        max(
            states,
            key=lambda value: (
                value.candidate.inserted_poi_reward,
                -value.candidate.target_error_m,
                value.candidate.signature,
            ),
        )
    )
    retain(
        max(
            states,
            key=lambda value: (
                len({visit.poi.category for visit in value.candidate.poi_visits}),
                value.candidate.inserted_poi_reward,
                value.candidate.signature,
            ),
        )
    )
    water = tuple(
        value for value in states if value.candidate.selected_verified_water_count > 0
    )
    retain(
        max(
            water,
            key=lambda value: (
                value.candidate.inserted_poi_reward,
                value.candidate.signature,
            ),
            default=None,
        )
    )
    retain(
        min(
            states,
            key=lambda value: (
                value.candidate.target_error_m,
                value.candidate.signature,
            ),
        )
    )
    for value in sorted(states, key=lambda item: auto_tour_ranking_key(item.candidate)):
        retain(value)
    return tuple(retained)


def _deduplicate_drafts(drafts: tuple[_Draft, ...]) -> tuple[_Draft, ...]:
    distinct: dict[str, _Draft] = {}
    for draft in drafts:
        distinct.setdefault(draft.signature, draft)
    return tuple(distinct.values())


def _deduplicate_candidates(
    candidates: tuple[AutoTourCandidate, ...],
) -> tuple[AutoTourCandidate, ...]:
    distinct: dict[str, AutoTourCandidate] = {}
    for candidate in candidates:
        distinct.setdefault(candidate.signature, candidate)
    return tuple(distinct.values())


def _with_open_metrics(
    candidate: AutoTourCandidate, direct_route: RouteResult
) -> AutoTourCandidate:
    metrics = analyze_open_route(
        geometry=candidate.route.geometry,
        route_distance_m=candidate.route.summary.distance_m,
        direct_geometry=direct_route.geometry,
        direct_distance_m=direct_route.summary.distance_m,
    )
    return candidate.model_copy(
        update={
            "direct_distance_m": metrics.direct_distance_m,
            "detour_ratio": metrics.detour_ratio,
            "destination_progress_monotonicity": (
                metrics.destination_progress_monotonicity
            ),
            "reverse_progress_distance_m": metrics.reverse_progress_distance_m,
            "reverse_progress_share": metrics.reverse_progress_share,
            "endpoint_axis_lateral_deviation_m": (
                metrics.endpoint_axis_lateral_deviation_m
            ),
            "near_parallel_corridor_share": metrics.near_parallel_corridor_share,
        }
    )


def _without_loop_geometry(route: RouteResult) -> RouteResult:
    """Mark loop-only analysis not applicable on a public open route."""
    if route.analysis.loop_geometry is None:
        return route
    return route.model_copy(
        update={"analysis": route.analysis.model_copy(update={"loop_geometry": None})}
    )


def _hard_points_by_direct_progress(
    points: tuple[Coordinate, ...],
    direct_geometry: tuple[tuple[float, float], ...],
) -> tuple[Coordinate, ...]:
    """Deterministically seed open hard-point order from direct-route progress."""
    if len(points) < 2:
        return points
    projection = LocalMetricProjection(
        sum(latitude for _, latitude in direct_geometry) / len(direct_geometry)
    )
    line = projection.project_line(direct_geometry)
    return tuple(
        point
        for _, _, point in sorted(
            (
                line.project(
                    Point(projection.project_position((point.lon, point.lat)))
                ),
                index,
                point,
            )
            for index, point in enumerate(points)
        )
    )


def _maximum_distance(request: AutoTourRequest) -> float:
    return maximum_auto_tour_distance_m(
        request.target_distance_m,
        request.tolerance_m,
        priority=request.distance_priority,
        requested_maximum_distance_m=request.maximum_distance_m,
    )


def _maximum_rejection_reason(
    request: AutoTourRequest,
) -> RequestedPlaceFailureReason:
    if request.maximum_distance_m is not None:
        return "requested_place_user_maximum_rejected"
    if request.distance_priority == "flexible":
        return "requested_place_server_maximum_rejected"
    return "requested_place_lower_utility_subset"


def _open_tour_key(
    candidate: AutoTourCandidate, request: AutoTourRequest
) -> tuple[object, ...]:
    """Rank endpoint-valid open paths without applying loop-only shape gates."""
    severe_backtracking = (
        candidate.route.analysis.immediate_backtrack.distance_m > 1_000.0
        and candidate.route.analysis.immediate_backtrack.share > 0.10
    )
    if request.distance_priority == "strict":
        return (
            0 if candidate.within_tolerance else 1,
            candidate.target_error_m,
            0
            if candidate.route.summary.distance_m <= _maximum_distance(request)
            else 1,
            1 if severe_backtracking else 0,
            -candidate.satisfied_must_visit_count,
            -candidate.satisfied_preferred_place_count,
            candidate.signature,
        )
    nature = candidate.route.analysis.nature
    return (
        0 if candidate.route.summary.distance_m <= _maximum_distance(request) else 1,
        1 if severe_backtracking else 0,
        -candidate.satisfied_must_visit_count,
        -candidate.satisfied_preferred_place_count,
        candidate.route.analysis.immediate_backtrack.share,
        candidate.reverse_progress_share
        if candidate.reverse_progress_share is not None
        else 1.0,
        candidate.route.analysis.repetition.repeated_distance.share,
        candidate.near_parallel_corridor_share
        if candidate.near_parallel_corridor_share is not None
        else 1.0,
        -candidate.total_poi_reward,
        (0, -nature.nature_score) if nature is not None else (1, 0.0),
        candidate.soft_distance_penalty,
        candidate.signature,
    )


def _open_candidate_portfolio(
    candidates: tuple[AutoTourCandidate, ...],
    *,
    request: AutoTourRequest,
    control: AutoTourCandidate,
) -> tuple[AutoTourCandidate, ...]:
    """Reserve coverage, near-target, and direct-control open-route roles."""
    ordered = tuple(
        sorted(candidates, key=lambda value: _open_tour_key(value, request))
    )
    if request.distance_priority != "flexible" or request.candidate_count == 1:
        return ordered[: request.candidate_count]
    selected: list[AutoTourCandidate] = []

    def retain(candidate: AutoTourCandidate | None) -> None:
        if candidate is None or candidate.signature in {
            value.signature for value in selected
        }:
            return
        selected.append(candidate)

    retain(ordered[0] if ordered else None)
    target_maximum = maximum_auto_tour_distance_m(
        request.target_distance_m,
        request.tolerance_m,
        priority="balanced",
        requested_maximum_distance_m=request.maximum_distance_m,
    )
    near_target = tuple(
        candidate
        for candidate in candidates
        if candidate.route.summary.distance_m <= target_maximum
    )
    retain(
        min(
            near_target,
            key=lambda candidate: (
                -candidate.satisfied_must_visit_count,
                -candidate.satisfied_preferred_place_count,
                candidate.target_error_m,
                _open_tour_key(candidate, request),
            ),
            default=None,
        )
    )
    retain(control)
    for candidate in ordered:
        if len(selected) >= request.candidate_count:
            break
        retain(candidate)
    return tuple(selected[: request.candidate_count])


def _with_requested_coverage_warning(
    candidate: AutoTourCandidate,
    request: AutoTourRequest,
    control: AutoTourCandidate,
) -> AutoTourCandidate:
    requested_count = (
        candidate.satisfied_must_visit_count + candidate.satisfied_preferred_place_count
    )
    control_count = (
        control.satisfied_must_visit_count + control.satisfied_preferred_place_count
    )
    if (
        request.distance_priority != "flexible"
        or candidate.route.summary.distance_m
        <= request.target_distance_m + request.tolerance_m
        or requested_count <= control_count
    ):
        return candidate
    return candidate.model_copy(
        update={
            "warnings": tuple(
                sorted(
                    {
                        *candidate.warnings,
                        "target_distance_exceeded_for_requested_coverage",
                    }
                )
            )
        }
    )


def _mark_cross_candidate_requested_routing(
    candidates: tuple[AutoTourCandidate, ...],
) -> tuple[AutoTourCandidate, ...]:
    routed_indices = {
        index
        for candidate in candidates
        for index, visit in enumerate(candidate.requested_place_visits)
        if visit.deliberately_routed
    }
    return tuple(
        candidate.model_copy(
            update={
                "requested_place_visits": tuple(
                    visit.model_copy(
                        update={
                            "deliberately_routed_in_another_retained_candidate": (
                                not visit.deliberately_routed
                                and index in routed_indices
                            )
                        }
                    )
                    for index, visit in enumerate(candidate.requested_place_visits)
                )
            }
        )
        for candidate in candidates
    )


def _apply_requested_search_failure_context(
    candidates: tuple[AutoTourCandidate, ...],
    state: _SearchState,
) -> tuple[AutoTourCandidate, ...]:
    reason = state.full_set_rejection_reason
    if reason not in {
        "requested_place_user_maximum_rejected",
        "requested_place_server_maximum_rejected",
        "requested_place_graph_unreachable",
        "requested_place_search_budget_exhausted",
    }:
        return candidates
    return tuple(
        candidate.model_copy(
            update={
                "requested_place_visits": tuple(
                    visit.model_copy(update={"failure_reason": reason})
                    if not visit.satisfied
                    and not visit.deliberately_routed
                    and visit.failure_reason
                    in {
                        "requested_place_safety_rejected",
                        "requested_place_lower_utility_subset",
                        "requested_place_distance_ceiling_rejected",
                    }
                    else visit
                    for visit in candidate.requested_place_visits
                )
            }
        )
        for candidate in candidates
    )


def _remove_coordinate(
    points: tuple[Coordinate, ...], coordinate: Coordinate
) -> tuple[Coordinate, ...] | None:
    for index in range(1, len(points) - 1):
        if _same_coordinate(points[index], coordinate):
            return (*points[:index], *points[index + 1 :])
    return None


def _replace_coordinate(
    points: tuple[Coordinate, ...],
    old_coordinate: Coordinate,
    new_coordinate: Coordinate,
) -> tuple[Coordinate, ...] | None:
    for index in range(1, len(points) - 1):
        if _same_coordinate(points[index], old_coordinate):
            return (*points[:index], new_coordinate, *points[index + 1 :])
    return None


def _same_coordinate(left: Coordinate, right: Coordinate) -> bool:
    return (left.lat, left.lon) == (right.lat, right.lon)


def _records_without_final_deltas(
    records: dict[str, InsertedPoiRecord],
) -> dict[str, InsertedPoiRecord]:
    """Mark marginal deltas unavailable after a global route repair."""
    return {
        poi_id: record
        if record.actual_distance_delta_m is None
        else InsertedPoiRecord(
            estimated_detour_m=record.estimated_detour_m,
            actual_distance_delta_m=None,
            marginal_utility=record.marginal_utility,
        )
        for poi_id, record in records.items()
    }


def _record_rejection(
    state: _SearchState,
    skeleton_id: str,
    opportunity: PoiOpportunity,
    reason: PoiRejectionReason,
    *,
    nearest_distance_m: float | None = None,
) -> None:
    values = state.rejected_by_skeleton.setdefault(skeleton_id, [])
    rejection = RejectedPoiOpportunity(
        poi_id=opportunity.match.feature.id,
        display_name=opportunity.match.feature.display_name,
        category=opportunity.match.feature.category,
        reason_code=reason,
        estimated_detour_m=opportunity.estimated_detour_m,
        nearest_route_distance_m=(
            opportunity.match.distance_m
            if nearest_distance_m is None
            else nearest_distance_m
        ),
    )
    if rejection not in values and len(values) < MAX_CANDIDATE_REJECTIONS:
        values.append(rejection)


def _comparison_rejection_reason(
    comparison: TourControlComparison,
) -> PoiRejectionReason:
    if "distance_tolerance" in comparison.rejection_reasons:
        return "distance_tolerance"
    if "backtracking_regression" in comparison.rejection_reasons:
        return "backtracking_regression"
    if "repetition_regression" in comparison.rejection_reasons:
        return "repetition_regression"
    if "geometry_regression" in comparison.rejection_reasons:
        return "geometry_regression"
    return "reward_too_low"


def _force_trade_off(candidate: AutoTourCandidate, reason: str) -> AutoTourCandidate:
    comparison = candidate.control_comparison.model_copy(
        update={
            "eligible": False,
            "rejection_reasons": tuple(
                sorted({*candidate.control_comparison.rejection_reasons, reason})
            ),
        }
    )
    return candidate.model_copy(
        update={
            "control_eligible": False,
            "control_comparison": comparison,
            "warnings": tuple(
                sorted({*candidate.warnings, "auto_tour_low_overlap_trade_off"})
            ),
        }
    )
