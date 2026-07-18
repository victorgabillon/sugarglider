"""Offline CLI for streaming OSM objects into a deterministic gzip POI index."""

import argparse
import gzip
import hashlib
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal, cast

import osmium
from shapely.errors import GEOSException
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.wkb import loads as load_wkb

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.domain.models import Coordinate
from sugarglider.pois.classification import (
    CLASSIFIER_VERSION,
    PoiClassification,
    classify_osm_tags,
)
from sugarglider.pois.errors import PoiIndexBuildError
from sugarglider.pois.models import (
    AccessStatus,
    PoiCategory,
    PoiFeature,
    PoiIndexDocument,
    PoiIndexMetadata,
    Potability,
    Wgs84BoundingBox,
)

DEFAULT_OSM_PBF = Path("data/osm/ile-de-france-latest.osm.pbf")
DEFAULT_OUTPUT = Path("data/pois/ile-de-france-poi-index.json.gz")
SUPPORTED_SOURCE_SUFFIXES = (".osm", ".xml", ".pbf", ".osm.pbf")

type Wgs84Position = tuple[float, float]


@dataclass(frozen=True)
class PoiIndexBuildReport:
    source: Path
    output: Path
    feature_count: int
    category_counts: dict[str, int]
    potability_counts: dict[str, int]
    access_counts: dict[str, int]
    skipped_invalid_count: int
    uncompressed_size_bytes: int
    compressed_size_bytes: int
    sha256: str
    bounding_box: Wgs84BoundingBox
    elapsed_seconds: float


def build_poi_index(osm_source: Path, output: Path) -> PoiIndexBuildReport:
    """Stream nodes, ways, and relation areas and atomically write one marker each."""
    started = time.perf_counter()
    _validate_source(osm_source)
    factory = osmium.geom.WKBFactory()
    features: dict[str, PoiFeature] = {}
    classified_relations: set[int] = set()
    handled_relations: set[int] = set()
    skipped_invalid = 0
    try:
        processor = osmium.FileProcessor(osm_source).with_locations().with_areas()
        header_box = processor.header.box()
        projection = _projection_for_header(header_box)
        for entity in processor:
            if isinstance(entity, osmium.osm.Node):
                classification = classify_osm_tags(
                    {tag.k: tag.v for tag in entity.tags}
                )
                if classification is None:
                    continue
                try:
                    coordinate = _node_coordinate(entity)
                    _insert_feature(
                        features,
                        _feature("node", entity.id, coordinate, classification),
                    )
                except (RuntimeError, ValueError, TypeError):
                    skipped_invalid += 1
            elif isinstance(entity, osmium.osm.Way):
                tags = {tag.k: tag.v for tag in entity.tags}
                classification = classify_osm_tags(tags)
                if classification is None:
                    continue
                try:
                    coordinate = _way_coordinate(
                        entity,
                        projection,
                        polygonal=tags.get("area") != "no",
                    )
                    _insert_feature(
                        features,
                        _feature("way", entity.id, coordinate, classification),
                    )
                except (GEOSException, RuntimeError, ValueError, TypeError):
                    skipped_invalid += 1
            elif isinstance(entity, osmium.osm.Relation):
                if classify_osm_tags({tag.k: tag.v for tag in entity.tags}) is not None:
                    classified_relations.add(entity.id)
            elif isinstance(entity, osmium.osm.Area) and not entity.from_way():
                osm_id = entity.orig_id()
                classification = classify_osm_tags(
                    {tag.k: tag.v for tag in entity.tags}
                )
                if classification is None:
                    continue
                handled_relations.add(osm_id)
                try:
                    geometry = load_wkb(factory.create_multipolygon(entity), hex=True)
                    coordinate = _polygon_coordinate(geometry, projection)
                    _insert_feature(
                        features,
                        _feature("relation", osm_id, coordinate, classification),
                    )
                except (GEOSException, RuntimeError, ValueError, TypeError):
                    skipped_invalid += 1
    except (RuntimeError, OSError) as exc:
        raise PoiIndexBuildError(
            f"failed to read OSM objects from {osm_source.name}"
        ) from exc

    skipped_invalid += len(classified_relations - handled_relations)
    ordered = tuple(features[key] for key in sorted(features))
    bounds = _document_bounds(ordered, header_box)
    category_counts = _feature_counts(ordered, "category")
    potability_counts = _feature_counts(ordered, "potability")
    access_counts = _feature_counts(ordered, "access_status")
    document = PoiIndexDocument(
        metadata=PoiIndexMetadata(
            source_basename=osm_source.name,
            source_size_bytes=osm_source.stat().st_size,
            feature_count=len(ordered),
            category_counts=cast(dict[PoiCategory, int], category_counts),
            potability_counts=cast(dict[Potability, int], potability_counts),
            access_counts=cast(dict[AccessStatus, int], access_counts),
            bounding_box=bounds,
            skipped_invalid_count=skipped_invalid,
            classifier_version=CLASSIFIER_VERSION,
        ),
        features=ordered,
    )
    payload = json.dumps(
        document.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    compressed_size = _write_deterministic_gzip_atomic(output, payload)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return PoiIndexBuildReport(
        source=osm_source,
        output=output,
        feature_count=len(ordered),
        category_counts=category_counts,
        potability_counts=potability_counts,
        access_counts=access_counts,
        skipped_invalid_count=skipped_invalid,
        uncompressed_size_bytes=len(payload),
        compressed_size_bytes=compressed_size,
        sha256=digest,
        bounding_box=bounds,
        elapsed_seconds=time.perf_counter() - started,
    )


def _validate_source(path: Path) -> None:
    if not path.is_file():
        raise PoiIndexBuildError(f"OSM source does not exist: {path}")
    if not any(
        str(path).lower().endswith(suffix) for suffix in SUPPORTED_SOURCE_SUFFIXES
    ):
        raise PoiIndexBuildError(f"unsupported OSM source format: {path.name}")


def _feature(
    osm_type: Literal["node", "way", "relation"],
    osm_id: int,
    coordinate: Coordinate,
    classification: PoiClassification,
) -> PoiFeature:
    if osm_type not in {"node", "way", "relation"} or osm_id < 0:
        raise ValueError("invalid OSM identity")
    return PoiFeature(
        id=f"{osm_type}/{osm_id}",
        osm_type=osm_type,
        osm_id=osm_id,
        coordinate=coordinate,
        category=classification.category,
        secondary_categories=classification.secondary_categories,
        group=classification.group,
        display_name=classification.display_name,
        name_source=classification.name_source,
        scenic_confidence=classification.scenic_confidence,
        potability=classification.potability,
        access_status=classification.access_status,
        ruins=classification.ruins,
        tags=classification.tags,
        source_updated_at=None,
        warnings=classification.warnings,
    )


def _insert_feature(features: dict[str, PoiFeature], feature: PoiFeature) -> None:
    if feature.id in features:
        raise PoiIndexBuildError(f"duplicate OSM object identity {feature.id}")
    features[feature.id] = feature


def _node_coordinate(node: osmium.osm.Node) -> Coordinate:
    if not node.location.valid():
        raise ValueError("node location is unavailable")
    return _coordinate(node.location.lon, node.location.lat)


def _way_coordinate(
    way: osmium.osm.Way,
    projection: LocalMetricProjection,
    *,
    polygonal: bool = True,
) -> Coordinate:
    positions = tuple(
        _validated_position(node.lon, node.lat)
        for node in way.nodes
        if node.location.valid()
    )
    if len(positions) != len(way.nodes) or len(positions) < 2:
        raise ValueError("way locations are incomplete")
    metric = tuple(projection.project_position(position) for position in positions)
    if positions[0] == positions[-1] and polygonal:
        if len(positions) < 4:
            raise ValueError("closed way has too few positions")
        polygon = Polygon(metric)
        if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
            raise ValueError("closed way polygon is invalid")
        point = polygon.representative_point()
    else:
        line = LineString(metric)
        if line.is_empty or not line.is_valid or line.length <= 0:
            raise ValueError("way line is invalid")
        point = line.interpolate(line.length / 2)
    longitude, latitude = projection.unproject_position((point.x, point.y))
    return _coordinate(longitude, latitude)


def _polygon_coordinate(
    geometry: BaseGeometry, projection: LocalMetricProjection
) -> Coordinate:
    if not isinstance(geometry, (Polygon, MultiPolygon)):
        raise ValueError("relation area is not polygonal")
    if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
        raise ValueError("relation polygon is invalid")
    metric = _project_polygonal(geometry, projection)
    if metric.is_empty or not metric.is_valid or metric.area <= 0:
        raise ValueError("projected relation polygon is invalid")
    point = metric.representative_point()
    longitude, latitude = projection.unproject_position((point.x, point.y))
    return _coordinate(longitude, latitude)


def _project_polygonal(
    geometry: Polygon | MultiPolygon, projection: LocalMetricProjection
) -> Polygon | MultiPolygon:
    if isinstance(geometry, Polygon):
        return _project_polygon(geometry, projection)
    return MultiPolygon(
        tuple(_project_polygon(polygon, projection) for polygon in geometry.geoms)
    )


def _project_polygon(polygon: Polygon, projection: LocalMetricProjection) -> Polygon:
    exterior = tuple(
        projection.project_position(_validated_position(x, y))
        for x, y in polygon.exterior.coords
    )
    holes = tuple(
        tuple(
            projection.project_position(_validated_position(x, y))
            for x, y in ring.coords
        )
        for ring in polygon.interiors
    )
    return Polygon(exterior, holes)


def _coordinate(longitude: float, latitude: float) -> Coordinate:
    longitude, latitude = _validated_position(longitude, latitude)
    return Coordinate(lat=latitude, lon=longitude)


def _validated_position(longitude: float, latitude: float) -> Wgs84Position:
    if not (
        isfinite(longitude)
        and isfinite(latitude)
        and -180 <= longitude <= 180
        and -90 <= latitude <= 90
    ):
        raise ValueError("invalid WGS84 position")
    return longitude, latitude


def _projection_for_header(box: osmium.osm.Box) -> LocalMetricProjection:
    reference_latitude = (
        (box.bottom_left.lat + box.top_right.lat) / 2 if box.valid() else 0.0
    )
    return LocalMetricProjection(reference_latitude)


def _document_bounds(
    features: tuple[PoiFeature, ...], header_box: osmium.osm.Box
) -> Wgs84BoundingBox:
    if header_box.valid():
        return (
            header_box.bottom_left.lon,
            header_box.bottom_left.lat,
            header_box.top_right.lon,
            header_box.top_right.lat,
        )
    if not features:
        raise PoiIndexBuildError(
            "OSM source has neither a header bounding box nor selected POIs"
        )
    longitudes = tuple(feature.coordinate.lon for feature in features)
    latitudes = tuple(feature.coordinate.lat for feature in features)
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def _feature_counts(
    features: tuple[PoiFeature, ...],
    field: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for feature in features:
        key = str(getattr(feature, field))
        counts[key] = counts.get(key, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _write_deterministic_gzip_atomic(output: Path, payload: bytes) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as raw_file:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw_file, mtime=0
            ) as gzip_file:
                gzip_file.write(payload)
            raw_file.flush()
            os.fsync(raw_file.fileno())
        os.replace(temporary_path, output)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return output.stat().st_size


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a deterministic local scenic and hydration POI index."
    )
    parser.add_argument("--osm-pbf", type=Path, default=DEFAULT_OSM_PBF)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _print_report(report: PoiIndexBuildReport) -> None:
    print(f"Source: {report.source.name}")
    print(f"Source bytes: {report.source.stat().st_size}")
    print(f"Output: {report.output}")
    print(f"Features: {report.feature_count}")
    print("Categories: " + _format_counts(report.category_counts))
    print("Potability: " + _format_counts(report.potability_counts))
    print("Access: " + _format_counts(report.access_counts))
    print(f"Skipped invalid: {report.skipped_invalid_count}")
    print(f"Bounding box: {report.bounding_box}")
    print(f"Uncompressed bytes: {report.uncompressed_size_bytes}")
    print(f"Compressed bytes: {report.compressed_size_bytes}")
    print(f"SHA-256: {report.sha256}")
    print(f"Elapsed: {report.elapsed_seconds:.3f} s")


def _format_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in counts.items()) or "none"


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = build_poi_index(arguments.osm_pbf, arguments.output)
    except PoiIndexBuildError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
