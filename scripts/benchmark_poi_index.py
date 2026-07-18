"""Benchmark lifespan-equivalent POI loading and representative viewport queries."""

import argparse
import resource
import statistics
import time
from pathlib import Path

from sugarglider.pois.index import PoiIndex, load_poi_index
from sugarglider.pois.models import PoiSearchRequest

VIEWPORTS: dict[str, tuple[float, float, float, float]] = {
    "Marly": (2.04, 48.80, 2.19, 48.94),
    "central Paris": (2.25, 48.80, 2.43, 48.91),
}


def _current_rss_kib() -> int | None:
    """Read Linux steady resident memory when available."""
    try:
        lines = Path("/proc/self/status").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("VmRSS:"):
            fields = line.split()
            return int(fields[1]) if len(fields) >= 2 else None
    return None


def _request(bounds: tuple[float, float, float, float]) -> PoiSearchRequest:
    west, south, east, north = bounds
    return PoiSearchRequest.model_validate(
        {
            "bbox": {
                "west": west,
                "south": south,
                "east": east,
                "north": north,
            },
            "groups": ["scenic", "hydration"],
            "potability": ["verified", "unknown"],
            "access": ["public", "restricted", "unknown"],
        }
    )


def _benchmark_viewport(
    index: PoiIndex,
    *,
    name: str,
    bounds: tuple[float, float, float, float],
    iterations: int,
    limit: int,
) -> None:
    request = _request(bounds)
    index.search(request, limit=limit)
    timings: list[float] = []
    response = None
    for _iteration in range(iterations):
        started = time.perf_counter()
        response = index.search(request, limit=limit)
        timings.append(time.perf_counter() - started)
    if response is None:
        raise RuntimeError("POI query benchmark did not run")
    print(f"{name} matches: {response.total_matching}")
    print(f"{name} returned: {response.returned_count}")
    print(f"{name} truncated: {response.truncated}")
    print(f"{name} median query: {statistics.median(timings) * 1000:.3f} ms")
    print(f"{name} maximum query: {max(timings) * 1000:.3f} ms")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark the local STRtree-backed regional POI index."
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=Path("data/pois/ile-de-france-poi-index.json.gz"),
    )
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--limit", type=int, default=1000)
    arguments = parser.parse_args()
    if arguments.iterations < 1:
        parser.error("--iterations must be positive")
    if arguments.limit < 1:
        parser.error("--limit must be positive")

    load_started = time.perf_counter()
    index = load_poi_index(arguments.index)
    load_elapsed = time.perf_counter() - load_started
    print(f"Index features: {index.metadata.feature_count}")
    print(f"Index load: {load_elapsed:.3f} s")
    current_rss_kib = _current_rss_kib()
    if current_rss_kib is not None:
        print(f"Process steady RSS after load: {current_rss_kib} KiB")
    measured_peak_rss_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_rss_kib = max(current_rss_kib or 0, measured_peak_rss_kib)
    print(f"Process peak RSS after load: {peak_rss_kib} KiB")
    print("Warm-up queries excluded: 1 per viewport")
    print(f"Measured queries: {arguments.iterations} per viewport")
    for name, bounds in VIEWPORTS.items():
        _benchmark_viewport(
            index,
            name=name,
            bounds=bounds,
            iterations=arguments.iterations,
            limit=arguments.limit,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
