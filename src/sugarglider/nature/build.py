"""CLI for streaming local OSM areas into a deterministic gzip JSON index."""

import argparse
import gzip
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import osmium
from shapely import normalize
from shapely.errors import GEOSException
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, mapping
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid
from shapely.wkb import loads as load_wkb

from sugarglider.nature.classification import (
    PRIMARY_CLASS_PRIORITY,
    classify_osm_tags,
    relevant_tags,
)
from sugarglider.nature.errors import NatureIndexBuildError
from sugarglider.nature.models import (
    MultiPolygonGeometry,
    NatureGeometry,
    NatureIndexDocument,
    NatureIndexFeature,
    NatureIndexMetadata,
    PolygonGeometry,
    Wgs84BoundingBox,
)

DEFAULT_OSM_PBF = Path("data/osm/ile-de-france-latest.osm.pbf")
DEFAULT_OUTPUT = Path("data/nature/ile-de-france-nature-index.json.gz")
SUPPORTED_SOURCE_SUFFIXES = (".osm", ".xml", ".pbf", ".osm.pbf")


@dataclass(frozen=True)
class NatureIndexBuildReport:
    source: Path
    output: Path
    feature_count: int
    category_counts: dict[str, int]
    skipped_invalid_features: int
    uncompressed_size_bytes: int
    compressed_size_bytes: int
    elapsed_seconds: float


def build_nature_index(osm_source: Path, output: Path) -> NatureIndexBuildReport:
    """Stream area objects, retain selected polygons, and atomically write an index."""
    started = time.perf_counter()
    if not osm_source.is_file():
        raise NatureIndexBuildError(f"OSM source does not exist: {osm_source}")
    if not any(
        str(osm_source).lower().endswith(suffix) for suffix in SUPPORTED_SOURCE_SUFFIXES
    ):
        raise NatureIndexBuildError(f"unsupported OSM source format: {osm_source.name}")

    factory = osmium.geom.WKBFactory()
    features: list[NatureIndexFeature] = []
    skipped_invalid = 0
    try:
        processor = osmium.FileProcessor(osm_source).with_areas()
        header_box = processor.header.box()
        for entity in processor:
            if not isinstance(entity, osmium.osm.Area):
                continue
            tags = {tag.k: tag.v for tag in entity.tags}
            classification = classify_osm_tags(tags)
            if classification is None:
                continue
            try:
                raw_geometry = load_wkb(factory.create_multipolygon(entity), hex=True)
                geometry = _valid_polygonal_geometry(raw_geometry)
                if geometry is None:
                    skipped_invalid += 1
                    continue
                source: Literal["way", "relation"] = (
                    "way" if entity.from_way() else "relation"
                )
                osm_id = entity.orig_id()
                feature_id = f"{source}/{osm_id}"
                features.append(
                    NatureIndexFeature(
                        feature_id=feature_id,
                        osm_id=osm_id,
                        osm_source=source,
                        primary_class=classification.primary_class,
                        park_or_protected=classification.park_or_protected,
                        tags=relevant_tags(tags),
                        geometry=_geometry_model(geometry),
                    )
                )
            except (GEOSException, RuntimeError, ValueError, TypeError):
                skipped_invalid += 1
    except (RuntimeError, OSError) as exc:
        raise NatureIndexBuildError(
            f"failed to read OSM areas from {osm_source.name}"
        ) from exc

    ordered_features = tuple(sorted(features, key=lambda feature: feature.feature_id))
    if len({feature.feature_id for feature in ordered_features}) != len(
        ordered_features
    ):
        raise NatureIndexBuildError(
            "OSM area processing produced duplicate feature IDs"
        )
    bounds = _document_bounds(ordered_features, header_box)
    _west, south, _east, north = bounds
    reference_latitude = (south + north) / 2
    counts = _category_counts(ordered_features)
    document = NatureIndexDocument(
        metadata=NatureIndexMetadata(
            source_basename=osm_source.name,
            source_size_bytes=osm_source.stat().st_size,
            reference_latitude=reference_latitude,
            bounding_box=bounds,
            category_counts=counts,
            feature_count=len(ordered_features),
        ),
        features=ordered_features,
    )
    payload = json.dumps(
        document.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    compressed_size = _write_deterministic_gzip_atomic(output, payload)
    return NatureIndexBuildReport(
        source=osm_source,
        output=output,
        feature_count=len(ordered_features),
        category_counts=counts,
        skipped_invalid_features=skipped_invalid,
        uncompressed_size_bytes=len(payload),
        compressed_size_bytes=compressed_size,
        elapsed_seconds=time.perf_counter() - started,
    )


def _valid_polygonal_geometry(
    geometry: BaseGeometry,
) -> Polygon | MultiPolygon | None:
    candidate = geometry if geometry.is_valid else make_valid(geometry)
    polygons: list[Polygon] = []
    if isinstance(candidate, Polygon):
        polygons.append(candidate)
    elif isinstance(candidate, MultiPolygon):
        polygons.extend(candidate.geoms)
    elif isinstance(candidate, GeometryCollection):
        for part in candidate.geoms:
            if isinstance(part, Polygon):
                polygons.append(part)
            elif isinstance(part, MultiPolygon):
                polygons.extend(part.geoms)
    polygons = [
        polygon for polygon in polygons if not polygon.is_empty and polygon.area > 0
    ]
    if not polygons:
        return None
    combined: Polygon | MultiPolygon = (
        polygons[0] if len(polygons) == 1 else MultiPolygon(tuple(polygons))
    )
    canonical = cast(BaseGeometry, normalize(combined))
    if isinstance(canonical, (Polygon, MultiPolygon)) and canonical.is_valid:
        return canonical
    return None


def _geometry_model(geometry: Polygon | MultiPolygon) -> NatureGeometry:
    geojson = mapping(geometry)
    if isinstance(geometry, Polygon):
        return PolygonGeometry.model_validate(geojson)
    return MultiPolygonGeometry.model_validate(geojson)


def _category_counts(features: tuple[NatureIndexFeature, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for category in PRIMARY_CLASS_PRIORITY:
        count = sum(feature.primary_class == category for feature in features)
        if count:
            counts[category] = count
    protected_count = sum(feature.park_or_protected for feature in features)
    if protected_count:
        counts["park_or_protected"] = protected_count
    return {key: counts[key] for key in sorted(counts)}


def _document_bounds(
    features: tuple[NatureIndexFeature, ...], header_box: osmium.osm.Box
) -> Wgs84BoundingBox:
    header_bounds: Wgs84BoundingBox | None = None
    if header_box.valid():
        header_bounds = (
            header_box.bottom_left.lon,
            header_box.bottom_left.lat,
            header_box.top_right.lon,
            header_box.top_right.lat,
        )
    feature_west: float | None = None
    feature_south: float | None = None
    feature_east: float | None = None
    feature_north: float | None = None
    for feature in features:
        for longitude, latitude in _feature_positions(feature.geometry):
            feature_west = (
                longitude if feature_west is None else min(feature_west, longitude)
            )
            feature_south = (
                latitude if feature_south is None else min(feature_south, latitude)
            )
            feature_east = (
                longitude if feature_east is None else max(feature_east, longitude)
            )
            feature_north = (
                latitude if feature_north is None else max(feature_north, latitude)
            )
    if feature_west is None and header_bounds is None:
        raise NatureIndexBuildError(
            "OSM source has neither a header bounding box nor selected features"
        )
    if feature_west is None:
        assert header_bounds is not None
        return header_bounds
    assert feature_south is not None
    assert feature_east is not None
    assert feature_north is not None
    feature_bounds: Wgs84BoundingBox = (
        feature_west,
        feature_south,
        feature_east,
        feature_north,
    )
    if header_bounds is None:
        return feature_bounds
    return (
        min(header_bounds[0], feature_bounds[0]),
        min(header_bounds[1], feature_bounds[1]),
        max(header_bounds[2], feature_bounds[2]),
        max(header_bounds[3], feature_bounds[3]),
    )


def _feature_positions(geometry: NatureGeometry) -> tuple[tuple[float, float], ...]:
    if isinstance(geometry, PolygonGeometry):
        return tuple(position for ring in geometry.coordinates for position in ring)
    return tuple(
        position
        for polygon in geometry.coordinates
        for ring in polygon
        for position in ring
    )


def _write_deterministic_gzip_atomic(output: Path, payload: bytes) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as raw_file:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw_file,
                mtime=0,
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
        description="Build a deterministic local OSM nature index."
    )
    parser.add_argument("--osm-pbf", type=Path, default=DEFAULT_OSM_PBF)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _print_report(report: NatureIndexBuildReport) -> None:
    print(f"Source: {report.source}")
    print(f"Output: {report.output}")
    print(f"Features: {report.feature_count}")
    print(
        "Classes: "
        + (
            ", ".join(f"{key}={value}" for key, value in report.category_counts.items())
            or "none"
        )
    )
    print(f"Skipped invalid: {report.skipped_invalid_features}")
    print(f"Uncompressed bytes: {report.uncompressed_size_bytes}")
    print(f"Compressed bytes: {report.compressed_size_bytes}")
    print(f"Elapsed: {report.elapsed_seconds:.3f} s")


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = build_nature_index(arguments.osm_pbf, arguments.output)
    except NatureIndexBuildError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
