"""Geometry preference ordering below established route-quality priorities."""

from sugarglider.analysis.loop_geometry import score_loop_geometry
from sugarglider.domain.analysis import (
    DistanceMetric,
    LoopGeometryAnalysis,
    NatureAnalysis,
)
from sugarglider.domain.generation import GeneratedCandidate
from sugarglider.domain.models import RouteResult
from sugarglider.generation.scoring import (
    is_natural_improvement,
    rank_candidates,
    rank_low_overlap_candidates,
    score_route,
)
from sugarglider.nature.scoring import score_nature


def _candidate(
    route: RouteResult,
    *,
    signature: str,
    within: bool = True,
    error: float = 0,
) -> GeneratedCandidate:
    return GeneratedCandidate(
        rank=1,
        route=route,
        optional_points=(),
        required_point_order=(),
        routing_points=(),
        construction="direct_order",
        target_error_m=error,
        within_tolerance=within,
        score=score_route(route, 1_000),
        signature=signature,
    )


def _with_geometry(
    route: RouteResult,
    *,
    near_parallel_share: float,
    compactness: float = 1,
    sector_balance: float = 1,
    elongation: float = 1,
    crossings: int = 0,
) -> RouteResult:
    breakdown = score_loop_geometry(
        self_crossing_count=crossings,
        near_parallel_share=near_parallel_share,
        compactness=compactness,
        sector_balance=sector_balance,
        elongation=elongation,
    )
    geometry = LoopGeometryAnalysis(
        closed=True,
        start_end_gap_m=0,
        enclosed_area_m2=1,
        convex_hull_area_m2=1,
        compactness=compactness,
        sector_count=8,
        sector_distance_shares=(0.125,) * 8,
        sector_balance=sector_balance,
        maximum_sector_distance_share=0.125,
        occupied_sector_count=8,
        angular_monotonicity=1,
        mean_radius_m=1,
        max_radius_m=1,
        elongation=elongation,
        self_crossing_count=crossings,
        near_parallel=DistanceMetric(
            distance_m=route.summary.distance_m * near_parallel_share,
            share=near_parallel_share,
        ),
        outbound_return_proximity=DistanceMetric(distance_m=0, share=0),
        penalty_breakdown=breakdown,
        warnings=(),
    )
    return route.model_copy(
        update={
            "analysis": route.analysis.model_copy(update={"loop_geometry": geometry})
        }
    )


def _with_overlap(
    route: RouteResult, *, repetition: float, backtrack: float
) -> RouteResult:
    analysis = route.analysis.model_copy(
        update={
            "repetition": route.analysis.repetition.model_copy(
                update={
                    "repeated_distance": DistanceMetric(
                        distance_m=route.summary.distance_m * repetition,
                        share=repetition,
                    )
                }
            ),
            "immediate_backtrack": DistanceMetric(
                distance_m=route.summary.distance_m * backtrack,
                share=backtrack,
            ),
        }
    )
    return route.model_copy(update={"analysis": analysis})


def _with_nature(route: RouteResult, score_share: float) -> RouteResult:
    distance = route.summary.distance_m
    unknown_share = 1 - score_share
    breakdown = score_nature(
        woodland_share=score_share,
        open_natural_share=0,
        agriculture_share=0,
        park_or_protected_share=0,
        near_water_share=0,
        urban_share=0,
        unknown_share=unknown_share,
    )
    zero = DistanceMetric(distance_m=0, share=0)
    nature = NatureAnalysis(
        available=True,
        index_format_version=1,
        index_feature_count=1,
        woodland=DistanceMetric(distance_m=distance * score_share, share=score_share),
        open_natural=zero,
        agriculture=zero,
        water_crossing=zero,
        urban=zero,
        unknown_landcover=DistanceMetric(
            distance_m=distance * unknown_share, share=unknown_share
        ),
        park_or_protected=zero,
        near_water=zero,
        nature_score=breakdown.final_score,
        score_breakdown=breakdown,
        warnings=(),
    )
    return route.model_copy(
        update={"analysis": route.analysis.model_copy(update={"nature": nature})}
    )


def test_off_mode_preserves_existing_signature_tie_break(
    route_result: RouteResult,
) -> None:
    worse = _candidate(
        _with_geometry(route_result, near_parallel_share=0.8), signature="a"
    )
    better = _candidate(
        _with_geometry(route_result, near_parallel_share=0.1), signature="z"
    )
    assert [item.signature for item in rank_candidates((better, worse))] == ["a", "z"]


def test_geometry_breaks_equivalent_candidates_and_unknown_sorts_last(
    route_result: RouteResult,
) -> None:
    better = _candidate(
        _with_geometry(route_result, near_parallel_share=0.1), signature="better"
    )
    worse = _candidate(
        _with_geometry(route_result, near_parallel_share=0.8), signature="worse"
    )
    unknown = _candidate(route_result, signature="unknown")
    ranked = rank_candidates(
        (unknown, worse, better), loop_geometry_preference="prefer"
    )
    assert [item.signature for item in ranked] == ["better", "worse", "unknown"]


def test_geometry_preference_retains_stable_signature_tie_break(
    route_result: RouteResult,
) -> None:
    left = _candidate(
        _with_geometry(route_result, near_parallel_share=0.2), signature="a"
    )
    right = _candidate(
        _with_geometry(route_result, near_parallel_share=0.2), signature="z"
    )
    assert [
        item.signature
        for item in rank_candidates((right, left), loop_geometry_preference="prefer")
    ] == ["a", "z"]


def test_geometry_cannot_override_tolerance_backtracking_or_repetition(
    route_result: RouteResult,
) -> None:
    pretty = _candidate(
        _with_geometry(
            _with_overlap(route_result, repetition=0.2, backtrack=0.2),
            near_parallel_share=0,
        ),
        signature="pretty",
        within=False,
    )
    tolerated = _candidate(
        _with_geometry(
            _with_overlap(route_result, repetition=0.2, backtrack=0.2),
            near_parallel_share=1,
        ),
        signature="tolerated",
    )
    assert (
        rank_candidates((pretty, tolerated), loop_geometry_preference="prefer")[
            0
        ].signature
        == "tolerated"
    )

    less_backtrack = _candidate(
        _with_geometry(
            _with_overlap(route_result, repetition=0.2, backtrack=0.1),
            near_parallel_share=1,
        ),
        signature="less-backtrack",
    )
    assert (
        rank_candidates(
            (pretty.model_copy(update={"within_tolerance": True}), less_backtrack),
            loop_geometry_preference="prefer",
        )[0].signature
        == "less-backtrack"
    )

    less_repetition = _candidate(
        _with_geometry(
            _with_overlap(route_result, repetition=0.1, backtrack=0.2),
            near_parallel_share=1,
        ),
        signature="less-repetition",
    )
    assert (
        rank_candidates(
            (pretty.model_copy(update={"within_tolerance": True}), less_repetition),
            loop_geometry_preference="prefer",
        )[0].signature
        == "less-repetition"
    )


def test_low_overlap_keeps_repetition_before_geometry_and_backtracking(
    route_result: RouteResult,
) -> None:
    pretty = _candidate(
        _with_geometry(
            _with_overlap(route_result, repetition=0.2, backtrack=0),
            near_parallel_share=0,
        ),
        signature="pretty",
    )
    less_repetition = _candidate(
        _with_geometry(
            _with_overlap(route_result, repetition=0.1, backtrack=0.1),
            near_parallel_share=1,
        ),
        signature="less-repetition",
    )
    assert (
        rank_low_overlap_candidates(
            (pretty, less_repetition), loop_geometry_preference="prefer"
        )[0].signature
        == "less-repetition"
    )


def test_geometry_precedes_nature_and_nature_cannot_worsen_geometry(
    route_result: RouteResult,
) -> None:
    geometry_favoured = _candidate(
        _with_nature(
            _with_geometry(route_result, near_parallel_share=0.1),
            0,
        ),
        signature="geometry",
    )
    nature_favoured = _candidate(
        _with_nature(
            _with_geometry(route_result, near_parallel_share=0.8),
            1,
        ),
        signature="nature",
    )
    assert (
        rank_candidates(
            (nature_favoured, geometry_favoured),
            nature_preference="prefer",
            loop_geometry_preference="prefer",
        )[0].signature
        == "geometry"
    )


def test_better_geometry_cannot_bypass_low_overlap_natural_improvement_gate(
    route_result: RouteResult,
) -> None:
    source = _candidate(
        _with_geometry(
            _with_overlap(route_result, repetition=0.2, backtrack=0.05),
            near_parallel_share=1,
        ),
        signature="source",
    )
    refined = _candidate(
        _with_geometry(
            _with_overlap(route_result, repetition=0.1, backtrack=0.1),
            near_parallel_share=0,
        ),
        signature="prettier-refined",
    )
    refined_geometry = refined.route.analysis.loop_geometry
    source_geometry = source.route.analysis.loop_geometry
    assert refined_geometry is not None
    assert source_geometry is not None
    assert (
        refined_geometry.penalty_breakdown.total
        < source_geometry.penalty_breakdown.total
    )
    assert not is_natural_improvement(refined, source)
