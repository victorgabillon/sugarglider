"""Validate PR88 evidence and analyze it, without reading or publishing a DEM.

Example: python -m sugarglider.offline_regions.elevation_analysis --help
All paths are supplied explicitly. The output may contain private route samples.
"""

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from sugarglider.analysis.elevation import (
    MAX_ELEVATION_SAMPLES,
    Digest,
    ElevationModel,
    ElevationParameters,
    ElevationProfile,
    ElevationSample,
    Height,
    analyze_elevation,
)
from sugarglider.domain.models import RoutingProfileId
from sugarglider.offline_regions.native_height_experiment import (
    MAX_INPUT_BYTES,
    HeightPlan,
    HeightSamplePoint,
    NativeResearchResult,
    ResearchRoute,
    sample_routed_geometry,
)


class NativeHeightSample(HeightSamplePoint, ElevationModel):
    model_config = ElevationModel.model_config
    height_m: Height | None
    python_height_m: Height | None
    absolute_error_m: Annotated[float, Field(ge=0, le=0.010001)] | None

    @model_validator(mode="after")
    def validate_comparison(self) -> Self:
        if self.height_m is None or self.python_height_m is None:
            if (self.height_m, self.python_height_m, self.absolute_error_m) != (
                None,
                None,
                None,
            ):
                raise ValueError("native comparison availability mismatch")
        elif self.absolute_error_m != abs(self.height_m - self.python_height_m):
            raise ValueError("native comparison error mismatch")
        return self


class NativeHeightDocument(ElevationModel):
    format: Literal["sugarglider-native-height-research-v1"]
    publication_allowed: Literal[False]
    routing_profile: RoutingProfileId
    geometry_sha256: Digest
    source_sha256: Digest
    route_distance_m: Annotated[float, Field(gt=0, le=200_000)]
    spacing_m: Annotated[float, Field(ge=1, le=1_000)]
    sample_count: Annotated[int, Field(ge=2, le=MAX_ELEVATION_SAMPLES)]
    available_count: Annotated[int, Field(ge=0, le=MAX_ELEVATION_SAMPLES)]
    unavailable_count: Annotated[int, Field(ge=0, le=MAX_ELEVATION_SAMPLES)]
    maximum_absolute_error_m: Annotated[float, Field(ge=0, le=0.010001)] | None
    samples: Annotated[
        tuple[NativeHeightSample, ...],
        Field(min_length=2, max_length=MAX_ELEVATION_SAMPLES),
    ]

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        errors = [
            sample.absolute_error_m
            for sample in self.samples
            if sample.absolute_error_m is not None
        ]
        if (
            self.sample_count != len(self.samples)
            or self.available_count != len(errors)
            or self.unavailable_count != len(self.samples) - len(errors)
            or self.maximum_absolute_error_m != max(errors, default=None)
        ):
            raise ValueError("native sample counts/comparison summary mismatch")
        return self


def read_evidence(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("elevation evidence exceeds byte limit")
    return data


def bind_native_profile(
    document: NativeHeightDocument,
    plan: HeightPlan,
    route: ResearchRoute,
    native: NativeResearchResult,
    *,
    plan_sha256: str,
) -> ElevationProfile:
    """Verify the precise route → sample plan → native heights → profile chain.

    Hashes bind evidence; they do not authenticate an untrusted data publisher.
    PR88's source hash is a compressed HGT identity, not a vertical datum claim.
    """
    geometry_sha256 = hashlib.sha256(
        json.dumps(route.geometry, separators=(",", ":")).encode()
    ).hexdigest()
    if (
        document.geometry_sha256 != plan.geometry_sha256
        or plan.geometry_sha256 != geometry_sha256
        or document.source_sha256 != plan.source_sha256
        or plan.source_sha256 != native.source_sha256
        or native.input_sha256 != plan_sha256
        or document.routing_profile != plan.routing_profile
        or plan.routing_profile != route.routing_profile
        or document.route_distance_m != plan.route_distance_m
        or plan.route_distance_m != route.distance_m
        or document.spacing_m != plan.spacing_m
    ):
        raise ValueError("elevation route/source/plan identity mismatch")
    expected = sample_routed_geometry(
        route, spacing_m=plan.spacing_m, maximum_samples=plan.maximum_samples
    )
    if plan.points != expected:
        raise ValueError("sample plan does not match normalized routed geometry")
    if len(document.samples) != len(expected) or len(native.heights) != len(expected):
        raise ValueError("native/profile sample count mismatch")
    for sample, point, height in zip(
        document.samples, expected, native.heights, strict=True
    ):
        if (
            any(
                getattr(sample, field) != getattr(point, field)
                for field in HeightSamplePoint.model_fields
            )
            or sample.height_m != height
        ):
            raise ValueError("elevation sample position/height mismatch")
    return ElevationProfile(
        source_sha256=document.source_sha256,
        geometry_sha256=document.geometry_sha256,
        routing_profile=document.routing_profile,
        route_distance_m=document.route_distance_m,
        height_reference="PR88 Valhalla Mobile 0.6.4 / core 3.9.1, precision=2",
        samples=tuple(
            ElevationSample(
                index=sample.index,
                distance_m=sample.distance_m,
                height_m=sample.height_m,
            )
            for sample in document.samples
        ),
    )


def verify_csv(document: NativeHeightDocument, data: bytes) -> None:
    """Cross-check the supplementary CSV; never use it to round routed progress."""
    reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
    fields = set(NativeHeightSample.model_fields)
    if reader.fieldnames is None or (
        set(reader.fieldnames) != fields or len(reader.fieldnames) != len(fields)
    ):
        raise ValueError("elevation CSV columns mismatch")
    count = 0
    for count, row in enumerate(reader, 1):
        if count > len(document.samples):
            raise ValueError("elevation CSV has extra rows")
        expected = document.samples[count - 1].model_dump()
        if set(row) != fields:
            raise ValueError("elevation CSV malformed row")
        for field, value in expected.items():
            text = row[field]
            if (value is None and text != "") or (
                value is not None and (text is None or float(text) != value)
            ):
                raise ValueError("elevation CSV sample mismatch")
    if count != len(document.samples):
        raise ValueError("elevation CSV sample count mismatch")


def load_native_profile(
    *,
    profile: Path,
    plan: Path,
    route: Path,
    native_result: Path,
    csv_path: Path | None,
) -> ElevationProfile:
    document = NativeHeightDocument.model_validate_json(read_evidence(profile))
    plan_bytes = read_evidence(plan)
    result = bind_native_profile(
        document,
        HeightPlan.model_validate_json(plan_bytes, strict=True),
        ResearchRoute.model_validate_json(read_evidence(route), strict=True),
        NativeResearchResult.model_validate_json(
            read_evidence(native_result), strict=True
        ),
        plan_sha256=hashlib.sha256(plan_bytes).hexdigest(),
    )
    if csv_path is not None:
        verify_csv(document, read_evidence(csv_path))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--native-result", type=Path, required=True)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--smoothing-radius-m", type=float, default=50)
    parser.add_argument("--maximum-gap-m", type=float, default=100)
    args = parser.parse_args()
    try:
        profile = load_native_profile(
            profile=args.profile,
            plan=args.plan,
            route=args.route,
            native_result=args.native_result,
            csv_path=args.csv,
        )
        result = analyze_elevation(
            profile,
            ElevationParameters(
                smoothing_radius_m=args.smoothing_radius_m,
                maximum_gap_m=args.maximum_gap_m,
            ),
        )
        print(result.model_dump_json(indent=2))
    except (OSError, ValueError) as error:
        print(f"elevation analysis rejected: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
