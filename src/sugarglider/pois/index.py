"""Load one immutable projected point index for bounded local POI searches."""

import gzip
import json
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import cast

from pydantic import ValidationError
from shapely import STRtree
from shapely.geometry import Point, Polygon, box
from shapely.geometry.base import BaseGeometry

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.pois.errors import PoiIndexFormatError, PoiIndexMissingError
from sugarglider.pois.models import (
    PoiFeature,
    PoiIndexDocument,
    PoiIndexMetadata,
    PoiIndexStatus,
    PoiSearchRequest,
    PoiSearchResponse,
)

SUPPORTED_FORMAT_VERSION = 1


class PoiIndex:
    """Immutable POI models and one reusable STRtree over projected points."""

    __slots__ = ("_features", "_metadata", "_projection", "_tree")

    def __init__(self, document: PoiIndexDocument) -> None:
        metadata = document.metadata
        if metadata.format_version != SUPPORTED_FORMAT_VERSION:
            raise PoiIndexFormatError(
                f"unsupported POI index format {metadata.format_version}"
            )
        west, south, east, north = metadata.bounding_box
        try:
            projection = LocalMetricProjection((south + north) / 2)
        except ValueError as exc:
            raise PoiIndexFormatError(str(exc)) from exc

        for feature in document.features:
            coordinate = feature.coordinate
            if not (
                west <= coordinate.lon <= east and south <= coordinate.lat <= north
            ):
                raise PoiIndexFormatError(
                    f"POI feature {feature.id} is outside the index bounds"
                )

        self._metadata = metadata
        self._features = document.features
        self._projection = projection
        self._tree = STRtree(
            tuple(
                Point(projection.project_position(_position(feature)))
                for feature in self._features
            )
        )

    @property
    def metadata(self) -> PoiIndexMetadata:
        return self._metadata

    @property
    def features(self) -> tuple[PoiFeature, ...]:
        return self._features

    @property
    def projection(self) -> LocalMetricProjection:
        return self._projection

    def query_indices(self, geometry: BaseGeometry) -> tuple[int, ...]:
        """Return only STRtree candidates, in stable source-index order."""
        raw: object = self._tree.query(geometry)
        return tuple(sorted(cast(Iterable[int], raw)))

    def search(self, request: PoiSearchRequest, *, limit: int) -> PoiSearchResponse:
        """Filter the spatial candidates without scanning the regional feature set."""
        query_bounds = _metric_query_bounds(request, self._projection)
        candidates = tuple(
            self._features[index] for index in self.query_indices(query_bounds)
        )
        matching = tuple(
            sorted(
                (feature for feature in candidates if _matches(feature, request)),
                key=_sort_key,
            )
        )
        returned = matching[:limit]
        truncated = len(returned) < len(matching)
        return PoiSearchResponse(
            available=True,
            total_matching=len(matching),
            returned_count=len(returned),
            truncated=truncated,
            features=returned,
            warnings=("poi_results_truncated",) if truncated else (),
        )

    def status(self) -> PoiIndexStatus:
        metadata = self._metadata
        return PoiIndexStatus(
            configured=True,
            available=True,
            index_path_basename=None,
            format_version=metadata.format_version,
            source_basename=metadata.source_basename,
            feature_count=metadata.feature_count,
            category_counts={
                str(key): value for key, value in metadata.category_counts.items()
            },
            potability_counts={
                str(key): value for key, value in metadata.potability_counts.items()
            },
            access_counts={
                str(key): value for key, value in metadata.access_counts.items()
            },
            warnings=(),
        )


def load_poi_index(path: Path) -> PoiIndex:
    """Load canonical gzip JSON once; this function never consults the source PBF."""
    if not path.is_file():
        raise PoiIndexMissingError(f"POI index does not exist: {path.name}")
    try:
        with gzip.open(path, "rt", encoding="utf-8") as index_file:
            raw: object = json.load(index_file)
        document = PoiIndexDocument.model_validate(raw)
        return PoiIndex(document)
    except PoiIndexFormatError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        raise PoiIndexFormatError(f"POI index {path.name} is invalid") from exc


def unavailable_poi_status(
    path: Path | None, *, warnings: tuple[str, ...]
) -> PoiIndexStatus:
    """Describe an unavailable index using only a safe configured basename."""
    return PoiIndexStatus(
        configured=path is not None,
        available=False,
        index_path_basename=path.name if path is not None else None,
        format_version=None,
        source_basename=None,
        feature_count=None,
        category_counts={},
        potability_counts={},
        access_counts={},
        warnings=tuple(sorted(set(warnings))),
    )


def available_poi_status(index: PoiIndex, path: Path) -> PoiIndexStatus:
    """Describe a loaded index while keeping its parent directory private."""
    return index.status().model_copy(update={"index_path_basename": path.name})


def unavailable_poi_search(*, warnings: tuple[str, ...]) -> PoiSearchResponse:
    """Return a structured no-data response while routing remains operational."""
    return PoiSearchResponse(
        available=False,
        total_matching=0,
        returned_count=0,
        truncated=False,
        features=(),
        warnings=tuple(sorted(set(warnings))),
    )


def _metric_query_bounds(
    request: PoiSearchRequest, projection: LocalMetricProjection
) -> Polygon:
    bbox = request.bbox
    southwest = projection.project_position((bbox.west, bbox.south))
    northeast = projection.project_position((bbox.east, bbox.north))
    return box(*southwest, *northeast)


def _matches(feature: PoiFeature, request: PoiSearchRequest) -> bool:
    if feature.group not in request.groups:
        return False
    if request.categories is not None and feature.category not in request.categories:
        return False
    if feature.potability == "non_potable" and "non_potable" not in request.potability:
        return False
    if feature.group == "hydration" and feature.potability not in request.potability:
        return False
    if feature.access_status == "private" and not request.include_private:
        return False
    return feature.access_status in request.access


def _sort_key(feature: PoiFeature) -> tuple[str, str, str, str, int]:
    return (
        feature.group,
        feature.category,
        unicodedata.normalize("NFKC", feature.display_name).casefold(),
        feature.osm_type,
        feature.osm_id,
    )


def _position(feature: PoiFeature) -> tuple[float, float]:
    return feature.coordinate.lon, feature.coordinate.lat
