"""Measure local index loading and isolated nature attribution for a saved route."""

import argparse
import statistics
import time
from pathlib import Path

from pydantic import ValidationError

from sugarglider.analysis.route import project_geometry_edges
from sugarglider.domain.models import RouteResult
from sugarglider.nature.analysis import NatureRouteAnalyzer
from sugarglider.nature.index import load_nature_index
from sugarglider.planning.result import PlanResult


def _route(path: Path) -> RouteResult:
    payload = path.read_text(encoding="utf-8")
    try:
        plan = PlanResult.model_validate_json(payload)
    except ValidationError:
        return RouteResult.model_validate_json(payload)
    if not plan.candidates:
        raise ValueError("plan result contains no candidate")
    return plan.candidates[0].route


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark STRtree-backed nature analysis for a saved route result."
    )
    parser.add_argument("route_result_json", type=Path)
    parser.add_argument(
        "--index",
        type=Path,
        default=Path("data/nature/ile-de-france-nature-index.json.gz"),
    )
    parser.add_argument("--water-buffer-m", type=float, default=100)
    parser.add_argument("--iterations", type=int, default=10)
    arguments = parser.parse_args()
    if arguments.iterations < 1:
        parser.error("--iterations must be positive")

    load_started = time.perf_counter()
    index = load_nature_index(arguments.index)
    analyzer = NatureRouteAnalyzer(
        index,
        water_buffer_m=arguments.water_buffer_m,
    )
    load_elapsed = time.perf_counter() - load_started
    route = _route(arguments.route_result_json)
    edges = project_geometry_edges(
        geometry=route.geometry,
        route_distance_m=route.summary.distance_m,
        path_details=route.path_details,
    ).edges
    timings: list[float] = []
    result = None
    for _iteration in range(arguments.iterations):
        started = time.perf_counter()
        result = analyzer.analyze_route(edges, route.summary.distance_m)
        timings.append(time.perf_counter() - started)
    if result is None:
        raise RuntimeError("benchmark did not run")
    print(f"Index features: {index.metadata.feature_count}")
    print(f"Index load: {load_elapsed:.3f} s")
    print(f"Route distance: {route.summary.distance_m:.1f} m")
    print(f"Geometry edges: {len(edges)}")
    print(f"Nature score: {result.nature_score:.1f}/100")
    print(f"Median analysis: {statistics.median(timings) * 1000:.2f} ms")
    print(f"Maximum analysis: {max(timings) * 1000:.2f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
