"""Immutable typed models for the deterministic nature index and public status."""

from math import isfinite
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from sugarglider.domain.models import GeoJsonPosition, ImmutableModel
from sugarglider.nature.classification import PrimaryNatureClass

type PolygonCoordinates = tuple[tuple[GeoJsonPosition, ...], ...]
type MultiPolygonCoordinates = tuple[PolygonCoordinates, ...]
type Wgs84BoundingBox = tuple[float, float, float, float]


class PolygonGeometry(ImmutableModel):
    type: Literal["Polygon"] = "Polygon"
    coordinates: Annotated[PolygonCoordinates, Field(min_length=1)]

    @model_validator(mode="after")
    def validate_rings(self) -> Self:
        for ring in self.coordinates:
            if len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError(
                    "polygon rings must be closed with at least four points"
                )
        return self


class MultiPolygonGeometry(ImmutableModel):
    type: Literal["MultiPolygon"] = "MultiPolygon"
    coordinates: Annotated[MultiPolygonCoordinates, Field(min_length=1)]

    @model_validator(mode="after")
    def validate_polygons(self) -> Self:
        for polygon in self.coordinates:
            PolygonGeometry(coordinates=polygon)
        return self


type NatureGeometry = PolygonGeometry | MultiPolygonGeometry


class NatureIndexFeature(ImmutableModel):
    """One selected OSM area with stable provenance and canonical tags."""

    feature_id: Annotated[str, Field(min_length=1)]
    osm_id: int
    osm_source: Literal["way", "relation"]
    primary_class: PrimaryNatureClass | None
    park_or_protected: bool
    tags: dict[str, str]
    geometry: NatureGeometry


class NatureIndexMetadata(ImmutableModel):
    """Deterministic index metadata; wall-clock build time is intentionally absent."""

    format_version: Literal[1] = 1
    source_basename: Annotated[str, Field(min_length=1)]
    source_size_bytes: Annotated[int, Field(ge=0)] | None = None
    source_mtime_ns: None = None
    reference_latitude: float
    bounding_box: Wgs84BoundingBox
    category_counts: dict[str, Annotated[int, Field(ge=0)]]
    feature_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def validate_metadata(self) -> Self:
        west, south, east, north = self.bounding_box
        if not all(isfinite(value) for value in self.bounding_box):
            raise ValueError("nature index bounding box must be finite")
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            raise ValueError("nature index bounding box is invalid")
        if (
            not isfinite(self.reference_latitude)
            or not -90 <= self.reference_latitude <= 90
        ):
            raise ValueError("nature index reference latitude is invalid")
        if not south <= self.reference_latitude <= north:
            raise ValueError(
                "nature index reference latitude must be inside its bounds"
            )
        return self


class NatureIndexDocument(ImmutableModel):
    metadata: NatureIndexMetadata
    features: tuple[NatureIndexFeature, ...]

    @model_validator(mode="after")
    def validate_counts_and_order(self) -> Self:
        if self.metadata.feature_count != len(self.features):
            raise ValueError("nature index feature count does not match features")
        feature_ids = tuple(feature.feature_id for feature in self.features)
        if feature_ids != tuple(sorted(feature_ids)) or len(set(feature_ids)) != len(
            feature_ids
        ):
            raise ValueError("nature index features must have unique sorted IDs")
        return self


class NatureIndexStatus(ImmutableModel):
    """Read-only safe runtime status without exposing host filesystem paths."""

    configured: bool
    available: bool
    index_path_basename: str | None
    format_version: int | None
    source_basename: str | None
    feature_count: Annotated[int, Field(ge=0)] | None
    class_counts: dict[str, Annotated[int, Field(ge=0)]]
    water_buffer_m: Annotated[float, Field(ge=0, le=1000)]
    warnings: tuple[str, ...]
