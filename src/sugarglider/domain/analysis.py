"""Immutable public models for explainable route-quality metrics."""

from math import isclose
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

type DetailValue = str | int | float | bool | None

NonNegativeFloat = Annotated[float, Field(ge=0)]
Share = Annotated[float, Field(ge=0, le=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class _ImmutableAnalysisModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class DistanceMetric(_ImmutableAnalysisModel):
    """A distance and its share of the authoritative complete route distance."""

    distance_m: NonNegativeFloat
    share: Share


class DetailBucket(_ImmutableAnalysisModel):
    """Distance attributed to one explicit GraphHopper detail value."""

    value: DetailValue
    distance_m: NonNegativeFloat
    share: Share


class DetailBreakdown(_ImmutableAnalysisModel):
    """Coverage and value buckets for one projected path detail."""

    detail: str
    covered_distance_m: NonNegativeFloat
    coverage_share: Share
    buckets: tuple[DetailBucket, ...]

    @model_validator(mode="after")
    def validate_bucket_total(self) -> Self:
        bucket_total = sum(bucket.distance_m for bucket in self.buckets)
        if not isclose(
            bucket_total,
            self.covered_distance_m,
            rel_tol=1e-9,
            abs_tol=1e-6,
        ):
            raise ValueError("detail bucket distances must sum to covered distance")
        return self


class RepetitionAnalysis(_ImmutableAnalysisModel):
    """Repeated traversal metrics derived only from known GraphHopper edge IDs."""

    edge_id_coverage: DistanceMetric
    available: bool
    unique_edge_count: NonNegativeInt
    traversed_edge_run_count: NonNegativeInt
    repeated_edge_count: NonNegativeInt
    repeated_distance: DistanceMetric


class RouteAnalysis(_ImmutableAnalysisModel):
    """Deterministic, raw route-quality measurements without a composite score."""

    route_distance_m: NonNegativeFloat
    geometry_distance_m: NonNegativeFloat
    distance_scale_factor: NonNegativeFloat
    detail_breakdowns: dict[str, DetailBreakdown]

    paved: DistanceMetric
    unpaved: DistanceMetric
    unknown_surface: DistanceMetric

    trail_like: DistanceMetric
    official_hiking_network: DistanceMetric
    major_road: DistanceMetric
    car_accessible: DistanceMetric

    repetition: RepetitionAnalysis
    warnings: tuple[str, ...]

    @model_validator(mode="after")
    def validate_surface_partition(self) -> Self:
        classified = (
            self.paved.distance_m
            + self.unpaved.distance_m
            + self.unknown_surface.distance_m
        )
        if not isclose(
            classified,
            self.route_distance_m,
            rel_tol=1e-9,
            abs_tol=1e-6,
        ):
            raise ValueError("surface metrics must partition the route distance")
        return self
