"""Bounded deterministic proposal-and-evaluation route generation service."""

from dataclasses import dataclass, field

from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.generation import (
    GeneratedCandidate,
    GenerationStatus,
    RouteGenerationRequest,
    RouteGenerationResult,
    SearchSummary,
)
from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.generation.geometry import (
    insert_optional_points,
    point_sequence_key,
    sample_optional_points,
)
from sugarglider.generation.scoring import rank_candidates, score_route
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

type PointSequenceKey = tuple[tuple[float, float], ...]


class TargetDistanceInfeasibleError(Exception):
    """GPX generation cannot return a candidate because baseline is too long."""


class RouteGenerationNoCandidateError(Exception):
    """GPX generation produced no graph-valid candidate."""


@dataclass
class _SearchState:
    search_budget: int
    evaluated: int = 0
    successful: int = 0
    rejected: int = 0
    proposal_count: int = 0
    budget_exhausted: bool = False
    path_cache: dict[PointSequenceKey, RoutedPath | None] = field(default_factory=dict)


@dataclass(frozen=True)
class _RefinementSource:
    candidate: GeneratedCandidate
    insertion_index: int
    proposal_distance_m: float
    factor_index: int


class RouteGenerationService:
    """Coordinate a small sequential search over GraphHopper round-trip proposals."""

    def __init__(
        self,
        backend: RoutingBackend,
        result_factory: RouteResultFactory | None = None,
        *,
        max_evaluations: int = 48,
        max_optional_snap_displacement_m: float = 300.0,
    ) -> None:
        if max_evaluations < 1:
            raise ValueError("generation search budget must be positive")
        if max_optional_snap_displacement_m < 0:
            raise ValueError("optional snap displacement must be non-negative")
        self._backend = backend
        self._result_factory = result_factory or RouteResultFactory()
        self._max_evaluations = max_evaluations
        self._max_optional_snap_displacement_m = max_optional_snap_displacement_m

    async def generate(self, request: RouteGenerationRequest) -> RouteGenerationResult:
        """Generate distinct candidates while preserving every required anchor."""
        required_points = tuple(request.points)
        baseline_path = await self._backend.route(required_points, request.profile)
        baseline = self._result_factory.create(
            name=request.name,
            path=baseline_path,
            input_point_count=request.required_point_count,
        )
        state = _SearchState(self._max_evaluations)
        maximum_acceptable = request.target_distance_m + request.tolerance_m
        if baseline.summary.distance_m > maximum_acceptable:
            return RouteGenerationResult(
                baseline=baseline,
                candidates=(),
                search=self._summary(
                    request,
                    baseline,
                    state,
                    status="infeasible",
                    warnings=("mandatory_route_exceeds_target_tolerance",),
                ),
            )

        drafts: list[GeneratedCandidate] = []
        signatures: set[str] = set()
        if (
            abs(baseline.summary.distance_m - request.target_distance_m)
            <= request.tolerance_m
        ):
            baseline_candidate = self._candidate(request, baseline, ())
            drafts.append(baseline_candidate)
            signatures.add(baseline_candidate.signature)

        remaining_extra_m = request.target_distance_m - baseline.summary.distance_m
        refinement_sources: list[_RefinementSource] = []
        if remaining_extra_m > 0:
            base_proposal_distance = remaining_extra_m / PROPOSAL_SURVIVAL_FACTOR
            stop_search = False
            for insertion_index, anchor in self._unique_insertion_anchors(
                required_points
            ):
                for factor_index, factor in enumerate(DISTANCE_FACTORS):
                    if state.evaluated >= state.search_budget:
                        state.budget_exhausted = True
                        stop_search = True
                        break
                    proposal_distance = self._clamp_proposal_distance(
                        base_proposal_distance * factor,
                        request.target_distance_m,
                    )
                    optional_points = await self._proposal_points(
                        request=request,
                        anchor=anchor,
                        insertion_index=insertion_index,
                        factor_index=factor_index,
                        refinement_round=0,
                        proposal_distance_m=proposal_distance,
                        state=state,
                    )
                    if not optional_points:
                        continue
                    candidate = await self._evaluate_candidate(
                        request=request,
                        required_points=required_points,
                        insertion_index=insertion_index,
                        optional_points=optional_points,
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
                            insertion_index=insertion_index,
                            proposal_distance_m=proposal_distance,
                            factor_index=factor_index,
                        )
                    )
                if stop_search:
                    break

            closest = sorted(
                refinement_sources,
                key=lambda source: (
                    source.candidate.target_error_m,
                    source.candidate.signature,
                ),
            )[: min(MAX_REFINEMENT_COUNT, request.candidate_count)]
            for source in closest:
                if state.evaluated >= state.search_budget:
                    state.budget_exhausted = True
                    break
                actual_distance = source.candidate.route.summary.distance_m
                if actual_distance <= 0:
                    continue
                adjustment = request.target_distance_m / actual_distance
                adjustment = min(
                    REFINEMENT_RATIO_MAX, max(REFINEMENT_RATIO_MIN, adjustment)
                )
                proposal_distance = self._clamp_proposal_distance(
                    source.proposal_distance_m * adjustment,
                    request.target_distance_m,
                )
                anchor = required_points[source.insertion_index]
                optional_points = await self._proposal_points(
                    request=request,
                    anchor=anchor,
                    insertion_index=source.insertion_index,
                    factor_index=source.factor_index,
                    refinement_round=1,
                    proposal_distance_m=proposal_distance,
                    state=state,
                )
                if not optional_points:
                    continue
                candidate = await self._evaluate_candidate(
                    request=request,
                    required_points=required_points,
                    insertion_index=source.insertion_index,
                    optional_points=optional_points,
                    state=state,
                )
                if candidate is None:
                    continue
                if candidate.signature in signatures:
                    state.rejected += 1
                    continue
                signatures.add(candidate.signature)
                drafts.append(candidate)

        ranked = rank_candidates(tuple(drafts))
        diversity = select_diverse_candidates(ranked, request.candidate_count)
        warnings: set[str] = set()
        if state.budget_exhausted:
            warnings.add("search_budget_exhausted")
        if diversity.low_edge_coverage and ranked:
            warnings.add("edge_id_coverage_too_low_for_diversity")
        if diversity.relaxed:
            warnings.add("candidate_diversity_relaxed")
        if not diversity.candidates:
            warnings.add("no_generated_candidate")
        status: GenerationStatus = (
            "within_tolerance"
            if any(candidate.within_tolerance for candidate in diversity.candidates)
            else "best_effort"
        )
        return RouteGenerationResult(
            baseline=baseline,
            candidates=diversity.candidates,
            search=self._summary(
                request,
                baseline,
                state,
                status=status,
                warnings=tuple(sorted(warnings)),
            ),
        )

    async def _proposal_points(
        self,
        *,
        request: RouteGenerationRequest,
        anchor: Coordinate,
        insertion_index: int,
        factor_index: int,
        refinement_round: int,
        proposal_distance_m: float,
        state: _SearchState,
    ) -> tuple[Coordinate, ...]:
        state.proposal_count += 1
        seed = self._derived_seed(
            request.seed, insertion_index, factor_index, refinement_round
        )
        try:
            proposal = await self._backend.round_trip(
                anchor, proposal_distance_m, seed, request.profile
            )
        except RoutingPointError:
            return ()
        return sample_optional_points(proposal.geometry, anchor)

    async def _evaluate_candidate(
        self,
        *,
        request: RouteGenerationRequest,
        required_points: tuple[Coordinate, ...],
        insertion_index: int,
        optional_points: tuple[Coordinate, ...],
        state: _SearchState,
    ) -> GeneratedCandidate | None:
        points = insert_optional_points(
            required_points, insertion_index, optional_points
        )
        key = point_sequence_key(points)
        cached = key in state.path_cache
        path = state.path_cache.get(key)
        if not cached:
            if state.evaluated >= state.search_budget:
                state.budget_exhausted = True
                return None
            state.evaluated += 1
            try:
                path = await self._backend.route(
                    points, request.profile, pass_through=True
                )
            except RoutingPointError:
                state.rejected += 1
                state.path_cache[key] = None
                return None
            state.path_cache[key] = path
        if path is None:
            return None
        if path.snapped_points is None or len(path.snapped_points) != len(points):
            if not cached:
                state.rejected += 1
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
                    state.path_cache[key] = None
                return None
        route = self._result_factory.create(
            name=request.name,
            path=path,
            input_point_count=request.required_point_count,
        )
        if not cached:
            state.successful += 1
        return self._candidate(request, route, optional_points)

    @staticmethod
    def _candidate(
        request: RouteGenerationRequest,
        route: RouteResult,
        optional_points: tuple[Coordinate, ...],
    ) -> GeneratedCandidate:
        target_error = abs(route.summary.distance_m - request.target_distance_m)
        return GeneratedCandidate(
            rank=1,
            route=route,
            optional_points=optional_points,
            target_error_m=target_error,
            within_tolerance=target_error <= request.tolerance_m,
            score=score_route(route, request.target_distance_m),
            signature=candidate_signature(route),
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

    @staticmethod
    def _summary(
        request: RouteGenerationRequest,
        baseline: RouteResult,
        state: _SearchState,
        *,
        status: GenerationStatus,
        warnings: tuple[str, ...],
    ) -> SearchSummary:
        return SearchSummary(
            status=status,
            target_distance_m=request.target_distance_m,
            tolerance_m=request.tolerance_m,
            baseline_distance_m=baseline.summary.distance_m,
            evaluated_candidate_count=state.evaluated,
            successful_candidate_count=state.successful,
            rejected_candidate_count=state.rejected,
            round_trip_proposal_count=state.proposal_count,
            search_budget=state.search_budget,
            search_budget_exhausted=state.budget_exhausted,
            seed=request.seed,
            warnings=warnings,
        )
