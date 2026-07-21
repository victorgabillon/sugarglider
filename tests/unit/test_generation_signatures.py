"""Stable route-signature behavior shared by planning modes."""

from sugarglider.domain.models import RouteResult
from sugarglider.planning.signatures import candidate_signature


def test_signature_is_deterministic(route_result: RouteResult) -> None:
    assert candidate_signature(route_result) == candidate_signature(
        route_result.model_copy(deep=True)
    )


def test_signature_falls_back_to_geometry_without_edge_ids(
    route_result: RouteResult,
) -> None:
    assert candidate_signature(route_result).startswith("geometry:")


def test_signature_separates_open_and_loop_topology(route_result: RouteResult) -> None:
    assert candidate_signature(route_result, topology="loop") != candidate_signature(
        route_result, topology="point_to_point"
    )
