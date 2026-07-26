"""Bounded alignment between analyzed spurs and routed leg geometry."""

from __future__ import annotations

from dataclasses import dataclass

from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.models import Coordinate
from sugarglider.planning.optimization.models import (
    OptimizationAnchor,
    SpurOptimizationTarget,
    TourOptimizationState,
)
from sugarglider.routing.backend import RoutedPath


@dataclass(frozen=True)
class LegSplice:
    """One exact source-leg vertex used for routing and reconstruction."""

    anchor: OptimizationAnchor
    geometry_index: int


def leg_splice(
    state: TourOptimizationState,
    target: SpurOptimizationTarget,
    *,
    anchor_id: str,
    coordinate: Coordinate,
    progress: float,
    maximum_distance_m: float,
) -> LegSplice | None:
    """Resolve an analyzed coordinate to a nearby vertex on its routed leg."""
    leg_index = target.containing_leg_start_index
    source_option = state.path_options[leg_index]
    left = state.anchors[leg_index]
    right = state.anchors[leg_index + 1]
    denominator = right.source_progress - left.source_progress
    if denominator <= 0:
        return None

    expected_share = (progress - left.source_progress) / denominator
    if not 0 <= expected_share <= 1:
        return None

    geometry = source_option.routed_path.geometry
    expected_index = expected_share * (len(geometry) - 1)
    requested = (coordinate.lon, coordinate.lat)
    eligible = tuple(
        (index, haversine_distance_m(position, requested))
        for index, position in enumerate(geometry)
        if haversine_distance_m(position, requested) <= maximum_distance_m
    )
    if not eligible:
        return None

    index, _distance = min(
        eligible,
        key=lambda value: (
            abs(value[0] - expected_index),
            value[1],
            value[0],
        ),
    )
    lon, lat = geometry[index]
    return LegSplice(
        anchor=_private_anchor(
            anchor_id,
            Coordinate(lat=lat, lon=lon),
            progress,
        ),
        geometry_index=index,
    )


def align_connector_endpoints(
    path: RoutedPath,
    start: tuple[float, float],
    end: tuple[float, float],
) -> RoutedPath | None:
    """Align sub-metre connector snaps with exact source-leg vertices."""
    maximum_alignment_m = 1.0
    if len(path.geometry) < 2 or (
        haversine_distance_m(path.geometry[0], start) > maximum_alignment_m
        or haversine_distance_m(path.geometry[-1], end) > maximum_alignment_m
    ):
        return None

    geometry = (start, *path.geometry[1:-1], end)
    return RoutedPath(
        distance_m=path.distance_m,
        duration_ms=path.duration_ms,
        ascend_m=path.ascend_m,
        descend_m=path.descend_m,
        geometry=geometry,
        snapped_points=(start, end),
        details=path.details,
    )


def _private_anchor(
    anchor_id: str,
    coordinate: Coordinate,
    progress: float,
) -> OptimizationAnchor:
    return OptimizationAnchor(
        id=anchor_id,
        name="Structural routing position",
        coordinate=coordinate,
        semantic_coordinate=coordinate,
        kind="fixed",
        source_progress=progress,
        exact_window=0,
    )
