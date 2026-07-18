"""Auto Tour POI corridor, close-enough, and reward tests."""

from collections import Counter

import pytest

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.domain.models import Coordinate
from sugarglider.pois.index import PoiIndex
from sugarglider.pois.models import PoiFeature, PoiIndexDocument
from sugarglider.tours.models import AutoTourRequest
from sugarglider.tours.poi_selection import (
    POI_VISIT_RADII_M,
    TourPoiSettings,
    build_poi_visits,
    shortlist_route_pois,
)
from sugarglider.tours.scoring import poi_reward

PROJECTION = LocalMetricProjection(48.87)
ORIGIN = PROJECTION.project_position((2.09, 48.87))


def _coordinate(x: float, y: float) -> Coordinate:
    lon, lat = PROJECTION.unproject_position((ORIGIN[0] + x, ORIGIN[1] + y))
    return Coordinate(lat=lat, lon=lon)


def _feature(
    osm_id: int,
    *,
    x: float,
    y: float,
    category: str,
    name: str,
    potability: str = "not_applicable",
    access: str = "public",
    confidence: str = "primary",
) -> PoiFeature:
    hydration = category in {"drinking_water", "fountain", "water_tap"}
    return PoiFeature.model_validate(
        {
            "id": f"node/{osm_id}",
            "osm_type": "node",
            "osm_id": osm_id,
            "coordinate": _coordinate(x, y),
            "category": category,
            "group": "hydration" if hydration else "scenic",
            "display_name": name,
            "name_source": "name",
            "scenic_confidence": "none" if hydration else confidence,
            "potability": potability,
            "access_status": access,
        }
    )


def _index(features: tuple[PoiFeature, ...]) -> PoiIndex:
    ordered = tuple(sorted(features, key=lambda feature: feature.id))

    def counts(field: str) -> dict[str, int]:
        values = Counter(str(getattr(feature, field)) for feature in ordered)
        return dict(sorted(values.items()))

    return PoiIndex(
        PoiIndexDocument.model_validate(
            {
                "metadata": {
                    "source_basename": "synthetic.osm.pbf",
                    "feature_count": len(ordered),
                    "category_counts": counts("category"),
                    "potability_counts": counts("potability"),
                    "access_counts": counts("access_status"),
                    "bounding_box": [1.0, 47.0, 3.0, 50.0],
                    "skipped_invalid_count": 0,
                },
                "features": ordered,
            }
        )
    )


def _route() -> tuple[tuple[float, float], ...]:
    return tuple(
        (coordinate.lon, coordinate.lat)
        for coordinate in (
            _coordinate(0, 0),
            _coordinate(5_000, 0),
            _coordinate(5_000, 2_000),
            _coordinate(0, 2_000),
            _coordinate(0, 0),
        )
    )


def _request(**updates: object) -> AutoTourRequest:
    values: dict[str, object] = {
        "start": _coordinate(0, 0),
        "target_distance_m": 14_000,
    }
    values.update(updates)
    return AutoTourRequest.model_validate(values)


def test_exact_category_visit_radii() -> None:
    assert POI_VISIT_RADII_M == {
        "viewpoint": 150.0,
        "observation_tower": 120.0,
        "castle": 200.0,
        "ruins": 150.0,
        "archaeological_site": 150.0,
        "tourism_attraction": 120.0,
        "drinking_water": 50.0,
        "fountain": 0.0,
        "water_tap": 0.0,
    }


def test_route_corridor_uses_exact_distance_order_and_safe_filters() -> None:
    index = _index(
        (
            _feature(1, x=1_000, y=100, category="viewpoint", name="View"),
            _feature(
                2,
                x=2_000,
                y=40,
                category="drinking_water",
                name="Water",
                potability="verified",
            ),
            _feature(
                3,
                x=2_100,
                y=10,
                category="fountain",
                name="Unknown",
                potability="unknown",
            ),
            _feature(
                4,
                x=2_200,
                y=10,
                category="water_tap",
                name="Unsafe",
                potability="non_potable",
            ),
            _feature(
                5,
                x=3_000,
                y=20,
                category="castle",
                name="Private",
                access="private",
            ),
        )
    )
    matches = index.query_near_route(_route(), 200, limit=20)
    assert tuple(match.feature.id for match in matches) == ("node/1", "node/2")
    assert matches[0].distance_m == pytest.approx(100, abs=0.1)
    assert matches[0].route_progress_share < matches[1].route_progress_share
    assert index.get_feature("node/2") is not None
    assert index.get_feature("node/999") is None


def test_zero_cost_overlapping_neighborhoods_and_verified_water_collection() -> None:
    features = (
        _feature(1, x=1_000, y=100, category="viewpoint", name="View"),
        _feature(2, x=1_020, y=120, category="castle", name="Castle"),
        _feature(
            3,
            x=2_000,
            y=40,
            category="drinking_water",
            name="Water",
            potability="verified",
        ),
    )
    index = _index(features)
    shortlist = shortlist_route_pois(
        index=index,
        route_geometry=_route(),
        routing_points=(
            _coordinate(0, 0),
            _coordinate(5_000, 0),
            _coordinate(5_000, 2_000),
            _coordinate(0, 2_000),
            _coordinate(0, 0),
        ),
        request=_request(),
        settings=TourPoiSettings(),
    )
    assert tuple(visit.poi.id for visit in shortlist.already_collected) == (
        "node/1",
        "node/2",
        "node/3",
    )
    assert all(visit.already_on_route for visit in shortlist.already_collected)
    assert all(visit.estimated_detour_m == 0 for visit in shortlist.already_collected)
    assert shortlist.opportunities == ()


def test_shortlist_detour_rewards_preferred_boost_and_progress_order() -> None:
    features = (
        _feature(1, x=1_000, y=250, category="viewpoint", name="View A"),
        _feature(2, x=2_000, y=300, category="viewpoint", name="View B"),
        _feature(
            3,
            x=3_000,
            y=200,
            category="tourism_attraction",
            name="Broad",
            confidence="broad",
        ),
    )
    index = _index(features)
    shortlist = shortlist_route_pois(
        index=index,
        route_geometry=_route(),
        routing_points=(
            _coordinate(0, 0),
            _coordinate(5_000, 0),
            _coordinate(5_000, 2_000),
            _coordinate(0, 2_000),
            _coordinate(0, 0),
        ),
        request=_request(preferred_poi_ids=("node/2", "node/3")),
        settings=TourPoiSettings(),
    )
    assert {
        opportunity.match.feature.id for opportunity in shortlist.opportunities
    } == {
        "node/1",
        "node/2",
        "node/3",
    }
    boosted = next(
        opportunity
        for opportunity in shortlist.opportunities
        if opportunity.match.feature.id == "node/2"
    )
    assert boosted.reward.preferred_id_boost == 3.0
    assert boosted.estimated_detour_m > 0

    first = poi_reward(features[0])
    repeated = poi_reward(features[1], prior_categories=("viewpoint",))
    assert first.category_diversity_bonus == 1.0
    assert repeated.category_diversity_bonus == 0.0
    assert repeated.diminishing_return_multiplier < 1.0


def test_build_visits_is_deterministic_and_route_progress_ordered() -> None:
    features = (
        _feature(1, x=3_000, y=20, category="castle", name="Later"),
        _feature(2, x=1_000, y=20, category="viewpoint", name="Earlier"),
    )
    index = _index(features)
    matches = index.query_near_route(
        _route(), 200, groups=("scenic",), include_broad_attractions=True
    )
    visits = build_poi_visits(
        matches=matches,
        preferred_poi_ids=frozenset(),
        base_already_ids=frozenset(feature.id for feature in features),
        inserted_records={},
    )
    assert tuple(visit.poi.id for visit in visits) == ("node/2", "node/1")
    assert visits == build_poi_visits(
        matches=matches,
        preferred_poi_ids=frozenset(),
        base_already_ids=frozenset(feature.id for feature in features),
        inserted_records={},
    )


def test_round_trip_control_collects_incidental_pois_without_inventing_anchors() -> (
    None
):
    index = _index(
        (
            _feature(1, x=1_000, y=100, category="viewpoint", name="Incidental"),
            _feature(2, x=2_000, y=300, category="castle", name="Opportunity"),
        )
    )
    shortlist = shortlist_route_pois(
        index=index,
        route_geometry=_route(),
        routing_points=(_coordinate(0, 0),),
        request=_request(),
        settings=TourPoiSettings(),
    )
    assert tuple(visit.poi.id for visit in shortlist.already_collected) == ("node/1",)
    assert shortlist.opportunities == ()


def test_verified_water_just_outside_final_visit_radius_is_not_claimed() -> None:
    water = _feature(
        1,
        x=2_000,
        y=50.2,
        category="drinking_water",
        name="Almost reached",
        potability="verified",
    )
    index = _index((water,))
    matches = index.query_near_route(
        _route(),
        100,
        groups=("hydration",),
    )
    assert matches[0].distance_m > 50
    assert (
        build_poi_visits(
            matches=matches,
            preferred_poi_ids=frozenset(),
            base_already_ids=frozenset(),
            inserted_records={},
        )
        == ()
    )
