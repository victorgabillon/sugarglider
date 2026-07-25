"""Structural dominance and the bounded public refinement reservation."""

from typing import cast

import pytest

from sugarglider.domain.analysis import RouteSpur, RouteSpurAnalysis
from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.planning.models import PLAN_REQUEST_ADAPTER, WaypointPlanRequest
from sugarglider.planning.pipeline import evaluate_candidate_portfolio
from sugarglider.planning.result import (
    PlanCandidate,
    PlanCandidateDiagnostics,
    PlanScore,
    PlanTraversal,
    PlanTraversalAnchor,
    ReachedPlanStop,
    TraversalAnchorKind,
)
from sugarglider.planning.structural import compare_structural_refinement
from sugarglider.pois.models import PoiApproachCandidate


def _request(route: RouteResult) -> WaypointPlanRequest:
    return cast(
        WaypointPlanRequest,
        PLAN_REQUEST_ADAPTER.validate_python(
            {
                "schema_version": 1,
                "kind": "waypoint_route",
                "name": "Structural portfolio",
                "topology": "point_to_point",
                "start": {
                    "lat": route.geometry[0][1],
                    "lon": route.geometry[0][0],
                },
                "end": {
                    "lat": route.geometry[-1][1],
                    "lon": route.geometry[-1][0],
                },
                "routing_profile": "hike",
                "candidate_count": 3,
                "seed": 7,
                "distance_objective": {
                    "target_m": 10_000,
                    "tolerance_m": 1_000,
                    "maximum_m": None,
                    "priority": "flexible",
                },
                "preferences": {
                    "nature": "off",
                    "loop_geometry": "off",
                    "path_selection": "shortest",
                },
                "waypoints": [],
                "waypoint_order": "fixed",
            }
        ),
    )


def _spur(
    *,
    spur_id: str = "spur/machine",
    name: str = "Machine de Marly",
    repeated_m: float = 1_500,
) -> RouteSpur:
    return RouteSpur(
        id=spur_id,
        kind="immediate_out_and_back",
        start_progress=0.2,
        turnaround_progress=0.4,
        end_progress=0.6,
        start_coordinate=(2.1, 48.87),
        turnaround_coordinate=(2.11, 48.871),
        end_coordinate=(2.1, 48.87),
        geometry=((2.1, 48.87), (2.11, 48.871), (2.1, 48.87)),
        outbound_distance_m=repeated_m,
        return_distance_m=repeated_m,
        repeated_distance_m=repeated_m,
        total_excursion_distance_m=2 * repeated_m,
        turnaround_connector_distance_m=0,
        maximum_separation_m=500,
        deliberate_stop_ids=("machine",),
        deliberate_stop_names=(name,),
        confidence="high",
        reason_codes=("contains_deliberate_stop",),
    )


def _route(
    base: RouteResult,
    *,
    distance_m: float,
    name: str,
    spurs: tuple[RouteSpur, ...] = (),
) -> RouteResult:
    spur_analysis = RouteSpurAnalysis(
        spurs=spurs,
        spur_count=len(spurs),
        total_excursion_distance_m=sum(
            spur.total_excursion_distance_m for spur in spurs
        ),
        total_repeated_distance_m=sum(spur.repeated_distance_m for spur in spurs),
        longest_spur_distance_m=max(
            (spur.total_excursion_distance_m for spur in spurs), default=0
        ),
    )
    return base.model_copy(
        update={
            "name": name,
            "summary": base.summary.model_copy(update={"distance_m": distance_m}),
            "analysis": base.analysis.model_copy(update={"spurs": spur_analysis}),
        }
    )


def _traversal(route: RouteResult, *, end_id: str = "endpoint/end") -> PlanTraversal:
    def anchor(
        anchor_id: str,
        name: str,
        kind: TraversalAnchorKind,
        progress: float,
        position: tuple[float, float],
    ) -> PlanTraversalAnchor:
        return PlanTraversalAnchor(
            id=anchor_id,
            name=name,
            kind=kind,
            routed_coordinate=Coordinate(lat=position[1], lon=position[0]),
            semantic_coordinate=Coordinate(lat=position[1], lon=position[0]),
            route_progress=progress,
            constraint_strength="exact",
            outcome="reached",
        )

    return PlanTraversal(
        direction="start_to_end",
        anchors=(
            anchor("endpoint/start", "Start", "start", 0, route.geometry[0]),
            anchor(end_id, "End", "end", 1, route.geometry[-1]),
        ),
    )


def _candidate(
    base: RouteResult,
    candidate_id: str,
    *,
    distance_m: float,
    backtracking_m: float,
    repetition_m: float | None = None,
    construction: str = "fixed_control",
    source_id: str | None = None,
    spurs: tuple[RouteSpur, ...] = (),
    target_error_m: float = 0,
    reached: tuple[ReachedPlanStop, ...] = (),
    end_id: str = "endpoint/end",
) -> PlanCandidate:
    route = _route(
        base,
        distance_m=distance_m,
        name=candidate_id,
        spurs=spurs,
    )
    details: dict[str, object] = {"construction": construction}
    if source_id is not None:
        details["source_candidate_id"] = source_id
    return PlanCandidate(
        id=candidate_id,
        kind="waypoint_route",
        topology="point_to_point",
        routing_profile="hike",
        rank=1,
        roles=(),
        route=route,
        score=PlanScore(total=target_error_m),
        traversal=_traversal(route, end_id=end_id),
        reached_stops=reached,
        diagnostics=PlanCandidateDiagnostics(
            safety_eligible=True,
            target_error_m=target_error_m,
            within_tolerance=target_error_m <= 1_000,
            requested_stop_count=sum(
                stop.selection_origin == "requested" for stop in reached
            ),
            immediate_backtracking_m=backtracking_m,
            repeated_distance_m=(
                backtracking_m if repetition_m is None else repetition_m
            ),
            spur_count=len(spurs),
            spur_repeated_distance_m=sum(spur.repeated_distance_m for spur in spurs),
            longest_spur_distance_m=max(
                (spur.total_excursion_distance_m for spur in spurs), default=0
            ),
            details=details,
        ),
    )


def _refinement_pair(
    route: RouteResult,
    *,
    source_distance_m: float = 10_000,
    distance_change_m: float = 500,
    source_backtracking_m: float = 1_000,
    resulting_backtracking_m: float = 200,
    construction: str = "edge_aware_global_optimization",
) -> tuple[PlanCandidate, PlanCandidate]:
    source = _candidate(
        route,
        "source",
        distance_m=source_distance_m,
        backtracking_m=source_backtracking_m,
    )
    refined = _candidate(
        route,
        "refined",
        distance_m=source_distance_m + distance_change_m,
        backtracking_m=resulting_backtracking_m,
        construction=construction,
        source_id=source.id,
        target_error_m=2_000,
    )
    return source, refined


def _requested_stop(route: RouteResult) -> ReachedPlanStop:
    coordinate = Coordinate(lat=route.geometry[0][1], lon=route.geometry[0][0])
    return ReachedPlanStop(
        id="machine",
        name="Machine de Marly",
        semantic_coordinate=coordinate,
        category="tourism_attraction",
        importance="prefer",
        selection_origin="requested",
        selection_method="already_reached",
        resolved_approach=PoiApproachCandidate(
            id="machine/approach",
            coordinate=coordinate,
            kind="exact_feature",
            source="imported_coordinate",
            access="public",
            semantic_distance_m=0,
            arrival_tolerance_m=25,
        ),
        route_progress=0,
        route_to_approach_m=0,
    )


def test_800_m_backtracking_reduction_with_500_m_extra_qualifies(
    route_result: RouteResult,
) -> None:
    source, refined = _refinement_pair(route_result)
    comparison = compare_structural_refinement(source, refined)
    assert comparison is not None
    assert comparison.structurally_dominant


def test_1500_m_spur_reduction_with_1800_m_extra_qualifies(
    route_result: RouteResult,
) -> None:
    spur = _spur()
    source = _candidate(
        route_result,
        "source",
        distance_m=40_000,
        backtracking_m=1_500,
        spurs=(spur,),
    )
    refined = _candidate(
        route_result,
        "refined",
        distance_m=41_800,
        backtracking_m=0,
        construction="edge_aware_global_optimization",
        source_id=source.id,
    )
    comparison = compare_structural_refinement(source, refined)
    assert comparison is not None
    assert comparison.structurally_dominant
    assert comparison.targeted_spur_names == ("Machine de Marly",)
    assert comparison.spur_repeated_distance_improvement_m == 1_500


def test_attempted_but_not_materially_improved_spur_is_absent_from_provenance(
    route_result: RouteResult,
) -> None:
    source_spur = _spur(repeated_m=1_500)
    residual_spur = _spur(repeated_m=1_100)
    source = _candidate(
        route_result,
        "source",
        distance_m=20_000,
        backtracking_m=1_500,
        spurs=(source_spur,),
    )
    refined = _candidate(
        route_result,
        "refined",
        distance_m=20_100,
        backtracking_m=0,
        spurs=(residual_spur,),
        construction="edge_aware_global_optimization",
        source_id=source.id,
    )

    comparison = compare_structural_refinement(source, refined)

    assert comparison is not None
    assert comparison.structurally_dominant
    assert comparison.targeted_spur_ids == ()
    assert comparison.targeted_spur_names == ()


def test_2500_m_extra_does_not_qualify(route_result: RouteResult) -> None:
    source, refined = _refinement_pair(
        route_result,
        source_distance_m=50_000,
        distance_change_m=2_500,
    )
    comparison = compare_structural_refinement(source, refined)
    assert comparison is not None
    assert not comparison.structurally_dominant
    assert comparison.exclusion_reason == "distance_increase_exceeded_rule"


def test_requested_coverage_regression_never_qualifies(
    route_result: RouteResult,
) -> None:
    stop = _requested_stop(route_result)
    source = _candidate(
        route_result,
        "source",
        distance_m=10_000,
        backtracking_m=1_000,
        reached=(stop,),
    )
    refined = _candidate(
        route_result,
        "refined",
        distance_m=10_100,
        backtracking_m=0,
        construction="edge_aware_global_optimization",
        source_id=source.id,
    )
    comparison = compare_structural_refinement(source, refined)
    assert comparison is not None
    assert comparison.exclusion_reason == "requested_coverage_regression"


def test_exact_failure_never_qualifies(route_result: RouteResult) -> None:
    source, refined = _refinement_pair(route_result)
    refined = refined.model_copy(
        update={"traversal": _traversal(refined.route, end_id="changed/end")}
    )
    comparison = compare_structural_refinement(source, refined)
    assert comparison is not None
    assert not comparison.exact_constraints_preserved
    assert comparison.exclusion_reason == "exact_constraints_not_preserved"


def test_severe_profile_regression_never_qualifies(
    route_result: RouteResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, refined = _refinement_pair(route_result)

    def quality(
        candidate_route: RouteResult,
    ) -> tuple[float, dict[str, float], bool]:
        return 0.0, {}, candidate_route.name == "refined"

    monkeypatch.setattr(
        "sugarglider.planning.structural.profile_quality_components", quality
    )
    comparison = compare_structural_refinement(source, refined)
    assert comparison is not None
    assert comparison.profile_regression
    assert comparison.exclusion_reason == "severe_profile_regression"


def test_best_structural_slot_is_rank_two_and_ignores_soft_target_error(
    route_result: RouteResult,
) -> None:
    source, refined = _refinement_pair(route_result)
    ordinary = (
        _candidate(
            route_result,
            "recommended",
            distance_m=10_000,
            backtracking_m=100,
            target_error_m=0,
        ),
        _candidate(
            route_result,
            "coverage",
            distance_m=10_000,
            backtracking_m=50,
            target_error_m=10,
        ),
        source,
    )
    second = refined.model_copy(
        update={
            "id": "second-refinement",
            "diagnostics": refined.diagnostics.model_copy(
                update={
                    "immediate_backtracking_m": 300,
                    "repeated_distance_m": 300,
                }
            ),
        }
    )
    portfolio = evaluate_candidate_portfolio(
        _request(route_result),
        (*ordinary, refined, second),
        limit=3,
    )
    assert portfolio.candidates[0].id == "recommended"
    structural = tuple(
        candidate
        for candidate in portfolio.candidates
        if "best_structural_refinement" in candidate.roles
    )
    assert len(structural) == 1
    assert structural[0].id == refined.id
    assert structural[0].rank == 2


def test_only_maximum_coverage_candidate_is_not_replaced(
    route_result: RouteResult,
) -> None:
    source, refined = _refinement_pair(route_result)
    recommended = _candidate(
        route_result,
        "recommended",
        distance_m=10_000,
        backtracking_m=100,
        target_error_m=0,
    )
    coverage = _candidate(
        route_result,
        "only-maximum-coverage",
        distance_m=10_000,
        backtracking_m=100,
        target_error_m=10,
        reached=(_requested_stop(route_result),),
    )

    portfolio = evaluate_candidate_portfolio(
        _request(route_result),
        (recommended, coverage, source, refined),
        limit=3,
        ranking_key=lambda candidate: (
            candidate.diagnostics.target_error_m,
            candidate.id,
        ),
    )

    assert tuple(candidate.id for candidate in portfolio.candidates) == (
        "recommended",
        "only-maximum-coverage",
        "refined",
    )
    assert "best_structural_refinement" in portfolio.candidates[2].roles


def test_composed_overall_and_novel_target_use_two_structural_slots(
    route_result: RouteResult,
) -> None:
    alpha = _spur(spur_id="spur/alpha", name="Alpha", repeated_m=1_500).model_copy(
        update={
            "start_progress": 0.1,
            "turnaround_progress": 0.2,
            "end_progress": 0.3,
            "deliberate_stop_ids": ("alpha",),
        }
    )
    beta = _spur(spur_id="spur/beta", name="Beta", repeated_m=1_200).model_copy(
        update={
            "start_progress": 0.4,
            "turnaround_progress": 0.5,
            "end_progress": 0.6,
            "deliberate_stop_ids": ("beta",),
        }
    )
    gamma = _spur(spur_id="spur/gamma", name="Gamma", repeated_m=900).model_copy(
        update={
            "start_progress": 0.7,
            "turnaround_progress": 0.8,
            "end_progress": 0.9,
            "deliberate_stop_ids": ("gamma",),
        }
    )
    source = _candidate(
        route_result,
        "source-three",
        distance_m=20_000,
        backtracking_m=3_600,
        repetition_m=3_600,
        spurs=(alpha, beta, gamma),
    )

    def refinement(
        candidate_id: str,
        remaining: tuple[RouteSpur, ...],
        backtracking_m: float,
    ) -> PlanCandidate:
        return _candidate(
            route_result,
            candidate_id,
            distance_m=20_500,
            backtracking_m=backtracking_m,
            repetition_m=sum(spur.repeated_distance_m for spur in remaining),
            construction="edge_aware_global_optimization",
            source_id=source.id,
            spurs=remaining,
            target_error_m=500,
        )

    composed = refinement("combined-alpha-beta", (gamma,), 500)
    alpha_only = refinement("alpha-only", (beta, gamma), 1_900)
    alpha_variant = refinement("alpha-variant", (beta, gamma), 2_000)
    gamma_only = refinement("gamma-only", (alpha, beta), 2_700)
    recommended = _candidate(
        route_result,
        "recommended",
        distance_m=20_000,
        backtracking_m=100,
        target_error_m=0,
    )

    portfolio = evaluate_candidate_portfolio(
        _request(route_result),
        (
            recommended,
            source,
            alpha_only,
            alpha_variant,
            gamma_only,
            composed,
        ),
        limit=3,
    )

    assert tuple(candidate.id for candidate in portfolio.candidates) == (
        "recommended",
        "combined-alpha-beta",
        "gamma-only",
    )
    assert "best_structural_refinement" in portfolio.candidates[1].roles
    assert "distinct_structural_refinement" in portfolio.candidates[2].roles
    assert portfolio.candidates[1].diagnostics.details["targeted_spur_names"] == (
        "Alpha",
        "Beta",
    )
    assert tuple(candidate.rank for candidate in portfolio.candidates) == (1, 2, 3)
    excluded = portfolio.best_excluded_structural_refinements
    assert len(excluded) <= 3
    excluded_sets = tuple(frozenset(value["targeted_spur_ids"]) for value in excluded)
    assert len(excluded_sets) == len(set(excluded_sets))
    repeated = evaluate_candidate_portfolio(
        _request(route_result),
        (
            recommended,
            source,
            alpha_only,
            alpha_variant,
            gamma_only,
            composed,
        ),
        limit=3,
    )
    assert tuple(candidate.id for candidate in repeated.candidates) == tuple(
        candidate.id for candidate in portfolio.candidates
    )


def test_best_excluded_summary_is_safe_and_deterministic(
    route_result: RouteResult,
) -> None:
    source, refined = _refinement_pair(route_result, distance_change_m=2_500)
    spur = _spur()
    source = source.model_copy(
        update={
            "route": _route(
                route_result,
                distance_m=10_000,
                name="source",
                spurs=(spur,),
            )
        }
    )
    refined = refined.model_copy(
        update={
            "diagnostics": refined.diagnostics.model_copy(
                update={
                    "details": {
                        "construction": "edge_aware_global_optimization",
                        "source_candidate_id": source.id,
                    }
                }
            )
        }
    )
    portfolio = evaluate_candidate_portfolio(
        _request(route_result), (source, refined), limit=1
    )
    summary = portfolio.best_excluded_refinement
    assert summary is not None
    assert summary["targeted_spur_names"] == ("Machine de Marly",)
    assert summary["reason_excluded"] == "distance_increase_exceeded_rule"
    assert not any("edge" in key for key in summary)


def test_global_optimizer_uses_structural_comparison(
    route_result: RouteResult,
) -> None:
    spur = _spur()
    source = _candidate(
        route_result,
        "source",
        distance_m=40_000,
        backtracking_m=1_500,
        spurs=(spur,),
    )
    refined = _candidate(
        route_result,
        "refined",
        distance_m=41_000,
        backtracking_m=0,
        construction="edge_aware_global_optimization",
        source_id=source.id,
    )
    comparison = compare_structural_refinement(source, refined)
    assert comparison is not None
    assert comparison.structurally_dominant
    assert comparison.targeted_spur_ids == (spur.id,)
