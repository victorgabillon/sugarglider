#!/usr/bin/env python3
"""Optional synthetic benchmark for the edge-aware global optimizer."""

from __future__ import annotations

import argparse
import asyncio
import json
from hashlib import sha256
from time import perf_counter
from typing import cast

from sugarglider.domain.models import Coordinate, PathDetailSegment
from sugarglider.planning.budget import SearchBudget, SearchPhase
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.optimization import (
    GlobalOptimizationDiagnostics,
    OptimizationAnchor,
    OptimizationSource,
    optimize_tours,
)
from sugarglider.planning.optimization.objective import edge_reuse_components
from sugarglider.routing.backend import AutoTourRoutingBackend, RoutedPath
from sugarglider.routing.composition import compose_routed_segments
from sugarglider.routing.result import RouteResultFactory


def _path(
    geometry: tuple[tuple[float, float], ...],
    edge_ids: tuple[int, ...],
    *,
    distance_m: float,
    snapped: tuple[tuple[float, float], tuple[float, float]],
) -> RoutedPath:
    return RoutedPath(
        distance_m=distance_m,
        duration_ms=max(1, round(distance_m)),
        ascend_m=None,
        descend_m=None,
        geometry=geometry,
        snapped_points=snapped,
        details={
            "edge_id": tuple(
                PathDetailSegment(
                    from_index=index,
                    to_index=index + 1,
                    value=edge_id,
                )
                for index, edge_id in enumerate(edge_ids)
            )
        },
    )


class _SyntheticBackend:
    async def alternative_routes(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: str = "hike",
        *,
        max_paths: int = 3,
        max_weight_factor: float = 1.6,
        max_share_factor: float = 0.5,
    ) -> tuple[RoutedPath, ...]:
        del profile, max_weight_factor, max_share_factor
        start_position = (start.lon, start.lat)
        end_position = (end.lon, end.lat)
        edge_id = int.from_bytes(
            sha256(repr((start_position, end_position)).encode()).digest()[:4],
            "big",
        )
        shortest = _path(
            (start_position, end_position),
            (edge_id,),
            distance_m=1_000,
            snapped=(start_position, end_position),
        )
        return (shortest,)[:max_paths]


def _source(stop_count: int) -> OptimizationSource:
    coordinates = tuple(
        Coordinate(
            lat=0.01 * (index // 5),
            lon=0.01 * (index % 5),
            name=f"Stop {index + 1}",
        )
        for index in range(stop_count)
    )
    first = coordinates[0]
    second = coordinates[1]
    turn = (first.lon + 0.01, first.lat + 0.01)
    tip = (first.lon + 0.02, first.lat + 0.01)
    first_leg = _path(
        ((first.lon, first.lat), turn, tip, turn, (second.lon, second.lat)),
        (1, 2, 2, 3),
        distance_m=3_000,
        snapped=((first.lon, first.lat), (second.lon, second.lat)),
    )
    remaining = tuple(
        _path(
            ((left.lon, left.lat), (right.lon, right.lat)),
            (100 + index,),
            distance_m=1_000,
            snapped=((left.lon, left.lat), (right.lon, right.lat)),
        )
        for index, (left, right) in enumerate(
            zip(coordinates[1:], coordinates[2:], strict=False)
        )
    )
    routed = compose_routed_segments((first_leg, *remaining))
    anchors = tuple(
        OptimizationAnchor(
            id=f"stop/{index}",
            name=coordinate.name or f"Stop {index + 1}",
            coordinate=coordinate,
            semantic_coordinate=coordinate,
            kind="exact" if index in {0, len(coordinates) - 1} else "fixed",
            source_progress=index / (len(coordinates) - 1),
            exact_window=int(index == len(coordinates) - 1),
        )
        for index, coordinate in enumerate(coordinates)
    )
    result_factory = RouteResultFactory()
    return OptimizationSource(
        source_candidate_id="synthetic/control",
        route=result_factory.create(
            name="Synthetic optimizer benchmark",
            path=routed,
            input_point_count=len(anchors),
            routing_profile="hike",
        ),
        routed_path=routed,
        anchors=anchors,
        topology="point_to_point",
        routing_profile="hike",
        target_distance_m=routed.distance_m,
        tolerance_m=10_000,
        distance_priority="flexible",
        maximum_distance_m=None,
        reached_requested_ids=frozenset(),
        approximated_requested_ids=frozenset(),
        dropped_requested_ids=frozenset(),
    )


async def _run(stop_count: int, seed: int) -> dict[str, object]:
    source = _source(stop_count)
    limits = {phase: 0 for phase in SearchPhase}
    limits[SearchPhase.GLOBAL_OPTIMIZATION] = 64
    context = PlanningSearchContext.create(
        backend=cast(AutoTourRoutingBackend, _SyntheticBackend()),
        budget=SearchBudget(limits, total_limit=64),
    )
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    started = perf_counter()
    result = await optimize_tours(
        (source,),
        context=context,
        result_factory=RouteResultFactory(),
        seed=seed,
        diagnostics=diagnostics,
    )
    elapsed_ms = (perf_counter() - started) * 1_000
    initial = edge_reuse_components(source.routed_path)
    best = (
        min(
            result.drafts,
            key=lambda draft: (
                draft.resulting_objective.lexicographic_key(),
                draft.stable_signature,
            ),
        )
        if result.drafts
        else None
    )
    final_objective = (
        best.resulting_objective
        if best is not None
        else next(
            (
                draft.source_objective
                for draft in result.drafts
                if draft.source_candidate_id == source.source_candidate_id
            ),
            None,
        )
    )
    final_repetition = (
        final_objective.total_repeated_distance_m
        if final_objective is not None
        else initial.total_repeated_distance_m
    )
    final_backtracking = (
        final_objective.immediate_backtracking_m
        if final_objective is not None
        else initial.immediate_return_distance_m
    )
    return {
        "stop_count": stop_count,
        "initial_route_quality": {
            "opposite_direction_reuse_m": initial.opposite_direction_reuse_m,
            "repeated_distance_m": initial.total_repeated_distance_m,
            "immediate_backtracking_m": initial.immediate_return_distance_m,
        },
        "final_route_quality": {
            "opposite_direction_reuse_m": (
                final_objective.opposite_direction_reuse_m
                if final_objective is not None
                else initial.opposite_direction_reuse_m
            ),
            "repeated_distance_m": final_repetition,
            "immediate_backtracking_m": final_backtracking,
        },
        "path_requests": diagnostics.lazy_path_requests,
        "cache_hits": diagnostics.graphhopper_cache_hits,
        "iterations": diagnostics.iterations,
        "complete_evaluations": len(result.drafts),
        "repetition_change_m": final_repetition - initial.total_repeated_distance_m,
        "backtracking_change_m": final_backtracking
        - initial.immediate_return_distance_m,
        "total_wall_time_ms": elapsed_ms,
        "routing_wait_time_ms": diagnostics.routing_wait_time_ms,
        "optimizer_cpu_time_ms": diagnostics.optimization_cpu_time_ms,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stops", type=int, default=24, choices=range(2, 51))
    parser.add_argument("--seed", type=int, default=42)
    arguments = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(_run(arguments.stops, arguments.seed)),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
