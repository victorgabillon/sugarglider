"""Load one immutable, projected, STRtree-backed local nature index."""

import gzip
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError
from shapely import STRtree, is_empty, is_valid
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.geometry.base import BaseGeometry

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.nature.classification import PrimaryNatureClass
from sugarglider.nature.errors import (
    NatureIndexFormatError,
    NatureIndexMissingError,
)
from sugarglider.nature.models import (
    MultiPolygonGeometry,
    NatureGeometry,
    NatureIndexDocument,
    NatureIndexMetadata,
    NatureIndexStatus,
    PolygonGeometry,
)
from sugarglider.nature.projection import validate_regional_latitude_span

SUPPORTED_FORMAT_VERSION = 1


@dataclass(frozen=True)
class IndexedNatureFeature:
    """Lightweight immutable provenance/classification and metric polygon."""

    feature_id: str
    osm_id: int
    osm_source: Literal["way", "relation"]
    primary_class: PrimaryNatureClass | None
    park_or_protected: bool
    tags: tuple[tuple[str, str], ...]
    metric_geometry: Polygon | MultiPolygon


class NatureIndex:
    """Immutable feature tuple and reusable spatial index loaded once per process."""

    __slots__ = (
        "_features",
        "_metadata",
        "_metric_bounds",
        "_projection",
        "_tree",
    )

    def __init__(self, document: NatureIndexDocument) -> None:
        metadata = document.metadata
        if metadata.format_version != SUPPORTED_FORMAT_VERSION:
            raise NatureIndexFormatError(
                f"unsupported nature index format {metadata.format_version}"
            )
        west, south, east, north = metadata.bounding_box
        try:
            validate_regional_latitude_span(south, north)
            projection = LocalMetricProjection(metadata.reference_latitude)
        except ValueError as exc:
            raise NatureIndexFormatError(str(exc)) from exc

        indexed: list[IndexedNatureFeature] = []
        for feature in document.features:
            if any(
                longitude < west
                or longitude > east
                or latitude < south
                or latitude > north
                for longitude, latitude in _feature_positions(feature.geometry)
            ):
                raise NatureIndexFormatError(
                    f"nature feature {feature.feature_id} is outside the index bounds"
                )
            indexed.append(
                IndexedNatureFeature(
                    feature_id=feature.feature_id,
                    osm_id=feature.osm_id,
                    osm_source=feature.osm_source,
                    primary_class=feature.primary_class,
                    park_or_protected=feature.park_or_protected,
                    tags=tuple(sorted(feature.tags.items())),
                    metric_geometry=_metric_geometry(feature.geometry, projection),
                )
            )

        valid_values = cast(Iterable[bool], is_valid(_metric_geometries(indexed)))
        empty_values = cast(Iterable[bool], is_empty(_metric_geometries(indexed)))
        for indexed_feature, valid, empty in zip(
            indexed, valid_values, empty_values, strict=True
        ):
            if empty or not valid:
                raise NatureIndexFormatError(
                    f"nature feature {indexed_feature.feature_id} is empty or invalid"
                )

        _validate_category_counts(document)
        metric_corner_a = projection.project_position((west, south))
        metric_corner_b = projection.project_position((east, north))
        self._metadata = metadata
        self._features = tuple(indexed)
        self._projection = projection
        self._metric_bounds = box(*metric_corner_a, *metric_corner_b)
        self._tree = STRtree(tuple(feature.metric_geometry for feature in indexed))

    @property
    def metadata(self) -> NatureIndexMetadata:
        return self._metadata

    @property
    def features(self) -> tuple[IndexedNatureFeature, ...]:
        return self._features

    @property
    def projection(self) -> LocalMetricProjection:
        return self._projection

    @property
    def metric_bounds(self) -> Polygon:
        return self._metric_bounds

    def query_indices(self, geometry: BaseGeometry) -> tuple[int, ...]:
        """Return deterministic feature indices whose bounds intersect geometry."""
        raw: object = self._tree.query(geometry)
        return tuple(sorted(cast(Iterable[int], raw)))

    def status(self, *, water_buffer_m: float) -> NatureIndexStatus:
        metadata = self._metadata
        return NatureIndexStatus(
            configured=True,
            available=True,
            index_path_basename=None,
            format_version=metadata.format_version,
            source_basename=metadata.source_basename,
            feature_count=metadata.feature_count,
            class_counts=dict(metadata.category_counts),
            water_buffer_m=water_buffer_m,
            warnings=(),
        )


def load_nature_index(path: Path) -> NatureIndex:
    """Load and validate a canonical gzip JSON index without parsing OSM data."""
    if not path.is_file():
        raise NatureIndexMissingError(f"nature index does not exist: {path.name}")
    try:
        with gzip.open(path, "rt", encoding="utf-8") as index_file:
            raw: object = json.load(index_file)
        document = NatureIndexDocument.model_validate(raw)
        return NatureIndex(document)
    except NatureIndexFormatError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        raise NatureIndexFormatError(f"nature index {path.name} is invalid") from exc


def unavailable_nature_status(
    path: Path | None,
    *,
    water_buffer_m: float,
    warnings: tuple[str, ...],
) -> NatureIndexStatus:
    """Build a safe unavailable status using only the configured basename."""
    return NatureIndexStatus(
        configured=path is not None,
        available=False,
        index_path_basename=path.name if path is not None else None,
        format_version=None,
        source_basename=None,
        feature_count=None,
        class_counts={},
        water_buffer_m=water_buffer_m,
        warnings=tuple(sorted(set(warnings))),
    )


def available_nature_status(
    index: NatureIndex, path: Path, *, water_buffer_m: float
) -> NatureIndexStatus:
    """Build a safe available status with the configured basename."""
    status = index.status(water_buffer_m=water_buffer_m)
    return status.model_copy(update={"index_path_basename": path.name})


def _metric_geometry(
    geometry: NatureGeometry,
    projection: LocalMetricProjection,
) -> Polygon | MultiPolygon:
    def ring(
        positions: tuple[tuple[float, float], ...],
    ) -> tuple[tuple[float, float], ...]:
        return tuple(projection.project_position(position) for position in positions)

    if isinstance(geometry, PolygonGeometry):
        shell, *holes = geometry.coordinates
        return Polygon(ring(shell), tuple(ring(hole) for hole in holes))
    if isinstance(geometry, MultiPolygonGeometry):
        return MultiPolygon(
            tuple(
                Polygon(
                    ring(polygon[0]),
                    tuple(ring(hole) for hole in polygon[1:]),
                )
                for polygon in geometry.coordinates
            )
        )
    raise NatureIndexFormatError("unsupported nature feature geometry")


def _feature_positions(geometry: NatureGeometry) -> Iterator[tuple[float, float]]:
    if isinstance(geometry, PolygonGeometry):
        for ring in geometry.coordinates:
            yield from ring
        return
    for polygon in geometry.coordinates:
        for ring in polygon:
            yield from ring


def _metric_geometries(
    features: list[IndexedNatureFeature],
) -> tuple[Polygon | MultiPolygon, ...]:
    return tuple(feature.metric_geometry for feature in features)


def _validate_category_counts(document: NatureIndexDocument) -> None:
    counts: dict[str, int] = {}
    for feature in document.features:
        if feature.primary_class is not None:
            counts[feature.primary_class] = counts.get(feature.primary_class, 0) + 1
        if feature.park_or_protected:
            counts["park_or_protected"] = counts.get("park_or_protected", 0) + 1
    expected = {key: value for key, value in sorted(counts.items())}
    if document.metadata.category_counts != expected:
        raise NatureIndexFormatError(
            "nature index category counts do not match features"
        )
