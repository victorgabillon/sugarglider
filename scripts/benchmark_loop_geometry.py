"""Benchmark isolated loop-geometry analysis for the existing Marly route."""

import argparse
import json
import statistics
import time
from pathlib import Path
from urllib.request import Request, urlopen

from pydantic import ValidationError

from sugarglider.analysis.loop_geometry import LoopGeometryRouteAnalyzer
from sugarglider.analysis.route import project_geometry_edges
from sugarglider.domain.generation import RouteGenerationResult
from sugarglider.domain.models import RouteResult

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REQUEST_PATH = REPOSITORY_ROOT / "examples/marly/request.json"


def _saved_route(path: Path) -> RouteResult:
    payload = path.read_text(encoding="utf-8")
    try:
        generation = RouteGenerationResult.model_validate_json(payload)
    except ValidationError:
        return RouteResult.model_validate_json(payload)
    if not generation.candidates:
        raise ValueError("generation result contains no candidate")
    return generation.candidates[0].route


def _live_route(api_url: str, request_path: Path) -> RouteResult:
    request_payload = json.loads(request_path.read_text(encoding="utf-8"))
    request = Request(
        f"{api_url.rstrip('/')}/v1/routes",
        data=json.dumps(request_payload, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=180) as response:  # noqa: S310
        return RouteResult.model_validate_json(response.read())


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark loop-geometry analysis after one excluded warm-up run. "
            "By default the running API routes examples/marly/request.json once."
        )
    )
    parser.add_argument(
        "route_result_json",
        nargs="?",
        type=Path,
        help="optional saved RouteResult or RouteGenerationResult JSON",
    )
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--request", type=Path, default=DEFAULT_REQUEST_PATH)
    parser.add_argument("--iterations", type=int, default=20)
    arguments = parser.parse_args()
    if arguments.iterations < 1:
        parser.error("--iterations must be positive")

    route = (
        _saved_route(arguments.route_result_json)
        if arguments.route_result_json is not None
        else _live_route(arguments.api_url, arguments.request)
    )
    projection = project_geometry_edges(
        geometry=route.geometry,
        route_distance_m=route.summary.distance_m,
        path_details=route.path_details,
    )
    analyzer = LoopGeometryRouteAnalyzer()

    analyzer.analyze_route(projection.edges, route.summary.distance_m)
    timings: list[float] = []
    analysis = None
    for _iteration in range(arguments.iterations):
        started = time.perf_counter()
        analysis = analyzer.analyze_route(
            projection.edges,
            route.summary.distance_m,
        )
        timings.append(time.perf_counter() - started)
    if analysis is None:
        raise RuntimeError("benchmark did not run")

    print(f"Route: {route.name}")
    print(f"Route distance: {route.summary.distance_m:.1f} m")
    print(f"Geometry edges: {len(projection.edges)}")
    print(f"Shape penalty: {analysis.penalty_breakdown.total:.6f}")
    print(f"Compactness: {analysis.compactness:.6f}")
    print(f"Sector balance: {analysis.sector_balance:.6f}")
    print("Warm-up runs excluded: 1")
    print(f"Measured runs: {arguments.iterations}")
    print(f"Median analysis: {statistics.median(timings) * 1000:.2f} ms")
    print(f"Maximum analysis: {max(timings) * 1000:.2f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
