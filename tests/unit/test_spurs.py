"""Edge-based route-spur detection, mapping, and attribution tests."""

from math import inf

import pytest
from pydantic import ValidationError

from sugarglider.analysis.route import RouteAnalyzer, project_geometry_edges
from sugarglider.analysis.spurs import (
    SpurDetectionSettings,
    SpurTraversalAnchor,
    _directed_runs,
    _DirectedRun,
    _find_candidates,
    _normalize_candidates,
    _SpurCandidate,
    detect_route_spurs,
    spur_interval_geometry,
    spur_repair_priority,
)
from sugarglider.domain.analysis import RouteSpur, RouteSpurAnalysis
from sugarglider.domain.models import (
    GeoJsonPosition,
    PathDetailSegment,
    RouteResult,
    RouteSummary,
)
from sugarglider.gpx.writer import write_gpx
from sugarglider.planning.auto_tour.ranking import canonical_auto_tour_key
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.evaluator import CandidateEvaluator
from sugarglider.planning.models import PLAN_REQUEST_ADAPTER, PlanRequestBase
from sugarglider.planning.result import PlanScore


def route(
    geometry: tuple[GeoJsonPosition, ...],
    edge_ids: tuple[int | None, ...],
    *,
    edge_distance_m: float = 100.0,
) -> RouteResult:
    details = {
        "edge_id": tuple(
            PathDetailSegment(from_index=index, to_index=index + 1, value=edge_id)
            for index, edge_id in enumerate(edge_ids)
            if edge_id is not None
        )
    }
    distance_m = edge_distance_m * len(edge_ids)
    return RouteResult(
        name="Synthetic spur",
        routing_profile="hike",
        summary=RouteSummary(
            distance_m=distance_m,
            duration_ms=1,
            input_point_count=2,
            routed_point_count=len(geometry),
        ),
        geometry=geometry,
        path_details=details,
        analysis=RouteAnalyzer().analyze(geometry, distance_m, details),
    )


def simple_spur() -> RouteResult:
    # A-B-C-D-C-B-E: B-C-D-C-B is the complete excursion.
    return route(
        (
            (0.000, 0.0),
            (0.001, 0.0),
            (0.002, 0.0),
            (0.003, 0.0),
            (0.002, 0.0),
            (0.001, 0.0),
            (0.000, 0.0),
        ),
        (10, 20, 30, 30, 20, 40),
    )


def open_spur() -> RouteResult:
    return route(
        (
            (0.000, 0.0),
            (0.001, 0.0),
            (0.002, 0.0),
            (0.003, 0.0),
            (0.002, 0.0),
            (0.001, 0.0),
            (0.004, 0.0),
        ),
        (10, 20, 30, 30, 20, 40),
    )


def chained_overlap_spurs() -> RouteResult:
    # The middle 1 traversal is both the first spur's return and the second
    # spur's outbound run: [1, 2, 2, 1] and [1, 3, 3, 1].
    return route(
        (
            (0.000, 0.0),
            (0.001, 0.0),
            (0.002, 0.0),
            (0.001, 0.0),
            (0.000, 0.0),
            (-0.001, 0.0),
            (0.000, 0.0),
            (0.001, 0.0),
        ),
        (1, 2, 2, 1, 3, 3, 1),
    )


def internal_runs(
    distances_m: tuple[float, ...] = (100.0,) * 8,
) -> tuple[_DirectedRun, ...]:
    runs: list[_DirectedRun] = []
    progress_m = 0.0
    for index, distance_m in enumerate(distances_m):
        start = (index * 0.01, 0.0)
        end = ((index + 1) * 0.01, 0.0)
        runs.append(
            _DirectedRun(
                edge_id=index,
                edge_indices=(index,),
                start=start,
                end=end,
                distance_m=distance_m,
                start_distance_m=progress_m,
                end_distance_m=progress_m + distance_m,
                component=0,
            )
        )
        progress_m += distance_m
    return tuple(runs)


def internal_candidate(
    start_run: int,
    end_run: int,
) -> _SpurCandidate:
    return _SpurCandidate(
        start_run=start_run,
        turnaround_start_run=start_run,
        turnaround_end_run=end_run,
        end_run=end_run,
        outbound_runs=frozenset((start_run,)),
        return_runs=frozenset((end_run,)),
    )


class _Scorer:
    calls = 0

    def score(self, *, request: PlanRequestBase, draft: CandidateDraft) -> PlanScore:
        del request, draft
        self.calls += 1
        return PlanScore(total=0)


def plan_request(kind: str, route_result: RouteResult) -> PlanRequestBase:
    common = {
        "schema_version": 1,
        "kind": kind,
        "name": "Spur plan",
        "topology": "point_to_point",
        "start": {
            "lat": route_result.geometry[0][1],
            "lon": route_result.geometry[0][0],
        },
        "end": {
            "lat": route_result.geometry[-1][1],
            "lon": route_result.geometry[-1][0],
        },
        "routing_profile": "hike",
        "candidate_count": 1,
        "seed": 0,
        "distance_objective": {
            "target_m": 1_000,
            "tolerance_m": 500,
            "maximum_m": None,
            "priority": "flexible",
        },
    }
    specific = (
        {
            "preferences": {
                "nature": "off",
                "path_selection": "shortest",
                "scenic": "off",
                "drinking_water": "off",
                "loop_geometry": "off",
                "direction": "any",
            },
            "hard_waypoints": [],
            "requested_stops": [],
            "preferred_discovered_poi_ids": [],
            "free_poi_spur_physical_m": 200,
        }
        if kind == "auto_tour"
        else {
            "preferences": {
                "nature": "off",
                "path_selection": "shortest",
                "loop_geometry": "off",
            },
            "waypoints": [],
            "waypoint_order": "fixed",
        }
    )
    return PLAN_REQUEST_ADAPTER.validate_python({**common, **specific})


def test_simple_spur_maps_maximal_interval_and_aggregate_distance() -> None:
    result = detect_route_spurs(simple_spur(), topology="point_to_point")

    assert result.spur_count == 1
    spur = result.spurs[0]
    assert spur.kind == "immediate_out_and_back"
    assert spur.start_coordinate == (0.001, 0.0)
    assert spur.turnaround_coordinate == pytest.approx((0.003, 0.0))
    assert spur.end_coordinate == (0.001, 0.0)
    assert spur.start_progress == pytest.approx(1 / 6)
    assert spur.turnaround_progress == pytest.approx(3 / 6)
    assert spur.end_progress == pytest.approx(5 / 6)
    assert spur.outbound_distance_m == pytest.approx(200)
    assert spur.return_distance_m == pytest.approx(200)
    assert spur.repeated_distance_m == pytest.approx(200)
    assert spur.total_excursion_distance_m == pytest.approx(400)
    assert result.total_repeated_distance_m == pytest.approx(
        simple_spur().analysis.immediate_backtrack.distance_m
    )
    assert spur_interval_geometry(spur) == spur.geometry
    assert spur_repair_priority(spur)[0] == pytest.approx(-200)


def test_two_separate_spurs_remain_distinct_and_do_not_double_count() -> None:
    result = detect_route_spurs(
        route(
            (
                (0.000, 0.0),
                (0.001, 0.0),
                (0.002, 0.0),
                (0.001, 0.0),
                (0.000, 0.0),
                (-0.001, 0.0),
                (-0.002, 0.0),
                (-0.001, 0.0),
                (0.000, 0.0),
            ),
            (1, 2, 2, 3, 4, 5, 5, 6),
        )
    )

    assert result.spur_count == 2
    assert result.total_repeated_distance_m == pytest.approx(200)
    assert result.total_excursion_distance_m == pytest.approx(400)
    assert result.spurs[0].end_progress < result.spurs[1].start_progress


def test_independent_spurs_at_one_branch_remain_separate() -> None:
    result = detect_route_spurs(
        route(
            (
                (0.000, 0.0),
                (0.001, 0.0),
                (0.002, 0.0),
                (0.001, 0.0),
                (0.000, 0.0),
                (-0.001, 0.0),
                (-0.002, 0.0),
                (-0.001, 0.0),
                (0.000, 0.0),
            ),
            (1, 2, 2, 1, 3, 4, 4, 3),
        )
    )

    assert result.spur_count == 2
    assert result.total_repeated_distance_m == pytest.approx(400)
    assert result.spurs[0].end_progress == result.spurs[1].start_progress


def test_nested_reversed_intervals_merge_into_one_maximal_spur() -> None:
    result = detect_route_spurs(
        route(
            (
                (0.0, 0.0),
                (0.001, 0.0),
                (0.002, 0.0),
                (0.003, 0.0),
                (0.002, 0.0),
                (0.001, 0.0),
                (0.0, 0.0),
            ),
            (1, 2, 3, 3, 2, 1),
        )
    )

    assert result.spur_count == 1
    assert result.spurs[0].repeated_distance_m == pytest.approx(300)
    assert result.spurs[0].total_excursion_distance_m == pytest.approx(600)


def test_exact_real_chained_overlap_is_pruned_in_route_index_space() -> None:
    result = detect_route_spurs(chained_overlap_spurs())

    assert result.spur_count == 1
    assert result.total_repeated_distance_m == pytest.approx(200)
    assert result.total_excursion_distance_m == pytest.approx(400)
    assert result.warnings == ("overlapping_spur_evidence_pruned",)


def test_duplicate_internal_candidates_normalize_to_one() -> None:
    routed = simple_spur()
    projection = project_geometry_edges(
        geometry=routed.geometry,
        route_distance_m=routed.summary.distance_m,
        path_details=routed.path_details,
    )
    runs = _directed_runs(projection.edges)
    candidate = _find_candidates(runs, SpurDetectionSettings())[0]

    normalized = _normalize_candidates(
        (candidate, candidate), runs, SpurDetectionSettings(), 1.0
    )

    assert normalized.candidates == (candidate,)
    assert normalized.warnings == ()


def test_nested_internal_candidates_retain_the_maximal_excursion() -> None:
    runs = internal_runs()
    outer = _SpurCandidate(
        start_run=0,
        turnaround_start_run=2,
        turnaround_end_run=5,
        end_run=7,
        outbound_runs=frozenset((0, 1, 2)),
        return_runs=frozenset((5, 6, 7)),
    )
    inner = _SpurCandidate(
        start_run=1,
        turnaround_start_run=2,
        turnaround_end_run=5,
        end_run=6,
        outbound_runs=frozenset((1, 2)),
        return_runs=frozenset((5, 6)),
    )

    normalized = _normalize_candidates(
        (inner, outer), runs, SpurDetectionSettings(), 1.0
    )

    assert len(normalized.candidates) == 1
    retained = normalized.candidates[0]
    assert (retained.start_run, retained.end_run) == (0, 7)
    assert retained.outbound_runs == outer.outbound_runs
    assert retained.return_runs == outer.return_runs
    assert normalized.warnings == ()


def test_partially_crossing_shared_corridor_evidence_merges_without_double_count() -> (
    None
):
    runs = internal_runs((100.0,) * 10)
    earlier = _SpurCandidate(
        start_run=0,
        turnaround_start_run=2,
        turnaround_end_run=5,
        end_run=7,
        outbound_runs=frozenset((0, 1, 2)),
        return_runs=frozenset((5, 6, 7)),
    )
    later = _SpurCandidate(
        start_run=1,
        turnaround_start_run=3,
        turnaround_end_run=6,
        end_run=8,
        outbound_runs=frozenset((1, 2, 3)),
        return_runs=frozenset((6, 7, 8)),
    )

    normalized = _normalize_candidates(
        (later, earlier), runs, SpurDetectionSettings(), 1.0
    )

    assert len(normalized.candidates) == 1
    retained = normalized.candidates[0]
    assert (retained.start_run, retained.end_run) == (0, 8)
    assert retained.return_runs == frozenset((5, 6, 7, 8))
    assert sum(runs[index].distance_m for index in retained.return_runs) == 400
    assert normalized.warnings == ()


def test_weighted_portfolio_beats_naive_input_order_greedy_selection() -> None:
    runs = internal_runs((100.0, 100.0, 100.0, 100.0, 100.0, 300.0, 100.0, 100.0))
    early = internal_candidate(0, 3)
    valuable_middle = internal_candidate(2, 5)
    late = internal_candidate(4, 7)

    normalized = _normalize_candidates(
        (early, valuable_middle, late),
        runs,
        SpurDetectionSettings(),
        1.0,
    )

    assert normalized.candidates == (valuable_middle,)
    assert normalized.warnings == ("overlapping_spur_evidence_pruned",)


def test_normalization_is_stable_under_reversed_candidate_input() -> None:
    runs = internal_runs((100.0, 100.0, 100.0, 100.0, 100.0, 300.0, 100.0, 100.0))
    candidates = (
        internal_candidate(0, 3),
        internal_candidate(2, 5),
        internal_candidate(4, 7),
    )

    forward = _normalize_candidates(candidates, runs, SpurDetectionSettings(), 1.0)
    reversed_input = _normalize_candidates(
        tuple(reversed(candidates)), runs, SpurDetectionSettings(), 1.0
    )

    assert reversed_input == forward


def test_same_direction_reuse_is_not_a_spur() -> None:
    result = detect_route_spurs(
        route(
            ((0.0, 0.0), (0.001, 0.0), (0.002, 0.0), (0.0, 0.0), (0.001, 0.0)),
            (1, 2, 3, 1),
        )
    )
    assert result.spurs == ()


@pytest.mark.parametrize(
    "geometry",
    [
        ((0.0, 0.0), (0.001, 0.001), (0.0, 0.002), (-0.001, 0.001), (0.0, 0.0)),
        (
            (0.0, 0.0),
            (0.001, 0.001),
            (0.0, 0.0),
            (-0.001, 0.001),
            (0.0, 0.002),
        ),
    ],
)
def test_closed_loop_or_figure_eight_crossing_alone_is_not_a_spur(
    geometry: tuple[GeoJsonPosition, ...],
) -> None:
    assert detect_route_spurs(route(geometry, (1, 2, 3, 4))).spurs == ()


def test_repeated_loop_endpoint_spur_maps_the_complete_route_interval() -> None:
    result = detect_route_spurs(
        route(
            (
                (0.0, 0.0),
                (0.001, 0.0),
                (0.002, 0.0),
                (0.001, 0.0),
                (0.0, 0.0),
            ),
            (1, 2, 2, 1),
        ),
        topology="loop",
    )

    assert result.spur_count == 1
    assert result.spurs[0].start_progress == 0
    assert result.spurs[0].end_progress == 1
    assert "near_route_endpoint" in result.spurs[0].reason_codes
    assert "loop_closure_overlap" in result.spurs[0].reason_codes


def test_tiny_reversed_wiggle_stays_below_distance_threshold() -> None:
    tiny = route(((0.0, 0.0), (0.001, 0.0), (0.0, 0.0)), (1, 1), edge_distance_m=40)
    assert detect_route_spurs(tiny).spurs == ()


def test_long_exact_reversed_corridor_is_high_confidence() -> None:
    result = detect_route_spurs(
        route(
            (
                (0.0, 0.0),
                (0.001, 0.0),
                (0.002, 0.0),
                (0.001, 0.0),
                (0.0, 0.0),
            ),
            (1, 2, 2, 1),
            edge_distance_m=300,
        )
    )

    assert result.spurs[0].confidence == "high"
    assert "exact_corridor_return" in result.spurs[0].reason_codes


def test_short_turnaround_connector_is_tolerated() -> None:
    result = detect_route_spurs(
        route(
            (
                (0.0, 0.0),
                (0.001, 0.0),
                (0.002, 0.0),
                (0.0021, 0.0),
                (0.002, 0.0),
                (0.001, 0.0),
                (0.0, 0.0),
            ),
            (1, 2, 9, 10, 2, 1),
            edge_distance_m=20,
        ),
        settings=SpurDetectionSettings(minimum_reversed_edge_distance_m=40),
    )
    assert result.spur_count == 1
    assert result.spurs[0].turnaround_connector_distance_m > 0
    assert "turnaround_connector_present" in result.spurs[0].reason_codes


def test_turnaround_connector_expansion_cannot_publish_chained_overlap() -> None:
    routed = route(
        (
            (0.000, 0.0),
            (0.001, 0.0),
            (0.002, 0.0),
            (0.003, 0.0),
            (0.002, 0.0),
            (0.001, 0.0),
            (0.000, 0.0),
            (-0.001, 0.0),
            (-0.002, 0.0),
            (-0.001, 0.0),
            (0.000, 0.0),
            (0.001, 0.0),
        ),
        (1, 2, 8, 9, 2, 1, 3, 10, 11, 3, 1),
        edge_distance_m=20,
    )

    result = detect_route_spurs(
        routed,
        settings=SpurDetectionSettings(minimum_reversed_edge_distance_m=40),
    )

    assert result.spur_count == 1
    assert result.warnings == ("overlapping_spur_evidence_pruned",)
    assert "turnaround_connector_present" in result.spurs[0].reason_codes


def test_loop_closure_overlap_still_yields_a_valid_non_overlapping_portfolio() -> None:
    result = detect_route_spurs(chained_overlap_spurs(), topology="loop")

    assert result.spur_count == 1
    assert "loop_closure_overlap" in result.spurs[0].reason_codes
    RouteSpurAnalysis.model_validate(result.model_dump())


def test_disjoint_intervals_with_nearly_equal_progress_boundaries_stay_separate() -> (
    None
):
    routed = route(
        (
            (0.000, 0.0),
            (0.001, 0.0),
            (0.002, 0.0),
            (0.001, 0.0),
            (0.000, 0.0),
            (0.000000000001, 0.0),
            (-0.001, 0.0),
            (-0.002, 0.0),
            (-0.001, 0.0),
            (0.000000000001, 0.0),
        ),
        (1, 2, 2, 1, 99, 3, 4, 4, 3),
    )

    result = detect_route_spurs(routed)

    assert result.spur_count == 2
    boundary_gap = result.spurs[1].start_progress - result.spurs[0].end_progress
    assert 0 <= boundary_gap < 1e-8


def test_incomplete_edge_coverage_warns_and_never_claims_high_confidence() -> None:
    incomplete = route(
        (
            (-0.001, 0.0),
            (0.0, 0.0),
            (0.001, 0.0),
            (0.002, 0.0),
            (0.001, 0.0),
            (0.0, 0.0),
        ),
        (None, 1, 2, 2, 1),
    )
    result = detect_route_spurs(incomplete)
    assert result.spur_count == 1
    assert result.spurs[0].confidence == "low"
    assert "incomplete_edge_coverage" in result.spurs[0].reason_codes
    assert result.warnings == ("spur_edge_id_coverage_insufficient",)


def test_stop_attribution_is_ordered_and_excludes_incidental_places() -> None:
    anchors = (
        SpurTraversalAnchor("stop/late", "Late stop", 0.70),
        SpurTraversalAnchor("stop/outside", "Incidental nearby POI", 0.90),
        SpurTraversalAnchor("exact/inside", "Exact waypoint", 0.40),
        SpurTraversalAnchor("stop/approx", "Approximate target", 0.60),
    )
    spur = detect_route_spurs(simple_spur(), anchors).spurs[0]
    assert spur.deliberate_stop_ids == (
        "exact/inside",
        "stop/approx",
        "stop/late",
    )
    assert spur.deliberate_stop_names == (
        "Exact waypoint",
        "Approximate target",
        "Late stop",
    )


def test_stop_attribution_is_recomputed_after_ambiguous_overlap_pruning() -> None:
    result = detect_route_spurs(
        chained_overlap_spurs(),
        (
            SpurTraversalAnchor("first", "Retained stop", 0.20),
            SpurTraversalAnchor("second", "Pruned interpretation stop", 0.80),
        ),
    )

    assert result.spurs[0].deliberate_stop_ids == ("first",)
    assert result.spurs[0].deliberate_stop_names == ("Retained stop",)


def test_reversed_route_is_analyzed_independently_with_new_identity() -> None:
    forward = simple_spur()
    reversed_route = route(
        tuple(reversed(forward.geometry)),
        tuple(reversed((10, 20, 30, 30, 20, 40))),
    )
    original = detect_route_spurs(forward).spurs[0]
    reversed_spur = detect_route_spurs(
        reversed_route,
        (SpurTraversalAnchor("stop/reversed", "Reversed stop", 0.4),),
    ).spurs[0]
    assert reversed_spur.model_dump() != original.model_dump()
    assert reversed_spur.deliberate_stop_ids == ("stop/reversed",)


def test_duplicate_adjacent_points_do_not_break_progress_mapping() -> None:
    result = detect_route_spurs(
        route(
            ((0.0, 0.0), (0.001, 0.0), (0.001, 0.0), (0.0, 0.0)),
            (1, 9, 1),
            edge_distance_m=100,
        ),
        settings=SpurDetectionSettings(
            minimum_reversed_edge_distance_m=50,
            maximum_turnaround_connector_distance_m=150,
        ),
    )
    assert result.spur_count == 1
    assert 0 <= result.spurs[0].turnaround_progress <= 1


def test_spur_ids_and_serialization_are_deterministic() -> None:
    first = detect_route_spurs(simple_spur())
    second = detect_route_spurs(simple_spur())
    assert first.model_dump_json() == second.model_dump_json()
    assert first.spurs[0].id.startswith("spur-")


def test_public_spur_rejects_nonfinite_metrics_and_unknown_fields() -> None:
    valid = detect_route_spurs(simple_spur()).spurs[0]
    with pytest.raises(ValidationError):
        RouteSpur.model_validate({**valid.model_dump(), "maximum_separation_m": inf})
    with pytest.raises(ValidationError):
        RouteSpur.model_validate({**valid.model_dump(), "avoidable": True})


def test_retained_public_intervals_pass_the_strict_analysis_validator() -> None:
    result = detect_route_spurs(
        route(
            (
                (0.000, 0.0),
                (0.001, 0.0),
                (0.002, 0.0),
                (0.001, 0.0),
                (0.000, 0.0),
                (-0.001, 0.0),
                (-0.002, 0.0),
                (-0.001, 0.0),
                (0.000, 0.0),
            ),
            (1, 2, 2, 3, 4, 5, 5, 6),
        )
    )

    validated = RouteSpurAnalysis.model_validate(result.model_dump())

    assert all(
        earlier.end_progress <= later.start_progress
        for earlier, later in zip(validated.spurs, validated.spurs[1:], strict=False)
    )


def test_settings_are_frozen_and_validate_finite_thresholds() -> None:
    settings = SpurDetectionSettings()
    with pytest.raises(AttributeError):
        settings.minimum_edge_id_coverage = 0.5  # type: ignore[misc]
    with pytest.raises(ValueError):
        SpurDetectionSettings(maximum_branch_coordinate_gap_m=inf)


@pytest.mark.parametrize("kind", ["auto_tour", "waypoint_route"])
def test_shared_evaluator_exposes_spurs_for_both_planning_modes(kind: str) -> None:
    route_result = open_spur()
    request = plan_request(kind, route_result)
    scorer = _Scorer()
    candidate = CandidateEvaluator().evaluate(
        request=request,
        draft=CandidateDraft(
            route=route_result,
            routing_points=(request.start, request.effective_end),
            topology="point_to_point",
            construction="spur_test",
            search_family=("auto_tour" if kind == "auto_tour" else "waypoint_control"),
        ),
        scorer=scorer,
    )

    assert scorer.calls == 1
    assert candidate.route.analysis.spurs.spur_count == 1
    assert candidate.diagnostics.spur_count == 1
    assert candidate.diagnostics.spur_repeated_distance_m == pytest.approx(
        candidate.route.analysis.spurs.total_repeated_distance_m
    )
    assert candidate.diagnostics.longest_spur_distance_m == pytest.approx(
        candidate.route.analysis.spurs.longest_spur_distance_m
    )
    assert "spurs" in candidate.model_dump(mode="json")["route"]["analysis"]


def test_spur_metadata_does_not_change_ranking_or_gpx() -> None:
    route_result = open_spur()
    request = plan_request("auto_tour", route_result)
    candidate = CandidateEvaluator().evaluate(
        request=request,
        draft=CandidateDraft(
            route=route_result,
            routing_points=(request.start, request.effective_end),
            topology="point_to_point",
            construction="spur_test",
            search_family="auto_tour",
        ),
        scorer=_Scorer(),
    )
    without_spurs = candidate.model_copy(
        update={
            "route": candidate.route.model_copy(
                update={
                    "analysis": candidate.route.analysis.model_copy(
                        update={"spurs": route_result.analysis.spurs}
                    )
                }
            )
        }
    )
    assert canonical_auto_tour_key(candidate, "flexible") == canonical_auto_tour_key(
        without_spurs, "flexible"
    )
    assert write_gpx(candidate.route) == write_gpx(without_spurs.route)
