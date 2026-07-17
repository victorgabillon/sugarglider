"""Pure composition of contiguous routed GraphHopper leg paths."""

from collections.abc import Mapping

from sugarglider.domain.models import PathDetailSegment
from sugarglider.routing.backend import RoutedPath


class RouteCompositionError(ValueError):
    """Routed leg paths cannot form one continuous route."""


def compose_routed_segments(segments: tuple[RoutedPath, ...]) -> RoutedPath:
    """Compose contiguous routed legs without inventing join geometry."""
    if not segments:
        raise RouteCompositionError("at least one routed segment is required")

    geometry = list(segments[0].geometry)
    if len(geometry) < 2:
        raise RouteCompositionError("every routed segment needs two geometry points")
    snapped = _snapped_endpoints(segments[0])
    _validate_snapped_geometry(segments[0], snapped)
    snapped_points = [snapped[0], snapped[1]]
    detail_segments: dict[str, list[PathDetailSegment]] = {}
    _append_details(
        detail_segments,
        segments[0].details,
        offset=0,
        geometry_length=len(segments[0].geometry),
    )

    for segment in segments[1:]:
        if len(segment.geometry) < 2:
            raise RouteCompositionError(
                "every routed segment needs two geometry points"
            )
        segment_snapped = _snapped_endpoints(segment)
        _validate_snapped_geometry(segment, segment_snapped)
        if geometry[-1] != segment.geometry[0]:
            raise RouteCompositionError("routed segment geometry is discontinuous")
        if snapped_points[-1] != segment_snapped[0]:
            raise RouteCompositionError(
                "routed segment snapped endpoints are discontinuous"
            )
        offset = len(geometry) - 1
        geometry.extend(segment.geometry[1:])
        snapped_points.append(segment_snapped[1])
        _append_details(
            detail_segments,
            segment.details,
            offset=offset,
            geometry_length=len(segment.geometry),
        )

    return RoutedPath(
        distance_m=sum(segment.distance_m for segment in segments),
        duration_ms=sum(segment.duration_ms for segment in segments),
        ascend_m=_optional_sum(tuple(segment.ascend_m for segment in segments)),
        descend_m=_optional_sum(tuple(segment.descend_m for segment in segments)),
        geometry=tuple(geometry),
        snapped_points=tuple(snapped_points),
        details={
            detail: _merge_adjacent(tuple(values))
            for detail, values in sorted(detail_segments.items())
        },
    )


def _snapped_endpoints(segment: RoutedPath) -> tuple[tuple[float, float], ...]:
    snapped = segment.snapped_points
    if snapped is None or len(snapped) != 2:
        raise RouteCompositionError(
            "every routed segment needs exactly two snapped endpoints"
        )
    return snapped


def _validate_snapped_geometry(
    segment: RoutedPath, snapped: tuple[tuple[float, float], ...]
) -> None:
    if segment.geometry[0] != snapped[0] or segment.geometry[-1] != snapped[-1]:
        raise RouteCompositionError(
            "routed segment snapped endpoints do not match geometry"
        )


def _append_details(
    destination: dict[str, list[PathDetailSegment]],
    details: Mapping[str, tuple[PathDetailSegment, ...]],
    *,
    offset: int,
    geometry_length: int,
) -> None:
    for detail, segments in sorted(details.items()):
        target = destination.setdefault(detail, [])
        previous_local_to = -1
        for segment in segments:
            if (
                segment.to_index >= geometry_length
                or segment.from_index < previous_local_to
            ):
                raise RouteCompositionError("routed segment path details are malformed")
            shifted = PathDetailSegment(
                from_index=segment.from_index + offset,
                to_index=segment.to_index + offset,
                value=segment.value,
            )
            if target and shifted.from_index < target[-1].to_index:
                raise RouteCompositionError("shifted path-detail intervals overlap")
            target.append(shifted)
            previous_local_to = segment.to_index


def _merge_adjacent(
    segments: tuple[PathDetailSegment, ...],
) -> tuple[PathDetailSegment, ...]:
    merged: list[PathDetailSegment] = []
    for segment in segments:
        if (
            merged
            and merged[-1].to_index == segment.from_index
            and merged[-1].value == segment.value
            and type(merged[-1].value) is type(segment.value)
        ):
            previous = merged[-1]
            merged[-1] = PathDetailSegment(
                from_index=previous.from_index,
                to_index=segment.to_index,
                value=previous.value,
            )
        else:
            merged.append(segment)
    return tuple(merged)


def _optional_sum(values: tuple[float | None, ...]) -> float | None:
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)
