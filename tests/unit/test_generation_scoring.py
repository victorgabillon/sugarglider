"""Exact PR3 score components and deterministic tolerance-first ranking."""

import pytest

from sugarglider.domain.analysis import DistanceMetric
from sugarglider.domain.generation import GeneratedCandidate
from sugarglider.domain.models import RouteResult
from sugarglider.generation.scoring import (
    is_natural_improvement,
    rank_candidates,
    rank_low_overlap_candidates,
    score_route,
)


def route_with_metrics(route: RouteResult, distance_m: float) -> RouteResult:
    metric = DistanceMetric
    analysis = route.analysis.model_copy(
        update={
            "route_distance_m": distance_m,
            "paved": metric(distance_m=distance_m * 0.3, share=0.3),
            "unpaved": metric(distance_m=distance_m * 0.3, share=0.3),
            "unknown_surface": metric(distance_m=distance_m * 0.4, share=0.4),
            "trail_like": metric(distance_m=distance_m * 0.5, share=0.5),
            "official_hiking_network": metric(distance_m=distance_m * 0.4, share=0.4),
            "major_road": metric(distance_m=distance_m * 0.1, share=0.1),
            "repetition": route.analysis.repetition.model_copy(
                update={
                    "repeated_distance": metric(distance_m=distance_m * 0.2, share=0.2)
                }
            ),
        }
    )
    return route.model_copy(
        update={
            "summary": route.summary.model_copy(update={"distance_m": distance_m}),
            "analysis": analysis,
        }
    )


def candidate(
    route: RouteResult,
    *,
    error: float,
    within: bool,
    signature: str,
    total_override: float | None = None,
) -> GeneratedCandidate:
    score = score_route(route, 1_000)
    if total_override is not None:
        score = score.model_copy(update={"total": total_override})
    return GeneratedCandidate(
        rank=1,
        route=route,
        optional_points=(),
        required_point_order=(),
        routing_points=(),
        construction="direct_order",
        target_error_m=error,
        within_tolerance=within,
        score=score,
        signature=signature,
    )


def test_fixed_score_exposes_every_weighted_component(
    route_result: RouteResult,
) -> None:
    route = route_with_metrics(route_result, 900.0)
    score = score_route(route, 1_000.0)
    assert score.distance_error_ratio == pytest.approx(0.1)
    assert score.repetition_penalty == pytest.approx(0.6)
    assert score.major_road_penalty == pytest.approx(0.2)
    assert score.paved_penalty == pytest.approx(0.3)
    assert score.unknown_surface_penalty == pytest.approx(0.1)
    assert score.trail_like_reward == pytest.approx(0.75)
    assert score.hiking_network_reward == pytest.approx(0.3)
    assert score.total == pytest.approx(1.15)


def test_within_tolerance_always_ranks_before_better_outside_score(
    route_result: RouteResult,
) -> None:
    route = route_with_metrics(route_result, 1_000.0)
    inside = candidate(
        route, error=100, within=True, signature="inside", total_override=100
    )
    outside = candidate(
        route, error=101, within=False, signature="outside", total_override=-100
    )
    ranked = rank_candidates((outside, inside))
    assert [item.signature for item in ranked] == ["inside", "outside"]
    assert [item.rank for item in ranked] == [1, 2]


def test_ranking_ties_use_error_then_signature(route_result: RouteResult) -> None:
    route = route_with_metrics(route_result, 1_000.0)
    candidates = (
        candidate(route, error=20, within=True, signature="b", total_override=1),
        candidate(route, error=10, within=True, signature="z", total_override=1),
        candidate(route, error=10, within=True, signature="a", total_override=1),
    )
    ranked = rank_candidates(candidates)
    assert [item.signature for item in ranked] == ["a", "z", "b"]


def test_lower_backtracking_wins_between_within_tolerance_candidates(
    route_result: RouteResult,
) -> None:
    route = route_with_metrics(route_result, 1_000.0)
    high_backtrack = route.model_copy(
        update={
            "analysis": route.analysis.model_copy(
                update={
                    "immediate_backtrack": DistanceMetric(distance_m=300, share=0.3)
                }
            )
        }
    )
    low_backtrack = route.model_copy(
        update={
            "analysis": route.analysis.model_copy(
                update={
                    "immediate_backtrack": DistanceMetric(distance_m=100, share=0.1)
                }
            )
        }
    )
    closer = candidate(
        high_backtrack,
        error=1,
        within=True,
        signature="closer",
        total_override=0,
    )
    natural = candidate(
        low_backtrack,
        error=100,
        within=True,
        signature="natural",
        total_override=10,
    )
    assert [item.signature for item in rank_candidates((closer, natural))] == [
        "natural",
        "closer",
    ]


def test_distance_pressure_leads_backtracking_outside_tolerance(
    route_result: RouteResult,
) -> None:
    close_route = route_with_metrics(route_result, 1_100.0)
    far_route = route_with_metrics(route_result, 1_500.0).model_copy(
        update={
            "analysis": route_with_metrics(route_result, 1_500.0).analysis.model_copy(
                update={"immediate_backtrack": DistanceMetric(distance_m=0, share=0)}
            )
        }
    )
    close = candidate(close_route, error=100, within=False, signature="close")
    far = candidate(far_route, error=500, within=False, signature="far")
    assert [item.signature for item in rank_candidates((far, close))] == [
        "close",
        "far",
    ]


def test_low_overlap_ranking_keeps_better_standard_repetition_first(
    route_result: RouteResult,
) -> None:
    base = route_with_metrics(route_result, 1_000.0)
    better = base.model_copy(
        update={
            "analysis": base.analysis.model_copy(
                update={
                    "repetition": base.analysis.repetition.model_copy(
                        update={
                            "repeated_distance": DistanceMetric(
                                distance_m=100, share=0.1
                            )
                        }
                    )
                }
            )
        }
    )
    worse = base.model_copy(
        update={
            "analysis": base.analysis.model_copy(
                update={
                    "repetition": base.analysis.repetition.model_copy(
                        update={
                            "repeated_distance": DistanceMetric(
                                distance_m=300, share=0.3
                            )
                        }
                    )
                }
            )
        }
    )
    standard = candidate(better, error=100, within=True, signature="standard")
    refined = candidate(worse, error=0, within=True, signature="refined")
    assert [
        item.signature for item in rank_low_overlap_candidates((refined, standard))
    ] == ["standard", "refined"]


def candidate_with_overlap(
    route_result: RouteResult,
    *,
    repetition: float,
    backtrack: float,
    signature: str,
) -> GeneratedCandidate:
    route = route_with_metrics(route_result, 1_000.0)
    analysis = route.analysis.model_copy(
        update={
            "repetition": route.analysis.repetition.model_copy(
                update={
                    "repeated_distance": DistanceMetric(
                        distance_m=1_000 * repetition,
                        share=repetition,
                    )
                }
            ),
            "immediate_backtrack": DistanceMetric(
                distance_m=1_000 * backtrack,
                share=backtrack,
            ),
        }
    )
    return candidate(
        route.model_copy(update={"analysis": analysis}),
        error=0,
        within=True,
        signature=signature,
    )


@pytest.mark.parametrize("backtrack", [0.1, 0.05])
def test_lower_repetition_with_equal_or_lower_backtracking_is_natural(
    route_result: RouteResult, backtrack: float
) -> None:
    source = candidate_with_overlap(
        route_result, repetition=0.3, backtrack=0.1, signature="source"
    )
    refined = candidate_with_overlap(
        route_result,
        repetition=0.2,
        backtrack=backtrack,
        signature="refined",
    )
    assert is_natural_improvement(refined, source)


@pytest.mark.parametrize(
    ("repetition", "backtrack"),
    [(0.2, 0.11), (0.31, 0.05)],
)
def test_one_metric_tradeoff_is_not_a_natural_improvement(
    route_result: RouteResult, repetition: float, backtrack: float
) -> None:
    source = candidate_with_overlap(
        route_result, repetition=0.3, backtrack=0.1, signature="source"
    )
    refined = candidate_with_overlap(
        route_result,
        repetition=repetition,
        backtrack=backtrack,
        signature="refined",
    )
    assert not is_natural_improvement(refined, source)


def test_natural_improvement_ties_remain_signature_deterministic(
    route_result: RouteResult,
) -> None:
    left = candidate_with_overlap(
        route_result, repetition=0.2, backtrack=0.1, signature="a"
    )
    right = candidate_with_overlap(
        route_result, repetition=0.2, backtrack=0.1, signature="b"
    )
    assert [item.signature for item in rank_low_overlap_candidates((right, left))] == [
        "a",
        "b",
    ]
