"""Bounded deterministic assembly of per-leg alternative routed paths."""

from dataclasses import dataclass, field

from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.generation.signatures import candidate_signature
from sugarglider.routing.backend import RoutedPath, RoutingBackend
from sugarglider.routing.composition import (
    RouteCompositionError,
    compose_routed_segments,
)
from sugarglider.routing.result import RouteResultFactory

MIN_LOW_OVERLAP_EDGE_COVERAGE = 0.90

type AlternativeCacheKey = tuple[
    float,
    float,
    float,
    float,
    str,
    int,
    float,
    float,
]


@dataclass(frozen=True)
class LowOverlapSettings:
    """Server-controlled bounds for alternative routing and beam expansion."""

    max_paths: int = 3
    max_weight_factor: float = 1.6
    max_share_factor: float = 0.5
    beam_width: int = 12
    max_leg_requests: int = 48
    source_count: int = 2

    def __post_init__(self) -> None:
        if not 1 <= self.max_paths <= 5:
            raise ValueError("low-overlap max paths must be between 1 and 5")
        if not 1.0 <= self.max_weight_factor <= 3.0:
            raise ValueError("low-overlap max weight factor must be between 1 and 3")
        if not 0.0 <= self.max_share_factor <= 1.0:
            raise ValueError("low-overlap max share factor must be between 0 and 1")
        if not 1 <= self.beam_width <= 50:
            raise ValueError("low-overlap beam width must be between 1 and 50")
        if self.max_leg_requests < 1:
            raise ValueError("low-overlap leg-request budget must be positive")
        if not 1 <= self.source_count <= 3:
            raise ValueError("low-overlap source count must be between 1 and 3")


@dataclass(frozen=True)
class BeamState:
    """One analyzed partial combination retained by the bounded beam."""

    segments: tuple[RoutedPath, ...]
    composed_path: RoutedPath
    completed_leg_count: int
    stable_signature: str
    repeated_edge_distance_m: float
    immediate_backtrack_distance_m: float
    total_distance_m: float
    all_primary_paths: bool


@dataclass(frozen=True)
class LowOverlapSearchResult:
    """Completed beam states and deterministic diagnostics for one source."""

    states: tuple[BeamState, ...]
    warnings: tuple[str, ...]


@dataclass
class LowOverlapBeamSearch:
    """Retrieve cached alternatives and assemble globally analyzed route paths."""

    backend: RoutingBackend
    structural_result_factory: RouteResultFactory
    settings: LowOverlapSettings
    request_count: int = 0
    cache_hit_count: int = 0
    alternative_path_count: int = 0
    budget_exhausted: bool = False
    _cache: dict[AlternativeCacheKey, tuple[RoutedPath, ...]] = field(
        default_factory=dict
    )

    async def assemble(
        self,
        *,
        name: str,
        routing_points: tuple[Coordinate, ...],
        profile: str,
        target_distance_m: float,
        input_point_count: int,
    ) -> LowOverlapSearchResult:
        """Close and refine one exact candidate routing-point sequence."""
        if len(routing_points) < 2:
            raise ValueError("low-overlap assembly requires at least two points")
        closed_points = (
            routing_points
            if _same_coordinate(routing_points[0], routing_points[-1])
            else (*routing_points, routing_points[0])
        )
        total_leg_count = len(closed_points) - 1
        beam: tuple[BeamState, ...] = ()
        warnings: set[str] = set()

        for leg_index, (start, end) in enumerate(
            zip(closed_points, closed_points[1:], strict=False)
        ):
            alternatives = await self._alternatives(start, end, profile)
            if alternatives is None:
                warnings.add("low_overlap_leg_budget_exhausted")
                return LowOverlapSearchResult((), tuple(sorted(warnings)))
            expanded: list[BeamState] = []
            for alternative_index, alternative in enumerate(alternatives):
                parent_states: tuple[BeamState | None, ...] = beam or (None,)
                for parent in parent_states:
                    segments = (
                        (alternative,)
                        if parent is None
                        else (*parent.segments, alternative)
                    )
                    try:
                        composed = compose_routed_segments(segments)
                    except RouteCompositionError:
                        continue
                    route = self.structural_result_factory.create(
                        name=name,
                        path=composed,
                        input_point_count=input_point_count,
                    )
                    expanded.append(
                        _beam_state(
                            segments=segments,
                            path=composed,
                            route=route,
                            completed_leg_count=leg_index + 1,
                            all_primary_paths=(
                                alternative_index == 0
                                and (parent is None or parent.all_primary_paths)
                            ),
                        )
                    )
            if not expanded:
                return LowOverlapSearchResult(
                    (), ("low_overlap_no_complete_candidate",)
                )
            beam = _prune_beam(
                tuple(expanded),
                beam_width=self.settings.beam_width,
                target_distance_m=target_distance_m,
                total_leg_count=total_leg_count,
            )

        if any(
            self.structural_result_factory.create(
                name=name,
                path=state.composed_path,
                input_point_count=input_point_count,
            ).analysis.repetition.edge_id_coverage.share
            < MIN_LOW_OVERLAP_EDGE_COVERAGE
            for state in beam
        ):
            warnings.add("low_overlap_edge_id_coverage_insufficient")
        return LowOverlapSearchResult(beam, tuple(sorted(warnings)))

    async def _alternatives(
        self, start: Coordinate, end: Coordinate, profile: str
    ) -> tuple[RoutedPath, ...] | None:
        key: AlternativeCacheKey = (
            start.lat,
            start.lon,
            end.lat,
            end.lon,
            profile,
            self.settings.max_paths,
            self.settings.max_weight_factor,
            self.settings.max_share_factor,
        )
        cached = self._cache.get(key)
        if cached is not None:
            self.cache_hit_count += 1
            return cached
        if self.request_count >= self.settings.max_leg_requests:
            self.budget_exhausted = True
            return None
        self.request_count += 1
        alternatives = await self.backend.alternative_routes(
            start,
            end,
            profile,
            max_paths=self.settings.max_paths,
            max_weight_factor=self.settings.max_weight_factor,
            max_share_factor=self.settings.max_share_factor,
        )
        self.alternative_path_count += len(alternatives)
        self._cache[key] = alternatives
        return alternatives


def _beam_state(
    *,
    segments: tuple[RoutedPath, ...],
    path: RoutedPath,
    route: RouteResult,
    completed_leg_count: int,
    all_primary_paths: bool,
) -> BeamState:
    return BeamState(
        segments=segments,
        composed_path=path,
        completed_leg_count=completed_leg_count,
        stable_signature=candidate_signature(route),
        repeated_edge_distance_m=(
            route.analysis.repetition.repeated_distance.distance_m
        ),
        immediate_backtrack_distance_m=route.analysis.immediate_backtrack.distance_m,
        total_distance_m=route.summary.distance_m,
        all_primary_paths=all_primary_paths,
    )


def _prune_beam(
    states: tuple[BeamState, ...],
    *,
    beam_width: int,
    target_distance_m: float,
    total_leg_count: int,
) -> tuple[BeamState, ...]:
    """Retain overlap, backtracking, progress, primary, and Pareto states."""
    distinct: dict[str, BeamState] = {}
    for state in sorted(states, key=_overlap_key):
        distinct.setdefault(state.stable_signature, state)
    candidates = tuple(distinct.values())
    expected = target_distance_m * (candidates[0].completed_leg_count / total_leg_count)
    progress_key = lambda state: (  # noqa: E731 - compact deterministic key
        abs(state.total_distance_m - expected),
        state.repeated_edge_distance_m,
        state.immediate_backtrack_distance_m,
        state.stable_signature,
    )

    retained: list[BeamState] = []
    signatures: set[str] = set()

    def retain(state: BeamState | None) -> None:
        if (
            state is not None
            and len(retained) < beam_width
            and state.stable_signature not in signatures
        ):
            retained.append(state)
            signatures.add(state.stable_signature)

    retain(min(candidates, key=_overlap_key))
    retain(
        min(
            candidates,
            key=lambda state: (
                state.immediate_backtrack_distance_m,
                state.repeated_edge_distance_m,
                abs(state.total_distance_m - expected),
                state.stable_signature,
            ),
        )
    )
    retain(min(candidates, key=progress_key))
    primary = tuple(state for state in candidates if state.all_primary_paths)
    retain(min(primary, key=lambda state: state.stable_signature, default=None))
    for state in sorted(candidates, key=progress_key):
        if _is_pareto_state(state, candidates, expected):
            retain(state)
    for state in sorted(candidates, key=_overlap_key):
        retain(state)
    return tuple(retained)


def _overlap_key(state: BeamState) -> tuple[float, float, float, str]:
    return (
        state.repeated_edge_distance_m,
        state.immediate_backtrack_distance_m,
        state.total_distance_m,
        state.stable_signature,
    )


def _is_pareto_state(
    state: BeamState, candidates: tuple[BeamState, ...], expected_distance_m: float
) -> bool:
    objective = (
        state.repeated_edge_distance_m,
        state.immediate_backtrack_distance_m,
        abs(state.total_distance_m - expected_distance_m),
    )
    for other in candidates:
        if other is state:
            continue
        other_objective = (
            other.repeated_edge_distance_m,
            other.immediate_backtrack_distance_m,
            abs(other.total_distance_m - expected_distance_m),
        )
        if all(
            other_value <= state_value
            for other_value, state_value in zip(other_objective, objective, strict=True)
        ) and any(
            other_value < state_value
            for other_value, state_value in zip(other_objective, objective, strict=True)
        ):
            return False
    return True


def _same_coordinate(left: Coordinate, right: Coordinate) -> bool:
    return (left.lat, left.lon) == (right.lat, right.lon)
