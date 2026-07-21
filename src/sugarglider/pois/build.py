"""Offline CLI for streaming OSM objects into a deterministic gzip POI index."""

import argparse
import gzip
import hashlib
import json
import os
import sys
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal, cast

import osmium
from shapely import STRtree
from shapely.errors import GEOSException
from shapely.geometry import LineString, MultiPoint, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.wkb import loads as load_wkb

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.models import Coordinate
from sugarglider.pois.classification import (
    CLASSIFIER_VERSION,
    PoiClassification,
    classify_osm_tags,
)
from sugarglider.pois.errors import PoiIndexBuildError
from sugarglider.pois.models import (
    AccessStatus,
    PoiApproachCandidate,
    PoiApproachKind,
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
type StructureSignature = tuple[str | None, str | None, str, str, str]


@dataclass(frozen=True)
class _AccessNode:
    osm_id: int
    coordinate: Coordinate
    kind: str
    access: AccessStatus
    name: str | None


@dataclass(frozen=True)
class _PedestrianPath:
    osm_id: int
    geometry: LineString
    access: AccessStatus
    node_ids: tuple[int, ...]
    coordinates: tuple[Coordinate, ...]
    structure: StructureSignature


@dataclass(frozen=True)
class PoiIndexBuildReport:
    source: Path
    output: Path
    feature_count: int
    category_counts: dict[str, int]
    potability_counts: dict[str, int]
    access_counts: dict[str, int]
    approach_counts: dict[str, int]
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
    polygon_geometries: dict[str, Polygon | MultiPolygon] = {}
    polygon_boundary_nodes: dict[str, frozenset[int]] = {}
    polygon_structures: dict[str, StructureSignature] = {}
    access_nodes: list[_AccessNode] = []
    public_paths: list[_PedestrianPath] = []
    classified_relations: set[int] = set()
    handled_relations: set[int] = set()
    skipped_invalid = 0
    try:
        processor = osmium.FileProcessor(osm_source).with_locations().with_areas()
        header_box = processor.header.box()
        projection = _projection_for_header(header_box)
        for entity in processor:
            if isinstance(entity, osmium.osm.Node):
                tags = {tag.k: tag.v for tag in entity.tags}
                classification = classify_osm_tags(tags)
                is_access_candidate = (
                    "entrance" in tags or tags.get("barrier") == "gate"
                )
                if classification is None and not is_access_candidate:
                    continue
                try:
                    coordinate = _node_coordinate(entity)
                    access_node = _access_node(entity.id, coordinate, tags)
                    if access_node is not None:
                        access_nodes.append(access_node)
                except (RuntimeError, ValueError, TypeError):
                    skipped_invalid += 1
                    continue
                if classification is None:
                    continue
                try:
                    _insert_feature(
                        features,
                        _feature(
                            "node",
                            entity.id,
                            coordinate,
                            classification,
                            approaches=_node_approaches(
                                entity.id, coordinate, classification
                            ),
                        ),
                    )
                except (RuntimeError, ValueError, TypeError):
                    skipped_invalid += 1
            elif isinstance(entity, osmium.osm.Way):
                tags = {tag.k: tag.v for tag in entity.tags}
                classification = classify_osm_tags(tags)
                public_path = _is_public_path(tags)
                if classification is None and not public_path:
                    continue
                try:
                    positions = _way_positions(entity)
                    if public_path:
                        public_paths.append(
                            _PedestrianPath(
                                osm_id=entity.id,
                                geometry=LineString(
                                    tuple(
                                        projection.project_position(position)
                                        for position in positions
                                    )
                                ),
                                access=_access_status(tags),
                                node_ids=tuple(node.ref for node in entity.nodes),
                                coordinates=tuple(
                                    _coordinate(longitude, latitude)
                                    for longitude, latitude in positions
                                ),
                                structure=_structure_signature(tags),
                            )
                        )
                    metric_geometry = (
                        _way_metric_geometry(
                            positions,
                            projection,
                            polygonal=tags.get("area") != "no",
                        )
                        if classification is not None
                        else None
                    )
                except (GEOSException, RuntimeError, ValueError, TypeError):
                    metric_geometry = None
                if classification is None:
                    continue
                try:
                    if metric_geometry is None:
                        raise ValueError("way geometry is unavailable")
                    coordinate = _metric_representative_coordinate(
                        metric_geometry, projection
                    )
                    feature = _feature("way", entity.id, coordinate, classification)
                    _insert_feature(
                        features,
                        feature,
                    )
                    if isinstance(metric_geometry, Polygon):
                        polygon_geometries[feature.id] = metric_geometry
                        polygon_boundary_nodes[feature.id] = frozenset(
                            node.ref for node in entity.nodes
                        )
                        polygon_structures[feature.id] = _structure_signature(tags)
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
                    if not isinstance(geometry, (Polygon, MultiPolygon)):
                        raise ValueError("relation area is not polygonal")
                    coordinate = _polygon_coordinate(geometry, projection)
                    relation_metric_geometry = _project_polygonal(geometry, projection)
                    feature = _feature("relation", osm_id, coordinate, classification)
                    _insert_feature(
                        features,
                        feature,
                    )
                    polygon_geometries[feature.id] = relation_metric_geometry
                    polygon_boundary_nodes[feature.id] = frozenset(
                        node.ref for ring in entity.outer_rings() for node in ring
                    )
                    polygon_structures[feature.id] = _structure_signature(
                        {tag.k: tag.v for tag in entity.tags}
                    )
                except (GEOSException, RuntimeError, ValueError, TypeError):
                    skipped_invalid += 1
    except (RuntimeError, OSError) as exc:
        raise PoiIndexBuildError(
            f"failed to read OSM objects from {osm_source.name}"
        ) from exc

    skipped_invalid += len(classified_relations - handled_relations)
    access_node_tree = STRtree(
        tuple(
            Point(projection.project_position((coordinate.lon, coordinate.lat)))
            for access_node in access_nodes
            for coordinate in (access_node.coordinate,)
        )
    )
    public_path_tree = STRtree(tuple(path.geometry for path in public_paths))
    for feature_id, geometry in polygon_geometries.items():
        feature = features[feature_id]
        features[feature_id] = feature.model_copy(
            update={
                "approach_candidates": _polygon_approaches(
                    feature,
                    geometry,
                    projection,
                    tuple(access_nodes),
                    access_node_tree,
                    tuple(public_paths),
                    public_path_tree,
                    boundary_node_ids=polygon_boundary_nodes.get(
                        feature_id, frozenset()
                    ),
                    feature_structure=polygon_structures.get(
                        feature_id, _structure_signature({})
                    ),
                )
            }
        )
    ordered = tuple(features[key] for key in sorted(features))
    bounds = _document_bounds(ordered, header_box)
    category_counts = _feature_counts(ordered, "category")
    potability_counts = _feature_counts(ordered, "potability")
    access_counts = _feature_counts(ordered, "access_status")
    approach_counts = _approach_counts(ordered)
    document = PoiIndexDocument(
        metadata=PoiIndexMetadata(
            source_basename=osm_source.name,
            source_size_bytes=osm_source.stat().st_size,
            feature_count=len(ordered),
            category_counts=cast(dict[PoiCategory, int], category_counts),
            potability_counts=cast(dict[Potability, int], potability_counts),
            access_counts=cast(dict[AccessStatus, int], access_counts),
            approach_counts=cast(dict[PoiApproachKind, int], approach_counts),
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
        approach_counts=approach_counts,
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
    *,
    approaches: tuple[PoiApproachCandidate, ...] = (),
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
        approach_candidates=approaches,
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


def _way_positions(way: osmium.osm.Way) -> tuple[Wgs84Position, ...]:
    positions = tuple(
        _validated_position(node.lon, node.lat)
        for node in way.nodes
        if node.location.valid()
    )
    if len(positions) != len(way.nodes) or len(positions) < 2:
        raise ValueError("way locations are incomplete")
    return positions


def _way_metric_geometry(
    positions: tuple[Wgs84Position, ...],
    projection: LocalMetricProjection,
    *,
    polygonal: bool,
) -> LineString | Polygon:
    metric = tuple(projection.project_position(position) for position in positions)
    if positions[0] == positions[-1] and polygonal:
        if len(positions) < 4:
            raise ValueError("closed way has too few positions")
        polygon = Polygon(metric)
        if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
            raise ValueError("closed way polygon is invalid")
        return polygon
    line = LineString(metric)
    if line.is_empty or not line.is_valid or line.length <= 0:
        raise ValueError("way line is invalid")
    return line


def _metric_representative_coordinate(
    geometry: LineString | Polygon,
    projection: LocalMetricProjection,
) -> Coordinate:
    point = (
        geometry.representative_point()
        if isinstance(geometry, Polygon)
        else geometry.interpolate(geometry.length / 2)
    )
    longitude, latitude = projection.unproject_position((point.x, point.y))
    return _coordinate(longitude, latitude)


def _access_status(tags: dict[str, str]) -> AccessStatus:
    access = tags.get("access", "").casefold()
    if access in {"private", "no"}:
        return "private"
    if access in {"customers", "permit", "destination"}:
        return "restricted"
    if access in {"yes", "permissive", "designated"}:
        return "public"
    return "unknown"


def _access_node(
    osm_id: int,
    coordinate: Coordinate,
    tags: dict[str, str],
) -> _AccessNode | None:
    entrance = tags.get("entrance")
    gate = tags.get("barrier") == "gate"
    if entrance is None and not gate:
        return None
    if entrance in {"no", "private"} or tags.get("locked") == "yes":
        return None
    access = _access_status(tags)
    if access in {"private", "restricted"}:
        return None
    return _AccessNode(
        osm_id=osm_id,
        coordinate=coordinate,
        kind="mapped_entrance" if entrance is not None else "mapped_gate",
        access=access,
        name=tags.get("name"),
    )


def _is_public_path(tags: dict[str, str]) -> bool:
    return (
        tags.get("highway")
        in {"footway", "path", "track", "pedestrian", "steps", "living_street"}
        and _access_status(tags) not in {"private", "restricted"}
        and tags.get("foot") not in {"no", "private"}
    )


def _structure_signature(tags: dict[str, str]) -> StructureSignature:
    return (
        tags.get("layer"),
        tags.get("level"),
        tags.get("bridge", "no"),
        tags.get("tunnel", "no"),
        tags.get("covered", tags.get("indoor", "no")),
    )


def _compatible_structures(
    feature: StructureSignature, path: StructureSignature
) -> bool:
    """Reject crossings that are not demonstrably on the same physical level."""
    feature_layer, feature_level, feature_bridge, feature_tunnel, feature_covered = (
        feature
    )
    path_layer, path_level, path_bridge, path_tunnel, path_covered = path
    if feature_layer != path_layer and (
        feature_layer is not None or path_layer is not None
    ):
        return False
    if feature_level != path_level and (
        feature_level is not None or path_level is not None
    ):
        return False
    return (
        feature_bridge == path_bridge
        and feature_tunnel == path_tunnel
        and feature_covered == path_covered
    )


def _node_approaches(
    osm_id: int,
    coordinate: Coordinate,
    classification: PoiClassification,
) -> tuple[PoiApproachCandidate, ...]:
    if classification.access_status in {"private", "restricted"}:
        return ()
    if classification.category == "drinking_water":
        kind: PoiApproachKind = "drinking_water_source"
        tolerance = 15.0
    elif classification.category == "viewpoint":
        kind = "viewpoint_location"
        tolerance = 20.0
    elif classification.category == "observation_tower":
        kind = "exact_feature"
        tolerance = 20.0
    else:
        kind = "exact_feature"
        tolerance = 25.0
    return (
        PoiApproachCandidate(
            id=f"node/{osm_id}/approach/00-exact",
            coordinate=coordinate,
            kind=kind,
            source="osm_feature",
            access=classification.access_status,
            semantic_distance_m=0.0,
            arrival_tolerance_m=tolerance,
            name=classification.display_name,
            osm_type="node",
            osm_id=osm_id,
            provenance="feature_geometry",
        ),
    )


def _polygon_approaches(
    feature: PoiFeature,
    geometry: Polygon | MultiPolygon,
    projection: LocalMetricProjection,
    access_nodes: tuple[_AccessNode, ...],
    access_node_tree: STRtree,
    public_paths: tuple[_PedestrianPath, ...],
    public_path_tree: STRtree,
    *,
    boundary_node_ids: frozenset[int],
    feature_structure: StructureSignature,
) -> tuple[PoiApproachCandidate, ...]:
    if feature.access_status in {"private", "restricted"}:
        return ()
    boundary = geometry.boundary
    candidates: list[PoiApproachCandidate] = []
    access_indices = tuple(
        sorted(
            cast(Iterable[int], access_node_tree.query(boundary.buffer(1.0).envelope))
        )
    )
    for access_index in access_indices:
        access_node = access_nodes[access_index]
        osm_id = access_node.osm_id
        coordinate = access_node.coordinate
        kind = access_node.kind
        access = access_node.access
        name = access_node.name
        metric = Point(projection.project_position((coordinate.lon, coordinate.lat)))
        topological = osm_id in boundary_node_ids
        if not topological and boundary.distance(metric) > 1.0:
            continue
        candidates.append(
            PoiApproachCandidate(
                id=f"{feature.id}/approach/00-{kind}-{osm_id}",
                coordinate=coordinate,
                kind=cast(PoiApproachKind, kind),
                source=(
                    "osm_entrance"
                    if topological and kind == "mapped_entrance"
                    else "osm_gate"
                    if topological
                    else "osm_spatial_boundary_inference"
                ),
                access=access,
                semantic_distance_m=haversine_distance_m(
                    (feature.coordinate.lon, feature.coordinate.lat),
                    (coordinate.lon, coordinate.lat),
                ),
                arrival_tolerance_m=20.0,
                name=name,
                osm_type="node",
                osm_id=osm_id,
                provenance=(
                    "way_boundary_node"
                    if topological and feature.osm_type == "way"
                    else "relation_boundary_node"
                    if topological
                    else "spatial_boundary_inferred"
                ),
                warnings=(
                    () if topological else ("spatial_boundary_association_unverified",)
                ),
            )
        )
    path_indices = tuple(
        sorted(cast(Iterable[int], public_path_tree.query(boundary.envelope)))
    )
    for path_index in path_indices:
        path = public_paths[path_index]
        if not _compatible_structures(feature_structure, path.structure):
            continue
        shared = tuple(
            (node_id, coordinate)
            for node_id, coordinate in zip(path.node_ids, path.coordinates, strict=True)
            if node_id in boundary_node_ids
        )
        for point_index, (node_id, coordinate) in enumerate(shared):
            candidates.append(
                PoiApproachCandidate(
                    id=(
                        f"{feature.id}/approach/10-path-{path.osm_id}-"
                        f"{node_id}-{point_index:02d}"
                    ),
                    coordinate=coordinate,
                    kind="public_path_boundary",
                    source="osm_path_intersection",
                    access=path.access,
                    semantic_distance_m=haversine_distance_m(
                        (feature.coordinate.lon, feature.coordinate.lat),
                        (coordinate.lon, coordinate.lat),
                    ),
                    arrival_tolerance_m=20.0,
                    osm_type="way",
                    osm_id=path.osm_id,
                    provenance="shared_path_boundary_node",
                )
            )
    unique: dict[tuple[int, int], PoiApproachCandidate] = {}
    for candidate in sorted(
        candidates,
        key=lambda value: (
            0
            if value.provenance in {"way_boundary_node", "relation_boundary_node"}
            else 1,
            0 if value.kind == "mapped_entrance" else 1,
            0 if value.kind == "mapped_gate" else 1,
            value.semantic_distance_m,
            value.id,
        ),
    ):
        key = (
            round(candidate.coordinate.lat * 10_000_000),
            round(candidate.coordinate.lon * 10_000_000),
        )
        unique.setdefault(key, candidate)
    retained = tuple(unique.values())[:8]
    return tuple(sorted(retained, key=lambda value: value.id))


def _intersection_points(geometry: BaseGeometry) -> tuple[Point, ...]:
    if geometry.is_empty:
        return ()
    if isinstance(geometry, Point):
        return (geometry,)
    if isinstance(geometry, MultiPoint):
        return tuple(sorted(geometry.geoms, key=lambda point: (point.x, point.y)))
    if isinstance(geometry, LineString):
        start, end = geometry.boundary.geoms
        return tuple(sorted((start, end), key=lambda point: (point.x, point.y)))
    points: list[Point] = []
    for part in getattr(geometry, "geoms", ()):
        points.extend(_intersection_points(part))
    return tuple(sorted(points, key=lambda point: (point.x, point.y)))


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


def _approach_counts(features: tuple[PoiFeature, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for feature in features:
        for approach in feature.approach_candidates:
            counts[approach.kind] = counts.get(approach.kind, 0) + 1
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
    print("Approaches: " + _format_counts(report.approach_counts))
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
