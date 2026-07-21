"""Attribute exact edge-ID out-and-back groups to selected POI approaches."""

from dataclasses import dataclass

from sugarglider.analysis.backtracking import (
    MAX_BACKTRACK_SPUR_EDGES,
    DirectedEdgeTraversal,
    classify_immediate_backtracking,
)
from sugarglider.analysis.route import known_edge_id, project_geometry_edges
from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.planning.auto_tour.models import (
    PoiExcursion,
    SelectedPoiStop,
    poi_excursion_penalty_m,
)


@dataclass(frozen=True)
class PoiExcursionAnalysis:
    excursions: tuple[PoiExcursion, ...]
    selected_stops: tuple[SelectedPoiStop, ...]
    attributed_immediate_backtracking_m: float
    non_poi_backtracking_m: float


def analyze_poi_excursions(
    route: RouteResult,
    selected_stops: tuple[SelectedPoiStop, ...],
    *,
    free_physical_spur_allowance_m: float,
) -> PoiExcursionAnalysis:
    """Build bounded shared excursions from the same exact backtracking semantics."""
    if not selected_stops or not any(
        stop.deliberately_inserted for stop in selected_stops
    ):
        return PoiExcursionAnalysis(
            (),
            selected_stops,
            0.0,
            route.analysis.immediate_backtrack.distance_m,
        )
    projection = project_geometry_edges(
        geometry=route.geometry,
        route_distance_m=route.summary.distance_m,
        path_details=route.path_details,
    )
    edges = projection.edges
    traversals = tuple(
        DirectedEdgeTraversal(
            edge_id=known_edge_id(edge),
            start=edge.start,
            end=edge.end,
            distance_m=edge.distance_m,
        )
        for edge in edges
    )
    returning = classify_immediate_backtracking(traversals)
    cumulative = [0.0]
    for edge in edges:
        cumulative.append(cumulative[-1] + edge.distance_m)
    route_distance = route.summary.distance_m
    unassigned = {
        stop.semantic_poi.id: stop
        for stop in selected_stops
        if stop.deliberately_inserted
    }
    excursions: list[PoiExcursion] = []
    assigned_excursion: dict[str, str] = {}
    for group_index, (start, end) in enumerate(_true_groups(returning), start=1):
        return_distance = sum(edge.distance_m for edge in edges[start:end])
        if return_distance <= 0:
            continue
        entry_distance = max(0.0, cumulative[start] - return_distance)
        exit_distance = cumulative[end]
        served = tuple(
            sorted(
                poi_id
                for poi_id, stop in unassigned.items()
                if entry_distance - 1e-6
                <= stop.route_progress_share * route_distance
                <= exit_distance + 1e-6
            )
        )
        if not served:
            continue
        excursion_id = f"poi-excursion/{group_index}"
        outward_distance = return_distance
        physical_distance = outward_distance + return_distance
        group_edge_count = end - start
        verified = (
            group_edge_count < MAX_BACKTRACK_SPUR_EDGES
            and not any(traversal.edge_id is None for traversal in traversals)
            and start >= group_edge_count
            and all(
                traversals[start - offset - 1].edge_id
                == traversals[start + offset].edge_id
                for offset in range(group_edge_count)
            )
        )
        effective_allowance = free_physical_spur_allowance_m if verified else 0.0
        excess = max(0.0, physical_distance - effective_allowance)
        warnings = tuple(
            sorted(
                {
                    warning
                    for threshold, warning in (
                        (800.0, "long_poi_excursion"),
                        (2_000.0, "severe_poi_excursion"),
                    )
                    if physical_distance > threshold
                }
                | ({"poi_excursion_unverified"} if not verified else set())
            )
        )
        anchor_position = edges[end - 1].end
        anchor = Coordinate(lat=anchor_position[1], lon=anchor_position[0])
        excursions.append(
            PoiExcursion(
                id=excursion_id,
                entry_anchor=anchor,
                exit_anchor=anchor,
                selected_poi_ids=served,
                outward_distance_m=outward_distance,
                returning_backtrack_distance_m=return_distance,
                physical_spur_distance_m=physical_distance,
                free_physical_spur_allowance_m=effective_allowance,
                penalized_physical_spur_distance_m=excess,
                verified=verified,
                penalty_m_equivalent=poi_excursion_penalty_m(
                    physical_distance, effective_allowance
                ),
                through_route=False,
                warnings=warnings,
            )
        )
        for poi_id in served:
            assigned_excursion[poi_id] = excursion_id
            unassigned.pop(poi_id, None)
    updated_stops = tuple(
        stop.model_copy(
            update={"excursion_id": assigned_excursion.get(stop.semantic_poi.id)}
        )
        for stop in selected_stops
    )
    attributed = sum(
        excursion.returning_backtrack_distance_m for excursion in excursions
    )
    total = route.analysis.immediate_backtrack.distance_m
    return PoiExcursionAnalysis(
        tuple(excursions),
        updated_stops,
        min(total, attributed),
        max(0.0, total - attributed),
    )


def _true_groups(values: tuple[bool, ...]) -> tuple[tuple[int, int], ...]:
    groups: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate((*values, False)):
        if value and start is None:
            start = index
        elif not value and start is not None:
            groups.append((start, index))
            start = None
    return tuple(groups)
