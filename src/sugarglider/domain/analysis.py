"""Immutable public models for explainable route-quality metrics."""

from math import isclose
from typing import Annotated, Literal, Self

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


class WalkingRouteQuality(_ImmutableAnalysisModel):
    activity_kind: Literal["walking"] = "walking"
    trail_like: DistanceMetric
    official_hiking_network: DistanceMetric
    technical_hiking: DistanceMetric
    steps: DistanceMetric
    poor_smoothness: DistanceMetric
    detail_coverage: dict[str, Share]


class RunningRouteQuality(_ImmutableAnalysisModel):
    activity_kind: Literal["running"] = "running"
    runnable_surface: DistanceMetric
    trail_like: DistanceMetric
    technical_trail: DistanceMetric
    steps: DistanceMetric
    poor_smoothness: DistanceMetric
    major_road: DistanceMetric
    detail_coverage: dict[str, Share]


class CyclingRouteQuality(_ImmutableAnalysisModel):
    activity_kind: Literal["cycling"] = "cycling"
    cycling_network: DistanceMetric
    cycleway_like: DistanceMetric
    paved: DistanceMetric
    suitable_unpaved: DistanceMetric
    track: DistanceMetric
    rough_surface: DistanceMetric
    steps: DistanceMetric
    major_road: DistanceMetric
    mtb_rating: DetailBreakdown
    detail_coverage: dict[str, Share]


type ActivityRouteQuality = Annotated[
    WalkingRouteQuality | RunningRouteQuality | CyclingRouteQuality,
    Field(discriminator="activity_kind"),
]


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


class LoopGeometryPenaltyBreakdown(_ImmutableAnalysisModel):
    """Every public fixed input, weight, and component of the shape penalty."""

    crossing_penalty_per_crossing: NonNegativeFloat
    crossing_count_input: Annotated[int, Field(ge=0, le=8)]
    crossing_penalty: NonNegativeFloat
    near_parallel_penalty_weight: NonNegativeFloat
    near_parallel_share_input: Share
    near_parallel_penalty: NonNegativeFloat
    compactness_penalty_weight: NonNegativeFloat
    compactness_input: Share
    compactness_penalty: NonNegativeFloat
    sector_imbalance_penalty_weight: NonNegativeFloat
    sector_balance_input: Share
    sector_imbalance_penalty: NonNegativeFloat
    elongation_penalty_weight: NonNegativeFloat
    elongation_input: Share
    elongation_penalty: NonNegativeFloat
    total: NonNegativeFloat

    @model_validator(mode="after")
    def validate_total(self) -> Self:
        components = (
            self.crossing_penalty
            + self.near_parallel_penalty
            + self.compactness_penalty
            + self.sector_imbalance_penalty
            + self.elongation_penalty
        )
        if not isclose(self.total, components, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("loop geometry penalty components must sum to total")
        return self


class LoopGeometryAnalysis(_ImmutableAnalysisModel):
    """Explainable projected global-loop geometry without a beauty score."""

    closed: bool
    start_end_gap_m: NonNegativeFloat
    enclosed_area_m2: NonNegativeFloat
    convex_hull_area_m2: NonNegativeFloat
    compactness: Share
    sector_count: Annotated[int, Field(ge=1)]
    sector_distance_shares: tuple[Share, ...]
    sector_balance: Share
    maximum_sector_distance_share: Share
    occupied_sector_count: NonNegativeInt
    angular_monotonicity: Share
    mean_radius_m: NonNegativeFloat
    max_radius_m: NonNegativeFloat
    elongation: Share
    self_crossing_count: NonNegativeInt
    near_parallel: DistanceMetric
    outbound_return_proximity: DistanceMetric
    penalty_breakdown: LoopGeometryPenaltyBreakdown
    warnings: tuple[str, ...]

    @model_validator(mode="after")
    def validate_geometry_metrics(self) -> Self:
        if len(self.sector_distance_shares) != self.sector_count:
            raise ValueError("sector distance shares must match sector count")
        sector_total = sum(self.sector_distance_shares)
        if sector_total > 0 and not isclose(
            sector_total, 1.0, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise ValueError("positive sector distance shares must sum to one")
        if not isclose(
            self.maximum_sector_distance_share,
            max(self.sector_distance_shares, default=0.0),
            rel_tol=0,
            abs_tol=1e-12,
        ):
            raise ValueError("maximum sector share must match sector distances")
        if self.occupied_sector_count != sum(
            share > 0 for share in self.sector_distance_shares
        ):
            raise ValueError("occupied sector count must match sector distances")
        breakdown = self.penalty_breakdown
        if not (
            breakdown.crossing_count_input == min(self.self_crossing_count, 8)
            and isclose(
                breakdown.near_parallel_share_input,
                self.near_parallel.share,
                rel_tol=0,
                abs_tol=1e-12,
            )
            and isclose(
                breakdown.compactness_input,
                self.compactness,
                rel_tol=0,
                abs_tol=1e-12,
            )
            and isclose(
                breakdown.sector_balance_input,
                self.sector_balance,
                rel_tol=0,
                abs_tol=1e-12,
            )
            and isclose(
                breakdown.elongation_input,
                self.elongation,
                rel_tol=0,
                abs_tol=1e-12,
            )
        ):
            raise ValueError("loop geometry penalty inputs must match public metrics")
        expected_components = (
            breakdown.crossing_penalty_per_crossing * breakdown.crossing_count_input,
            breakdown.near_parallel_penalty_weight
            * breakdown.near_parallel_share_input,
            breakdown.compactness_penalty_weight * (1.0 - breakdown.compactness_input),
            breakdown.sector_imbalance_penalty_weight
            * (1.0 - breakdown.sector_balance_input),
            breakdown.elongation_penalty_weight * (1.0 - breakdown.elongation_input),
        )
        components = (
            breakdown.crossing_penalty,
            breakdown.near_parallel_penalty,
            breakdown.compactness_penalty,
            breakdown.sector_imbalance_penalty,
            breakdown.elongation_penalty,
        )
        if not all(
            isclose(component, expected, rel_tol=1e-12, abs_tol=1e-12)
            for component, expected in zip(components, expected_components, strict=True)
        ):
            raise ValueError(
                "loop geometry penalty components must match public weights and inputs"
            )
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

    major_road: DistanceMetric
    car_accessible: DistanceMetric
    activity_quality: ActivityRouteQuality

    repetition: RepetitionAnalysis
    immediate_backtrack: DistanceMetric
    backtrack_edge_id_coverage: DistanceMetric
    loop_geometry: LoopGeometryAnalysis | None = None
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

    @property
    def trail_like(self) -> DistanceMetric:
        quality = self.activity_quality
        if isinstance(quality, (WalkingRouteQuality, RunningRouteQuality)):
            return quality.trail_like
        return DistanceMetric(distance_m=0.0, share=0.0)

    @property
    def official_hiking_network(self) -> DistanceMetric:
        quality = self.activity_quality
        if isinstance(quality, WalkingRouteQuality):
            return quality.official_hiking_network
        return DistanceMetric(distance_m=0.0, share=0.0)
