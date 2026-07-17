"""Stable signatures, exact dedup primitives, and edge-set diversity tests."""

from sugarglider.analysis.route import RouteAnalyzer
from sugarglider.domain.generation import GeneratedCandidate
from sugarglider.domain.models import PathDetailSegment, RouteResult, RouteSummary
from sugarglider.generation.scoring import score_route
from sugarglider.generation.signatures import (
    candidate_signature,
    jaccard_similarity,
    select_diverse_candidates,
)


def route_for_edges(edge_ids: list[int], *, coverage: float = 1.0) -> RouteResult:
    geometry = tuple((index * 0.001, 0.0) for index in range(len(edge_ids) + 1))
    details = {
        "edge_id": tuple(
            PathDetailSegment(from_index=index, to_index=index + 1, value=edge_id)
            for index, edge_id in enumerate(edge_ids)
        )
    }
    distance = float(len(edge_ids) * 100)
    analysis = RouteAnalyzer().analyze(geometry, distance, details)
    if coverage < 1:
        analysis = analysis.model_copy(
            update={
                "repetition": analysis.repetition.model_copy(
                    update={
                        "edge_id_coverage": (
                            analysis.repetition.edge_id_coverage.model_copy(
                                update={"share": coverage}
                            )
                        )
                    }
                )
            }
        )
    return RouteResult(
        name="candidate",
        summary=RouteSummary(
            distance_m=distance,
            duration_ms=1,
            input_point_count=2,
            routed_point_count=len(geometry),
        ),
        geometry=geometry,
        path_details=details,
        analysis=analysis,
    )


def candidate(route: RouteResult, signature: str | None = None) -> GeneratedCandidate:
    return GeneratedCandidate(
        rank=1,
        route=route,
        optional_points=(),
        required_point_order=(),
        routing_points=(),
        construction="direct_order",
        target_error_m=0,
        within_tolerance=True,
        score=score_route(route, route.summary.distance_m),
        signature=signature or candidate_signature(route),
    )


def test_edge_run_signature_is_stable_and_not_python_hash() -> None:
    route = route_for_edges([1, 1, 2, 1])
    first = candidate_signature(route)
    second = candidate_signature(route.model_copy(deep=True))
    assert first == second
    assert first.startswith("edges:")
    assert len(first.removeprefix("edges:")) == 64


def test_low_coverage_uses_rounded_geometry_fallback() -> None:
    route = route_for_edges([1, 2], coverage=0.5)
    assert candidate_signature(route).startswith("geometry:")


def test_jaccard_similarity() -> None:
    assert jaccard_similarity(frozenset({1, 2}), frozenset({2, 3})) == 1 / 3
    assert jaccard_similarity(frozenset(), frozenset()) == 1.0


def test_diversity_prefers_distinct_edge_sets() -> None:
    first = candidate(route_for_edges(list(range(20))), "first")
    similar = candidate(route_for_edges([*range(19), 99]), "similar")
    distinct = candidate(route_for_edges(list(range(100, 120))), "distinct")
    selection = select_diverse_candidates((first, similar, distinct), 2)
    assert [item.signature for item in selection.candidates] == ["first", "distinct"]
    assert not selection.relaxed


def test_diversity_can_fill_with_nonidentical_similar_candidate() -> None:
    first = candidate(route_for_edges(list(range(20))), "first")
    similar = candidate(route_for_edges([*range(19), 99]), "similar")
    selection = select_diverse_candidates((first, similar), 2)
    assert [item.signature for item in selection.candidates] == ["first", "similar"]
    assert selection.relaxed


def test_low_coverage_is_reported() -> None:
    low = candidate(route_for_edges([1, 2], coverage=0.5), "low")
    selection = select_diverse_candidates((low,), 1)
    assert selection.low_edge_coverage


def test_low_coverage_does_not_disable_diversity_for_well_covered_pairs() -> None:
    low = candidate(route_for_edges([500, 501], coverage=0.5), "low")
    first = candidate(route_for_edges(list(range(20))), "first")
    similar = candidate(route_for_edges([*range(19), 99]), "similar")
    distinct = candidate(route_for_edges(list(range(100, 120))), "distinct")

    selection = select_diverse_candidates((low, first, similar, distinct), 3)

    assert [item.signature for item in selection.candidates] == [
        "low",
        "first",
        "distinct",
    ]
    assert selection.low_edge_coverage
    assert not selection.relaxed
