"""Deterministic semantic-POI resolution and strict route approaches."""

from shapely.geometry import Point

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.models import GeoJsonPosition
from sugarglider.planning.auto_tour.models import RequestedTourPlace
from sugarglider.planning.constraints.resolver import mapped_approach_candidates
from sugarglider.pois.approaches import (
    MAX_APPROACHES_PER_POI,
    approach_order_key,
)
from sugarglider.pois.approaches import (
    approach_candidates_for_feature as approach_candidates_for_feature,
)
from sugarglider.pois.index import PoiIndex
from sugarglider.pois.models import PoiApproachCandidate

MAX_EVALUATED_APPROACHES_PER_POI = MAX_APPROACHES_PER_POI


def resolve_requested_stops(
    places: tuple[RequestedTourPlace, ...], index: PoiIndex | None
) -> tuple[RequestedTourPlace, ...]:
    prepared = tuple(
        place
        if place.id is not None
        else place.model_copy(
            update={
                "id": (
                    f"requested/original/{place.original_index}"
                    if place.original_index is not None
                    else f"requested/import/{position}"
                )
            }
        )
        for position, place in enumerate(places)
    )
    return tuple(resolve_requested_place(place, index) for place in prepared)


def resolve_requested_place(
    place: RequestedTourPlace, index: PoiIndex | None
) -> RequestedTourPlace:
    """Resolve a requested place without changing its semantic ownership."""
    if place.approach_override is not None:
        distance = haversine_distance_m(
            (place.coordinate.lon, place.coordinate.lat),
            (place.approach_override.lon, place.approach_override.lat),
        )
        override = PoiApproachCandidate(
            id=(
                f"requested/{place.id or place.original_index or 0}"
                "/approach/00-override"
            ),
            coordinate=place.approach_override.model_copy(update={"name": None}),
            kind="user_override",
            source="user_override",
            access="unknown",
            semantic_distance_m=distance,
            arrival_tolerance_m=place.arrival_tolerance_m,
            name=place.name,
            provenance="user_override",
        )
        return place.model_copy(
            update={
                "approach_candidates": (override,),
                "chosen_approach": override,
            }
        )

    strict_snap = PoiApproachCandidate(
        id=(
            f"requested/{place.id or place.original_index or 0}/approach/90-strict-snap"
        ),
        coordinate=place.coordinate.model_copy(update={"name": None}),
        kind="strict_graph_snap",
        source="imported_coordinate",
        access="unknown",
        semantic_distance_m=0.0,
        arrival_tolerance_m=min(25.0, place.arrival_tolerance_m),
        name=place.name,
        provenance="imported_coordinate",
    )

    feature, mapped_candidates = mapped_approach_candidates(
        index=index,
        coordinate=place.coordinate,
        name=place.name,
        osm_reference=place.osm_reference,
        radius_m=place.access_search_radius_m,
    )

    # A best-effort coordinate without an explicit OSM reference remains
    # coordinate-owned. An implicit name match is only an alternative.
    if place.constraint_strength == "best_effort" and place.osm_reference is None:
        return place.model_copy(
            update={
                "approach_candidates": (strict_snap, *mapped_candidates),
                "chosen_approach": strict_snap,
                "approach_resolution_drop_reason": None,
            }
        )

    # Explicit OSM references, and the existing non-best-effort feature
    # semantics, remain feature-authoritative.
    if feature is not None:
        return place.model_copy(
            update={
                "osm_reference": feature.id,
                "approach_candidates": mapped_candidates,
                "chosen_approach": (
                    mapped_candidates[0] if mapped_candidates else None
                ),
                "approach_resolution_drop_reason": (
                    "private_or_restricted"
                    if feature.access_status in {"private", "restricted"}
                    else "no_meaningful_approach"
                    if not mapped_candidates
                    else None
                ),
            }
        )

    return place.model_copy(
        update={
            "approach_candidates": (strict_snap,),
            "chosen_approach": strict_snap,
        }
    )


def choose_route_dependent_approaches(
    places: tuple[RequestedTourPlace, ...],
    control_geometry: tuple[GeoJsonPosition, ...],
) -> tuple[RequestedTourPlace, ...]:
    """Choose one bounded approach using its cost proxy against a routed control."""
    if not places or len(control_geometry) < 2:
        return places
    projection = LocalMetricProjection(control_geometry[0][1])
    line = projection.project_line(control_geometry)
    selected: list[RequestedTourPlace] = []
    for place in places:
        candidates = place.approach_candidates[:MAX_EVALUATED_APPROACHES_PER_POI]
        if not candidates or candidates[0].kind == "user_override":
            selected.append(place)
            continue
        approach = min(
            candidates,
            key=lambda candidate: (
                line.distance(
                    Point(
                        projection.project_position(
                            (candidate.coordinate.lon, candidate.coordinate.lat)
                        )
                    )
                ),
                approach_order_key(candidate)[0],
                candidate.semantic_distance_m,
                candidate.id,
            ),
        )
        selected.append(place.model_copy(update={"chosen_approach": approach}))
    return tuple(selected)
