"""Bounded PR19 spur targets and downstream rejoin positions."""

from __future__ import annotations

from hashlib import sha256

from sugarglider.analysis.route import (
    canonical_edge_traversals,
    haversine_distance_m,
    known_edge_id,
    project_geometry_edges,
)
from sugarglider.analysis.spurs import spur_repair_priority
from sugarglider.domain.models import Coordinate
from sugarglider.planning.optimization.models import (
    GlobalOptimizationSettings,
    OptimizationSource,
    RejoinPosition,
    SpurOptimizationTarget,
)

_EPSILON = 1e-9


def optimization_targets(
    source: OptimizationSource,
    settings: GlobalOptimizationSettings,
) -> tuple[SpurOptimizationTarget, ...]:
    """Build bounded targets from the final PR19 spur evidence."""
    if len(source.anchors) < 2:
        return ()
    projection = project_geometry_edges(
        geometry=source.route.geometry,
        route_distance_m=source.route.summary.distance_m,
        path_details=source.route.path_details,
    )
    prefixes = _edge_prefix(tuple(edge.distance_m for edge in projection.edges))
    targets: list[SpurOptimizationTarget] = []
    for spur in sorted(source.route.analysis.spurs.spurs, key=spur_repair_priority):
        if (
            spur.confidence == "low"
            or spur.repeated_distance_m < settings.minimum_structural_improvement_m
            or "near_route_endpoint" in spur.reason_codes
        ):
            continue
        containing_leg = next(
            (
                index
                for index, (left, right) in enumerate(
                    zip(source.anchors, source.anchors[1:], strict=False)
                )
                if left.source_progress - _EPSILON
                <= spur.turnaround_progress
                < right.source_progress - _EPSILON
            ),
            None,
        )
        if containing_leg is None:
            continue
        right = source.anchors[containing_leg + 1]
        if spur.end_progress > right.source_progress + _EPSILON:
            continue
        if any(
            spur.turnaround_progress + _EPSILON
            < anchor.source_progress
            < spur.end_progress - _EPSILON
            for anchor in source.anchors
        ):
            continue
        start_m = spur.start_progress * source.route.summary.distance_m
        turnaround_m = spur.turnaround_progress * source.route.summary.distance_m
        inbound = tuple(
            edge
            for index, edge in enumerate(projection.edges)
            if prefixes[index] < turnaround_m and prefixes[index + 1] > start_m
        )
        inbound_keys = frozenset(
            edge_id for edge in inbound if (edge_id := known_edge_id(edge)) is not None
        )
        inbound_distance = sum(
            edge.distance_m for edge in inbound if known_edge_id(edge) is not None
        )
        inbound_traversals = canonical_edge_traversals(inbound)
        inbound_geometry = (
            (inbound[0].start, *(edge.end for edge in inbound)) if inbound else ()
        )
        if not inbound_keys or inbound_distance <= 0:
            continue
        stable = sha256(
            f"{source.source_candidate_id}:{spur.id}:"
            f"{spur.turnaround_progress:.9f}".encode()
        ).hexdigest()[:16]
        targets.append(
            SpurOptimizationTarget(
                source_candidate_id=source.source_candidate_id,
                spur_id=spur.id,
                stop_ids=spur.deliberate_stop_ids,
                stop_names=spur.deliberate_stop_names,
                start_progress=spur.start_progress,
                turnaround_progress=spur.turnaround_progress,
                end_progress=spur.end_progress,
                turnaround_coordinate=_coordinate(spur.turnaround_coordinate),
                original_rejoin_coordinate=_coordinate(spur.end_coordinate),
                repeated_distance_m=spur.repeated_distance_m,
                inbound_edge_keys=inbound_keys,
                inbound_traversals=inbound_traversals,
                inbound_geometry=inbound_geometry,
                inbound_distance_m=inbound_distance,
                containing_leg_start_index=containing_leg,
                containing_leg_end_index=containing_leg,
                next_mandatory_progress=right.source_progress,
                stable_id=f"spur-target/{stable}",
            )
        )
        if len(targets) == settings.maximum_spurs_per_source:
            break
    return tuple(targets)


def downstream_rejoins(
    source: OptimizationSource,
    target: SpurOptimizationTarget,
    settings: GlobalOptimizationSettings,
) -> tuple[RejoinPosition, ...]:
    """Generate genuine downstream graph positions before the semantic boundary."""
    route_distance = source.route.summary.distance_m
    projection = project_geometry_edges(
        geometry=source.route.geometry,
        route_distance_m=route_distance,
        path_details=source.route.path_details,
    )
    prefixes = _edge_prefix(tuple(edge.distance_m for edge in projection.edges))
    positions = tuple(
        (
            Coordinate(lon=edge.end[0], lat=edge.end[1]),
            prefixes[index + 1] / route_distance if route_distance > 0 else 0.0,
        )
        for index, edge in enumerate(projection.edges)
    )
    samples: list[tuple[Coordinate, float, str, float]] = []

    def sample_at_or_after(
        progress: float, source_kind: str, distance_after_m: float
    ) -> None:
        selected = next(
            (
                value
                for value in positions
                if value[1] >= progress - _EPSILON
                and value[1] > target.end_progress + _EPSILON
                and value[1] <= target.next_mandatory_progress + _EPSILON
            ),
            None,
        )
        if selected is not None:
            samples.append((*selected, source_kind, distance_after_m))

    first = next(
        (
            value
            for value in positions
            if value[1] > target.end_progress + _EPSILON
            and value[1] <= target.next_mandatory_progress + _EPSILON
        ),
        None,
    )
    if first is not None:
        samples.append(
            (
                first[0],
                first[1],
                "first_after_spur",
                max(0.0, (first[1] - target.end_progress) * route_distance),
            )
        )
    for distance_m in settings.rejoin_distances_m:
        progress = (
            target.end_progress + distance_m / route_distance
            if route_distance > 0
            else 1.0
        )
        sample_at_or_after(progress, "distance_sample", distance_m)
    for anchor in source.anchors:
        if (
            anchor.source_progress > target.end_progress + _EPSILON
            and anchor.source_progress <= target.next_mandatory_progress + _EPSILON
        ):
            samples.append(
                (
                    anchor.coordinate,
                    anchor.source_progress,
                    (
                        "mandatory_boundary"
                        if anchor.source_progress == target.next_mandatory_progress
                        else "semantic_anchor"
                    ),
                    (anchor.source_progress - target.end_progress) * route_distance,
                )
            )
    ordered = sorted(
        samples, key=lambda value: (value[1], value[2], value[0].lat, value[0].lon)
    )
    retained: list[RejoinPosition] = []
    for coordinate, progress, source_kind, distance_m in ordered:
        if source.topology == "loop" and progress >= 1.0 - _EPSILON:
            continue
        if any(
            abs(progress - prior.source_progress) <= _EPSILON
            or haversine_distance_m(
                (coordinate.lon, coordinate.lat),
                (prior.coordinate.lon, prior.coordinate.lat),
            )
            < 50.0
            for prior in retained
        ):
            continue
        stable = sha256(
            f"{target.stable_id}:{progress:.9f}:"
            f"{coordinate.lat:.7f}:{coordinate.lon:.7f}".encode()
        ).hexdigest()[:16]
        retained.append(
            RejoinPosition(
                coordinate=coordinate,
                source_progress=progress,
                source_kind=source_kind,  # type: ignore[arg-type]
                distance_after_spur_m=max(0.0, distance_m),
                stable_id=f"rejoin/{stable}",
            )
        )
        if len(retained) == settings.maximum_spur_rejoin_positions:
            break
    return tuple(retained)


def _edge_prefix(distances: tuple[float, ...]) -> tuple[float, ...]:
    values = [0.0]
    for distance in distances:
        values.append(values[-1] + distance)
    return tuple(values)


def _coordinate(value: tuple[float, float]) -> Coordinate:
    return Coordinate(lon=value[0], lat=value[1])
