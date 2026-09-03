"""Static architecture contracts for PR34 local routing primitives and profiles."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "android/app"
KOTLIN = ANDROID / "src/main/java/io/github/victorgabillon/sugarglider"
DEBUG_KOTLIN = ANDROID / "src/debug/java/io/github/victorgabillon/sugarglider"
RELEASE_KOTLIN = ANDROID / "src/release/java/io/github/victorgabillon/sugarglider"
STATIC = ROOT / "src/sugarglider/web/static"
PROFILE_IDS = (
    "trail_run",
    "hike",
    "city_bike",
    "gravel_bike",
    "mountain_bike",
    "road_bike",
)


def test_boundary_owns_six_strict_profiles_and_bounded_ordered_points() -> None:
    boundary = (KOTLIN / "NativeRouteEngine.kt").read_text()
    protocol = (KOTLIN / "BridgeProtocol.kt").read_text()
    assert "LOCAL_ROUTE_REQUEST_VERSION = 2" in boundary
    assert "MIN_LOCAL_ROUTE_POINTS = 2" in boundary
    assert "MAX_LOCAL_ROUTE_POINTS = 16" in boundary
    for profile_id in PROFILE_IDS:
        assert f'"{profile_id}",' in boundary
    assert "points: List<LocalRouteCoordinate>" in boundary
    assert "points.all(LocalRouteCoordinate::isValid)" in boundary
    assert '"route_version"' in protocol
    assert '"points"' in protocol
    local_fields = protocol[
        protocol.index("private val localRouteFields") : protocol.index(
            "private val coordinateFields"
        )
    ]
    assert '"origin"' not in local_fields
    assert '"destination"' not in local_fields
    assert "NativeRouteFailureCode.UNSUPPORTED_PROFILE" in protocol


def test_typed_profile_policies_are_complete_and_not_aliases() -> None:
    policy = (DEBUG_KOTLIN / "ValhallaProfilePolicy.kt").read_text()
    for enum_name in (
        "TRAIL_RUN",
        "HIKE",
        "CITY_BIKE",
        "GRAVEL_BIKE",
        "MOUNTAIN_BIKE",
        "ROAD_BIKE",
    ):
        assert f"LocalRouteProfile.{enum_name}" in policy
    for bicycle_type in ("Hybrid", "Cross", "Mountain", "Road"):
        assert f"BicycleCostingOptions.BicycleType.{bicycle_type}" in policy
    assert "PedestrianCostingOptions(" in policy
    assert "BicycleCostingOptions(" in policy
    assert "policies.keys == LocalRouteProfile.entries.toSet()" in policy
    assert ".distinct().size == 6" in policy
    assert "JSONObject" not in policy


def test_pack_v1_v2_semantics_and_profile_aware_selection_are_explicit() -> None:
    registry = (KOTLIN / "RoutingPackRegistry.kt").read_text()
    engine = (DEBUG_KOTLIN / "NativeRouteEngineFactory.kt").read_text()
    assert "ROUTING_PACK_MANIFEST_SCHEMA_VERSION_V1 = 1" in registry
    assert "ROUTING_PACK_MANIFEST_SCHEMA_VERSION = 2" in registry
    assert 'MANIFEST_V2_FIELDS = MANIFEST_V1_FIELDS + "access_modes"' in registry
    assert "listOf(LocalRouteAccessMode.FOOT)" in registry
    assert "strictAccessModes" in registry
    assert "points.all(manifest.bounds::contains)" in registry
    assert ".filter { it.supports(accessMode) }" in registry
    assert "RoutingPackSelection.NoGeographicCoverage" in registry
    assert "RoutingPackSelection.NoCompatibleAccessMode" in registry
    assert "registry.select(request.points, request.profile.accessMode)" in engine
    assert "NO_COVERING_ROUTING_PACK" in engine
    assert "NO_COMPATIBLE_ROUTING_PACK" in engine


def test_multileg_route_is_graph_derived_bounded_and_preserves_identity() -> None:
    engine = (DEBUG_KOTLIN / "NativeRouteEngineFactory.kt").read_text()
    boundary = (KOTLIN / "NativeRouteEngine.kt").read_text()
    assert "request.points.map" in engine
    assert "RoutingWaypoint.Type.`break`" in engine
    assert "trip.legs.size != request.points.size - 1" in engine
    assert "joinLocalRouteLegGeometries" in engine
    assert "geometry += leg.drop(1)" in engine
    assert 'IllegalArgumentException("disconnected route legs")' in engine
    assert "profile = request.profile" in engine
    assert "packId = selectedPack.packId" in engine
    assert "snappedPoints = joinedGeometry.snappedPoints" in engine
    assert "MAX_LOCAL_ROUTE_VERTICES" in engine
    assert "MAX_LOCAL_ROUTE_REPLY_BYTES" in boundary
    assert "fetch(" not in engine
    assert "straight-line" not in engine.lower()


def test_capabilities_and_results_are_truthful_and_path_free() -> None:
    protocol = (KOTLIN / "BridgeProtocol.kt").read_text()
    boundary = (KOTLIN / "NativeRouteEngine.kt").read_text()
    for field in (
        '"installed_pack_ids"',
        '"supported_profile_ids"',
        '"pack_capabilities"',
        '"access_modes"',
        '"profile"',
        '"pack_id"',
        '"snapped_points"',
    ):
        assert field in protocol
    assert "supportedProfiles == LocalRouteProfile.entries.filter" in boundary
    assert "absolutePath" not in protocol
    assert 'NO_COMPATIBLE_ROUTING_PACK("no_compatible_routing_pack")' in boundary


def test_release_stays_unavailable_and_shared_bridge_security_is_unchanged() -> None:
    release = (RELEASE_KOTLIN / "NativeRouteEngineFactory.kt").read_text()
    activity = (KOTLIN / "MainActivity.kt").read_text()
    transport = (STATIC / "native_bridge_transport.js").read_text()
    assert "enabled = false" in release
    assert "packs = emptyList()" in release
    assert "supportedProfiles = emptyList()" in release
    assert "NativeRouteFailureCode.ROUTING_PACK_UNAVAILABLE" in release
    assert "com.valhalla" not in release
    combined = activity + release
    assert "addJavascriptInterface" not in combined
    assert "sourceOrigin.toString()," in activity
    assert "pendingLocalRoute !== operation" in activity
    assert "const pending = new Map()" in transport
    assert "cancelOwner" in transport


def test_debug_ui_and_harness_cover_profiles_via_and_compatibility() -> None:
    source = (STATIC / "local_routing.js").read_text()
    index = (STATIC / "index.html").read_text()
    harness = (
        ROOT / "tests/browser/pr34_local_routing_profiles_harness.js"
    ).read_text()
    for profile_id in PROFILE_IDS:
        assert f'"{profile_id}"' in source
        assert f'value="{profile_id}"' in index
    assert "LOCAL_ROUTE_VERSION = 2" in source
    assert "MAX_ROUTE_POINTS = 16" in source
    assert "MARLY_VIA_SMOKE_TEST" in source
    assert 'id="local-routing-profile"' in index
    assert 'id="local-routing-via-smoke-button"' in index
    assert "globalThis.fetch" not in source
    for scenario in (
        "strict_profile_and_pack_capabilities",
        "strict_v2_ordered_multi_point_wire",
        "via_route_preserves_public_profile",
        "incompatible_pack_failure_without_fetch",
    ):
        assert f'scenarios.push("{scenario}")' in harness


def test_docs_record_feasibility_limits_and_physical_acceptance() -> None:
    docs = (ROOT / "docs/pr34-local-routing-primitives-profiles.md").read_text()
    for marker in (
        "GraphHopper remains the reference backend",
        "trace_attributes",
        "edge or way identity",
        "mobile wrapper's public Kotlin/JNI surface",
        "missing edge identity and attributes must remain visibly unavailable",
        "PR34 passed physical acceptance on a Fairphone 6",
    ):
        assert marker in docs
