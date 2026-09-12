"""Cross-layer contracts for the debug-only shared local Waypoint Route core."""

import re
from pathlib import Path

from sugarglider.planning.models import DistanceObjective, WaypointPlanRequest
from sugarglider.planning.validation import EXACT_WAYPOINT_FIDELITY_M

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src/sugarglider/web/static"
CORE = STATIC / "local_waypoint_route.js"
HARNESS = ROOT / "tests/browser/pr38_local_waypoint_route_harness.js"


def _constant(source: str, name: str) -> int:
    match = re.search(rf"const {name} = ([\d_]+);", source)
    assert match is not None, name
    return int(match.group(1).replace("_", ""))


def test_local_endpoints_and_closure_follow_pr35_but_interiors_follow_canonical() -> (
    None
):
    source = CORE.read_text()
    auto_tour = (STATIC / "local_auto_tour.js").read_text()
    assert (
        _constant(source, "LOCAL_WAYPOINT_HARD_ENDPOINT_SNAP_TOLERANCE_M")
        == _constant(auto_tour, "HARD_START_SNAP_TOLERANCE_M")
        == 25
    )
    assert (
        _constant(source, "LOCAL_WAYPOINT_ROUTE_CLOSURE_TOLERANCE_M")
        == _constant(auto_tour, "ROUTE_CLOSURE_TOLERANCE_M")
        == 25
    )
    assert (
        _constant(source, "LOCAL_WAYPOINT_EXACT_INTERIOR_FIDELITY_M")
        == EXACT_WAYPOINT_FIDELITY_M
        == 300
    )
    assert "closureGap > LOCAL_WAYPOINT_ROUTE_CLOSURE_TOLERANCE_M" in source
    assert "snapped_waypoint_not_on_ordered_geometry" in source
    assert "geometry_vertex_index: cursor" in source
    assert "maximum_snap_distance_m: threshold" in source
    native = (
        ROOT
        / "android/app/src/main/java/io/github/victorgabillon/sugarglider"
        / "NativeRouteEngineFactory.kt"
    ).read_text()
    assert "snappedPoints += leg.last()" in native
    assert "disconnected route legs" in native


def test_local_point_limit_is_explicit_and_never_truncates_canonical_waypoints() -> (
    None
):
    source = CORE.read_text()
    primitive = (STATIC / "local_routing.js").read_text()
    maximum = _constant(source, "LOCAL_WAYPOINT_MAX_WAYPOINTS")
    assert maximum == _constant(primitive, "MAX_ROUTE_POINTS") - 2 == 14
    schema = WaypointPlanRequest.model_json_schema()
    assert schema["properties"]["waypoints"]["maxItems"] == 30
    assert "rawWaypoints.length + 2 > MAX_ROUTE_POINTS" in source
    assert 'fail("too_many_waypoints"' in source
    assert "original_waypoint_indices" in source
    assert "actual_waypoint_order" in source
    assert "waypoints.slice(" not in source


def test_distance_limits_and_canonical_supported_subset_remain_truthful() -> None:
    source = CORE.read_text()
    schema = DistanceObjective.model_json_schema()["properties"]
    assert (
        _constant(source, "LOCAL_WAYPOINT_MAX_DISTANCE_M")
        == schema["target_m"]["maximum"]
    )
    for code in (
        "unsupported_constraint_strength",
        "unsupported_approach_override",
        "unsupported_best_effort_bound",
        "unsupported_preference",
        "unsupported_flexible_maximum",
        "strict_distance_tolerance_missed",
        "maximum_distance_exceeded",
        "target_distance_missed",
    ):
        assert f'"{code}"' in source
    assert "Number.isSafeInteger(value.seed)" in source
    assert "fieldsAllowed(value, REQUEST_FIELDS)" in source
    assert "fieldsAllowed(point, WAYPOINT_FIELDS)" in source


def test_order_proposals_and_native_calls_are_strictly_bounded() -> None:
    source = CORE.read_text()
    auto_tour = (STATIC / "local_auto_tour.js").read_text()
    assert _constant(source, "LOCAL_WAYPOINT_ROUTE_CALL_BUDGET") == 16
    assert _constant(source, "LOCAL_WAYPOINT_ROUTE_CALL_BUDGET") <= _constant(
        auto_tour, "LOCAL_AUTO_TOUR_ROUTE_CALL_BUDGET"
    )
    assert _constant(source, "MAX_ORDER_PROPOSALS") == 16
    assert "seedShuffle(reversals, request.seed)" in source
    context = (STATIC / "local_planning_context.js").read_text()
    assert source.count('context.requestRoute(points, "waypoint")') == 1
    assert "await route(" not in source
    assert "totalLimit: routeCallBudget" in source
    assert "context.totalUsed >= routeCallBudget" in source
    assert context.index("used += 1") < context.index(
        "route({ profile, points: coordinates })"
    )
    assert "search_diagnostics: context.snapshot()" in source
    assert "unattempted_order_count" in source
    assert "Promise.all(" not in source
    assert "Math.random(" not in source


def test_result_reuses_native_reply_parser_without_a_second_transport_or_fallback() -> (
    None
):
    source = CORE.read_text()
    assert 'from "./local_routing.js"' in source
    assert "parseLocalRoutingReply(JSON.stringify(rawReply))" in source
    assert "geometry: reply.geometry" in source
    assert "routing_pack_identity_changed" in source
    for unavailable in (
        "exact_edge_repetition: null",
        "path_attributes: null",
        "nature_score: null",
        "poi_quality: null",
    ):
        assert unavailable in source
    for forbidden in (
        "fetch(",
        "generatePlan(",
        "native_bridge_transport",
        "sugargliderNative",
        "postMessage(",
        "selectRoutingPack",
        "setTimeout(",
    ):
        assert forbidden not in source


def test_lifecycle_retains_native_drain_and_request_identity_ownership() -> None:
    source = CORE.read_text()
    invalidate = source.split("function invalidate() {", 1)[1].split("\n  }", 1)[0]
    assert "generation += 1" in invalidate
    assert "active = null" not in invalidate
    assert "active.identity === identity" in source
    assert 'fail("local_generation_busy")' in source
    assert source.count("if (!owns(request, ownedGeneration)) return null") >= 3
    assert "ownedEpoch !== epoch" in source
    assert "validateLocalWaypointRouteRequest(getRequest())" in source


def test_current_intent_and_native_generate_use_the_shared_production_engine() -> None:
    app = (STATIC / "app.js").read_text()
    local = (STATIC / "local_routing.js").read_text()
    index = (STATIC / "index.html").read_text()
    release = (
        ROOT
        / "android/app/src/main/java/io/github/victorgabillon/sugarglider"
        / "NativeRouteEngineFactory.kt"
    ).read_text()
    assert "readLocalWaypointRouteRequest" not in app
    assert "invalidateLocalWaypointRoute" not in app
    assert "? await localPlanner.generate(request, state.abortController.signal)" in app
    assert "profileAvailable: Boolean(selectedProfileStatus()?.available)" in app
    assert "Server Generate remains unavailable" in app
    assert "onCapabilities(capabilities)" in local
    assert "if (!capabilities.enabled) return false" in local
    assert ": await generatePlan(request, state.abortController.signal)" in app
    assert "const localPlanner = isBundledAndroidApp()" in app
    assert "createLocalPlanner({ withRegion: withPlanningRegion })" in app
    assert "enabled = true" in release
    for element in ("button", "status", "results"):
        assert f'id="local-waypoint-route-{element}"' in index
    assert "Route ordered planner points locally" in index
    assert "Generate experimental Local Waypoint Route from planner" in index


def test_ui_request_getter_is_read_only_and_shares_existing_serialization() -> None:
    source = CORE.read_text()
    app = (STATIC / "app.js").read_text()
    state = (STATIC / "state.js").read_text()
    getter = source.split("export function readLocalWaypointRouteRequest(", 1)[1].split(
        "\n}", 1
    )[0]
    assert "readPlannerOptionsFromControls(byId)" in getter
    assert "waypointPlanRequestSnapshot({" in getter
    assert "updateOptionsFromControls(" not in getter
    assert "currentPlanRequest(" not in getter
    assert "state.plan =" not in getter
    assert "state.options = readPlannerOptionsFromControls(byId)" in app
    assert "function commonPlanState(endpoints, planner = state)" in state
    assert "waypointPlanState(planner.points, planner.options)" in state
    assert "waypointPlanState(state.points, state.options)" in state
    snapshot = state.split("export function waypointPlanRequestSnapshot(", 1)[1].split(
        "\n}", 1
    )[0]
    assert "saveActivePoints(" not in snapshot
    assert "setRouteTopology(" not in snapshot
    assert "state.plan =" not in snapshot
    harness = HARNESS.read_text()
    for scenario in (
        "hard_start_25m_boundary",
        "hard_point_to_point_end_25m_boundary",
        "hard_loop_return_25m_boundary",
        "graph_derived_loop_closure",
        "exact_waypoint_300m_boundary",
        "readonly_ui_rejection_preserves_shared_state_and_controls",
        "readonly_ui_supported_snapshot_preserves_shared_state_and_controls",
        "readonly_ui_never_normalizes_unsupported_intent",
    ):
        assert scenario in harness
    assert "readLocalWaypointRouteRequest(state, (id) => controls.get(id))" in harness


def test_waypoint_rendering_has_its_own_layers_and_preserves_existing_overlays() -> (
    None
):
    source = (STATIC / "map.js").read_text()
    assert 'LOCAL_WAYPOINT_ROUTE_PREFIX = "local-waypoint-route-experiment-"' in source
    renderer = source.split("export function renderLocalWaypointRouteCandidates(", 1)[
        1
    ].split("\n}", 1)[0]
    assert "clearLocalWaypointRouteCandidates();" in renderer
    assert "renderLocalCandidateLayers(" in renderer
    assert "clearRoutes(" not in renderer
    assert "clearLocalExperimentalRoute(" not in renderer
    clearer = source.split("export function clearLocalWaypointRouteCandidates()", 1)[
        1
    ].split("\n}", 1)[0]
    assert "clearByPrefix(LOCAL_WAYPOINT_ROUTE_PREFIX)" in clearer
    assert "LOCAL_AUTO_TOUR_PREFIX" not in clearer


def test_offline_module_is_precached_in_exactly_v28_and_harness_is_local() -> None:
    worker = (STATIC / "service-worker.js").read_text()
    assert "`${SHELL_CACHE_PREFIX}v41`" in worker
    assert '"/static/local_waypoint_route.js"' in worker
    html = HARNESS.with_suffix(".html").read_text()
    harness = HARNESS.read_text()
    references = re.findall(r'from "([^"]+)"', html + harness)
    for reference in references:
        assert reference.startswith(".")
        assert (HARNESS.parent / reference).is_file()
    assert 'addEventListener("unhandledrejection"' in html
    assert 'addEventListener("error"' in html
    assert "setTimeout(" not in harness
    assert "data/routing-packs/" not in harness
    assert "data/map-packs/" not in harness


def test_documentation_keeps_unsupported_semantics_and_physical_status_explicit() -> (
    None
):
    document = (ROOT / "docs/pr38-local-waypoint-route.md").read_text()
    for marker in (
        "14 interior waypoints",
        "16 local-route calls",
        "300 m",
        "25 m",
        "200 km",
        "approach",
        "best_effort",
        "approach_override",
        "PR39",
        "PR40",
        "PR41",
        "no GraphHopper parity",
        "no cross-pack stitching",
        "v22",
        "hotspot",
    ):
        assert marker in document
    acceptance = document.split("## Fairphone physical acceptance\n", 1)[1]
    assert (
        "Fairphone 6 backend-isolated physical acceptance: PASS"
        in acceptance.splitlines()
    )
    assert "PENDING" not in document
    # Pin the observed outcomes and scoped claim, not just a generic PASS token.
    for row in (
        "| Fixed local Waypoint Route | PASS; 7.677 km; "
        "exactly 1 native `local_route` call. |",
        "| Optimized local Waypoint Route | PASS; 2 / 16 native calls; "
        "identical repeat preserved candidate IDs, order and recommendation. |",
        "| `hike` loop | PASS; graph-derived closure gap 0 m. |",
        "| `gravel_bike` loop | PASS; graph-derived closure gap 0 m. |",
        "| Marly → Paris → Marly | PASS; native pack identities "
        "`marly-dev-v1` → `paris-dev-v1` → `marly-dev-v1`. |",
        "| Cross-pack request | Explicit `no_covering_routing_pack`; "
        "no stitching or fallback. |",
        "| Unsupported `low_overlap` preference | Explicit "
        "`unsupported_preference`; zero native route calls; "
        "normal planner state preserved. |",
    ):
        assert row in acceptance.splitlines()
    prose = " ".join(acceptance.split())
    for claim in (
        "The hotspot remained enabled because it provides Internet "
        "to the development computer.",
        "Endpoint and loop-return snaps and graph-derived closure satisfied "
        "the <=25 m requirements; exact interior waypoint snaps satisfied "
        "the <=300 m requirement.",
        "Zero Sugarglider backend routing/generation requests were observed "
        "during local Waypoint Route generation.",
        "No production defect was demonstrated.",
        "This acceptance shows that PR38 local Waypoint Route generation "
        "does not require the Sugarglider routing/generation backend "
        "in the exercised cases.",
        "This was not a radios-off acceptance, zero-network acceptance, "
        "production/release acceptance, or GraphHopper parity demonstration.",
    ):
        assert claim in prose
