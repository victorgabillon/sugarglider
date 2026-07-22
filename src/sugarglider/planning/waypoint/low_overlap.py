"""Bounded low-overlap assembly using only shared-gateway alternative legs."""

from dataclasses import dataclass

from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.models import WaypointPlanRequest
from sugarglider.planning.routing_gateway import SearchBudgetExhaustedError
from sugarglider.planning.waypoint.models import WaypointSequenceProposal
from sugarglider.routing.backend import RoutedPath
from sugarglider.routing.composition import (
    RouteCompositionError,
    compose_routed_segments,
)
from sugarglider.routing.errors import RoutingError
from sugarglider.routing.result import RouteResultFactory


@dataclass(frozen=True)
class LowOverlapPath:
    proposal: WaypointSequenceProposal
    path: RoutedPath
    all_primary_paths: bool


@dataclass(frozen=True)
class _BeamState:
    segments: tuple[RoutedPath, ...]
    path: RoutedPath
    repeated_m: float
    backtracking_m: float
    all_primary_paths: bool


async def refine_low_overlap(
    *,
    request: WaypointPlanRequest,
    source: WaypointSequenceProposal,
    context: PlanningSearchContext,
    structural_result_factory: RouteResultFactory,
    beam_width: int = 8,
) -> tuple[LowOverlapPath, ...]:
    """Compose a deterministic beam without a second cache or request budget."""
    beam: tuple[_BeamState, ...] = ()
    for leg_index, (start, end) in enumerate(
        zip(source.routing_points, source.routing_points[1:], strict=False)
    ):
        try:
            alternatives = await context.routes.alternative_routes(
                start,
                end,
                request.routing_profile,
                max_paths=3,
                max_weight_factor=1.6,
                max_share_factor=0.5,
            )
        except (RoutingError, SearchBudgetExhaustedError):
            return ()
        expanded: list[_BeamState] = []
        for alternative_index, alternative in enumerate(alternatives):
            parents: tuple[_BeamState | None, ...] = beam or (None,)
            for parent in parents:
                segments = (
                    (alternative,)
                    if parent is None
                    else (*parent.segments, alternative)
                )
                try:
                    path = compose_routed_segments(segments)
                    route = structural_result_factory.create(
                        name=request.name,
                        path=path,
                        input_point_count=leg_index + 2,
                        routing_profile=request.routing_profile,
                    )
                except (RouteCompositionError, RoutingError):
                    continue
                expanded.append(
                    _BeamState(
                        segments=segments,
                        path=path,
                        repeated_m=(
                            route.analysis.repetition.repeated_distance.distance_m
                        ),
                        backtracking_m=(route.analysis.immediate_backtrack.distance_m),
                        all_primary_paths=(
                            alternative_index == 0
                            and (parent is None or parent.all_primary_paths)
                        ),
                    )
                )
        if not expanded:
            return ()
        beam = _prune(
            tuple(expanded),
            beam_width=beam_width,
            target_progress_m=(
                request.distance_objective.target_m
                * (leg_index + 1)
                / (len(source.routing_points) - 1)
            ),
        )
    refined = source.__class__(
        routing_points=source.routing_points,
        exact_points=source.exact_points,
        exact_point_positions=source.exact_point_positions,
        original_indices=source.original_indices,
        exact_point_ids=source.exact_point_ids,
        topology=source.topology,
        construction="low_overlap_beam",
        order_provenance=source.order_provenance,
        detour_provenance=source.detour_provenance,
    )
    return tuple(
        LowOverlapPath(refined, state.path, state.all_primary_paths) for state in beam
    )


def _prune(
    states: tuple[_BeamState, ...], *, beam_width: int, target_progress_m: float
) -> tuple[_BeamState, ...]:
    ordered = sorted(
        states,
        key=lambda state: (
            state.repeated_m,
            state.backtracking_m,
            abs(state.path.distance_m - target_progress_m),
            tuple(state.path.geometry),
        ),
    )
    retained = ordered[:beam_width]
    primary = next((state for state in states if state.all_primary_paths), None)
    if primary is not None and primary not in retained:
        retained[-1] = primary
    return tuple(retained)
