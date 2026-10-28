"""Bounded, lossless Nature partitions for one continuous routing region.

Whole OSM features belong to exactly one partition. Neither polygons nor routing
geometry are clipped at partition boundaries. The manifest pins every file.
"""

import argparse
import gzip
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from shapely.geometry import shape

from sugarglider.nature.models import NatureIndexDocument, NatureIndexFeature
from sugarglider.offline_regions.models import (
    RegionalManifest,
    RegionBounds,
    RelativePath,
    Sha256,
    StrictModel,
    canonical_json,
    contained_path,
)

MAX_PARTITIONS = 64
MAX_PARTITION_POSITIONS = 500_000
MAX_PARTITION_BYTES = 16 * 1024 * 1024
MAX_DIRECTORY_BYTES = 32_768


class NaturePartition(StrictModel):
    path: RelativePath
    bounds: RegionBounds
    feature_count: Annotated[int, Field(gt=0, le=250_000)]
    position_count: Annotated[int, Field(gt=0, le=MAX_PARTITION_POSITIONS)]


class NaturePartitions(StrictModel):
    schema_version: Literal[1] = 1
    source_sha256: Sha256
    source_basename: str
    source_size_bytes: Annotated[int, Field(gt=0)]
    bounds: RegionBounds
    reference_latitude: float
    feature_count: Annotated[int, Field(ge=0, le=250_000)]
    position_count: Annotated[int, Field(ge=0)]
    partitions: Annotated[
        tuple[NaturePartition, ...], Field(min_length=1, max_length=MAX_PARTITIONS)
    ]

    @model_validator(mode="after")
    def exact_partition_inventory(self) -> Self:
        if tuple(p.path for p in self.partitions) != tuple(
            partition_path(i) for i in range(len(self.partitions))
        ):
            raise ValueError("invalid Nature partition inventory")
        if self.feature_count != sum(p.feature_count for p in self.partitions) or (
            self.position_count != sum(p.position_count for p in self.partitions)
        ):
            raise ValueError("Nature partition totals differ")
        if not self.bounds[1] <= self.reference_latitude <= self.bounds[3]:
            raise ValueError("invalid Nature reference latitude")
        return self


def partition_path(index: int) -> str:
    return f"nature/part-{index:03}.json.gz"


def position_count(feature: NatureIndexFeature) -> int:
    geometry = feature.geometry
    polygons = (
        (geometry.coordinates,) if geometry.type == "Polygon" else geometry.coordinates
    )
    return sum(len(ring) for polygon in polygons for ring in polygon)


def partition_document(
    document: NatureIndexDocument, features: tuple[NatureIndexFeature, ...]
) -> NatureIndexDocument:
    counts: Counter[str] = Counter()
    for feature in features:
        if feature.primary_class is not None:
            counts[feature.primary_class] += 1
        if feature.park_or_protected:
            counts["park_or_protected"] += 1
    return NatureIndexDocument(
        metadata=document.metadata.model_copy(
            update={"feature_count": len(features), "category_counts": dict(counts)}
        ),
        features=tuple(sorted(features, key=lambda f: f.feature_id)),
    )


def partition_nature(
    source: Path, output: Path, source_sha256: str
) -> NaturePartitions:
    """Build privately into a fresh directory; never mutate an existing index."""
    document = NatureIndexDocument.model_validate_json(
        gzip.decompress(source.read_bytes())
    )
    if not document.features:
        raise ValueError("partitioning an empty Nature index is unnecessary")
    output.mkdir()
    bounds = {
        f.feature_id: tuple(shape(f.geometry.model_dump()).bounds)
        for f in document.features
    }
    positions = {f.feature_id: position_count(f) for f in document.features}
    parts: list[NaturePartition] = []

    def emit(features: tuple[NatureIndexFeature, ...]) -> None:
        count = sum(positions[f.feature_id] for f in features)
        payload = canonical_json(
            partition_document(document, features).model_dump(mode="json")
        )
        if count > MAX_PARTITION_POSITIONS or len(payload) > MAX_PARTITION_BYTES:
            if len(features) < 2:
                raise ValueError(
                    "one Nature feature exceeds the bounded partition limit"
                )
            # Split complete features spatially; large crossing features remain
            # intact, with their full extent in the directory's pruning bounds.
            axis = max(
                range(2),
                key=lambda a: (
                    max(bounds[f.feature_id][a + 2] for f in features)
                    - min(bounds[f.feature_id][a] for f in features)
                ),
            )
            ordered = tuple(
                sorted(
                    features,
                    key=lambda f: (
                        bounds[f.feature_id][axis] + bounds[f.feature_id][axis + 2],
                        f.feature_id,
                    ),
                )
            )
            middle = len(ordered) // 2
            emit(ordered[:middle])
            emit(ordered[middle:])
            return
        if len(parts) >= MAX_PARTITIONS:
            raise ValueError("Nature partition count exceeds limit")
        path = partition_path(len(parts))
        extent = tuple(
            (min if a < 2 else max)(bounds[f.feature_id][a] for f in features)
            for a in range(4)
        )
        part = NaturePartition.model_validate(
            {
                "path": path,
                "bounds": extent,
                "feature_count": len(features),
                "position_count": count,
            }
        )
        (output / Path(path).name).write_bytes(
            gzip.compress(payload, compresslevel=9, mtime=0)
        )
        parts.append(part)

    emit(document.features)
    result = NaturePartitions(
        source_sha256=source_sha256,
        source_basename=document.metadata.source_basename,
        source_size_bytes=document.metadata.source_size_bytes or 0,
        bounds=document.metadata.bounding_box,
        reference_latitude=document.metadata.reference_latitude,
        feature_count=len(document.features),
        position_count=sum(positions.values()),
        partitions=tuple(parts),
    )
    payload = canonical_json(result.model_dump(mode="json"))
    if len(payload) > MAX_DIRECTORY_BYTES:
        raise ValueError("Nature partition directory exceeds limit")
    (output / "partitions.json").write_bytes(payload)
    return result


def verify_nature_partitions(root: Path, manifest: RegionalManifest) -> None:
    directory_path = contained_path(root, "nature/partitions.json")
    if directory_path.stat().st_size > MAX_DIRECTORY_BYTES:
        raise ValueError("Nature partition directory exceeds limit")
    directory = NaturePartitions.model_validate_json(directory_path.read_bytes())
    if (
        directory.source_sha256 != manifest.source.sha256
        or directory.source_basename != manifest.source.basename
        or directory.source_size_bytes != manifest.source.byte_size
        or directory.bounds != manifest.bounds
        or tuple(p.path for p in directory.partitions)
        != tuple(f.path for f in manifest.components.nature.files[1:])
    ):
        raise ValueError("Nature partition identity mismatch")
    seen: set[str] = set()
    for part in directory.partitions:
        with gzip.open(contained_path(root, part.path), "rb") as stream:
            payload = stream.read(MAX_PARTITION_BYTES + 1)
        if len(payload) > MAX_PARTITION_BYTES:
            raise ValueError("Nature partition exceeds expanded byte limit")
        document = NatureIndexDocument.model_validate_json(payload)
        metadata = document.metadata
        if (
            metadata.source_basename != directory.source_basename
            or metadata.source_size_bytes != directory.source_size_bytes
            or metadata.bounding_box != directory.bounds
            or metadata.reference_latitude != directory.reference_latitude
            or metadata.feature_count != part.feature_count
            or sum(position_count(f) for f in document.features) != part.position_count
            or any(f.feature_id in seen for f in document.features)
        ):
            raise ValueError("Nature partition contents mismatch")
        if partition_document(document, document.features).metadata != metadata:
            raise ValueError("Nature partition category counts mismatch")
        extents = [shape(f.geometry.model_dump()).bounds for f in document.features]
        bounds = tuple((min if a < 2 else max)(b[a] for b in extents) for a in range(4))
        if bounds != part.bounds:
            raise ValueError("Nature partition pruning bounds mismatch")
        seen.update(f.feature_id for f in document.features)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    args = parser.parse_args()
    result = partition_nature(args.source, args.output, args.source_sha256)
    print(canonical_json(result.model_dump(mode="json")).decode(), end="")


if __name__ == "__main__":
    main()
