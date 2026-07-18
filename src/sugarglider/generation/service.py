"""Bounded deterministic proposal-and-evaluation route generation service."""

from dataclasses import dataclass, field
from math import atan2, hypot, pi

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import RouteAnalyzer, haversine_distance_m
from sugarglider.domain.generation import (
    CandidateConstruction,
    GeneratedCandidate,
    GenerationStatus,
    LoopGeometryPreference,
    NaturePreference,
    RequiredPointVisit,
    RouteGenerationRequest,
    RouteGenerationResult,
    SearchSummary,
)
from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.generation.geometry import (
    ProposalPointSequence,
    ProposalVariant,
    insert_optional_points,
    point_sequence_key,
    proposal_point_sequences,
)
from sugarglider.generation.low_overlap import (
    LowOverlapBeamSearch,
    LowOverlapSettings,
)
from sugarglider.generation.ordering import (
    MAX_ORDER_PROPOSALS,
    PointOrder,
    generate_order_proposals,
    ordered_closed_points,
)
from sugarglider.generation.scoring import (
    NATURAL_IMPROVEMENT_EPSILON,
    is_natural_improvement,
    rank_candidates,
    rank_low_overlap_candidates,
    score_route,
)
from sugarglider.generation.signatures import (
    candidate_signature,
    select_diverse_candidates,
)
from sugarglider.routing.backend import RoutedPath, RoutingBackend
from sugarglider.routing.errors import RoutingPointError
from sugarglider.routing.result import RouteResultFactory

DISTANCE_FACTORS = (0.60, 0.80, 1.00, 1.20, 1.45)
MIN_PROPOSAL_DISTANCE_M = 2_000.0
MAX_PROPOSAL_DISTANCE_M = 30_000.0
PROPOSAL_SURVIVAL_FACTOR = 0.75
REFINEMENT_RATIO_MIN = 0.70
REFINEMENT_RATIO_MAX = 1.30
MAX_REFINEMENT_COUNT = 3
MAX_PROMISING_ORDERS = 3
LOOP_GEOMETRY_EXTRA_EVALUATIONS = 12
LOOP_GEOMETRY_IMPROVEMENT_EPSILON = 1e-12
GLOBAL_SECTOR_COUNT = 8

type PointSequenceKey = tuple[tuple[float, float], ...]
type ProposalCacheKey = tuple[float, float, float, int, str]


class TargetDistanceInfeasibleError(Exception):
    """GPX generation cannot return a candidate because baseline is too long."""


class RouteGenerationNoCandidateError(Exception):
    """GPX generation produced no graph-valid candidate."""


@dataclass
class _SearchState:
    base_search_budget: int
    loop_geometry_extra_evaluation_budget: int
    evaluated: int = 0
    successful: int = 0
    rejected: int = 0
    proposal_count: int = 0
    derived_proposal_sequence_count: int = 0
    evaluated_order_count: int = 0
    successful_order_count: int = 0
    rejected_order_count: int = 0
    base_budget_exhausted: bool = False
    loop_geometry_extra_evaluated: int = 0
    loop_geometry_extra_successful: int = 0
    loop_geometry_extra_rejected: int = 0
    path_cache: dict[PointSequenceKey, RoutedPath | None] = field(default_factory=dict)
    proposal_cache: dict[ProposalCacheKey, RoutedPath | None] = field(
        default_factory=dict
    )

    @property
    def search_budget(self) -> int:
        return self.base_search_budget + self.loop_geometry_extra_evaluation_budget

    @property
    def base_evaluated(self) -> int:
        return self.evaluated - self.loop_geometry_extra_evaluated

    @property
    def budget_exhausted(self) -> bool:
        if self.loop_geometry_extra_evaluation_budget == 0:
            return self.base_budget_exhausted
        return (
            self.base_budget_exhausted
            and self.loop_geometry_extra_evaluated
            >= self.loop_geometry_extra_evaluation_budget
        )


@dataclass(frozen=True)
class _RefinementSource:
    candidate: GeneratedCandidate
    insertion_index: int
    proposal_distance_m: float
    factor_index: int
    required_points: tuple[Coordinate, ...]
    required_point_order: tuple[RequiredPointVisit, ...]
    variant: ProposalVariant


@dataclass(frozen=True)
class _OrderSource:
    required_points: tuple[Coordinate, ...]
    required_point_order: tuple[RequiredPointVisit, ...]
    route: RouteResult
    signature: str


@dataclass(frozen=True)
class _OrderEvaluation:
    all_sources: tuple[_OrderSource, ...]
    retained_sources: tuple[_OrderSource, ...]
    best_source: _OrderSource


@dataclass(frozen=True)
class _DetourDescriptor:
    source: _OrderSource
    insertion_index: int
    anchor: Coordinate
    factor_index: int
    proposal_distance_m: float


@dataclass(frozen=True)
class _LowOverlapSummary:
    alternative_leg_request_count: int = 0
    alternative_path_count: int = 0
    refined_source_count: int = 0
    candidate_count: int = 0
    request_budget: int = 0
    budget_exhausted: bool = False
    pre_repeated_share: float | None = None
    best_repeated_share: float | None = None
    pre_backtrack_share: float | None = None
    best_backtrack_share: float | None = None
    nature_off_recommended_signature: str | None = None
    nature_off_recommended_score: float | None = None
    best_available_nature_score: float | None = None
    best_available_loop_geometry_penalty: float | None = None


@dataclass(frozen=True)
class _RefinedCandidate:
    candidate: GeneratedCandidate
    source: GeneratedCandidate
    natural_improvement: bool


class RouteGenerationService:
    """Coordinate a small sequential search over GraphHopper round-trip proposals."""

    def __init__(
        self,
        backend: RoutingBackend,
        result_factory: RouteResultFactory | None = None,
        *,
        structural_result_factory: RouteResultFactory | None = None,
        max_evaluations: int = 48,
        loop_geometry_extra_evaluations: int = LOOP_GEOMETRY_EXTRA_EVALUATIONS,
        max_optional_snap_displacement_m: float = 300.0,
        low_overlap_settings: LowOverlapSettings | None = None,
        nature_index_available: bool = False,
        nature_index_feature_count: int | None = None,
    ) -> None:
        if max_evaluations < 1:
            raise ValueError("generation search budget must be positive")
        if max_optional_snap_displacement_m < 0:
            raise ValueError("optional snap displacement must be non-negative")
        if loop_geometry_extra_evaluations < 0:
            raise ValueError("loop geometry extra budget must be non-negative")
        self._backend = backend
        self._result_factory = result_factory or RouteResultFactory()
        self._structural_result_factory = (
            structural_result_factory
            if structural_result_factory is not None
            else RouteResultFactory(RouteAnalyzer())
        )
        self._max_evaluations = max_evaluations
        self._loop_geometry_extra_evaluations = loop_geometry_extra_evaluations
        self._max_optional_snap_displacement_m = max_optional_snap_displacement_m
        self._low_overlap_settings = low_overlap_settings or LowOverlapSettings()
        self._nature_index_available = nature_index_available
        self._nature_index_feature_count = nature_index_feature_count

    async def generate(self, request: RouteGenerationRequest) -> RouteGenerationResult:
        """Generate distinct candidates while preserving every mandatory point."""
        nature_preference = self._effective_nature_preference(request)
        initial_warnings = self._nature_warnings(request)
        supplied_points = request.supplied_required_points
        fixed_order = tuple(range(len(supplied_points)))
        fixed_points = ordered_closed_points(supplied_points, fixed_order)
        baseline_path = await self._backend.route(fixed_points, request.profile)
        baseline = self._result_factory.create(
            name=request.name,
            path=baseline_path,
            input_point_count=request.required_point_count,
        )
        state = _SearchState(
            self._max_evaluations,
            (
                self._loop_geometry_extra_evaluations
                if request.loop_geometry_preference == "prefer"
                else 0
            ),
        )
        state.path_cache[point_sequence_key(fixed_points)] = baseline_path
        fixed_visits = self._required_visits(supplied_points, fixed_order)
        fixed_source = _OrderSource(
            required_points=fixed_points,
            required_point_order=fixed_visits,
            route=baseline,
            signature=candidate_signature(baseline),
        )
        all_order_sources: tuple[_OrderSource, ...] = (fixed_source,)
        order_sources: tuple[_OrderSource, ...] = (fixed_source,)
        best_order_source = fixed_source
        if request.point_order_mode == "optimize_loop":
            order_evaluation = await self._evaluate_order_sources(
                request=request,
                supplied_points=supplied_points,
                fixed_source=fixed_source,
                state=state,
            )
            all_order_sources = order_evaluation.all_sources
            order_sources = order_evaluation.retained_sources
            best_order_source = order_evaluation.best_source

        maximum_acceptable = request.target_distance_m + request.tolerance_m
        if all(
            source.route.summary.distance_m > maximum_acceptable
            for source in all_order_sources
        ):
            return RouteGenerationResult(
                baseline=baseline,
                candidates=(),
                search=self._summary(
                    request,
                    baseline,
                    best_order_source.route,
                    state,
                    status="infeasible",
                    warnings=tuple(
                        sorted(
                            {
                                "mandatory_route_exceeds_target_tolerance",
                                *initial_warnings,
                                *(
                                    ("nature_analysis_incomplete",)
                                    if nature_preference == "prefer"
                                    and baseline.analysis.nature is None
                                    else ()
                                ),
                                *(
                                    ("loop_geometry_analysis_incomplete",)
                                    if request.loop_geometry_preference == "prefer"
                                    and baseline.analysis.loop_geometry is None
                                    else ()
                                ),
                                *self._route_nature_warnings((baseline,)),
                            }
                        )
                    ),
                    low_overlap=(
                        _LowOverlapSummary(
                            request_budget=(self._low_overlap_settings.max_leg_requests)
                        )
                        if request.path_selection_mode == "low_overlap"
                        else None
                    ),
                ),
            )

        drafts: list[GeneratedCandidate] = []
        signatures: set[str] = set()
        for source in order_sources:
            if (
                abs(source.route.summary.distance_m - request.target_distance_m)
                <= request.tolerance_m
                and source.signature not in signatures
            ):
                order_candidate = self._candidate(
                    request,
                    source.route,
                    (),
                    source.required_point_order,
                    source.required_points[:-1],
                    "direct_order",
                )
                drafts.append(order_candidate)
                signatures.add(order_candidate.signature)

        refinement_sources: list[_RefinementSource] = []
        descriptor_groups = tuple(
            self._detour_descriptors(request, source, balanced=False)
            for source in order_sources
        )
        descriptor_index = 0
        while state.base_evaluated < state.base_search_budget and any(
            descriptor_index < len(group) for group in descriptor_groups
        ):
            for group in descriptor_groups:
                if descriptor_index >= len(group):
                    continue
                if state.base_evaluated >= state.base_search_budget:
                    state.base_budget_exhausted = True
                    break
                descriptor = group[descriptor_index]
                proposal_sequences = await self._proposal_sequences(
                    request=request,
                    anchor=descriptor.anchor,
                    insertion_index=descriptor.insertion_index,
                    factor_index=descriptor.factor_index,
                    refinement_round=0,
                    proposal_distance_m=descriptor.proposal_distance_m,
                    state=state,
                    prefer_balanced=False,
                )
                for sequence in proposal_sequences:
                    if state.base_evaluated >= state.base_search_budget:
                        state.base_budget_exhausted = True
                        break
                    candidate = await self._evaluate_candidate(
                        request=request,
                        required_points=descriptor.source.required_points,
                        required_point_order=descriptor.source.required_point_order,
                        insertion_index=descriptor.insertion_index,
                        optional_points=sequence.optional_points,
                        construction=sequence.construction,
                        state=state,
                    )
                    if candidate is None:
                        continue
                    if candidate.signature in signatures:
                        state.rejected += 1
                        continue
                    signatures.add(candidate.signature)
                    drafts.append(candidate)
                    refinement_sources.append(
                        _RefinementSource(
                            candidate=candidate,
                            insertion_index=descriptor.insertion_index,
                            proposal_distance_m=descriptor.proposal_distance_m,
                            factor_index=descriptor.factor_index,
                            required_points=descriptor.source.required_points,
                            required_point_order=(
                                descriptor.source.required_point_order
                            ),
                            variant=sequence.variant,
                        )
                    )
            descriptor_index += 1

        if state.base_evaluated >= state.base_search_budget and any(
            descriptor_index < len(group) for group in descriptor_groups
        ):
            state.base_budget_exhausted = True

        closest = sorted(
            refinement_sources,
            key=lambda source: (
                source.candidate.target_error_m,
                source.candidate.signature,
            ),
        )[: min(MAX_REFINEMENT_COUNT, request.candidate_count)]
        for refinement in closest:
            if state.base_evaluated >= state.base_search_budget:
                state.base_budget_exhausted = True
                break
            actual_distance = refinement.candidate.route.summary.distance_m
            if actual_distance <= 0:
                continue
            adjustment = request.target_distance_m / actual_distance
            adjustment = min(
                REFINEMENT_RATIO_MAX, max(REFINEMENT_RATIO_MIN, adjustment)
            )
            proposal_distance = self._clamp_proposal_distance(
                refinement.proposal_distance_m * adjustment,
                request.target_distance_m,
            )
            anchor = refinement.required_points[refinement.insertion_index]
            proposal_sequences = await self._proposal_sequences(
                request=request,
                anchor=anchor,
                insertion_index=refinement.insertion_index,
                factor_index=refinement.factor_index,
                refinement_round=1,
                proposal_distance_m=proposal_distance,
                state=state,
                variant=refinement.variant,
                prefer_balanced=False,
            )
            if not proposal_sequences:
                continue
            sequence = proposal_sequences[0]
            candidate = await self._evaluate_candidate(
                request=request,
                required_points=refinement.required_points,
                required_point_order=refinement.required_point_order,
                insertion_index=refinement.insertion_index,
                optional_points=sequence.optional_points,
                construction=sequence.construction,
                state=state,
            )
            if candidate is None:
                continue
            if candidate.signature in signatures:
                state.rejected += 1
                continue
            signatures.add(candidate.signature)
            drafts.append(candidate)

        primary_drafts = tuple(drafts)
        warnings: set[str] = set(initial_warnings)
        primary_ranked = self._rank_standard_staged(
            primary_drafts,
            nature_preference=nature_preference,
            loop_geometry_preference="off",
            warnings=warnings,
        )
        primary_diversity = select_diverse_candidates(
            primary_ranked, request.candidate_count
        )
        primary_candidates = primary_diversity.candidates
        primary_control = primary_candidates[0] if primary_candidates else None
        extra_candidates = (
            await self._evaluate_loop_geometry_extra(
                request=request,
                order_sources=order_sources,
                state=state,
                signatures=signatures,
            )
            if request.loop_geometry_preference == "prefer"
            else ()
        )
        all_drafts = (*primary_drafts, *extra_candidates)
        if request.loop_geometry_preference == "off":
            ranked = primary_candidates
            diversity = primary_diversity
        else:
            ranked = self._rank_standard_with_control(
                primary_candidates=primary_candidates,
                extra_candidates=extra_candidates,
                control=primary_control,
                nature_preference=nature_preference,
                warnings=warnings,
            )
            diversity = select_diverse_candidates(ranked, request.candidate_count)
        warnings.update(
            self._route_nature_warnings(
                (baseline, *(candidate.route for candidate in all_drafts))
            )
        )
        if nature_preference == "prefer" and any(
            candidate.route.analysis.nature is None for candidate in all_drafts
        ):
            warnings.add("nature_analysis_incomplete")
        if request.loop_geometry_preference == "prefer" and any(
            route.analysis.loop_geometry is None
            for route in (baseline, *(candidate.route for candidate in all_drafts))
        ):
            warnings.add("loop_geometry_analysis_incomplete")
        if state.budget_exhausted:
            warnings.add("search_budget_exhausted")
        if diversity.low_edge_coverage and ranked:
            warnings.add("edge_id_coverage_too_low_for_diversity")
        if diversity.relaxed:
            warnings.add("candidate_diversity_relaxed")
        if not diversity.candidates:
            warnings.add("no_generated_candidate")
        if request.point_order_mode == "optimize_loop":
            if (
                best_order_source.route.analysis.repetition.repeated_distance.share
                >= baseline.analysis.repetition.repeated_distance.share
            ):
                warnings.add("order_optimization_no_repetition_improvement")
            if (
                best_order_source.route.analysis.immediate_backtrack.share
                >= baseline.analysis.immediate_backtrack.share
            ):
                warnings.add("order_optimization_no_backtrack_improvement")
        final_candidates = (
            primary_candidates
            if request.loop_geometry_preference == "off"
            else self._retain_recommendation_and_control(
                ranked=ranked,
                diverse=diversity.candidates,
                recommendation=(ranked[0] if ranked else None),
                control=primary_control,
                candidate_count=request.candidate_count,
            )
        )
        low_overlap_summary = _LowOverlapSummary()
        if request.path_selection_mode == "low_overlap" and final_candidates:
            low_overlap_control = (
                self._low_overlap_source_order(primary_candidates)[0]
                if primary_candidates
                else final_candidates[0]
            )
            (
                final_candidates,
                low_overlap_summary,
                low_overlap_warnings,
            ) = await self._refine_low_overlap(
                request=request,
                standard_candidates=final_candidates,
                analyzed_candidates=all_drafts,
                control_source=low_overlap_control,
                nature_preference=nature_preference,
                loop_geometry_preference=request.loop_geometry_preference,
            )
            warnings.update(low_overlap_warnings)
        elif request.path_selection_mode == "low_overlap":
            low_overlap_summary = _LowOverlapSummary(
                request_budget=self._low_overlap_settings.max_leg_requests
            )
            warnings.add("low_overlap_no_complete_candidate")
        status: GenerationStatus = (
            "within_tolerance"
            if any(candidate.within_tolerance for candidate in final_candidates)
            else "best_effort"
        )
        return RouteGenerationResult(
            baseline=baseline,
            candidates=final_candidates,
            search=self._summary(
                request,
                baseline,
                best_order_source.route,
                state,
                status=status,
                warnings=tuple(sorted(warnings)),
                low_overlap=low_overlap_summary,
                candidates=final_candidates,
                analyzed_candidates=all_drafts,
            ),
        )

    async def _evaluate_order_sources(
        self,
        *,
        request: RouteGenerationRequest,
        supplied_points: tuple[Coordinate, ...],
        fixed_source: _OrderSource,
        state: _SearchState,
    ) -> _OrderEvaluation:
        """Route all bounded orders, then protect the best expandable source."""
        sources = [fixed_source]
        signatures = {fixed_source.signature}
        proposals = generate_order_proposals(supplied_points, limit=MAX_ORDER_PROPOSALS)
        for order in proposals[1:]:
            if state.base_evaluated >= state.base_search_budget:
                state.base_budget_exhausted = True
                break
            points = ordered_closed_points(supplied_points, order)
            key = point_sequence_key(points)
            if key in state.path_cache:
                continue
            state.evaluated += 1
            state.evaluated_order_count += 1
            try:
                path = await self._backend.route(
                    points, request.profile, pass_through=True
                )
            except RoutingPointError:
                state.rejected += 1
                state.rejected_order_count += 1
                state.path_cache[key] = None
                continue
            state.path_cache[key] = path
            if path.snapped_points is None or len(path.snapped_points) != len(points):
                state.rejected += 1
                state.rejected_order_count += 1
                state.path_cache[key] = None
                continue
            route = self._result_factory.create(
                name=request.name,
                path=path,
                input_point_count=request.required_point_count,
            )
            signature = candidate_signature(route)
            if signature in signatures:
                state.rejected += 1
                state.rejected_order_count += 1
                continue
            signatures.add(signature)
            state.successful += 1
            state.successful_order_count += 1
            sources.append(
                _OrderSource(
                    required_points=points,
                    required_point_order=self._required_visits(supplied_points, order),
                    route=route,
                    signature=signature,
                )
            )

        ranked = rank_candidates(
            tuple(
                self._candidate(
                    request,
                    source.route,
                    (),
                    source.required_point_order,
                    source.required_points[:-1],
                    "direct_order",
                )
                for source in sources
            )
        )
        by_signature = {source.signature: source for source in sources}
        ranked_sources = tuple(
            by_signature[candidate.signature] for candidate in ranked
        )
        best_source = ranked_sources[0]
        expandable = tuple(
            source
            for source in sources
            if source.route.summary.distance_m < request.target_distance_m
        )
        best_expandable = min(
            expandable,
            key=lambda source: (
                abs(source.route.summary.distance_m - request.target_distance_m),
                source.route.analysis.immediate_backtrack.share,
                source.route.analysis.repetition.repeated_distance.share,
                source.signature,
            ),
            default=None,
        )
        retained: list[_OrderSource] = []
        retained_signatures: set[str] = set()

        def retain(source: _OrderSource | None) -> None:
            if (
                source is not None
                and source.signature not in retained_signatures
                and len(retained) < MAX_PROMISING_ORDERS
            ):
                retained.append(source)
                retained_signatures.add(source.signature)

        retain(best_source)
        retain(best_expandable)
        for source in ranked_sources:
            retain(source)
        return _OrderEvaluation(tuple(sources), tuple(retained), best_source)

    def _detour_descriptors(
        self,
        request: RouteGenerationRequest,
        source: _OrderSource,
        *,
        balanced: bool,
    ) -> tuple[_DetourDescriptor, ...]:
        remaining_extra_m = request.target_distance_m - source.route.summary.distance_m
        if remaining_extra_m <= 0:
            return ()
        base_proposal_distance = remaining_extra_m / PROPOSAL_SURVIVAL_FACTOR
        anchors = self._unique_insertion_anchors(source.required_points)
        if not balanced:
            schedule = tuple(
                (insertion_index, anchor, factor_index, factor)
                for insertion_index, anchor in anchors
                for factor_index, factor in enumerate(DISTANCE_FACTORS)
            )
        else:
            balanced_anchors = self._balanced_insertion_anchors(anchors)
            schedule = tuple(
                (insertion_index, anchor, factor_index, factor)
                for factor_index, factor in enumerate(DISTANCE_FACTORS)
                for insertion_index, anchor in balanced_anchors
            )
        return tuple(
            _DetourDescriptor(
                source=source,
                insertion_index=insertion_index,
                anchor=anchor,
                factor_index=factor_index,
                proposal_distance_m=self._clamp_proposal_distance(
                    base_proposal_distance * factor,
                    request.target_distance_m,
                ),
            )
            for insertion_index, anchor, factor_index, factor in schedule
        )

    async def _evaluate_loop_geometry_extra(
        self,
        *,
        request: RouteGenerationRequest,
        order_sources: tuple[_OrderSource, ...],
        state: _SearchState,
        signatures: set[str],
    ) -> tuple[GeneratedCandidate, ...]:
        """Evaluate balanced-only sequences from successful cached base proposals."""
        if state.loop_geometry_extra_evaluation_budget == 0:
            return ()
        candidates: list[GeneratedCandidate] = []
        seen_point_sequences = set(state.path_cache)
        descriptor_groups = tuple(
            self._detour_descriptors(request, source, balanced=True)
            for source in order_sources
        )
        descriptor_index = 0
        while (
            state.loop_geometry_extra_evaluated
            < state.loop_geometry_extra_evaluation_budget
            and any(descriptor_index < len(group) for group in descriptor_groups)
        ):
            for group in descriptor_groups:
                if descriptor_index >= len(group):
                    continue
                descriptor = group[descriptor_index]
                sequences = await self._proposal_sequences(
                    request=request,
                    anchor=descriptor.anchor,
                    insertion_index=descriptor.insertion_index,
                    factor_index=descriptor.factor_index,
                    refinement_round=0,
                    proposal_distance_m=descriptor.proposal_distance_m,
                    state=state,
                    prefer_balanced=True,
                    cached_only=True,
                )
                for sequence in sequences:
                    points = insert_optional_points(
                        descriptor.source.required_points,
                        descriptor.insertion_index,
                        sequence.optional_points,
                    )
                    point_key = point_sequence_key(points)
                    if point_key in seen_point_sequences:
                        continue
                    seen_point_sequences.add(point_key)
                    if (
                        state.loop_geometry_extra_evaluated
                        >= state.loop_geometry_extra_evaluation_budget
                    ):
                        break
                    candidate = await self._evaluate_candidate(
                        request=request,
                        required_points=descriptor.source.required_points,
                        required_point_order=(descriptor.source.required_point_order),
                        insertion_index=descriptor.insertion_index,
                        optional_points=sequence.optional_points,
                        construction="sector_balanced_detour",
                        state=state,
                        extra_lane=True,
                    )
                    if candidate is None:
                        continue
                    if candidate.signature in signatures:
                        state.successful -= 1
                        state.loop_geometry_extra_successful -= 1
                        state.rejected += 1
                        state.loop_geometry_extra_rejected += 1
                        continue
                    signatures.add(candidate.signature)
                    candidates.append(candidate)
            descriptor_index += 1
        return tuple(candidates)

    @staticmethod
    def _required_visits(
        supplied_points: tuple[Coordinate, ...], order: PointOrder
    ) -> tuple[RequiredPointVisit, ...]:
        return tuple(
            RequiredPointVisit(
                original_index=original_index,
                coordinate=supplied_points[original_index],
            )
            for original_index in order
        )

    async def _proposal_sequences(
        self,
        *,
        request: RouteGenerationRequest,
        anchor: Coordinate,
        insertion_index: int,
        factor_index: int,
        refinement_round: int,
        proposal_distance_m: float,
        state: _SearchState,
        variant: ProposalVariant | None = None,
        prefer_balanced: bool,
        cached_only: bool = False,
    ) -> tuple[ProposalPointSequence, ...]:
        seed = self._derived_seed(
            request.seed, insertion_index, factor_index, refinement_round
        )
        key: ProposalCacheKey = (
            anchor.lat,
            anchor.lon,
            proposal_distance_m,
            seed,
            request.profile,
        )
        if cached_only:
            proposal = state.proposal_cache.get(key)
        else:
            state.proposal_count += 1
            try:
                proposal = await self._backend.round_trip(
                    anchor, proposal_distance_m, seed, request.profile
                )
            except RoutingPointError:
                proposal = None
            if request.loop_geometry_preference == "prefer" and proposal is not None:
                state.proposal_cache[key] = proposal
        if proposal is None:
            return ()
        sequences = proposal_point_sequences(
            proposal.geometry,
            anchor,
            request.supplied_required_points[0],
            prefer_balanced=prefer_balanced,
            include_legacy_control=not cached_only,
            variant=variant,
        )
        state.derived_proposal_sequence_count += len(sequences)
        return sequences

    async def _evaluate_candidate(
        self,
        *,
        request: RouteGenerationRequest,
        required_points: tuple[Coordinate, ...],
        required_point_order: tuple[RequiredPointVisit, ...],
        insertion_index: int,
        optional_points: tuple[Coordinate, ...],
        construction: CandidateConstruction,
        state: _SearchState,
        extra_lane: bool = False,
    ) -> GeneratedCandidate | None:
        points = insert_optional_points(
            required_points, insertion_index, optional_points
        )
        key = point_sequence_key(points)
        cached = key in state.path_cache
        path = state.path_cache.get(key)
        if not cached:
            if extra_lane:
                if (
                    state.loop_geometry_extra_evaluated
                    >= state.loop_geometry_extra_evaluation_budget
                ):
                    return None
            elif state.base_evaluated >= state.base_search_budget:
                state.base_budget_exhausted = True
                return None
            state.evaluated += 1
            if extra_lane:
                state.loop_geometry_extra_evaluated += 1
            try:
                path = await self._backend.route(
                    points, request.profile, pass_through=True
                )
            except RoutingPointError:
                state.rejected += 1
                if extra_lane:
                    state.loop_geometry_extra_rejected += 1
                state.path_cache[key] = None
                return None
            state.path_cache[key] = path
        if path is None:
            return None
        if path.snapped_points is None or len(path.snapped_points) != len(points):
            if not cached:
                state.rejected += 1
                if extra_lane:
                    state.loop_geometry_extra_rejected += 1
                state.path_cache[key] = None
            return None
        first_optional_index = insertion_index + 1
        for offset, optional_point in enumerate(optional_points):
            snapped = path.snapped_points[first_optional_index + offset]
            displacement = haversine_distance_m(
                (optional_point.lon, optional_point.lat), snapped
            )
            if displacement > self._max_optional_snap_displacement_m:
                if not cached:
                    state.rejected += 1
                    if extra_lane:
                        state.loop_geometry_extra_rejected += 1
                    state.path_cache[key] = None
                return None
        route = self._result_factory.create(
            name=request.name,
            path=path,
            input_point_count=request.required_point_count,
        )
        if not cached:
            state.successful += 1
            if extra_lane:
                state.loop_geometry_extra_successful += 1
        return self._candidate(
            request,
            route,
            optional_points,
            required_point_order,
            points[:-1],
            construction,
        )

    @staticmethod
    def _candidate(
        request: RouteGenerationRequest,
        route: RouteResult,
        optional_points: tuple[Coordinate, ...],
        required_point_order: tuple[RequiredPointVisit, ...],
        routing_points: tuple[Coordinate, ...],
        construction: CandidateConstruction,
    ) -> GeneratedCandidate:
        target_error = abs(route.summary.distance_m - request.target_distance_m)
        return GeneratedCandidate(
            rank=1,
            route=route,
            optional_points=optional_points,
            required_point_order=required_point_order,
            routing_points=routing_points,
            construction=construction,
            target_error_m=target_error,
            within_tolerance=target_error <= request.tolerance_m,
            score=score_route(route, request.target_distance_m),
            signature=candidate_signature(route),
        )

    async def _refine_low_overlap(
        self,
        *,
        request: RouteGenerationRequest,
        standard_candidates: tuple[GeneratedCandidate, ...],
        analyzed_candidates: tuple[GeneratedCandidate, ...],
        control_source: GeneratedCandidate,
        nature_preference: NaturePreference,
        loop_geometry_preference: LoopGeometryPreference,
    ) -> tuple[
        tuple[GeneratedCandidate, ...],
        _LowOverlapSummary,
        tuple[str, ...],
    ]:
        """Refine selected standard candidates using one cached leg-search budget."""
        existing_source_order = self._low_overlap_source_order(standard_candidates)
        if nature_preference == "off" and loop_geometry_preference == "off":
            sources = existing_source_order[: self._low_overlap_settings.source_count]
        else:
            sources = self._preference_aware_refinement_sources(
                control_source,
                existing_source_order,
                analyzed_candidates,
                loop_geometry_preference=loop_geometry_preference,
                nature_preference=nature_preference,
            )
        pre = sources[0]
        search = LowOverlapBeamSearch(
            self._backend,
            self._structural_result_factory,
            self._low_overlap_settings,
        )
        refined_entries: list[_RefinedCandidate] = []
        refined_signatures: set[str] = {
            candidate.signature for candidate in standard_candidates
        }
        warnings: set[str] = set()
        refined_source_count = 0
        for source in sources:
            try:
                result = await search.assemble(
                    name=request.name,
                    routing_points=source.routing_points,
                    profile=request.profile,
                    target_distance_m=request.target_distance_m,
                    input_point_count=request.required_point_count,
                )
            except RoutingPointError:
                continue
            warnings.update(result.warnings)
            if result.states:
                refined_source_count += 1
            for state in result.states:
                route = self._result_factory.create(
                    name=request.name,
                    path=state.composed_path,
                    input_point_count=request.required_point_count,
                )
                candidate = self._candidate(
                    request,
                    route,
                    source.optional_points,
                    source.required_point_order,
                    source.routing_points,
                    "alternative_leg_beam",
                )
                if candidate.signature in refined_signatures:
                    continue
                refined_signatures.add(candidate.signature)
                refined_entries.append(
                    _RefinedCandidate(
                        candidate=candidate,
                        source=source,
                        natural_improvement=is_natural_improvement(candidate, source),
                    )
                )

        if search.budget_exhausted:
            warnings.add("low_overlap_leg_budget_exhausted")
        refined = tuple(entry.candidate for entry in refined_entries)
        best_refined = (
            rank_low_overlap_candidates(
                refined,
                nature_preference,
                loop_geometry_preference,
            )[0]
            if refined
            else None
        )
        if best_refined is None:
            warnings.add("low_overlap_no_complete_candidate")
            best_repeated_share = pre.route.analysis.repetition.repeated_distance.share
            best_backtrack_share = pre.route.analysis.immediate_backtrack.share
        else:
            best_repeated_share = (
                best_refined.route.analysis.repetition.repeated_distance.share
            )
            best_backtrack_share = best_refined.route.analysis.immediate_backtrack.share
        if refined_entries and not any(
            entry.natural_improvement for entry in refined_entries
        ):
            warnings.add("low_overlap_no_natural_improvement")
        if refined_entries and not any(
            entry.candidate.route.analysis.repetition.repeated_distance.share
            < entry.source.route.analysis.repetition.repeated_distance.share
            - NATURAL_IMPROVEMENT_EPSILON
            for entry in refined_entries
        ):
            warnings.add("low_overlap_no_repetition_improvement")

        natural_within_tolerance = tuple(
            entry.candidate
            for entry in refined_entries
            if entry.natural_improvement and entry.candidate.within_tolerance
        )
        if loop_geometry_preference == "off":
            off_recommended = (
                rank_low_overlap_candidates(natural_within_tolerance, "off", "off")[0]
                if natural_within_tolerance
                else pre
            )
            recommended = off_recommended
            if nature_preference == "prefer" and natural_within_tolerance:
                preferred = rank_low_overlap_candidates(
                    natural_within_tolerance,
                    nature_preference,
                    "off",
                )[0]
                if self._nature_improves(
                    self._nature_score(preferred), self._nature_score(recommended)
                ):
                    recommended = preferred
                else:
                    warnings.add("nature_no_candidate_improvement")
            elif nature_preference == "prefer":
                warnings.add("nature_no_candidate_improvement")
        else:
            control_improvements = tuple(
                entry.candidate
                for entry in refined_entries
                if entry.source.signature == control_source.signature
                and entry.natural_improvement
                and entry.candidate.within_tolerance
            )
            off_recommended = (
                rank_low_overlap_candidates(control_improvements, "off", "off")[0]
                if control_improvements
                else control_source
            )
            recommended = off_recommended
            geometry_pool = self._deduplicate_candidates(
                (off_recommended, *natural_within_tolerance)
            )
            geometry_preferred = rank_low_overlap_candidates(
                geometry_pool, "off", "prefer"
            )[0]
            if (
                geometry_preferred.signature != off_recommended.signature
                and self._passes_geometry_control_gate(
                    off_recommended,
                    geometry_preferred,
                    low_overlap=True,
                )
            ):
                recommended = geometry_preferred
            else:
                warnings.add("loop_geometry_no_candidate_improvement")

            if nature_preference == "prefer" and geometry_pool:
                nature_candidate = rank_low_overlap_candidates(
                    geometry_pool,
                    "prefer",
                    "prefer",
                )[0]
                if self._geometry_ordering_key(
                    nature_candidate, low_overlap=True
                ) <= self._geometry_ordering_key(
                    recommended, low_overlap=True
                ) and self._nature_improves(
                    self._nature_score(nature_candidate),
                    self._nature_score(recommended),
                ):
                    recommended = nature_candidate
                else:
                    warnings.add("nature_no_candidate_improvement")

        combined = tuple((*standard_candidates, *refined))
        if loop_geometry_preference == "prefer" and any(
            candidate.route.analysis.loop_geometry is None for candidate in combined
        ):
            warnings.add("loop_geometry_analysis_incomplete")
        ranked = rank_low_overlap_candidates(
            combined,
            nature_preference,
            loop_geometry_preference,
        )
        diversity = select_diverse_candidates(ranked, request.candidate_count)
        selected: list[GeneratedCandidate] = []
        selected_signatures: set[str] = set()

        def retain(candidate: GeneratedCandidate | None) -> None:
            if (
                candidate is not None
                and len(selected) < request.candidate_count
                and candidate.signature not in selected_signatures
            ):
                selected.append(candidate)
                selected_signatures.add(candidate.signature)

        retain(recommended)
        if loop_geometry_preference == "off":
            if request.candidate_count >= 2:
                retain(pre)
        else:
            if request.candidate_count >= 2:
                retain(off_recommended)
            if request.candidate_count >= 3:
                retain(control_source)
        for candidate in diversity.candidates:
            retain(candidate)
        for candidate in ranked:
            retain(candidate)
        selected = [
            candidate.model_copy(update={"rank": rank})
            for rank, candidate in enumerate(selected, start=1)
        ]
        if diversity.low_edge_coverage:
            warnings.add("edge_id_coverage_too_low_for_diversity")
        if diversity.relaxed:
            warnings.add("candidate_diversity_relaxed")

        summary = _LowOverlapSummary(
            alternative_leg_request_count=search.request_count,
            alternative_path_count=search.alternative_path_count,
            refined_source_count=refined_source_count,
            candidate_count=len(refined_entries),
            request_budget=self._low_overlap_settings.max_leg_requests,
            budget_exhausted=search.budget_exhausted,
            pre_repeated_share=(pre.route.analysis.repetition.repeated_distance.share),
            best_repeated_share=best_repeated_share,
            pre_backtrack_share=pre.route.analysis.immediate_backtrack.share,
            best_backtrack_share=best_backtrack_share,
            nature_off_recommended_signature=off_recommended.signature,
            nature_off_recommended_score=self._nature_score(off_recommended),
            best_available_nature_score=self._best_nature_score(combined),
            best_available_loop_geometry_penalty=(
                self._best_loop_geometry_penalty(combined)
            ),
        )
        return tuple(selected), summary, tuple(sorted(warnings))

    def _preference_aware_refinement_sources(
        self,
        control_source: GeneratedCandidate,
        existing_source_order: tuple[GeneratedCandidate, ...],
        analyzed_candidates: tuple[GeneratedCandidate, ...],
        *,
        loop_geometry_preference: LoopGeometryPreference,
        nature_preference: NaturePreference,
    ) -> tuple[GeneratedCandidate, ...]:
        """Retain PR5 control, geometry, nature, then deterministic source order."""
        limit = self._low_overlap_settings.source_count
        selected: list[GeneratedCandidate] = []
        signatures: set[str] = set()

        def retain(candidate: GeneratedCandidate | None) -> None:
            if (
                candidate is not None
                and len(selected) < limit
                and candidate.signature not in signatures
            ):
                selected.append(candidate)
                signatures.add(candidate.signature)

        retain(control_source)
        geometry_eligible = tuple(
            candidate
            for candidate in analyzed_candidates
            if candidate.within_tolerance
            and candidate.route.analysis.loop_geometry is not None
        )
        if not geometry_eligible:
            geometry_eligible = tuple(
                candidate
                for candidate in analyzed_candidates
                if candidate.route.analysis.loop_geometry is not None
            )
        if loop_geometry_preference == "prefer":
            retain(
                min(
                    geometry_eligible,
                    key=lambda candidate: (
                        self._known_loop_geometry_penalty(candidate),
                        candidate.signature,
                    ),
                    default=None,
                )
            )
        eligible = tuple(
            candidate
            for candidate in analyzed_candidates
            if candidate.within_tolerance
            and candidate.route.analysis.nature is not None
        )
        if not eligible:
            eligible = tuple(
                candidate
                for candidate in analyzed_candidates
                if candidate.route.analysis.nature is not None
            )
        if nature_preference == "prefer":
            retain(
                min(
                    eligible,
                    key=lambda candidate: (
                        -self._known_nature_score(candidate),
                        candidate.signature,
                    ),
                    default=None,
                )
            )
        for candidate in existing_source_order:
            retain(candidate)
        for candidate in analyzed_candidates:
            retain(candidate)
        return tuple(selected)

    def _nature_aware_refinement_sources(
        self,
        existing_source_order: tuple[GeneratedCandidate, ...],
        analyzed_candidates: tuple[GeneratedCandidate, ...],
    ) -> tuple[GeneratedCandidate, ...]:
        """Compatibility helper for the existing PR7 nature-only source policy."""
        return self._preference_aware_refinement_sources(
            existing_source_order[0],
            existing_source_order,
            analyzed_candidates,
            loop_geometry_preference="off",
            nature_preference="prefer",
        )

    @staticmethod
    def _unique_insertion_anchors(
        required_points: tuple[Coordinate, ...],
    ) -> tuple[tuple[int, Coordinate], ...]:
        seen: set[tuple[float, float]] = set()
        anchors: list[tuple[int, Coordinate]] = []
        for index, point in enumerate(required_points[:-1]):
            key = (point.lat, point.lon)
            if key in seen:
                continue
            seen.add(key)
            anchors.append((index, point))
        return tuple(anchors)

    @staticmethod
    def _balanced_insertion_anchors(
        anchors: tuple[tuple[int, Coordinate], ...],
    ) -> tuple[tuple[int, Coordinate], ...]:
        """Keep start first, then greedily spread anchors across global sectors."""
        if len(anchors) < 2:
            return anchors
        first = anchors[0]
        global_start = first[1]
        projection = LocalMetricProjection(global_start.lat)
        metric_start = projection.project_position((global_start.lon, global_start.lat))
        metadata: dict[int, tuple[int, float]] = {}
        for insertion_index, anchor in anchors[1:]:
            metric = projection.project_position((anchor.lon, anchor.lat))
            dx = metric[0] - metric_start[0]
            dy = metric[1] - metric_start[1]
            angle = atan2(dy, dx) % (2 * pi)
            metadata[insertion_index] = (
                min(
                    GLOBAL_SECTOR_COUNT - 1,
                    int(angle / (2 * pi / GLOBAL_SECTOR_COUNT)),
                ),
                hypot(dx, dy),
            )
        remaining = list(anchors[1:])
        selected = [first]
        selected_sectors: list[int] = []
        while remaining:

            def key(item: tuple[int, Coordinate]) -> tuple[bool, int, float, int]:
                insertion_index, _anchor = item
                sector, radius = metadata[insertion_index]
                minimum_distance = (
                    min(
                        _circular_sector_distance(sector, other)
                        for other in selected_sectors
                    )
                    if selected_sectors
                    else 0
                )
                return (
                    sector not in selected_sectors,
                    minimum_distance,
                    radius,
                    -insertion_index,
                )

            chosen = max(remaining, key=key)
            remaining.remove(chosen)
            selected.append(chosen)
            selected_sectors.append(metadata[chosen[0]][0])
        return tuple(selected)

    @staticmethod
    def _clamp_proposal_distance(distance_m: float, target_distance_m: float) -> float:
        maximum = max(
            MIN_PROPOSAL_DISTANCE_M,
            min(MAX_PROPOSAL_DISTANCE_M, target_distance_m * 0.8),
        )
        return min(maximum, max(MIN_PROPOSAL_DISTANCE_M, distance_m))

    @staticmethod
    def _derived_seed(
        request_seed: int,
        insertion_index: int,
        factor_index: int,
        refinement_round: int,
    ) -> int:
        return (
            request_seed * 1_000_003
            + insertion_index * 10_007
            + factor_index * 101
            + refinement_round * 1_000_000_007
        ) & 0x7FFF_FFFF

    def _summary(
        self,
        request: RouteGenerationRequest,
        baseline: RouteResult,
        best_order: RouteResult,
        state: _SearchState,
        *,
        status: GenerationStatus,
        warnings: tuple[str, ...],
        low_overlap: _LowOverlapSummary | None = None,
        candidates: tuple[GeneratedCandidate, ...] = (),
        analyzed_candidates: tuple[GeneratedCandidate, ...] = (),
    ) -> SearchSummary:
        low_overlap_metrics = low_overlap or _LowOverlapSummary()
        return SearchSummary(
            status=status,
            target_distance_m=request.target_distance_m,
            tolerance_m=request.tolerance_m,
            baseline_distance_m=baseline.summary.distance_m,
            best_order_distance_m=best_order.summary.distance_m,
            evaluated_candidate_count=state.evaluated,
            successful_candidate_count=state.successful,
            rejected_candidate_count=state.rejected,
            round_trip_proposal_count=state.proposal_count,
            derived_proposal_sequence_count=state.derived_proposal_sequence_count,
            evaluated_order_count=state.evaluated_order_count,
            successful_order_count=state.successful_order_count,
            rejected_order_count=state.rejected_order_count,
            fixed_order_repeated_share=(
                baseline.analysis.repetition.repeated_distance.share
            ),
            best_order_repeated_share=(
                best_order.analysis.repetition.repeated_distance.share
            ),
            fixed_order_backtrack_share=baseline.analysis.immediate_backtrack.share,
            best_order_backtrack_share=(best_order.analysis.immediate_backtrack.share),
            alternative_leg_request_count=(
                low_overlap_metrics.alternative_leg_request_count
            ),
            alternative_path_count=low_overlap_metrics.alternative_path_count,
            low_overlap_refined_source_count=(low_overlap_metrics.refined_source_count),
            low_overlap_candidate_count=low_overlap_metrics.candidate_count,
            low_overlap_request_budget=low_overlap_metrics.request_budget,
            low_overlap_budget_exhausted=low_overlap_metrics.budget_exhausted,
            pre_low_overlap_repeated_share=low_overlap_metrics.pre_repeated_share,
            best_low_overlap_repeated_share=low_overlap_metrics.best_repeated_share,
            pre_low_overlap_backtrack_share=low_overlap_metrics.pre_backtrack_share,
            best_low_overlap_backtrack_share=low_overlap_metrics.best_backtrack_share,
            low_overlap_requested=request.path_selection_mode == "low_overlap",
            nature_requested=request.nature_preference == "prefer",
            nature_index_available=self._nature_index_available,
            nature_index_feature_count=self._nature_index_feature_count,
            recommended_nature_score=(
                self._nature_score(candidates[0]) if candidates else None
            ),
            best_available_nature_score=(
                max(
                    (
                        score
                        for score in (
                            low_overlap_metrics.best_available_nature_score,
                            self._best_nature_score(analyzed_candidates),
                        )
                        if score is not None
                    ),
                    default=None,
                )
            ),
            loop_geometry_requested=request.loop_geometry_preference == "prefer",
            base_search_budget=state.base_search_budget,
            loop_geometry_extra_evaluation_budget=(
                state.loop_geometry_extra_evaluation_budget
            ),
            loop_geometry_extra_evaluated_count=(state.loop_geometry_extra_evaluated),
            loop_geometry_extra_successful_count=(state.loop_geometry_extra_successful),
            loop_geometry_extra_rejected_count=(state.loop_geometry_extra_rejected),
            recommended_loop_geometry_penalty=(
                self._loop_geometry_penalty(candidates[0]) if candidates else None
            ),
            best_available_loop_geometry_penalty=(
                min(
                    (
                        penalty
                        for penalty in (
                            low_overlap_metrics.best_available_loop_geometry_penalty,
                            self._best_loop_geometry_penalty(analyzed_candidates),
                        )
                        if penalty is not None
                    ),
                    default=None,
                )
            ),
            search_budget=state.search_budget,
            search_budget_exhausted=state.budget_exhausted,
            seed=request.seed,
            warnings=warnings,
        )

    def _effective_nature_preference(
        self, request: RouteGenerationRequest
    ) -> NaturePreference:
        if request.nature_preference == "prefer" and self._nature_index_available:
            return "prefer"
        return "off"

    def _rank_standard_staged(
        self,
        candidates: tuple[GeneratedCandidate, ...],
        *,
        nature_preference: NaturePreference,
        loop_geometry_preference: LoopGeometryPreference,
        warnings: set[str],
    ) -> tuple[GeneratedCandidate, ...]:
        """Apply off, geometry, then nature promotion with strict improvement."""
        ranked = rank_candidates(candidates, "off", "off")
        if loop_geometry_preference == "prefer":
            geometry_ranked = rank_candidates(candidates, "off", "prefer")
            if (
                ranked
                and geometry_ranked
                and self._loop_geometry_improves(
                    self._loop_geometry_penalty(geometry_ranked[0]),
                    self._loop_geometry_penalty(ranked[0]),
                )
            ):
                ranked = geometry_ranked
            else:
                warnings.add("loop_geometry_no_candidate_improvement")
        if nature_preference == "prefer":
            nature_ranked = rank_candidates(
                candidates,
                "prefer",
                loop_geometry_preference,
            )
            if (
                ranked
                and nature_ranked
                and self._nature_improves(
                    self._nature_score(nature_ranked[0]),
                    self._nature_score(ranked[0]),
                )
            ):
                ranked = nature_ranked
            else:
                warnings.add("nature_no_candidate_improvement")
        return ranked

    def _rank_standard_with_control(
        self,
        *,
        primary_candidates: tuple[GeneratedCandidate, ...],
        extra_candidates: tuple[GeneratedCandidate, ...],
        control: GeneratedCandidate | None,
        nature_preference: NaturePreference,
        warnings: set[str],
    ) -> tuple[GeneratedCandidate, ...]:
        """Gate balanced exploration against the exact legacy recommendation."""
        combined = self._deduplicate_candidates(
            (*primary_candidates, *extra_candidates)
        )
        if control is None:
            return self._rank_standard_staged(
                combined,
                nature_preference=nature_preference,
                loop_geometry_preference="prefer",
                warnings=warnings,
            )

        recommended = control
        geometry_pool = combined
        geometry_candidate = (
            rank_candidates(geometry_pool, "off", "prefer")[0]
            if geometry_pool
            else control
        )
        if (
            geometry_candidate.signature != control.signature
            and self._passes_geometry_control_gate(
                control,
                geometry_candidate,
                low_overlap=False,
            )
        ):
            recommended = geometry_candidate
        else:
            warnings.add("loop_geometry_no_candidate_improvement")

        if nature_preference == "prefer" and combined:
            nature_candidate = rank_candidates(combined, "prefer", "prefer")[0]
            if self._geometry_ordering_key(
                nature_candidate, low_overlap=False
            ) <= self._geometry_ordering_key(
                recommended, low_overlap=False
            ) and self._nature_improves(
                self._nature_score(nature_candidate),
                self._nature_score(recommended),
            ):
                recommended = nature_candidate
            else:
                warnings.add("nature_no_candidate_improvement")

        generally_ranked = rank_candidates(
            combined,
            nature_preference,
            "prefer",
        )
        return self._recommendation_first(generally_ranked, recommended)

    def _passes_geometry_control_gate(
        self,
        control: GeneratedCandidate,
        candidate: GeneratedCandidate,
        *,
        low_overlap: bool,
    ) -> bool:
        control_higher = self._higher_priority_key(control, low_overlap=low_overlap)
        candidate_higher = self._higher_priority_key(candidate, low_overlap=low_overlap)
        if candidate_higher < control_higher:
            return True
        if candidate_higher > control_higher:
            return False
        candidate_penalty = self._loop_geometry_penalty(candidate)
        control_penalty = self._loop_geometry_penalty(control)
        return candidate_penalty is not None and (
            control_penalty is None or candidate_penalty < control_penalty
        )

    @staticmethod
    def _higher_priority_key(
        candidate: GeneratedCandidate, *, low_overlap: bool
    ) -> tuple[int, float, float, float]:
        tolerance_class = 0 if candidate.within_tolerance else 1
        outside_pressure = (
            candidate.score.distance_error_ratio
            if not candidate.within_tolerance
            else 0.0
        )
        backtrack = candidate.route.analysis.immediate_backtrack.share
        repetition = candidate.route.analysis.repetition.repeated_distance.share
        if low_overlap:
            return tolerance_class, outside_pressure, repetition, backtrack
        return tolerance_class, outside_pressure, backtrack, repetition

    def _geometry_ordering_key(
        self, candidate: GeneratedCandidate, *, low_overlap: bool
    ) -> tuple[object, ...]:
        penalty = self._loop_geometry_penalty(candidate)
        return (
            *self._higher_priority_key(candidate, low_overlap=low_overlap),
            1 if penalty is None else 0,
            0.0 if penalty is None else penalty,
        )

    @staticmethod
    def _deduplicate_candidates(
        candidates: tuple[GeneratedCandidate, ...],
    ) -> tuple[GeneratedCandidate, ...]:
        unique: list[GeneratedCandidate] = []
        signatures: set[str] = set()
        for candidate in candidates:
            if candidate.signature in signatures:
                continue
            signatures.add(candidate.signature)
            unique.append(candidate)
        return tuple(unique)

    @staticmethod
    def _recommendation_first(
        ranked: tuple[GeneratedCandidate, ...],
        recommendation: GeneratedCandidate,
    ) -> tuple[GeneratedCandidate, ...]:
        ordered = (
            recommendation,
            *(
                candidate
                for candidate in ranked
                if candidate.signature != recommendation.signature
            ),
        )
        return tuple(
            candidate.model_copy(update={"rank": rank})
            for rank, candidate in enumerate(ordered, start=1)
        )

    @staticmethod
    def _retain_recommendation_and_control(
        *,
        ranked: tuple[GeneratedCandidate, ...],
        diverse: tuple[GeneratedCandidate, ...],
        recommendation: GeneratedCandidate | None,
        control: GeneratedCandidate | None,
        candidate_count: int,
    ) -> tuple[GeneratedCandidate, ...]:
        selected: list[GeneratedCandidate] = []
        signatures: set[str] = set()

        def retain(candidate: GeneratedCandidate | None) -> None:
            if (
                candidate is not None
                and len(selected) < candidate_count
                and candidate.signature not in signatures
            ):
                selected.append(candidate)
                signatures.add(candidate.signature)

        retain(recommendation)
        retain(control)
        for candidate in diverse:
            retain(candidate)
        for candidate in ranked:
            retain(candidate)
        return tuple(
            candidate.model_copy(update={"rank": rank})
            for rank, candidate in enumerate(selected, start=1)
        )

    @staticmethod
    def _low_overlap_source_order(
        candidates: tuple[GeneratedCandidate, ...],
    ) -> tuple[GeneratedCandidate, ...]:
        return tuple(
            sorted(
                candidates,
                key=lambda candidate: (
                    0 if candidate.within_tolerance else 1,
                    candidate.route.analysis.repetition.repeated_distance.share,
                    candidate.route.analysis.immediate_backtrack.share,
                    candidate.target_error_m,
                    candidate.signature,
                ),
            )
        )

    def _nature_warnings(self, request: RouteGenerationRequest) -> tuple[str, ...]:
        if request.nature_preference == "prefer" and not self._nature_index_available:
            return ("nature_index_unavailable",)
        return ()

    @staticmethod
    def _route_nature_warnings(routes: tuple[RouteResult, ...]) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    warning
                    for route in routes
                    if route.analysis.nature is not None
                    for warning in route.analysis.nature.warnings
                }
            )
        )

    @staticmethod
    def _nature_score(candidate: GeneratedCandidate) -> float | None:
        nature = candidate.route.analysis.nature
        return nature.nature_score if nature is not None else None

    @staticmethod
    def _known_nature_score(candidate: GeneratedCandidate) -> float:
        nature = candidate.route.analysis.nature
        if nature is None:
            raise ValueError("candidate has no nature analysis")
        return nature.nature_score

    @classmethod
    def _best_nature_score(
        cls, candidates: tuple[GeneratedCandidate, ...]
    ) -> float | None:
        scores = tuple(
            score
            for candidate in candidates
            if (score := cls._nature_score(candidate)) is not None
        )
        return max(scores, default=None)

    @staticmethod
    def _loop_geometry_penalty(candidate: GeneratedCandidate) -> float | None:
        geometry = candidate.route.analysis.loop_geometry
        return geometry.penalty_breakdown.total if geometry is not None else None

    @staticmethod
    def _known_loop_geometry_penalty(candidate: GeneratedCandidate) -> float:
        geometry = candidate.route.analysis.loop_geometry
        if geometry is None:
            raise ValueError("candidate has no loop geometry analysis")
        return geometry.penalty_breakdown.total

    @classmethod
    def _best_loop_geometry_penalty(
        cls, candidates: tuple[GeneratedCandidate, ...]
    ) -> float | None:
        penalties = tuple(
            penalty
            for candidate in candidates
            if (penalty := cls._loop_geometry_penalty(candidate)) is not None
        )
        return min(penalties, default=None)

    @staticmethod
    def _loop_geometry_improves(
        preferred: float | None, previous: float | None
    ) -> bool:
        if preferred is None:
            return False
        return previous is None or (
            preferred < previous - LOOP_GEOMETRY_IMPROVEMENT_EPSILON
        )

    @staticmethod
    def _nature_improves(preferred: float | None, previous: float | None) -> bool:
        if preferred is None:
            return False
        return previous is None or preferred > previous + NATURAL_IMPROVEMENT_EPSILON


def _circular_sector_distance(left: int, right: int) -> int:
    difference = abs(left - right)
    return min(difference, GLOBAL_SECTOR_COUNT - difference)
