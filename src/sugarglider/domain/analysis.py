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


class NatureWeightedComponent(_ImmutableAnalysisModel):
    """One public nature-score weight, input share, and signed score effect."""

    weight: float
    share: Share
    points: float


class NatureScoreBreakdown(_ImmutableAnalysisModel):
    """Every component of the bounded explainable mapped-nature score."""

    base_score: float
    woodland_reward: NatureWeightedComponent
    open_natural_reward: NatureWeightedComponent
    agriculture_reward: NatureWeightedComponent
    park_or_protected_reward: NatureWeightedComponent
    near_water_reward: NatureWeightedComponent
    urban_penalty: NatureWeightedComponent
    unknown_penalty: NatureWeightedComponent
    raw_score: float
    final_score: Annotated[float, Field(ge=0, le=100)]


class NatureAnalysis(_ImmutableAnalysisModel):
    """Mapped OSM land-cover partition, overlays, and explainable score."""

    available: bool
    index_format_version: Annotated[int, Field(ge=1)]
    index_feature_count: NonNegativeInt
    woodland: DistanceMetric
    open_natural: DistanceMetric
    agriculture: DistanceMetric
    water_crossing: DistanceMetric
    urban: DistanceMetric
    unknown_landcover: DistanceMetric
    park_or_protected: DistanceMetric
    near_water: DistanceMetric
    nature_score: Annotated[float, Field(ge=0, le=100)]
    score_breakdown: NatureScoreBreakdown
    warnings: tuple[str, ...]

    @model_validator(mode="after")
    def validate_score(self) -> Self:
        if not isclose(
            self.nature_score,
            self.score_breakdown.final_score,
            rel_tol=0,
            abs_tol=1e-9,
        ):
            raise ValueError("nature score must match its public breakdown")
        return self


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
    immediate_backtrack: DistanceMetric
    backtrack_edge_id_coverage: DistanceMetric
    nature: NatureAnalysis | None = None
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
        if self.nature is not None:
            nature_partition = sum(
                metric.distance_m
                for metric in (
                    self.nature.woodland,
                    self.nature.open_natural,
                    self.nature.agriculture,
                    self.nature.water_crossing,
                    self.nature.urban,
                    self.nature.unknown_landcover,
                )
            )
            if not isclose(
                nature_partition,
                self.route_distance_m,
                rel_tol=1e-9,
                abs_tol=1e-6,
            ):
                raise ValueError("nature primary metrics must partition route distance")
        return self
