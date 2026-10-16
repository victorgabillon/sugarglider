"""Reproducible offline filter/sampling sensitivity and analysis-only benchmark.

No candidate ranking or default selection uses these private-route results.
Median/deadband are comparison methods, not alternate production algorithms.
"""

import argparse
import gc
import json
import math
import platform
import statistics
import sys
import time
import tracemalloc
from itertools import pairwise
from pathlib import Path
from typing import TypedDict

from sugarglider.analysis.elevation import (
    MAX_ELEVATION_SAMPLES,
    ElevationParameters,
    ElevationProfile,
    ElevationSample,
    analyze_elevation,
)
from sugarglider.offline_regions.elevation_analysis import (
    load_native_profile,
    read_evidence,
)
from sugarglider.offline_regions.elevation_hgt_probe import probe_hgt_file
from sugarglider.offline_regions.native_height_experiment import (
    ResearchRoute,
    sample_routed_geometry,
)


class ChangeTotals(TypedDict):
    ascent_m: float
    descent_m: float


def change_totals(heights: list[float]) -> ChangeTotals:
    return {
        "ascent_m": math.fsum(max(0.0, b - a) for a, b in pairwise(heights)),
        "descent_m": math.fsum(max(0.0, a - b) for a, b in pairwise(heights)),
    }


def median_three(heights: list[float]) -> list[float]:
    """Symmetric index-based comparator; deliberately unsuitable for irregular x."""
    return [
        heights[0],
        *(
            float(statistics.median(heights[index - 1 : index + 2]))
            for index in range(1, len(heights) - 1)
        ),
        heights[-1],
    ]


def deadband_totals(heights: list[float], threshold_m: float) -> ChangeTotals:
    """Common causal counter: accept the whole change when it crosses a band.

    Terminal sub-threshold change is not credited. This can be direction biased
    and does not produce a consistent filtered profile: research comparator only.
    """
    previous = heights[0]
    accepted = [previous]
    for height in heights[1:]:
        if abs(height - previous) >= threshold_m:
            accepted.append(height)
            previous = height
    return change_totals(accepted)


def sensitivity(profile: ElevationProfile) -> dict[str, object]:
    heights = [point.height_m for point in profile.samples]
    if analyze_elevation(profile).coverage != "complete":
        raise ValueError("comparison study requires complete distance coverage")
    available = [height for height in heights if height is not None]
    box = []
    for radius in (0.0, 25.0, 50.0, 75.0, 100.0, 150.0, 250.0):
        result = analyze_elevation(
            profile, ElevationParameters(smoothing_radius_m=radius)
        )
        box.append(
            {
                "radius_m": radius,
                "ascent_m": result.total_ascent_m,
                "descent_m": result.total_descent_m,
                "coverage": result.coverage,
            }
        )
    return {
        "raw": change_totals(available),
        "distance_box": box,
        "median_three": change_totals(median_three(available)),
        "causal_deadband": [
            {
                "threshold_m": threshold,
                "forward": deadband_totals(available, threshold),
                "reverse": deadband_totals(list(reversed(available)), threshold),
            }
            for threshold in (1.0, 2.0, 3.0, 5.0, 10.0)
        ],
    }


def benchmark(
    profile: ElevationProfile, *, repetitions: int = 200
) -> dict[str, object]:
    if not 10 <= repetitions <= 1_000:
        raise ValueError("benchmark repetitions must be in [10, 1000]")
    for _ in range(10):
        analyze_elevation(profile)
    durations = []
    for _ in range(repetitions):
        started = time.perf_counter_ns()
        analyze_elevation(profile)
        durations.append((time.perf_counter_ns() - started) / 1_000_000)
    gc.collect()
    tracemalloc.start()
    try:
        analyze_elevation(profile)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {
        "samples": len(profile.samples),
        "repetitions": repetitions,
        "median_ms": statistics.median(durations),
        "p95_ms": sorted(durations)[math.ceil(len(durations) * 0.95) - 1],
        "minimum_ms": min(durations),
        "maximum_ms": max(durations),
        "peak_additional_python_bytes": peak,
    }


def _with_samples(
    original: ElevationProfile,
    samples: tuple[ElevationSample, ...],
    *,
    reference: str,
) -> ElevationProfile:
    return ElevationProfile(
        source_sha256=original.source_sha256,
        geometry_sha256=original.geometry_sha256,
        routing_profile=original.routing_profile,
        route_distance_m=original.route_distance_m,
        height_reference=reference,
        samples=samples,
    )


def sampling_study(profile: ElevationProfile) -> list[dict[str, object]]:
    """Native subsets, retaining endpoints; no terrain is invented between them."""
    rows: list[dict[str, object]] = []
    for stride in (1, 2, 4, 8):
        indices = list(range(0, len(profile.samples) - 1, stride))
        indices.append(len(profile.samples) - 1)
        source = _with_samples(
            profile,
            tuple(
                ElevationSample(
                    index=index,
                    distance_m=profile.samples[original].distance_m,
                    height_m=profile.samples[original].height_m,
                )
                for index, original in enumerate(indices)
            ),
            reference=f"native subset stride={stride}; sensitivity only",
        )
        result = analyze_elevation(source, ElevationParameters(maximum_gap_m=1_000))
        rows.append(
            {
                "stride": stride,
                "samples": len(source.samples),
                "maximum_gap_m": 1_000,
                "default_policy_coverage": analyze_elevation(source).coverage,
                "raw_ascent_m": result.raw_observed_ascent_m,
                "raw_descent_m": result.raw_observed_descent_m,
                "filtered_ascent_m": result.total_ascent_m,
                "filtered_descent_m": result.total_descent_m,
            }
        )
    return rows


def dem_sampling_study(
    profile: ElevationProfile, route: ResearchRoute, tile: Path
) -> list[dict[str, object]]:
    """Same-DEM interpolation, NOT a new native run or independent ground truth."""
    probe = probe_hgt_file(tile, profile.source_sha256)
    rows: list[dict[str, object]] = []
    for spacing in (12.5, 25.0, 50.0, 100.0, 200.0):
        points = sample_routed_geometry(route, spacing_m=spacing)
        source = _with_samples(
            profile,
            tuple(
                ElevationSample(
                    index=point.index,
                    distance_m=point.distance_m,
                    height_m=probe.sample(latitude=point.lat, longitude=point.lon),
                )
                for point in points
            ),
            reference=(
                "same HGT Python bilinear sampler; not native or independent truth"
            ),
        )
        result = analyze_elevation(source, ElevationParameters(maximum_gap_m=1_000))
        rows.append(
            {
                "spacing_m": spacing,
                "samples": len(source.samples),
                "maximum_gap_m": 1_000,
                "default_policy_coverage": analyze_elevation(source).coverage,
                "raw_ascent_m": result.raw_observed_ascent_m,
                "raw_descent_m": result.raw_observed_descent_m,
                "filtered_ascent_m": result.total_ascent_m,
                "filtered_descent_m": result.total_descent_m,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--native-result", type=Path, required=True)
    parser.add_argument("--csv", type=Path)
    parser.add_argument(
        "--tile", type=Path, help="optional checksum-pinned same-DEM study"
    )
    parser.add_argument("--repetitions", type=int, default=200)
    args = parser.parse_args()
    try:
        source = load_native_profile(
            profile=args.profile,
            plan=args.plan,
            route=args.route,
            native_result=args.native_result,
            csv_path=args.csv,
        )
        large = ElevationProfile(
            source_sha256="0" * 64,
            geometry_sha256="0" * 64,
            routing_profile="hike",
            route_distance_m=(MAX_ELEVATION_SAMPLES - 1) * 50.0,
            height_reference="synthetic maximum-budget benchmark",
            samples=tuple(
                ElevationSample(
                    index=index,
                    distance_m=index * 50.0,
                    height_m=100 + 50 * math.sin(index / 10),
                )
                for index in range(MAX_ELEVATION_SAMPLES)
            ),
        )
        report = {
            "publication_allowed": False,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "analysis": analyze_elevation(source).model_dump(mode="json"),
            "sensitivity": sensitivity(source),
            "native_decimation": sampling_study(source),
            "performance": [
                benchmark(profile, repetitions=args.repetitions)
                for profile in (source, large)
            ],
            "same_dem_resampling": dem_sampling_study(
                source,
                ResearchRoute.model_validate_json(read_evidence(args.route)),
                args.tile,
            )
            if args.tile
            else None,
        }
        print(json.dumps(report, indent=2, allow_nan=False))
    except (OSError, ValueError) as error:
        print(f"elevation study rejected: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
