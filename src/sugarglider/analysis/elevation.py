"""Optional, immutable elevation analysis; no routing, terrain IO or GPX changes.

The distance box integrates the piecewise-linear height signal in metres, not
sample indices. Constant extension at each covered run's ends and retaining its
original endpoints make the filter reversal symmetric and variation diminishing.
Unknown samples and excessive spacing always break runs, even inside a window.
"""

import hashlib
import math
import struct
from bisect import bisect_left, bisect_right
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sugarglider.domain.models import RoutingProfileId

MAX_ELEVATION_SAMPLES = 2_048  # PR88 native request budget; never silently resample.
ALGORITHM_VERSION: Literal["distance-box-v1"] = "distance-box-v1"
NUMERICAL_TOLERANCE_M = 1e-7

type Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
type Height = Annotated[float, Field(ge=-16_384, le=16_384)]
type Distance = Annotated[float, Field(ge=0, le=200_000)]


class ElevationModel(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", allow_inf_nan=False, strict=True
    )


class ElevationSample(ElevationModel):
    index: Annotated[int, Field(ge=0)]
    distance_m: Distance
    height_m: Height | None


class ElevationProfile(ElevationModel):
    """Caller supplies heights already bound to this exact route and DEM source.

    Repeated coordinates are fine; duplicate or decreasing progress is not.
    Zero and negative heights are real data. Neither means missing.
    """

    schema_version: Literal[1] = 1
    source_sha256: Digest
    geometry_sha256: Digest
    routing_profile: RoutingProfileId
    route_distance_m: Annotated[float, Field(gt=0, le=200_000)]
    height_reference: Annotated[str, Field(min_length=1, max_length=200)]
    samples: Annotated[
        tuple[ElevationSample, ...],
        Field(min_length=2, max_length=MAX_ELEVATION_SAMPLES),
    ]

    @model_validator(mode="after")
    def validate_progress(self) -> Self:
        if self.samples[0].distance_m != 0:
            raise ValueError("elevation must begin at route distance zero")
        if self.samples[-1].distance_m != self.route_distance_m:
            raise ValueError("elevation endpoint does not match route distance")
        previous = -1.0
        for index, point in enumerate(self.samples):
            if point.index != index or point.distance_m <= previous:
                raise ValueError("elevation indices/progress must be strictly ordered")
            previous = point.distance_m
        return self


class ElevationParameters(ElevationModel):
    """Versioned policy, in physical units; thresholds are never density derived."""

    smoothing_radius_m: Annotated[float, Field(ge=0, le=500)] = 50.0
    maximum_gap_m: Annotated[float, Field(gt=0, le=1_000)] = 100.0
    boundary_policy: Literal["constant-extension-retain-endpoints"] = (
        "constant-extension-retain-endpoints"
    )
    missing_policy: Literal["split-no-fill"] = "split-no-fill"

    @model_validator(mode="after")
    def validate_radius(self) -> Self:
        if 0 < self.smoothing_radius_m < 1:
            raise ValueError("smoothing radius must be zero or at least one metre")
        return self


class FilteredElevationSample(ElevationSample):
    filtered_height_m: Height | None
    segment_index: int | None


class ElevationSegment(ElevationModel):
    """Inclusive sample indices, including isolated available samples."""

    first_index: int
    last_index: int
    distance_m: float


class ElevationAnalysis(ElevationModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["distance-box-v1"] = ALGORITHM_VERSION
    parameters: ElevationParameters
    source_sha256: Digest
    geometry_sha256: Digest
    profile_sha256: Digest
    routing_profile: RoutingProfileId
    route_distance_m: float
    height_reference: str
    coverage: Literal["complete", "partial", "unavailable"]
    available_sample_count: int
    analyzed_distance_m: float
    unknown_distance_m: float
    # Partial values describe covered runs only, never an estimated full route.
    raw_observed_ascent_m: float | None
    raw_observed_descent_m: float | None
    observed_ascent_m: float | None
    observed_descent_m: float | None
    total_ascent_m: float | None
    total_descent_m: float | None
    minimum_height_m: float | None
    maximum_height_m: float | None
    segments: tuple[ElevationSegment, ...]
    samples: tuple[FilteredElevationSample, ...]


def profile_digest(profile: ElevationProfile) -> str:
    """Portable v1 identity without materializing another whole profile.

    SHA256(magic, four length-prefixed UTF8 strings, >dI route length/count,
    then >IdB index/distance/presence and optional >d height per sample).
    Numeric fields use big-endian IEEE754 binary64 / unsigned integers.
    """
    digest = hashlib.sha256(b"sugarglider-elevation-profile-v1\0")
    for value in (
        profile.source_sha256,
        profile.geometry_sha256,
        profile.routing_profile,
        profile.height_reference,
    ):
        encoded = value.encode("utf-8")
        digest.update(struct.pack(">I", len(encoded)))
        digest.update(encoded)
    digest.update(struct.pack(">dI", profile.route_distance_m, len(profile.samples)))
    for sample in profile.samples:
        digest.update(
            struct.pack(
                ">IdB",
                sample.index,
                sample.distance_m,
                int(sample.height_m is not None),
            )
        )
        if sample.height_m is not None:
            digest.update(struct.pack(">d", sample.height_m))
    return digest.hexdigest()


def _smooth(
    samples: tuple[ElevationSample, ...], first: int, last: int, radius: float
) -> tuple[list[float], list[float]]:
    """O(k log k) exact box integral and O(k) memory for one covered run."""
    heights: list[float] = []
    distances: list[float] = []
    for index in range(first, last + 1):
        point = samples[index]
        assert point.height_m is not None
        heights.append(point.height_m)
        distances.append(point.distance_m - samples[first].distance_m)
    if len(heights) <= 2 or radius == 0:
        return heights, heights

    # Integrate offsets to limit cancellation on flat/high-altitude profiles.
    origin = heights[0]
    offsets = [height - origin for height in heights]
    count = len(heights) - 1
    areas = [0.0] * (2 * count)
    for index in range(count):
        areas[count + index] = (
            (offsets[index] + offsets[index + 1])
            * 0.5
            * (distances[index + 1] - distances[index])
        )
    for index in range(count - 1, 0, -1):
        areas[index] = areas[index * 2] + areas[index * 2 + 1]

    def whole_edges(left: int, right: int) -> float:
        # Bounded range-sum tree: unlike subtracting route-wide prefix areas,
        # a tiny window late in a long route never subtracts two huge numbers.
        left += count
        right += count
        parts = []
        while left < right:
            if left % 2:
                parts.append(areas[left])
                left += 1
            if right % 2:
                right -= 1
                parts.append(areas[right])
            left //= 2
            right //= 2
        return math.fsum(parts)

    def partial(edge: int, start: float, end: float) -> float:
        width = distances[edge + 1] - distances[edge]
        delta = offsets[edge + 1] - offsets[edge]
        start_height = offsets[edge] + delta * ((start - distances[edge]) / width)
        end_height = offsets[edge] + delta * ((end - distances[edge]) / width)
        return (start_height + end_height) * 0.5 * (end - start)

    def window_area(center: float) -> float:
        left, right = max(0.0, center - radius), min(distances[-1], center + radius)
        first_edge = bisect_right(distances, left) - 1
        last_edge = bisect_left(distances, right) - 1
        extension = offsets[-1] * max(0.0, center + radius - distances[-1])
        if first_edge == last_edge:
            return partial(first_edge, left, right) + extension
        return math.fsum(
            (
                partial(first_edge, left, distances[first_edge + 1]),
                whole_edges(first_edge + 1, last_edge),
                partial(last_edge, distances[last_edge], right),
                extension,
            )
        )

    # Preserve the true net height change; every interior value is a convex
    # average. Clipping only protects the height bounds against roundoff.
    low, high = min(heights), max(heights)
    return heights, [
        heights[0],
        *(
            min(
                high,
                max(
                    low,
                    origin + window_area(distance) / (2 * radius),
                ),
            )
            for distance in distances[1:-1]
        ),
        heights[-1],
    ]


def _changes(heights: list[float]) -> tuple[float, float]:
    return (
        math.fsum(max(0.0, b - a) for a, b in pairwise(heights)),
        math.fsum(max(0.0, a - b) for a, b in pairwise(heights)),
    )


def analyze_elevation(
    profile: ElevationProfile, parameters: ElevationParameters | None = None
) -> ElevationAnalysis:
    """Analyze a validated profile without touching its route or any service.

    Complete coverage means every adjacent sample interval is supported, not
    proof of terrain accuracy. Partial totals remain null; observed quantities
    sum only supported runs. No change across a gap contributes to D+/D−.
    """
    parameters = parameters or ElevationParameters()
    points = profile.samples
    runs: list[tuple[int, int]] = []
    first: int | None = None
    for index, point in enumerate(points):
        if first is not None and (
            point.height_m is None
            or point.distance_m - points[index - 1].distance_m
            > parameters.maximum_gap_m
        ):
            runs.append((first, index - 1))
            first = None
        if point.height_m is not None and first is None:
            first = index
    if first is not None:
        runs.append((first, len(points) - 1))

    filtered_heights: list[float | None] = [None] * len(points)
    segment_indices: list[int | None] = [None] * len(points)
    raw_up: list[float] = []
    raw_down: list[float] = []
    up: list[float] = []
    down: list[float] = []
    segments: list[ElevationSegment] = []
    for segment_index, (start, end) in enumerate(runs):
        original, filtered = _smooth(points, start, end, parameters.smoothing_radius_m)
        raw_ascent, raw_descent = _changes(original)
        ascent, descent = _changes(filtered)
        # A failed invariant must never turn into a plausible public number.
        if (
            ascent > raw_ascent + NUMERICAL_TOLERANCE_M
            or descent > raw_descent + NUMERICAL_TOLERANCE_M
        ):
            raise ValueError("elevation smoothing increased variation")
        if end > start:
            raw_up.append(raw_ascent)
            raw_down.append(raw_descent)
            up.append(ascent)
            down.append(descent)
        segments.append(
            ElevationSegment(
                first_index=start,
                last_index=end,
                distance_m=points[end].distance_m - points[start].distance_m,
            )
        )
        for index, height in enumerate(filtered, start):
            filtered_heights[index] = height
            segment_indices[index] = segment_index

    available = [point.height_m for point in points if point.height_m is not None]
    analyzed = math.fsum(segment.distance_m for segment in segments)
    complete = len(runs) == 1 and runs[0] == (0, len(points) - 1)
    observed_up = math.fsum(up) if up else None
    observed_down = math.fsum(down) if down else None
    return ElevationAnalysis(
        parameters=parameters,
        source_sha256=profile.source_sha256,
        geometry_sha256=profile.geometry_sha256,
        profile_sha256=profile_digest(profile),
        routing_profile=profile.routing_profile,
        route_distance_m=profile.route_distance_m,
        height_reference=profile.height_reference,
        coverage="complete" if complete else "partial" if available else "unavailable",
        available_sample_count=len(available),
        analyzed_distance_m=analyzed,
        unknown_distance_m=max(0.0, profile.route_distance_m - analyzed),
        raw_observed_ascent_m=math.fsum(raw_up) if raw_up else None,
        raw_observed_descent_m=math.fsum(raw_down) if raw_down else None,
        observed_ascent_m=observed_up,
        observed_descent_m=observed_down,
        total_ascent_m=observed_up if complete else None,
        total_descent_m=observed_down if complete else None,
        minimum_height_m=min(available, default=None),
        maximum_height_m=max(available, default=None),
        segments=tuple(segments),
        samples=tuple(
            FilteredElevationSample(
                index=point.index,
                distance_m=point.distance_m,
                height_m=point.height_m,
                filtered_height_m=filtered_heights[index],
                segment_index=segment_indices[index],
            )
            for index, point in enumerate(points)
        ),
    )
