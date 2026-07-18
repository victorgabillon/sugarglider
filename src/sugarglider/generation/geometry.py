"""Pure routed-proposal sampling and ordered waypoint insertion helpers."""

from dataclasses import dataclass
from itertools import pairwise
from math import atan2, hypot, pi
from typing import Literal

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.generation import CandidateConstruction
from sugarglider.domain.models import Coordinate, GeoJsonPosition

SAMPLE_FRACTIONS = (0.25, 0.50, 0.75)
BALANCED_SAMPLE_FRACTIONS = tuple(index / 12 for index in range(1, 12))
MIN_OPTIONAL_POINT_SEPARATION_M = 50.0
GLOBAL_SECTOR_COUNT = 8

ProposalVariant = Literal["balanced_forward", "balanced_reverse", "legacy"]


@dataclass(frozen=True)
class ProposalPointSequence:
    """One deterministic sequence derived from one GraphHopper proposal path."""

    optional_points: tuple[Coordinate, ...]
    variant: ProposalVariant
    construction: CandidateConstruction


@dataclass(frozen=True)
class _SampledProposalPosition:
    position: GeoJsonPosition
    fraction: float
    radius_m: float
    sector: int


def sample_optional_points(
    geometry: tuple[GeoJsonPosition, ...],
    start: Coordinate,
    *,
    minimum_separation_m: float = MIN_OPTIONAL_POINT_SEPARATION_M,
) -> tuple[Coordinate, ...]:
    """Sample proposal positions at cumulative, rather than array-index, fractions."""
    if len(geometry) < 2:
        return ()
    sampled = _sample_filtered_positions(
        geometry,
        start,
        SAMPLE_FRACTIONS,
        minimum_separation_m=minimum_separation_m,
    )

    return tuple(
        Coordinate(lat=lat, lon=lon, name=f"Generated detour {index}")
        for index, (lon, lat) in enumerate(sampled, start=1)
    )


def proposal_point_sequences(
    geometry: tuple[GeoJsonPosition, ...],
    anchor: Coordinate,
    global_start: Coordinate,
    *,
    prefer_balanced: bool,
    include_legacy_control: bool = True,
    variant: ProposalVariant | None = None,
    minimum_separation_m: float = MIN_OPTIONAL_POINT_SEPARATION_M,
) -> tuple[ProposalPointSequence, ...]:
    """Derive bounded forward/reverse/control sequences from one routed proposal."""
    if not prefer_balanced:
        legacy = sample_optional_points(
            geometry, anchor, minimum_separation_m=minimum_separation_m
        )
        return (
            (ProposalPointSequence(legacy, "legacy", "round_trip_detour"),)
            if legacy
            else ()
        )

    balanced = _balanced_optional_points(
        geometry,
        anchor,
        global_start,
        minimum_separation_m=minimum_separation_m,
    )
    legacy = sample_optional_points(
        geometry, anchor, minimum_separation_m=minimum_separation_m
    )
    requested = (
        tuple(
            sequence
            for sequence in (
                ProposalPointSequence(
                    balanced, "balanced_forward", "sector_balanced_detour"
                ),
                ProposalPointSequence(
                    _renamed(tuple(reversed(balanced))),
                    "balanced_reverse",
                    "sector_balanced_detour",
                ),
                ProposalPointSequence(legacy, "legacy", "round_trip_detour"),
            )
            if include_legacy_control or sequence.variant != "legacy"
        )
        if variant is None
        else (_variant_sequence(variant, balanced=balanced, legacy=legacy),)
    )
    distinct: list[ProposalPointSequence] = []
    keys: set[tuple[tuple[float, float], ...]] = set()
    for sequence in requested:
        if not sequence.optional_points:
            continue
        key = point_sequence_key(sequence.optional_points)
        if key in keys:
            continue
        keys.add(key)
        distinct.append(sequence)
    return tuple(distinct)


def _variant_sequence(
    variant: ProposalVariant,
    *,
    balanced: tuple[Coordinate, ...],
    legacy: tuple[Coordinate, ...],
) -> ProposalPointSequence:
    if variant == "balanced_forward":
        return ProposalPointSequence(balanced, variant, "sector_balanced_detour")
    if variant == "balanced_reverse":
        return ProposalPointSequence(
            _renamed(tuple(reversed(balanced))),
            variant,
            "sector_balanced_detour",
        )
    return ProposalPointSequence(legacy, variant, "round_trip_detour")


def _balanced_optional_points(
    geometry: tuple[GeoJsonPosition, ...],
    anchor: Coordinate,
    global_start: Coordinate,
    *,
    minimum_separation_m: float,
) -> tuple[Coordinate, ...]:
    fraction_positions = _sample_filtered_fraction_positions(
        geometry,
        anchor,
        BALANCED_SAMPLE_FRACTIONS,
        minimum_separation_m=minimum_separation_m,
    )
    projection = LocalMetricProjection(global_start.lat)
    metric_start = projection.project_position((global_start.lon, global_start.lat))
    candidates: list[_SampledProposalPosition] = []
    for fraction, position in fraction_positions:
        metric = projection.project_position(position)
        dx = metric[0] - metric_start[0]
        dy = metric[1] - metric_start[1]
        angle = atan2(dy, dx) % (2 * pi)
        candidates.append(
            _SampledProposalPosition(
                position=position,
                fraction=fraction,
                radius_m=hypot(dx, dy),
                sector=min(
                    GLOBAL_SECTOR_COUNT - 1,
                    int(angle / (2 * pi / GLOBAL_SECTOR_COUNT)),
                ),
            )
        )
    selected: list[_SampledProposalPosition] = []
    while candidates and len(selected) < 3:
        if not selected:
            chosen = max(candidates, key=lambda item: (item.radius_m, -item.fraction))
        else:
            sectors = tuple(item.sector for item in selected)
            chosen = max(
                candidates,
                key=lambda item: (
                    item.sector not in sectors,
                    min(
                        _circular_sector_distance(item.sector, other)
                        for other in sectors
                    ),
                    item.radius_m,
                    -item.fraction,
                ),
            )
        selected.append(chosen)
        candidates.remove(chosen)
    ordered = sorted(selected, key=lambda item: item.fraction)
    return tuple(
        Coordinate(
            lat=item.position[1], lon=item.position[0], name=f"Generated detour {index}"
        )
        for index, item in enumerate(ordered, start=1)
    )


def _sample_filtered_positions(
    geometry: tuple[GeoJsonPosition, ...],
    start: Coordinate,
    fractions: tuple[float, ...],
    *,
    minimum_separation_m: float,
) -> tuple[GeoJsonPosition, ...]:
    return tuple(
        position
        for _fraction, position in _sample_filtered_fraction_positions(
            geometry,
            start,
            fractions,
            minimum_separation_m=minimum_separation_m,
        )
    )


def _sample_filtered_fraction_positions(
    geometry: tuple[GeoJsonPosition, ...],
    start: Coordinate,
    fractions: tuple[float, ...],
    *,
    minimum_separation_m: float,
) -> tuple[tuple[float, GeoJsonPosition], ...]:
    if len(geometry) < 2:
        return ()
    lengths = tuple(
        haversine_distance_m(left, right) for left, right in pairwise(geometry)
    )
    total_distance = sum(lengths)
    if total_distance <= 0:
        return ()
    start_position = (start.lon, start.lat)
    sampled: list[tuple[float, GeoJsonPosition]] = []
    for fraction in fractions:
        position = _interpolate_position(geometry, lengths, total_distance * fraction)
        if position is None:
            continue
        if haversine_distance_m(start_position, position) < minimum_separation_m:
            continue
        if any(
            haversine_distance_m(existing, position) < minimum_separation_m
            for _existing_fraction, existing in sampled
        ):
            continue
        if (
            position == geometry[-1]
            and haversine_distance_m(geometry[-1], start_position)
            < minimum_separation_m
        ):
            continue
        sampled.append((fraction, position))
    return tuple(sampled)


def _interpolate_position(
    geometry: tuple[GeoJsonPosition, ...],
    lengths: tuple[float, ...],
    target_distance: float,
) -> GeoJsonPosition | None:
    traversed = 0.0
    for index, segment_distance in enumerate(lengths):
        next_distance = traversed + segment_distance
        if next_distance >= target_distance and segment_distance > 0:
            ratio = (target_distance - traversed) / segment_distance
            start_lon, start_lat = geometry[index]
            end_lon, end_lat = geometry[index + 1]
            return (
                start_lon + (end_lon - start_lon) * ratio,
                start_lat + (end_lat - start_lat) * ratio,
            )
        traversed = next_distance
    return None


def _circular_sector_distance(left: int, right: int) -> int:
    difference = abs(left - right)
    return min(difference, GLOBAL_SECTOR_COUNT - difference)


def _renamed(points: tuple[Coordinate, ...]) -> tuple[Coordinate, ...]:
    return tuple(
        point.model_copy(update={"name": f"Generated detour {index}"})
        for index, point in enumerate(points, start=1)
    )


def insert_optional_points(
    required_points: tuple[Coordinate, ...],
    insertion_index: int,
    optional_points: tuple[Coordinate, ...],
) -> tuple[Coordinate, ...]:
    """Insert optional points after one anchor without changing required order."""
    if insertion_index < 0 or insertion_index >= len(required_points) - 1:
        raise ValueError("optional-point insertion index is outside the closed route")
    return (
        *required_points[: insertion_index + 1],
        *optional_points,
        *required_points[insertion_index + 1 :],
    )


def point_sequence_key(
    points: tuple[Coordinate, ...],
) -> tuple[tuple[float, float], ...]:
    """Return an exact deterministic cache key without point names."""
    return tuple((point.lat, point.lon) for point in points)
