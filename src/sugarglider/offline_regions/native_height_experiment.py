"""Offline research planning/comparison for native height, never route generation."""

import argparse
import hashlib
import json
import math
import sys
from itertools import accumulate, pairwise
from pathlib import Path
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.models import GeoJsonPosition, ImmutableModel, RoutingProfileId
from sugarglider.offline_regions.elevation_hgt_probe import HgtProbe, probe_hgt_file

MAX_GEOMETRY_VERTICES = 20_000
MAX_HEIGHT_SAMPLES = 2_048
MAX_INPUT_BYTES = 2 * 1024 * 1024


class ResearchModel(ImmutableModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class ResearchRoute(ResearchModel):
    routing_profile: RoutingProfileId
    distance_m: Annotated[float, Field(gt=0, le=200_000)]
    geometry: Annotated[
        tuple[GeoJsonPosition, ...],
        Field(min_length=2, max_length=MAX_GEOMETRY_VERTICES),
    ]


class HeightSamplePoint(ResearchModel):
    index: Annotated[int, Field(ge=0)]
    distance_m: Annotated[float, Field(ge=0)]
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]
    edge_index: Annotated[int, Field(ge=0)]
    edge_fraction: Annotated[float, Field(ge=0, le=1)]


class HeightPlan(ResearchModel):
    schema_version: Literal[1] = 1
    publication_allowed: Literal[False] = False
    routing_profile: RoutingProfileId
    route_distance_m: Annotated[float, Field(gt=0, le=200_000)]
    geometry_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    source_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    spacing_m: Annotated[float, Field(ge=1, le=1_000)]
    maximum_samples: Annotated[int, Field(ge=2, le=MAX_HEIGHT_SAMPLES)]
    points: Annotated[
        tuple[HeightSamplePoint, ...],
        Field(min_length=2, max_length=MAX_HEIGHT_SAMPLES),
    ]


def sample_routed_geometry(
    route: ResearchRoute,
    *,
    spacing_m: float = 50,
    maximum_samples: int = MAX_HEIGHT_SAMPLES,
) -> tuple[HeightSamplePoint, ...]:
    """Sample adjacent routed edges; retain the supplied route and its distance.

    Normalize edge lengths to backend total before choosing sample positions.
    Coordinates are quantized only in the independent height-request shape.
    No points/edges are added to, removed from, or replaced in the route itself.
    """
    if not math.isfinite(spacing_m) or not 1 <= spacing_m <= 1_000:
        raise ValueError("spacing must be finite and between 1 and 1000 m")
    if (
        type(maximum_samples) is not int
        or not 2 <= maximum_samples <= MAX_HEIGHT_SAMPLES
    ):
        raise ValueError("invalid sample budget")
    count = math.ceil(route.distance_m / spacing_m) + 1
    if count > maximum_samples:
        raise ValueError("sample budget exceeded; spacing was not silently changed")
    lengths = []
    for start, end in pairwise(route.geometry):
        if abs(end[0] - start[0]) > 180:
            raise ValueError("dateline-crossing research geometry is unsupported")
        lengths.append(haversine_distance_m(start, end))
    measured = sum(lengths)
    if measured <= 0:
        raise ValueError("degenerate routed geometry")
    normalized = [length * route.distance_m / measured for length in lengths]
    cumulative = [0.0, *accumulate(normalized)]
    cumulative[-1] = route.distance_m
    distances = [index * spacing_m for index in range(count - 1)]
    distances.append(route.distance_m)
    edge = 0
    points = []
    for index, distance in enumerate(distances):
        while edge < len(lengths) - 1 and cumulative[edge + 1] <= distance:
            edge += 1
        fraction = (
            min(1.0, max(0.0, (distance - cumulative[edge]) / normalized[edge]))
            if normalized[edge] > 0
            else 1.0
        )
        start, end = route.geometry[edge : edge + 2]
        coordinate = (
            route.geometry[0]
            if index == 0
            else route.geometry[-1]
            if index == count - 1
            else (
                start[0] + fraction * (end[0] - start[0]),
                start[1] + fraction * (end[1] - start[1]),
            )
        )
        points.append(
            HeightSamplePoint(
                index=index,
                distance_m=distance,
                lat=round(coordinate[1], 6),
                lon=round(coordinate[0], 6),
                edge_index=edge,
                edge_fraction=fraction,
            )
        )
    return tuple(points)


def height_plan(
    route: ResearchRoute,
    probe: HgtProbe,
    *,
    spacing_m: float = 50,
    maximum_samples: int = MAX_HEIGHT_SAMPLES,
) -> HeightPlan:
    geometry_bytes = json.dumps(route.geometry, separators=(",", ":")).encode()
    return HeightPlan(
        routing_profile=route.routing_profile,
        route_distance_m=route.distance_m,
        geometry_sha256=hashlib.sha256(geometry_bytes).hexdigest(),
        source_sha256=probe.source_sha256,
        spacing_m=spacing_m,
        maximum_samples=maximum_samples,
        points=sample_routed_geometry(
            route, spacing_m=spacing_m, maximum_samples=maximum_samples
        ),
    )


def compare_heights(
    plan: HeightPlan,
    heights: tuple[float | None, ...],
    probe: HgtProbe,
    *,
    # RapidJSON SetMaxDecimalPlaces truncates positive precision, so the
    # native precision=2 error is below 1 cm. Add 1 micrometre for numeric
    # effects. This verifies serialization, not DEM vertical accuracy.
    tolerance_m: float = 0.010001,
) -> dict[str, object]:
    if plan.source_sha256 != probe.source_sha256:
        raise ValueError("source identity mismatch")
    if len(heights) != len(plan.points):
        raise ValueError("native height count mismatch")
    if not math.isfinite(tolerance_m) or not 0 <= tolerance_m <= 1:
        raise ValueError("invalid comparison tolerance")
    samples: list[dict[str, object]] = []
    errors = []
    for point, native in zip(plan.points, heights, strict=True):
        expected = probe.sample(latitude=point.lat, longitude=point.lon)
        if (native is None) != (expected is None):
            raise ValueError("native/Python availability mismatch")
        error = None
        if native is not None and expected is not None:
            if not math.isfinite(native) or not -16_384 <= native <= 16_384:
                raise ValueError("invalid native height")
            error = abs(native - expected)
            if error > tolerance_m:
                raise ValueError(f"native/Python height error exceeds {tolerance_m} m")
            errors.append(error)
        samples.append(
            {
                **point.model_dump(),
                "height_m": native,
                "python_height_m": expected,
                "absolute_error_m": error,
            }
        )
    return {
        "format": "sugarglider-native-height-research-v1",
        "publication_allowed": False,
        "routing_profile": plan.routing_profile,
        "geometry_sha256": plan.geometry_sha256,
        "source_sha256": plan.source_sha256,
        "route_distance_m": plan.route_distance_m,
        "spacing_m": plan.spacing_m,
        "sample_count": len(samples),
        "available_count": len(errors),
        "unavailable_count": len(samples) - len(errors),
        "maximum_absolute_error_m": max(errors, default=None),
        "samples": samples,
    }


def _read(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("research input exceeds byte limit")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--route", type=Path, required=True)
    prepare.add_argument("--spacing-m", type=float, default=50)
    prepare.add_argument("--maximum-samples", type=int, default=MAX_HEIGHT_SAMPLES)
    compare = subparsers.add_parser("compare")
    compare.add_argument("--plan", type=Path, required=True)
    compare.add_argument("--native-result", type=Path, required=True)
    for command in (prepare, compare):
        command.add_argument("--tile", type=Path, required=True)
        command.add_argument("--sha256", required=True)
    args = parser.parse_args()
    try:
        probe = probe_hgt_file(args.tile, args.sha256)
        if args.operation == "prepare":
            route = ResearchRoute.model_validate_json(_read(args.route))
            plan = height_plan(
                route,
                probe,
                spacing_m=args.spacing_m,
                maximum_samples=args.maximum_samples,
            )
            print(plan.model_dump_json(indent=2))
        else:
            plan_bytes = _read(args.plan)
            plan = HeightPlan.model_validate_json(plan_bytes)
            result = NativeResearchResult.model_validate_json(_read(args.native_result))
            if result.source_sha256 != plan.source_sha256:
                raise ValueError("native source identity mismatch")
            if result.input_sha256 != hashlib.sha256(plan_bytes).hexdigest():
                raise ValueError("native input identity mismatch")
            print(json.dumps(compare_heights(plan, result.heights, probe), indent=2))
    except (OSError, ValueError) as error:
        print(f"native height research rejected: {error}", file=sys.stderr)
        return 1
    return 0


class NativeResearchResult(ResearchModel):
    source_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    input_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    heights: Annotated[
        tuple[float | None, ...], Field(min_length=2, max_length=MAX_HEIGHT_SAMPLES)
    ]


if __name__ == "__main__":
    raise SystemExit(main())
