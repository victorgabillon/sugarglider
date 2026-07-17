"""Pure routed-leg composition tests."""

from collections.abc import Mapping

import pytest

from sugarglider.domain.models import GeoJsonPosition, PathDetailSegment
from sugarglider.routing.backend import RoutedPath
from sugarglider.routing.composition import (
    RouteCompositionError,
    compose_routed_segments,
)


def leg(
    geometry: tuple[GeoJsonPosition, ...],
    *,
    distance: float = 100.0,
    duration: int = 10,
    ascend: float | None = 2.0,
    descend: float | None = 1.0,
    details: Mapping[str, tuple[PathDetailSegment, ...]] | None = None,
    snapped: tuple[GeoJsonPosition, ...] | None = None,
) -> RoutedPath:
    return RoutedPath(
        distance_m=distance,
        duration_ms=duration,
        ascend_m=ascend,
        descend_m=descend,
        geometry=geometry,
        snapped_points=snapped or (geometry[0], geometry[-1]),
        details=details or {},
    )


def detail(start: int, end: int, value: str | int | None) -> PathDetailSegment:
    return PathDetailSegment(from_index=start, to_index=end, value=value)


def test_two_segments_omit_join_and_sum_authoritative_values() -> None:
    result = compose_routed_segments(
        (
            leg(((0.0, 0.0), (1.0, 0.0)), distance=120, duration=12),
            leg(((1.0, 0.0), (2.0, 0.0)), distance=80, duration=8),
        )
    )
    assert result.geometry == ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0))
    assert result.distance_m == 200
    assert result.duration_ms == 20
    assert result.ascend_m == 4
    assert result.descend_m == 2
    assert result.snapped_points == result.geometry


def test_three_segments_shift_details_and_preserve_missing_gaps() -> None:
    result = compose_routed_segments(
        (
            leg(
                ((0.0, 0.0), (1.0, 0.0)),
                details={"edge_id": (detail(0, 1, 10),)},
            ),
            leg(((1.0, 0.0), (2.0, 0.0))),
            leg(
                ((2.0, 0.0), (3.0, 0.0)),
                details={"edge_id": (detail(0, 1, 30),)},
            ),
        )
    )
    assert result.geometry == (
        (0.0, 0.0),
        (1.0, 0.0),
        (2.0, 0.0),
        (3.0, 0.0),
    )
    assert result.details["edge_id"] == (detail(0, 1, 10), detail(2, 3, 30))
    assert result.snapped_points == result.geometry


def test_adjacent_equal_details_merge_and_explicit_null_is_preserved() -> None:
    result = compose_routed_segments(
        (
            leg(
                ((0.0, 0.0), (1.0, 0.0)),
                details={"surface": (detail(0, 1, None),)},
            ),
            leg(
                ((1.0, 0.0), (2.0, 0.0)),
                details={"surface": (detail(0, 1, None),)},
            ),
        )
    )
    assert result.details["surface"] == (detail(0, 2, None),)


def test_optional_elevation_is_unknown_when_any_leg_is_unknown() -> None:
    result = compose_routed_segments(
        (
            leg(((0.0, 0.0), (1.0, 0.0))),
            leg(
                ((1.0, 0.0), (2.0, 0.0)),
                ascend=None,
                descend=None,
            ),
        )
    )
    assert result.ascend_m is None
    assert result.descend_m is None


def test_discontinuous_geometry_is_rejected_without_fallback() -> None:
    with pytest.raises(RouteCompositionError, match="discontinuous"):
        compose_routed_segments(
            (
                leg(((0.0, 0.0), (1.0, 0.0))),
                leg(((1.1, 0.0), (2.0, 0.0))),
            )
        )


def test_segment_snapped_endpoints_must_match_own_geometry() -> None:
    inconsistent = leg(
        ((0.0, 0.0), (1.0, 0.0)),
        snapped=((0.1, 0.0), (1.0, 0.0)),
    )
    with pytest.raises(RouteCompositionError, match="do not match geometry"):
        compose_routed_segments((inconsistent,))


def test_continuous_geometry_with_discontinuous_snaps_is_rejected() -> None:
    with pytest.raises(RouteCompositionError):
        compose_routed_segments(
            (
                leg(((0.0, 0.0), (1.0, 0.0))),
                leg(
                    ((1.0, 0.0), (2.0, 0.0)),
                    snapped=((1.1, 0.0), (2.0, 0.0)),
                ),
            )
        )


def test_continuous_snaps_with_discontinuous_geometry_is_rejected() -> None:
    with pytest.raises(RouteCompositionError):
        compose_routed_segments(
            (
                leg(((0.0, 0.0), (1.0, 0.0))),
                leg(
                    ((1.1, 0.0), (2.0, 0.0)),
                    snapped=((1.0, 0.0), (2.0, 0.0)),
                ),
            )
        )


@pytest.mark.parametrize(
    "malformed",
    [
        leg(((0.0, 0.0),), snapped=((0.0, 0.0), (0.0, 0.0))),
        RoutedPath(
            100,
            10,
            None,
            None,
            ((0.0, 0.0), (1.0, 0.0)),
            None,
            {},
        ),
        RoutedPath(
            100,
            10,
            None,
            None,
            ((0.0, 0.0), (1.0, 0.0)),
            ((0.0, 0.0),),
            {},
        ),
    ],
)
def test_malformed_geometry_or_snapped_endpoints_are_rejected(
    malformed: RoutedPath,
) -> None:
    with pytest.raises(RouteCompositionError):
        compose_routed_segments((malformed,))
