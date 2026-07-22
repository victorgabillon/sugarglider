"""Shared profile-aware exact, approach, and best-effort resolution."""

from typing import cast

import pytest

from sugarglider.domain.models import Coordinate
from sugarglider.planning.budget import SearchBudget, SearchPhase
from sugarglider.planning.constraints.resolver import ConstraintResolver
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.profiles import RoutingProfileId
from sugarglider.routing.backend import AutoTourRoutingBackend, RoutedPath


class _SnapBackend:
    def __init__(self, *, displacement_degrees: float = 0.001) -> None:
        self.displacement_degrees = displacement_degrees
        self.calls = 0
        self.profiles: list[RoutingProfileId] = []

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: RoutingProfileId = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        del pass_through
        self.calls += 1
        self.profiles.append(profile)
        start = (points[0].lon, points[0].lat)
        snapped_end = (
            points[-1].lon,
            points[-1].lat + self.displacement_degrees,
        )
        return RoutedPath(
            distance_m=1_000,
            duration_ms=600_000,
            ascend_m=None,
            descend_m=None,
            geometry=(start, snapped_end),
            snapped_points=(start, snapped_end),
            details={},
        )


def _context(backend: _SnapBackend) -> PlanningSearchContext:
    limits = {phase: 0 for phase in SearchPhase}
    limits[SearchPhase.APPROACH] = 4
    return PlanningSearchContext.create(
        backend=cast(AutoTourRoutingBackend, backend),
        budget=SearchBudget(limits),
    )


@pytest.mark.asyncio
async def test_exact_resolution_never_routes_or_weakens() -> None:
    backend = _SnapBackend()
    resolver = ConstraintResolver(routes=_context(backend).routes, poi_index=None)
    semantic = Coordinate(lat=48.87, lon=2.09)
    resolved = await resolver.resolve(
        constraint_id="exact-1",
        constraint_name="Exact gate",
        semantic_coordinate=semantic,
        strength="exact",
        anchor=Coordinate(lat=48.86, lon=2.08),
        profile="hike",
    )
    assert resolved.status == "exact"
    assert resolved.routed_coordinate == semantic
    assert backend.calls == 0


@pytest.mark.asyncio
async def test_approach_rejects_far_profile_snap_but_best_effort_explains_it() -> None:
    semantic = Coordinate(lat=48.87, lon=2.09)
    anchor = Coordinate(lat=48.86, lon=2.08)

    approach_backend = _SnapBackend()
    approach = await ConstraintResolver(
        routes=_context(approach_backend).routes, poi_index=None
    ).resolve(
        constraint_id="place-1",
        constraint_name="Semantic place",
        semantic_coordinate=semantic,
        strength="approach",
        anchor=anchor,
        profile="city_bike",
    )
    assert approach.status == "unresolved"
    assert approach.reason == "no_profile_compatible_approach"

    best_backend = _SnapBackend()
    context = _context(best_backend)
    resolver = ConstraintResolver(routes=context.routes, poi_index=None)
    best = await resolver.resolve(
        constraint_id="place-1",
        constraint_name="Semantic place",
        semantic_coordinate=semantic,
        strength="best_effort",
        anchor=anchor,
        profile="city_bike",
        maximum_best_effort_distance_m=500,
    )
    assert best.status == "approximated"
    assert best.distance_m is not None and 100 < best.distance_m < 120
    assert best.reason == "nearest_routeable_point_used"
    assert best.warnings == ("access_unknown", "nearest_routeable_point_used")
    assert best.approach is not None
    assert best.approach.provenance == "imported_coordinate"
    assert (
        type(best.approach).model_validate(best.approach.model_dump(mode="json"))
        == best.approach
    )
    assert best_backend.profiles == ["city_bike"]

    again = await resolver.resolve(
        constraint_id="place-1",
        constraint_name="Semantic place",
        semantic_coordinate=semantic,
        strength="best_effort",
        anchor=anchor,
        profile="city_bike",
        maximum_best_effort_distance_m=500,
    )
    assert again == best
    assert best_backend.calls == 1
    cache = context.routes.cache_snapshot()
    assert cache.hit_count == 1
    assert cache.backend_call_count == cache.miss_count == 1
