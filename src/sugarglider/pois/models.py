"""Immutable public models for the deterministic local POI index and API."""

from math import isfinite
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from sugarglider.domain.models import Coordinate, ImmutableModel

type PoiCategory = Literal[
    "viewpoint",
    "castle",
    "ruins",
    "archaeological_site",
    "observation_tower",
    "tourism_attraction",
    "drinking_water",
    "fountain",
    "water_tap",
]
type PoiGroup = Literal["scenic", "hydration"]
type ScenicConfidence = Literal["primary", "broad", "none"]
type Potability = Literal["verified", "unknown", "non_potable", "not_applicable"]
type PoiPotabilityFilter = Literal["verified", "unknown", "non_potable"]
type AccessStatus = Literal["public", "restricted", "private", "unknown"]
type OsmType = Literal["node", "way", "relation"]
type NameSource = Literal["name", "category_fallback"]
type Wgs84BoundingBox = tuple[float, float, float, float]
type PublicTags = tuple[tuple[str, str], ...]
type PoiApproachKind = Literal[
    "exact_feature",
    "drinking_water_source",
    "viewpoint_location",
    "mapped_entrance",
    "mapped_gate",
    "public_path_boundary",
    "nearby_public_path",
    "user_override",
    "strict_graph_snap",
]
type PoiApproachSource = Literal[
    "osm_feature",
    "osm_entrance",
    "osm_gate",
    "osm_path_intersection",
    "osm_spatial_boundary_inference",
    "imported_coordinate",
    "user_override",
]
type PoiApproachProvenance = Literal[
    "feature_geometry",
    "way_boundary_node",
    "relation_boundary_node",
    "shared_path_boundary_node",
    "spatial_boundary_inferred",
    "imported_coordinate",
    "user_override",
]


class PoiApproachCandidate(ImmutableModel):
    """One bounded, meaningful route target distinct from a POI centroid."""

    id: Annotated[str, Field(min_length=1, max_length=320)]
    coordinate: Coordinate
    kind: PoiApproachKind
    source: PoiApproachSource
    access: AccessStatus
    semantic_distance_m: Annotated[float, Field(ge=0)]
    graph_snap_distance_m: Annotated[float, Field(ge=0)] | None = None
    arrival_tolerance_m: Annotated[float, Field(gt=0, le=100)]
    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    osm_type: OsmType | None = None
    osm_id: Annotated[int, Field(ge=0)] | None = None
    provenance: PoiApproachProvenance = "feature_geometry"
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_osm_reference(self) -> Self:
        if (self.osm_type is None) != (self.osm_id is None):
            raise ValueError("approach OSM type and ID must be supplied together")
        if self.coordinate.name is not None:
            raise ValueError("approach coordinates must not contain a duplicate name")
        if self.warnings != tuple(sorted(set(self.warnings))):
            raise ValueError("approach warnings must be sorted and unique")
        return self


class PoiFeature(ImmutableModel):
    """One selected OSM object reduced to one deterministic discovery point."""

    id: Annotated[str, Field(min_length=1)]
    osm_type: OsmType
    osm_id: Annotated[int, Field(ge=0)]
    coordinate: Coordinate
    category: PoiCategory
    secondary_categories: tuple[PoiCategory, ...] = ()
    group: PoiGroup
    display_name: Annotated[str, Field(min_length=1)]
    name_source: NameSource
    scenic_confidence: ScenicConfidence
    potability: Potability
    access_status: AccessStatus
    ruins: bool = False
    tags: PublicTags = ()
    source_updated_at: str | None = None
    warnings: tuple[str, ...] = ()
    approach_candidates: Annotated[
        tuple[PoiApproachCandidate, ...], Field(max_length=8)
    ] = ()

    @model_validator(mode="after")
    def validate_identity_and_stable_collections(self) -> Self:
        if self.id != f"{self.osm_type}/{self.osm_id}":
            raise ValueError("POI ID must match its OSM type and ID")
        if self.coordinate.name is not None:
            raise ValueError("POI coordinates must not duplicate the display name")
        tag_keys = tuple(key for key, _value in self.tags)
        if tag_keys != tuple(sorted(tag_keys)) or len(tag_keys) != len(set(tag_keys)):
            raise ValueError("POI public tags must have unique sorted keys")
        if self.category in self.secondary_categories or len(
            self.secondary_categories
        ) != len(set(self.secondary_categories)):
            raise ValueError("POI secondary categories must be unique and non-primary")
        if self.warnings != tuple(sorted(set(self.warnings))):
            raise ValueError("POI warnings must be sorted and unique")
        approach_ids = tuple(approach.id for approach in self.approach_candidates)
        if approach_ids != tuple(sorted(approach_ids)) or len(approach_ids) != len(
            set(approach_ids)
        ):
            raise ValueError("POI approaches must have unique sorted IDs")
        if any(
            approach.access in {"private", "restricted"}
            for approach in self.approach_candidates
        ):
            raise ValueError("private or restricted approaches must not be published")
        if self.access_status in {"private", "restricted"} and self.approach_candidates:
            raise ValueError("private or restricted features cannot publish approaches")
        expected_group: PoiGroup = (
            "hydration"
            if self.category in {"drinking_water", "fountain", "water_tap"}
            else "scenic"
        )
        if self.group != expected_group:
            raise ValueError("POI group must match its primary category")
        return self


class PoiBuildConfiguration(ImmutableModel):
    """Stable builder choices recorded inside deterministic index bytes."""

    classifier_version: Literal["1"] = "1"
    geometry_policy: Literal["semantic-point_with-bounded-public-approaches"] = (
        "semantic-point_with-bounded-public-approaches"
    )
    identity_policy: Literal["osm-type-and-id"] = "osm-type-and-id"
    include_non_potable: bool = True


class PoiIndexMetadata(ImmutableModel):
    """Deterministic POI index metadata without a wall-clock build timestamp."""

    format_version: Literal[2] = 2
    source_basename: Annotated[str, Field(min_length=1)]
    source_size_bytes: Annotated[int, Field(ge=0)] | None = None
    feature_count: Annotated[int, Field(ge=0)]
    category_counts: dict[PoiCategory, Annotated[int, Field(ge=0)]]
    potability_counts: dict[Potability, Annotated[int, Field(ge=0)]]
    access_counts: dict[AccessStatus, Annotated[int, Field(ge=0)]]
    approach_counts: dict[PoiApproachKind, Annotated[int, Field(ge=0)]] = Field(
        default_factory=dict
    )
    bounding_box: Wgs84BoundingBox
    skipped_invalid_count: Annotated[int, Field(ge=0)]
    build_configuration: PoiBuildConfiguration = PoiBuildConfiguration()
    classifier_version: Literal["1"] = "1"

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        west, south, east, north = self.bounding_box
        if not all(isfinite(value) for value in self.bounding_box):
            raise ValueError("POI index bounding box must be finite")
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            raise ValueError("POI index bounding box is invalid")
        return self


class PoiIndexDocument(ImmutableModel):
    metadata: PoiIndexMetadata
    features: tuple[PoiFeature, ...]

    @model_validator(mode="after")
    def validate_counts_and_order(self) -> Self:
        if self.metadata.feature_count != len(self.features):
            raise ValueError("POI index feature count does not match features")
        feature_ids = tuple(feature.id for feature in self.features)
        if feature_ids != tuple(sorted(feature_ids)) or len(feature_ids) != len(
            set(feature_ids)
        ):
            raise ValueError("POI index features must have unique sorted IDs")
        if _counts(self.features, "category") != self.metadata.category_counts:
            raise ValueError("POI category counts do not match features")
        if _counts(self.features, "potability") != self.metadata.potability_counts:
            raise ValueError("POI potability counts do not match features")
        if _counts(self.features, "access_status") != self.metadata.access_counts:
            raise ValueError("POI access counts do not match features")
        if _approach_counts(self.features) != self.metadata.approach_counts:
            raise ValueError("POI approach counts do not match features")
        return self


class PoiIndexStatus(ImmutableModel):
    """Safe runtime status that never exposes a host filesystem path."""

    configured: bool
    available: bool
    index_path_basename: str | None
    format_version: int | None
    source_basename: str | None
    feature_count: Annotated[int, Field(ge=0)] | None
    category_counts: dict[str, Annotated[int, Field(ge=0)]]
    potability_counts: dict[str, Annotated[int, Field(ge=0)]]
    access_counts: dict[str, Annotated[int, Field(ge=0)]]
    approach_counts: dict[str, Annotated[int, Field(ge=0)]] = Field(
        default_factory=dict
    )
    warnings: tuple[str, ...]


class PoiBoundingBox(ImmutableModel):
    west: float
    south: float
    east: float
    north: float

    @model_validator(mode="after")
    def validate_non_dateline_bounds(self) -> Self:
        values = (self.west, self.south, self.east, self.north)
        if not all(isfinite(value) for value in values):
            raise ValueError("POI search bounds must be finite")
        if not (
            -180 <= self.west < self.east <= 180
            and -90 <= self.south < self.north <= 90
        ):
            raise ValueError("POI search requires a valid non-dateline bounding box")
        return self


class PoiSearchRequest(ImmutableModel):
    bbox: PoiBoundingBox
    groups: tuple[PoiGroup, ...] = ("scenic", "hydration")
    categories: tuple[PoiCategory, ...] | None = None
    potability: tuple[PoiPotabilityFilter, ...] = ("verified", "unknown")
    access: tuple[AccessStatus, ...] = ("public", "restricted", "unknown")
    include_private: bool = False
    limit: Annotated[int, Field(ge=1, le=5000)] | None = None

    @model_validator(mode="after")
    def validate_unique_filters(self) -> Self:
        collections = (self.groups, self.potability, self.access)
        if any(len(values) != len(set(values)) for values in collections):
            raise ValueError("POI filters must not contain duplicates")
        if self.categories is not None and len(self.categories) != len(
            set(self.categories)
        ):
            raise ValueError("POI category filters must not contain duplicates")
        return self


class PoiSearchResponse(ImmutableModel):
    available: bool
    total_matching: Annotated[int, Field(ge=0)]
    returned_count: Annotated[int, Field(ge=0)]
    truncated: bool
    features: tuple[PoiFeature, ...]
    warnings: tuple[str, ...]

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.returned_count != len(self.features):
            raise ValueError("returned POI count must match features")
        if self.total_matching < self.returned_count:
            raise ValueError("total POI matches cannot be below returned count")
        if self.truncated != (self.returned_count < self.total_matching):
            raise ValueError("POI truncation must match returned and total counts")
        return self


def _counts(
    features: tuple[PoiFeature, ...],
    field: Literal["category", "potability", "access_status"],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for feature in features:
        key = str(getattr(feature, field))
        counts[key] = counts.get(key, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _approach_counts(features: tuple[PoiFeature, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for feature in features:
        for approach in feature.approach_candidates:
            counts[approach.kind] = counts.get(approach.kind, 0) + 1
    return {key: counts[key] for key in sorted(counts)}
