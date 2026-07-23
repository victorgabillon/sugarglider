"""Deterministic downstream rejoin generation and source-anchor projection."""

from hashlib import sha256
from math import isclose

from shapely.geometry import Point

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.analysis import RouteSpur
from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.planning.refinement.models import (
    RejoinCandidate,
    RejoinSource,
    RepairAnchor,
    RepairAnchorKind,
    SpurClosureSettings,
)


def locate_repair_anchors(
    route: RouteResult,
    routing_points: tuple[Coordinate, ...],
    *,
    exact_coordinates: frozenset[tuple[float, float]] = frozenset(),
    deliberate_coordinates: frozenset[tuple[float, float]] = frozenset(),
) -> tuple[RepairAnchor, ...]:
    """Locate routing intent on authoritative route geometry in source order."""
    projection = LocalMetricProjection(route.geometry[0][1])
    line = projection.project_line(route.geometry)
    located: list[RepairAnchor] = []
    prior = 0.0
    for index, coordinate in enumerate(routing_points):
        point = Point(projection.project_position((coordinate.lon, coordinate.lat)))
        progress = float(line.project(point) / line.length) if line.length > 0 else 0.0
        if index == len(routing_points) - 1:
            progress = 1.0
        elif index == 0:
            progress = 0.0
        progress = max(prior, progress)
        key = (coordinate.lat, coordinate.lon)
        kind: RepairAnchorKind = (
            "exact"
            if key in exact_coordinates or index in {0, len(routing_points) - 1}
            else "deliberate"
            if key in deliberate_coordinates
            else "routing_hint"
        )
        located.append(
            RepairAnchor(
                id=f"routing-point-{index}",
                coordinate=coordinate,
                route_progress=progress,
                kind=kind,
            )
        )
        prior = progress
    return tuple(located)


def generate_rejoin_candidates(
    route: RouteResult,
    spur: RouteSpur,
    anchors: tuple[RepairAnchor, ...],
    *,
    topology: str,
    settings: SpurClosureSettings | None = None,
) -> tuple[RejoinCandidate, ...]:
    """Generate bounded downstream points without bypassing mandatory anchors."""
    resolved = settings or SpurClosureSettings()
    maximum_progress = 1.0
    boundary = next(
        (
            anchor
            for anchor in anchors
            if anchor.mandatory and anchor.route_progress > spur.end_progress + 1e-9
        ),
        None,
    )
    if boundary is not None:
        maximum_progress = boundary.route_progress
    samples: list[tuple[Coordinate, float, RejoinSource, float]] = []
    end_anchor = next(
        (
            anchor
            for anchor in anchors
            if anchor.mandatory
            and abs(anchor.route_progress - spur.end_progress) <= 1e-9
        ),
        None,
    )
    samples.append(
        (
            end_anchor.coordinate
            if end_anchor is not None
            else _coordinate(spur.end_coordinate),
            spur.end_progress,
            "first_after_spur",
            0.0,
        )
    )
    for distance_m in resolved.rejoin_distances_m:
        target_m = spur.end_progress * route.summary.distance_m + distance_m
        progress = (
            target_m / route.summary.distance_m if route.summary.distance_m > 0 else 1.0
        )
        if progress >= maximum_progress - 1e-9 or progress >= 1.0 - 1e-9:
            continue
        samples.append(
            (
                _coordinate_at_distance(route, target_m),
                progress,
                "distance_sample",
                distance_m,
            )
        )
    for anchor in anchors:
        if (
            anchor.route_progress <= spur.end_progress + 1e-9
            or anchor.route_progress > maximum_progress + 1e-9
        ):
            continue
        source: RejoinSource = (
            "deliberate_anchor" if anchor.mandatory else "routing_point"
        )
        samples.append(
            (
                anchor.coordinate,
                anchor.route_progress,
                source,
                (anchor.route_progress - spur.end_progress) * route.summary.distance_m,
            )
        )
    if boundary is not None:
        samples.append(
            (
                boundary.coordinate,
                boundary.route_progress,
                "deliberate_anchor",
                (boundary.route_progress - spur.end_progress)
                * route.summary.distance_m,
            )
        )
    ordered = sorted(
        samples,
        key=lambda value: (value[1], value[2], value[0].lat, value[0].lon),
    )
    retained: list[RejoinCandidate] = []
    for coordinate, progress, source, distance_m in ordered:
        if topology == "loop" and progress >= 1.0 - 1e-9:
            continue
        if progress < spur.end_progress - 1e-9:
            continue
        if any(
            haversine_distance_m(
                (coordinate.lon, coordinate.lat),
                (prior.coordinate.lon, prior.coordinate.lat),
            )
            < 50.0
            for prior in retained
        ):
            continue
        stable = sha256(
            f"{spur.id}:{progress:.9f}:{coordinate.lat:.7f}:{coordinate.lon:.7f}".encode()
        ).hexdigest()[:16]
        retained.append(
            RejoinCandidate(
                coordinate=coordinate,
                source_progress=min(1.0, max(0.0, progress)),
                source_kind=source,
                distance_after_spur_m=max(0.0, distance_m),
                stable_id=f"rejoin-{stable}",
            )
        )
        if len(retained) == resolved.maximum_rejoins_per_spur:
            break
    return tuple(retained)


def _coordinate(position: tuple[float, float]) -> Coordinate:
    return Coordinate(lon=position[0], lat=position[1])


def _coordinate_at_distance(route: RouteResult, target_m: float) -> Coordinate:
    if target_m <= 0:
        return _coordinate(route.geometry[0])
    raw_lengths = tuple(
        haversine_distance_m(left, right)
        for left, right in zip(route.geometry, route.geometry[1:], strict=False)
    )
    raw_total = sum(raw_lengths)
    if raw_total <= 0 or route.summary.distance_m <= 0:
        return _coordinate(route.geometry[-1])
    target_raw = min(raw_total, target_m * raw_total / route.summary.distance_m)
    prefix = 0.0
    for left, right, length in zip(
        route.geometry, route.geometry[1:], raw_lengths, strict=True
    ):
        if prefix + length < target_raw and not isclose(prefix + length, target_raw):
            prefix += length
            continue
        share = 0.0 if length <= 0 else (target_raw - prefix) / length
        return Coordinate(
            lon=left[0] + (right[0] - left[0]) * share,
            lat=left[1] + (right[1] - left[1]) * share,
        )
    return _coordinate(route.geometry[-1])
