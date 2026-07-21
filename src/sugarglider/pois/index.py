"""Load one immutable projected point index for bounded local POI searches."""

import gzip
import json
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import ValidationError
from shapely import STRtree
from shapely.geometry import Point, Polygon, box
from shapely.geometry.base import BaseGeometry

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.pois.approaches import (
    all_approach_candidates_for_feature,
    approach_order_key,
)
from sugarglider.pois.errors import PoiIndexFormatError, PoiIndexMissingError
from sugarglider.pois.models import (
    PoiApproachCandidate,
    PoiFeature,
    PoiIndexDocument,
    PoiIndexMetadata,
    PoiIndexStatus,
    PoiSearchRequest,
    PoiSearchResponse,
)

SUPPORTED_FORMAT_VERSION = 2


@dataclass(frozen=True)
class PoiRouteMatch:
    """One exact projected point-to-route corridor match."""

    feature: PoiFeature
    distance_m: float
    route_progress_share: float
    approach: PoiApproachCandidate | None = None


class PoiIndex:
    """Immutable POI models and one reusable STRtree over projected points."""

    __slots__ = (
        "_approach_feature_indices",
        "_approach_indices",
        "_approach_tree",
        "_by_id",
        "_feature_tree",
        "_features",
        "_metadata",
        "_projection",
    )

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
            for approach in all_approach_candidates_for_feature(feature):
                approach_coordinate = approach.coordinate
                if not (
                    west <= approach_coordinate.lon <= east
                    and south <= approach_coordinate.lat <= north
                ):
                    raise PoiIndexFormatError(
                        f"POI approach {approach.id} is outside the index bounds"
                    )

        self._metadata = metadata
        self._features = document.features
        self._by_id = {feature.id: feature for feature in self._features}
        self._projection = projection
        self._feature_tree = STRtree(
            tuple(
                Point(projection.project_position(_position(feature)))
                for feature in self._features
            )
        )
        approach_entries = tuple(
            (feature_index, approach_index, approach)
            for feature_index, feature in enumerate(self._features)
            for approach_index, approach in enumerate(
                all_approach_candidates_for_feature(feature)
            )
        )
        self._approach_feature_indices = tuple(
            feature_index
            for feature_index, _approach_index, _approach in approach_entries
        )
        self._approach_indices = tuple(
            approach_index
            for _feature_index, approach_index, _approach in approach_entries
        )
        self._approach_tree = STRtree(
            tuple(
                Point(projection.project_position(_position(approach)))
                for _feature_index, _approach_index, approach in approach_entries
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
        raw: object = self._feature_tree.query(geometry)
        return tuple(sorted(cast(Iterable[int], raw)))

    def query_approach_indices(self, geometry: BaseGeometry) -> tuple[int, ...]:
        """Return stable approach-tree entry indices for a projected geometry."""
        raw: object = self._approach_tree.query(geometry)
        return tuple(sorted(cast(Iterable[int], raw)))

    def get_feature(self, poi_id: str) -> PoiFeature | None:
        """Return one stable feature without scanning the regional tuple."""
        return self._by_id.get(poi_id)

    def query_near_route(
        self,
        route_geometry: tuple[tuple[float, float], ...],
        radius_m: float,
        *,
        groups: tuple[str, ...] = ("scenic", "hydration"),
        include_broad_attractions: bool = False,
        limit: int = 500,
    ) -> tuple[PoiRouteMatch, ...]:
        """Query the STRtree envelope, then measure only exact corridor candidates."""
        if radius_m < 0:
            raise ValueError("POI route corridor radius must be non-negative")
        if limit < 1:
            raise ValueError("POI route corridor limit must be positive")
        if len(route_geometry) < 2:
            raise ValueError("POI route corridor requires a line")
        line = self._projection.project_line(route_geometry)
        if line.is_empty or not line.is_valid or line.length <= 0:
            raise ValueError("POI route corridor requires a valid non-empty line")
        envelope = line.buffer(radius_m).envelope
        best_by_feature: dict[int, tuple[float, PoiApproachCandidate]] = {}
        for tree_index in self.query_approach_indices(envelope):
            feature_index = self._approach_feature_indices[tree_index]
            feature = self._features[feature_index]
            approaches = all_approach_candidates_for_feature(feature)
            approach = approaches[self._approach_indices[tree_index]]
            point = Point(
                self._projection.project_position(
                    (approach.coordinate.lon, approach.coordinate.lat)
                )
            )
            distance = float(line.distance(point))
            if distance > radius_m:
                continue
            previous = best_by_feature.get(feature_index)
            if previous is None or (distance, approach_order_key(approach)) < (
                previous[0],
                approach_order_key(previous[1]),
            ):
                best_by_feature[feature_index] = (distance, approach)

        matches: list[PoiRouteMatch] = []
        for feature_index, (distance, approach) in sorted(best_by_feature.items()):
            feature = self._features[feature_index]
            if feature.group not in groups:
                continue
            if (
                feature.access_status == "private"
                or feature.potability == "non_potable"
            ):
                continue
            if feature.group == "hydration" and feature.potability != "verified":
                continue
            if (
                feature.category == "tourism_attraction"
                and not include_broad_attractions
            ):
                continue
            point = Point(
                self._projection.project_position(
                    (approach.coordinate.lon, approach.coordinate.lat)
                )
            )
            progress = float(line.project(point) / line.length)
            matches.append(PoiRouteMatch(feature, distance, progress, approach))
        matches.sort(
            key=lambda match: (
                match.route_progress_share,
                match.feature.category,
                unicodedata.normalize("NFKC", match.feature.display_name).casefold(),
                match.feature.id,
            )
        )
        return tuple(matches[:limit])

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
            approach_counts={
                str(key): value for key, value in metadata.approach_counts.items()
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
        approach_counts={},
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


def _position(feature: PoiFeature | PoiApproachCandidate) -> tuple[float, float]:
    return feature.coordinate.lon, feature.coordinate.lat
