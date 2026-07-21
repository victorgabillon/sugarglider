"""Bounded graph-derived target-distance detour proposals."""

from dataclasses import dataclass

from sugarglider.domain.models import Coordinate
from sugarglider.planning.budget import SearchPhase
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.models import WaypointPlanRequest
from sugarglider.planning.routing_gateway import SearchBudgetExhaustedError
from sugarglider.planning.waypoint.models import (
    WaypointConstruction,
    WaypointSequenceProposal,
)
from sugarglider.routing.backend import RoutedPath
from sugarglider.routing.errors import RoutingError

MIN_LOOP_PROPOSAL_M = 2_000.0
MAX_LOOP_PROPOSAL_M = 30_000.0
MAX_DETOUR_PROPOSALS = 8


@dataclass(frozen=True)
class DetourProposalStats:
    graph_proposals_requested: int
    proposals_created: int
    proposals_rejected_before_routing: int


async def target_detour_proposals(
    *,
    request: WaypointPlanRequest,
    sources: tuple[tuple[WaypointSequenceProposal, RoutedPath], ...],
    context: PlanningSearchContext,
    limit: int = MAX_DETOUR_PROPOSALS,
) -> tuple[tuple[WaypointSequenceProposal, ...], DetourProposalStats]:
    """Derive optional anchors only from routed GraphHopper proposal geometry."""
    backend_calls_before = context.routes.cache_snapshot().backend_call_count
    proposals: list[WaypointSequenceProposal] = []
    rejected = 0
    seen: set[tuple[tuple[float, float], ...]] = set()
    for source_index, (source, path) in enumerate(sources):
        if len(proposals) >= limit:
            break
        if path.distance_m >= (
            request.distance_objective.target_m - request.distance_objective.tolerance_m
        ):
            continue
        try:
            if request.topology == "loop":
                derived = await _loop_detour(
                    request=request,
                    source=source,
                    source_index=source_index,
                    missing_distance_m=(
                        request.distance_objective.target_m - path.distance_m
                    ),
                    context=context,
                )
            else:
                derived = await _open_detours(
                    request=request,
                    source=source,
                    context=context,
                )
        except (RoutingError, SearchBudgetExhaustedError):
            rejected += 1
            continue
        for proposal in derived:
            key = tuple((point.lat, point.lon) for point in proposal.routing_points)
            if key in seen:
                rejected += 1
                continue
            seen.add(key)
            proposals.append(proposal)
            if len(proposals) >= limit:
                break
    requested = (
        context.routes.cache_snapshot().backend_call_count - backend_calls_before
    )
    return tuple(proposals), DetourProposalStats(requested, len(proposals), rejected)


async def _loop_detour(
    *,
    request: WaypointPlanRequest,
    source: WaypointSequenceProposal,
    source_index: int,
    missing_distance_m: float,
    context: PlanningSearchContext,
) -> tuple[WaypointSequenceProposal, ...]:
    proposals: list[WaypointSequenceProposal] = []
    for factor_index, factor in enumerate((0.9, 1.2, 1.5)):
        distance_m = min(
            MAX_LOOP_PROPOSAL_M,
            max(MIN_LOOP_PROPOSAL_M, missing_distance_m * factor),
        )
        proposal_path = await context.routes.round_trip(
            source.exact_points[0],
            distance_m,
            request.seed + source_index * 104_729 + factor_index * 7_919,
            request.routing_profile,
            phase=SearchPhase.SKELETON,
        )
        via = _sample_via_points(proposal_path, source.exact_points[0])
        if not via:
            continue
        proposals.append(
            _insert_after_exact(
                source,
                exact_index=0,
                via=via,
                construction="round_trip_detour",
                provenance=f"graphhopper_round_trip_geometry:{factor_index}",
            )
        )
    return tuple(proposals)


async def _open_detours(
    *,
    request: WaypointPlanRequest,
    source: WaypointSequenceProposal,
    context: PlanningSearchContext,
) -> tuple[WaypointSequenceProposal, ...]:
    proposals: list[WaypointSequenceProposal] = []
    for leg_index, (start, end) in enumerate(
        zip(source.exact_points, source.exact_points[1:], strict=False)
    ):
        alternatives = await context.routes.alternative_routes(
            start,
            end,
            request.routing_profile,
            max_paths=3,
            max_weight_factor=2.0,
            max_share_factor=0.8,
            phase=SearchPhase.SKELETON,
        )
        for alternative_index, path in enumerate(alternatives[1:], start=1):
            via = _sample_via_points(path, start, end)
            if not via:
                continue
            proposals.append(
                _insert_after_exact(
                    source,
                    exact_index=leg_index,
                    via=via,
                    construction="open_alternative_detour",
                    provenance=f"alternative_leg:{leg_index}:{alternative_index}",
                )
            )
    return tuple(proposals)


def _sample_via_points(
    path: RoutedPath, *excluded: Coordinate
) -> tuple[Coordinate, ...]:
    if len(path.geometry) < 4:
        return ()
    excluded_keys = {(point.lat, point.lon) for point in excluded}
    indices = sorted(
        {multiplier * len(path.geometry) // 5 for multiplier in range(1, 5)}
    )
    sampled: list[Coordinate] = []
    for index in indices:
        lon, lat = path.geometry[index]
        point = Coordinate(lat=lat, lon=lon)
        if (lat, lon) in excluded_keys or point in sampled:
            continue
        sampled.append(point)
    return tuple(sampled)


def _insert_after_exact(
    source: WaypointSequenceProposal,
    *,
    exact_index: int,
    via: tuple[Coordinate, ...],
    construction: WaypointConstruction,
    provenance: str,
) -> WaypointSequenceProposal:
    insertion_position = source.exact_point_positions[exact_index] + 1
    points = (
        *source.routing_points[:insertion_position],
        *via,
        *source.routing_points[insertion_position:],
    )
    positions = tuple(
        position if position < insertion_position else position + len(via)
        for position in source.exact_point_positions
    )
    return WaypointSequenceProposal(
        routing_points=points,
        exact_points=source.exact_points,
        exact_point_positions=positions,
        original_indices=source.original_indices,
        topology=source.topology,
        construction=construction,
        order_provenance=source.order_provenance,
        detour_provenance=provenance,
    )
