"""Generic deterministic ordering for stored and compatibility POI approaches."""

from sugarglider.pois.models import (
    PoiApproachCandidate,
    PoiApproachKind,
    PoiFeature,
)

MAX_APPROACHES_PER_POI = 4

APPROACH_PRIORITY: dict[PoiApproachKind, int] = {
    "user_override": 0,
    "drinking_water_source": 1,
    "viewpoint_location": 1,
    "exact_feature": 2,
    "mapped_entrance": 3,
    "mapped_gate": 4,
    "public_path_boundary": 5,
    "nearby_public_path": 6,
    "strict_graph_snap": 7,
}


def approach_order_key(candidate: PoiApproachCandidate) -> tuple[int, float, str]:
    """Order meaningful approaches without depending on tour-service semantics."""
    return (
        APPROACH_PRIORITY[candidate.kind],
        candidate.semantic_distance_m,
        candidate.id,
    )


def approach_candidates_for_feature(
    feature: PoiFeature,
) -> tuple[PoiApproachCandidate, ...]:
    """Return bounded stored approaches plus the format-2 exact-node fallback."""
    return all_approach_candidates_for_feature(feature)[:MAX_APPROACHES_PER_POI]


def all_approach_candidates_for_feature(
    feature: PoiFeature,
) -> tuple[PoiApproachCandidate, ...]:
    """Return every stored approach for spatial indexing, in stable order."""
    if feature.approach_candidates:
        return tuple(sorted(feature.approach_candidates, key=approach_order_key))
    if feature.osm_type != "node" or feature.access_status in {
        "private",
        "restricted",
    }:
        return ()
    if feature.category == "drinking_water":
        kind: PoiApproachKind = "drinking_water_source"
        tolerance = 15.0
    elif feature.category == "viewpoint":
        kind = "viewpoint_location"
        tolerance = 20.0
    elif feature.category == "observation_tower":
        kind = "exact_feature"
        tolerance = 20.0
    else:
        kind = "exact_feature"
        tolerance = 25.0
    return (
        PoiApproachCandidate(
            id=f"{feature.id}/approach/00-exact",
            coordinate=feature.coordinate,
            kind=kind,
            source="osm_feature",
            access=feature.access_status,
            semantic_distance_m=0.0,
            arrival_tolerance_m=tolerance,
            name=feature.display_name,
            osm_type=feature.osm_type,
            osm_id=feature.osm_id,
            provenance="feature_geometry",
        ),
    )
