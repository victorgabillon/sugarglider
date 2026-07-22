"""PR15 routing-profile registry, identity, policy, and packaging contracts."""

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from sugarglider.analysis.route import RouteAnalyzer
from sugarglider.domain.analysis import (
    CyclingRouteQuality,
    RunningRouteQuality,
    WalkingRouteQuality,
)
from sugarglider.domain.models import Coordinate, PathDetailSegment
from sugarglider.planning.budget import SearchBudget, SearchPhase
from sugarglider.planning.cache import RouteCacheKey, RoutingOperation
from sugarglider.planning.models import PLAN_REQUEST_ADAPTER
from sugarglider.planning.profile_quality import (
    PROFILE_QUALITY_POLICIES,
    profile_aware_drop_reason,
    profile_quality_components,
)
from sugarglider.planning.routing_gateway import CachedRoutingGateway
from sugarglider.planning.signatures import candidate_signature
from sugarglider.routing.backend import AutoTourRoutingBackend, RoutedPath
from sugarglider.routing.profiles import (
    ROUTING_PROFILES,
    SNAP_PREVENTION_ORDER,
    RoutingProfile,
    routing_profile,
    routing_profile_catalog,
)
from sugarglider.routing.result import RouteResultFactory

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_IDS = (
    "trail_run",
    "hike",
    "city_bike",
    "gravel_bike",
    "mountain_bike",
    "road_bike",
)
BACKEND_IDS = (
    "trail_run",
    "hike",
    "bike",
    "gravel_bike",
    "mtb",
    "racingbike",
)


def _request(profile: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "waypoint_route",
        "name": "Profile identity",
        "topology": "point_to_point",
        "start": {"lat": 48.85, "lon": 2.36},
        "end": {"lat": 48.87, "lon": 2.10},
        "routing_profile": profile,
        "candidate_count": 1,
        "seed": 7,
        "distance_objective": {
            "target_m": 25_000,
            "tolerance_m": 2_000,
            "maximum_m": None,
            "priority": "flexible",
        },
        "preferences": {
            "nature": "off",
            "path_selection": "shortest",
            "loop_geometry": "off",
        },
        "waypoints": [],
        "waypoint_order": "fixed",
    }


def _path() -> RoutedPath:
    geometry = ((2.0, 48.0), (2.01, 48.01), (2.02, 48.02))
    segments = (PathDetailSegment(from_index=0, to_index=2, value="ASPHALT"),)
    return RoutedPath(
        distance_m=2_000,
        duration_ms=100,
        ascend_m=None,
        descend_m=None,
        geometry=geometry,
        snapped_points=(geometry[0], geometry[-1]),
        details={
            "surface": segments,
            "road_class": tuple(
                value.model_copy(update={"value": "CYCLEWAY"}) for value in segments
            ),
            "bike_network": tuple(
                value.model_copy(update={"value": "LOCAL"}) for value in segments
            ),
            "edge_id": tuple(
                value.model_copy(update={"value": 12}) for value in segments
            ),
        },
    )


def test_registry_is_complete_ordered_immutable_and_elevation_truthful() -> None:
    assert tuple(profile.id for profile in ROUTING_PROFILES) == PUBLIC_IDS
    assert (
        tuple(profile.graphhopper_profile for profile in ROUTING_PROFILES)
        == BACKEND_IDS
    )
    assert all(not profile.elevation_aware for profile in ROUTING_PROFILES)
    with pytest.raises(ValidationError):
        routing_profile("hike").display_name = "Changed"


def test_packaged_snap_preventions_are_supported_unique_and_canonical() -> None:
    supported = set(SNAP_PREVENTION_ORDER)
    for profile in ROUTING_PROFILES:
        assert profile.snap_preventions == ("motorway", "trunk", "ferry")
        assert set(profile.snap_preventions) <= supported
        assert len(profile.snap_preventions) == len(set(profile.snap_preventions))
        assert "steps" not in profile.snap_preventions


@pytest.mark.parametrize(
    "snap_preventions",
    (("steps",), ("ferry", "motorway"), ("motorway", "motorway")),
)
def test_invalid_packaged_snap_preventions_are_rejected(
    snap_preventions: tuple[str, ...],
) -> None:
    packaged = routing_profile("hike").model_dump()
    packaged["snap_preventions"] = snap_preventions
    with pytest.raises(ValidationError, match="snap_preventions|snap preventions"):
        RoutingProfile.model_validate(packaged)


def test_steps_remain_exposed_through_road_class_and_activity_quality() -> None:
    for profile in ROUTING_PROFILES:
        assert "road_class" in profile.requested_path_details
        assert "steps" in profile.allowed_quality_metrics

    path = _path()
    road_class = tuple(
        segment.model_copy(update={"value": "STEPS"})
        for segment in path.details["road_class"]
    )
    path = replace(path, details={**path.details, "road_class": road_class})
    factory = RouteResultFactory(RouteAnalyzer())
    for profile_id in ("hike", "trail_run", "city_bike"):
        quality = factory.create(
            name="steps",
            path=path,
            input_point_count=2,
            routing_profile=profile_id,
        ).analysis.activity_quality
        assert quality.steps.share == 1


@pytest.mark.parametrize("profile", PUBLIC_IDS)
def test_strict_requests_accept_exact_public_profiles(profile: str) -> None:
    request = PLAN_REQUEST_ADAPTER.validate_python(_request(profile))
    assert request.routing_profile == profile


@pytest.mark.parametrize("alias", ("bike", "mtb", "racingbike", "running"))
def test_backend_names_and_aliases_are_not_public(alias: str) -> None:
    with pytest.raises(ValidationError):
        PLAN_REQUEST_ADAPTER.validate_python(_request(alias))


def test_catalog_is_stable_and_hides_backend_names() -> None:
    catalog = routing_profile_catalog(frozenset(BACKEND_IDS))
    assert tuple(status.profile.id for status in catalog.profiles) == PUBLIC_IDS
    assert all(status.available and not status.warnings for status in catalog.profiles)
    payload = catalog.model_dump_json()
    assert '"racingbike"' not in payload and '"mtb"' not in payload


def test_activity_analysis_and_profile_signature_identity() -> None:
    path = _path()
    factory = RouteResultFactory(RouteAnalyzer())
    hike = factory.create(
        name="same",
        path=path,
        input_point_count=2,
        routing_profile="hike",
    )
    run = factory.create(
        name="same",
        path=path,
        input_point_count=2,
        routing_profile="trail_run",
    )
    bike = factory.create(
        name="same",
        path=path,
        input_point_count=2,
        routing_profile="city_bike",
    )
    assert isinstance(hike.analysis.activity_quality, WalkingRouteQuality)
    assert isinstance(run.analysis.activity_quality, RunningRouteQuality)
    assert isinstance(bike.analysis.activity_quality, CyclingRouteQuality)
    assert candidate_signature(hike) != candidate_signature(run)
    assert bike.analysis.activity_quality.cycleway_like.share == 1


def test_every_profile_has_one_quality_policy_and_profile_drop_reasons() -> None:
    assert tuple(policy.profile_id for policy in PROFILE_QUALITY_POLICIES) == PUBLIC_IDS
    bike = RouteResultFactory().create(
        name="bike",
        path=_path(),
        input_point_count=2,
        routing_profile="road_bike",
    )
    total, components, severe = profile_quality_components(bike)
    assert total < 0 and components["paved_reward"] > 0 and not severe
    assert profile_aware_drop_reason("city_bike", "graph_unreachable") == (
        "profile_unreachable"
    )


class _Backend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str,
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        del points, pass_through
        self.calls.append(profile)
        return _path()


@pytest.mark.asyncio
async def test_request_cache_isolated_by_public_and_backend_profile() -> None:
    limits = {phase: 0 for phase in SearchPhase}
    limits[SearchPhase.CONTROL] = 2
    backend = _Backend()
    gateway = CachedRoutingGateway(
        cast(AutoTourRoutingBackend, backend),
        SearchBudget(limits, total_limit=2),
    )
    points = (Coordinate(lat=48, lon=2), Coordinate(lat=48.02, lon=2.02))
    await gateway.route(points, "hike")
    await gateway.route(points, "city_bike")
    assert backend.calls == ["hike", "city_bike"]
    hike_key = RouteCacheKey(
        operation=RoutingOperation.ROUTE,
        profile_id="hike",
        backend_profile="hike",
        coordinates=((48.0, 2.0), (48.02, 2.02)),
        pass_through=False,
        custom_options=(("snap_preventions", "motorway,trunk,ferry"),),
    )
    assert gateway.peek(hike_key) is not None
    assert (
        gateway.peek(
            replace(
                hike_key,
                custom_options=(("snap_preventions", "motorway,trunk"),),
            )
        )
        is None
    )
    snapshot = gateway.cache_snapshot()
    assert snapshot.miss_count == snapshot.backend_call_count == 2


def test_graphhopper_config_models_fingerprint_and_examples_are_complete() -> None:
    config = (ROOT / "infrastructure/graphhopper/config.yml").read_text()
    for backend in BACKEND_IDS:
        assert f"name: {backend}" in config
        assert f"profile: {backend}" in config
    for encoded_value in (
        "foot_access",
        "bike_access",
        "mtb_access",
        "racingbike_access",
        "foot_network",
        "bike_network",
        "hike_rating",
        "mtb_rating",
        "roundabout",
        "country",
    ):
        assert encoded_value in config
    for filename in ("trail_run.json", "gravel_bike.json"):
        model = json.loads(
            (ROOT / "infrastructure/graphhopper/custom_models" / filename).read_text()
        )
        assert model["priority"]
        assert all(
            float(statement["multiply_by"]) <= 1 for statement in model["priority"]
        )
    entrypoint = (ROOT / "infrastructure/graphhopper/entrypoint.sh").read_text()
    rebuild = (ROOT / "scripts/rebuild_graph_cache.sh").read_text()
    assert "import-fingerprint" in entrypoint and "make rebuild-graph" in entrypoint
    assert "! -name '.gitkeep'" in entrypoint
    assert "! -name '.gitkeep'" in rebuild
    dockerfile = (ROOT / "infrastructure/graphhopper/Dockerfile").read_text()
    assert "${GRAPHHOPPER_VERSION}" in dockerfile
    examples = sorted((ROOT / "examples/profiles").glob("*.json"))
    assert len(examples) == 6
    assert {
        json.loads(path.read_text())["routing_profile"] for path in examples
    } == set(PUBLIC_IDS)


def test_activity_specific_missing_details_stay_visibly_unknown() -> None:
    path = replace(_path(), details={})
    cycling = (
        RouteResultFactory()
        .create(
            name="unknown",
            path=path,
            input_point_count=2,
            routing_profile="mountain_bike",
        )
        .analysis
    )
    assert cycling.activity_quality.activity_kind == "cycling"
    assert cycling.activity_quality.detail_coverage == {}
    assert "bike_network_coverage_incomplete" in cycling.warnings
    assert "foot_network_coverage_incomplete" not in cycling.warnings
