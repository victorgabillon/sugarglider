"""One bounded profile-aware fallback resolver for both planning modes."""

import unicodedata
from dataclasses import dataclass
from typing import Literal

from shapely.geometry import Point

from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.models import Coordinate
from sugarglider.planning.budget import SearchPhase
from sugarglider.planning.models import ConstraintStrength
from sugarglider.planning.profiles import RoutingProfileId
from sugarglider.planning.routing_gateway import (
    CachedRoutingGateway,
    SearchBudgetExhaustedError,
)
from sugarglider.pois.approaches import approach_candidates_for_feature
from sugarglider.pois.index import PoiIndex
from sugarglider.pois.models import PoiApproachCandidate, PoiFeature
from sugarglider.routing.errors import RoutingError

type ResolutionStatus = Literal[
    "exact", "reached_approach", "approximated", "unresolved"
]

NORMAL_APPROACH_TOLERANCE_M = 25.0


@dataclass(frozen=True)
class ConstraintResolution:
    """A truthful resolution; semantic and routed locations stay distinct."""

    status: ResolutionStatus
    constraint_id: str
    constraint_name: str
    strength: ConstraintStrength
    semantic_coordinate: Coordinate
    routed_coordinate: Coordinate | None
    approach: PoiApproachCandidate | None
    distance_m: float | None
    normal_tolerance_m: float
    configured_maximum_m: float | None
    reason: str
    warnings: tuple[str, ...] = ()


class ConstraintResolver:
    """Resolve constraints using local provenance and the shared route gateway."""

    def __init__(
        self, *, routes: CachedRoutingGateway, poi_index: PoiIndex | None
    ) -> None:
        self._routes = routes
        self._poi_index = poi_index

    async def resolve(
        self,
        *,
        constraint_id: str,
        constraint_name: str,
        semantic_coordinate: Coordinate,
        strength: ConstraintStrength,
        anchor: Coordinate,
        profile: RoutingProfileId,
        access_search_radius_m: float = 500.0,
        maximum_best_effort_distance_m: float | None = None,
        osm_reference: str | None = None,
        approach_override: Coordinate | None = None,
    ) -> ConstraintResolution:
        if strength == "exact":
            return ConstraintResolution(
                status="exact",
                constraint_id=constraint_id,
                constraint_name=constraint_name,
                strength=strength,
                semantic_coordinate=semantic_coordinate,
                routed_coordinate=semantic_coordinate,
                approach=None,
                distance_m=0.0,
                normal_tolerance_m=NORMAL_APPROACH_TOLERANCE_M,
                configured_maximum_m=None,
                reason="explicit_exact_coordinate",
            )

        candidates = list(
            self._mapped_approaches(
                semantic_coordinate,
                constraint_name,
                osm_reference,
                access_search_radius_m,
            )
        )
        if approach_override is not None:
            semantic_distance = _distance(semantic_coordinate, approach_override)
            if semantic_distance <= 1_000.0:
                candidates.append(
                    PoiApproachCandidate(
                        id=f"constraint/{constraint_id}/approach/user",
                        coordinate=approach_override.model_copy(update={"name": None}),
                        kind="user_override",
                        source="user_override",
                        access="unknown",
                        semantic_distance_m=semantic_distance,
                        arrival_tolerance_m=NORMAL_APPROACH_TOLERANCE_M,
                        name=constraint_name,
                        provenance="user_override",
                    )
                )
        candidates.append(
            PoiApproachCandidate(
                id=f"constraint/{constraint_id}/approach/strict-snap",
                coordinate=semantic_coordinate.model_copy(update={"name": None}),
                kind="strict_graph_snap",
                source="imported_coordinate",
                access="unknown",
                semantic_distance_m=0.0,
                arrival_tolerance_m=NORMAL_APPROACH_TOLERANCE_M,
                name=constraint_name,
                provenance="imported_coordinate",
            )
        )

        budget_exhausted = False
        for approach in candidates:
            try:
                resolution = await self._probe(
                    constraint_id=constraint_id,
                    constraint_name=constraint_name,
                    semantic_coordinate=semantic_coordinate,
                    strength=strength,
                    anchor=anchor,
                    profile=profile,
                    approach=approach,
                    access_search_radius_m=access_search_radius_m,
                    maximum_best_effort_distance_m=(maximum_best_effort_distance_m),
                )
            except SearchBudgetExhaustedError:
                budget_exhausted = True
                break
            except RoutingError:
                continue
            if resolution is not None:
                return resolution

        return ConstraintResolution(
            status="unresolved",
            constraint_id=constraint_id,
            constraint_name=constraint_name,
            strength=strength,
            semantic_coordinate=semantic_coordinate,
            routed_coordinate=None,
            approach=None,
            distance_m=None,
            normal_tolerance_m=NORMAL_APPROACH_TOLERANCE_M,
            configured_maximum_m=maximum_best_effort_distance_m,
            reason=(
                "route_budget_exhausted"
                if budget_exhausted
                else "no_profile_compatible_approach"
            ),
        )

    async def _probe(
        self,
        *,
        constraint_id: str,
        constraint_name: str,
        semantic_coordinate: Coordinate,
        strength: ConstraintStrength,
        anchor: Coordinate,
        profile: RoutingProfileId,
        approach: PoiApproachCandidate,
        access_search_radius_m: float,
        maximum_best_effort_distance_m: float | None,
    ) -> ConstraintResolution | None:
        path = await self._routes.route(
            (anchor, approach.coordinate),
            profile,
            phase=SearchPhase.APPROACH,
            topology_options=(("constraint_resolution", strength),),
        )
        if path.snapped_points is None or len(path.snapped_points) != 2:
            return None
        snapped_lon, snapped_lat = path.snapped_points[-1]
        routed = Coordinate(lat=snapped_lat, lon=snapped_lon)
        snap_distance = _distance(approach.coordinate, routed)
        semantic_distance = _distance(semantic_coordinate, routed)
        warnings = ("access_unknown",) if approach.access == "unknown" else ()
        if snap_distance <= approach.arrival_tolerance_m:
            return ConstraintResolution(
                status="reached_approach",
                constraint_id=constraint_id,
                constraint_name=constraint_name,
                strength=strength,
                semantic_coordinate=semantic_coordinate,
                routed_coordinate=routed,
                approach=approach.model_copy(update={"coordinate": routed}),
                distance_m=semantic_distance,
                normal_tolerance_m=approach.arrival_tolerance_m,
                configured_maximum_m=maximum_best_effort_distance_m,
                reason=(
                    "nearest_routeable_point_used"
                    if approach.kind == "strict_graph_snap"
                    else "resolved_profile_compatible_approach"
                ),
                warnings=warnings,
            )
        maximum = maximum_best_effort_distance_m or access_search_radius_m
        if strength == "best_effort" and semantic_distance <= maximum:
            fallback = approach.model_copy(
                update={
                    "coordinate": routed,
                    "kind": "strict_graph_snap",
                    "source": "imported_coordinate",
                    "semantic_distance_m": semantic_distance,
                    "provenance": "imported_coordinate",
                }
            )
            return ConstraintResolution(
                status="approximated",
                constraint_id=constraint_id,
                constraint_name=constraint_name,
                strength=strength,
                semantic_coordinate=semantic_coordinate,
                routed_coordinate=routed,
                approach=fallback,
                distance_m=semantic_distance,
                normal_tolerance_m=NORMAL_APPROACH_TOLERANCE_M,
                configured_maximum_m=maximum,
                reason="nearest_routeable_point_used",
                warnings=tuple(sorted({*warnings, "nearest_routeable_point_used"})),
            )
        return None

    def _mapped_approaches(
        self,
        coordinate: Coordinate,
        name: str,
        osm_reference: str | None,
        radius_m: float,
    ) -> tuple[PoiApproachCandidate, ...]:
        _feature, approaches = mapped_approach_candidates(
            index=self._poi_index,
            coordinate=coordinate,
            name=name,
            osm_reference=osm_reference,
            radius_m=radius_m,
        )
        return approaches


def mapped_approach_candidates(
    *,
    index: PoiIndex | None,
    coordinate: Coordinate,
    name: str,
    osm_reference: str | None,
    radius_m: float,
) -> tuple[PoiFeature | None, tuple[PoiApproachCandidate, ...]]:
    """Resolve the local semantic feature and safe approaches for either mode."""
    if index is None:
        return None, ()
    if osm_reference is not None:
        feature = index.get_feature(osm_reference)
        if feature is not None and _distance(coordinate, feature.coordinate) > radius_m:
            feature = None
    else:
        center = Point(
            index.projection.project_position((coordinate.lon, coordinate.lat))
        )
        normalized = _normalized_name(name)
        matches = (
            index.features[item]
            for item in index.query_indices(center.buffer(radius_m).envelope)
        )
        feature = min(
            (
                value
                for value in matches
                if _normalized_name(value.display_name) == normalized
                and _distance(coordinate, value.coordinate) <= radius_m
            ),
            key=lambda value: (_distance(coordinate, value.coordinate), value.id),
            default=None,
        )
    if feature is None or feature.access_status in {"private", "restricted"}:
        return feature, ()
    return feature, tuple(
        approach
        for approach in approach_candidates_for_feature(feature)
        if approach.access not in {"private", "restricted"}
    )


def _distance(left: Coordinate, right: Coordinate) -> float:
    return haversine_distance_m((left.lon, left.lat), (right.lon, right.lat))


def _normalized_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
