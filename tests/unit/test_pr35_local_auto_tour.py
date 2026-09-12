"""Architecture and cross-language geometry contracts for PR35."""

import json
from math import isclose
from pathlib import Path
from typing import Any, cast

import pytest

from sugarglider.analysis.loop_geometry import LoopGeometryRouteAnalyzer
from sugarglider.analysis.route import project_geometry_edges
from sugarglider.domain.models import GeoJsonPosition

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src/sugarglider/web/static"
AUTO_TOUR = STATIC / "local_auto_tour.js"
FIXTURE = ROOT / "tests/fixtures/pr35_local_loop_geometry_golden.json"
PROFILE_IDS = (
    "trail_run",
    "hike",
    "city_bike",
    "gravel_bike",
    "mountain_bike",
    "road_bike",
)


def test_request_and_skeleton_search_are_strict_bounded_and_deterministic() -> None:
    source = AUTO_TOUR.read_text()
    for field in (
        "start",
        "target_distance_m",
        "tolerance_m",
        "candidate_count",
        "seed",
        "profile",
        "direction_preference",
    ):
        assert f'"{field}"' in source
    assert "exactFields(value, REQUEST_FIELDS)" in source
    assert "MIN_CANDIDATE_COUNT = 1" in source
    assert "MAX_CANDIDATE_COUNT = 3" in source
    assert "seededRandom(seed)" in source
    assert 'id: "triangle"' in source
    assert 'id: "asymmetric-triangle"' in source
    assert 'id: "diamond"' in source
    assert 'Object.freeze(["any", "clockwise", "counterclockwise"])' in source
    assert '"point_to_point"' not in source


def test_search_uses_only_pr34_routes_with_one_correction_and_strict_budget() -> None:
    source = AUTO_TOUR.read_text()
    local = (STATIC / "local_routing.js").read_text()
    transport = (STATIC / "native_bridge_transport.js").read_text()
    assert "LOCAL_AUTO_TOUR_ROUTE_CALL_BUDGET = 24" in source
    context = (STATIC / "local_planning_context.js").read_text()
    assert "state.context.totalUsed >= routeCallBudget" in source
    assert "totalLimit: routeCallBudget" in source
    assert "state.context.requestRoute(skeleton.points, phase)" in source
    assert "used >= totalLimit || phaseUsage[phase] >= limits[phase]" in context
    assert context.index("used += 1") < context.index(
        "route({ profile, points: coordinates })"
    )
    assert "await route(" not in source
    assert "MIN_CORRECTION_FACTOR = 0.7" in source
    assert "MAX_CORRECTION_FACTOR = 1.3" in source
    assert "skeleton.correction_step + 1" in source
    assert 'from "./local_routing.js"' in source
    assert 'from "./native_bridge_transport.js"' not in source
    assert "createLocalAutoTourExperiment" in local
    assert "const pending = new Map()" in transport
    assert "fetch(" not in source
    assert "generatePlan" not in source


def test_hard_validation_ranking_and_unavailable_metrics_are_truthful() -> None:
    source = AUTO_TOUR.read_text()
    for marker in (
        "HARD_START_SNAP_TOLERANCE_M = 25",
        "GENERATED_CONTROL_SNAP_TOLERANCE_M = 300",
        "hardMaximumDistance(request)",
        "snapped_point_count_mismatch",
        "profile_identity_mismatch",
        "pack_identity_changed_during_correction",
        "route_not_closed",
        "sampled_self_crossing_count",
        "sampled_outbound_return_proximity_share",
        "gross_immediate_reversal_share",
        "signed_area_compactness",
        "insufficient_geometry_diversity",
        "candidateRankKey",
        "exact_edge_repetition: null",
        "path_attributes: null",
        '"exact_edge_repetition_unavailable"',
        '"nature_analysis_unavailable"',
    ):
        assert marker in source


def test_normal_android_generate_uses_local_core_with_release_gate_retained() -> None:
    index = (STATIC / "index.html").read_text()
    app = (STATIC / "app.js").read_text()
    map_source = (STATIC / "map.js").read_text()
    release = (
        ROOT
        / "android/app/src/release/java/io/github/victorgabillon/sugarglider"
        / "NativeRouteEngineFactory.kt"
    ).read_text()
    for element_id in (
        "local-auto-tour-button",
        "local-auto-tour-smoke-button",
        "local-auto-tour-target-km",
        "local-auto-tour-tolerance-km",
        "local-auto-tour-candidate-count",
        "local-auto-tour-seed",
        "local-auto-tour-direction",
        "local-auto-tour-status",
        "local-auto-tour-results",
    ):
        assert f'id="{element_id}"' in index
    assert "Loop-only and bounded, with optional installed places/nature" in index
    assert "renderLocalAutoTourCandidates" in app
    assert "renderLocalAutoTourCandidates" in map_source
    assert "? await localPlanner.generate(request, state.abortController.signal)" in app
    assert ": await generatePlan(request, state.abortController.signal)" in app
    assert "const localPlanner = localRoutingBridge.nativeAvailable" in app
    assert "enabled = false" in release


def test_concurrency_harness_covers_single_flight_staleness_and_no_fallback() -> None:
    harness = (ROOT / "tests/browser/pr35_local_auto_tour_harness.js").read_text()
    html = (ROOT / "tests/browser/pr35_local_auto_tour_harness.html").read_text()
    assert harness.count('scenarios.push("') == 9
    for scenario in (
        "strict_request_and_six_profiles",
        "seeded_triangle_diamond_and_direction",
        "bounded_adaptation_and_deterministic_identity",
        "snap_route_and_cross_pack_rejection",
        "geometry_golden_and_structural_ranking",
        "diversity_and_unavailable_metrics",
        "duplicate_generation_is_single_flight",
        "stale_generation_cannot_render",
        "no_fetch_or_graphhopper_fallback",
    ):
        assert f'scenarios.push("{scenario}")' in harness
    assert "first === duplicate" in harness
    assert "maximumActiveRoutes" in harness
    assert "globalThis.fetch = async" in harness
    assert "runPr35LocalAutoTourHarness" in html


@pytest.mark.parametrize("fixture_id", ["square", "crossing", "narrow_hairpin"])
def test_geometry_golden_fixture_matches_python_server_analysis(
    fixture_id: str,
) -> None:
    fixtures = cast(list[dict[str, Any]], json.loads(FIXTURE.read_text()))
    fixture = next(value for value in fixtures if value["id"] == fixture_id)
    raw_geometry = cast(list[list[float]], fixture["geometry"])
    geometry: tuple[GeoJsonPosition, ...] = tuple(
        (float(position[0]), float(position[1])) for position in raw_geometry
    )
    route_distance_m = float(fixture["route_distance_m"])
    edges = project_geometry_edges(
        geometry=geometry,
        route_distance_m=route_distance_m,
        path_details={},
    ).edges
    analysis = LoopGeometryRouteAnalyzer().analyze_route(edges, route_distance_m)
    expected = cast(dict[str, object], fixture["expected"])

    assert analysis.closed is expected["closed"]
    assert analysis.self_crossing_count == expected["self_crossing_count"]
    assert isclose(
        analysis.angular_monotonicity,
        float(cast(float, expected["angular_monotonicity"])),
        rel_tol=0,
        abs_tol=1e-9,
    )
    if "compactness" in expected:
        assert analysis.compactness == pytest.approx(
            float(cast(float, expected["compactness"]))
        )
    if "outbound_return_proximity_share" in expected:
        assert analysis.outbound_return_proximity.share == pytest.approx(
            float(cast(float, expected["outbound_return_proximity_share"]))
        )


def test_documentation_records_physical_acceptance_and_limits_explicit() -> None:
    docs = (ROOT / "docs/pr35-local-auto-tour.md").read_text()
    for marker in (
        "Physical acceptance: **PASS on Fairphone 6**",
        "24 local-route calls",
        "one scale correction",
        "sampled geometric approximations",
        "Exact edge repetition remains unavailable",
        "GraphHopper remains the reference backend",
        "Point-to-point local Auto Tour is not implemented",
    ):
        assert marker in docs
