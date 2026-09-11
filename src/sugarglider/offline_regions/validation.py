"""Build-time validation of existing independent formats, without changing them."""

import gzip
import re
import struct
import tarfile
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from sugarglider.nature.models import NatureIndexDocument
from sugarglider.offline_regions.map_manifest import file_sha256, validate_archive
from sugarglider.offline_regions.models import (
    Identifier,
    RegionalManifest,
    RegionBounds,
    RegionSpec,
    StrictModel,
    contained_path,
)
from sugarglider.pois.models import PoiIndexDocument


class MapManifest(StrictModel):
    schema_version: Literal[1]
    pack_id: Identifier
    display_name: Annotated[str, Field(min_length=1, max_length=120)]
    bounds: RegionBounds
    min_zoom: Annotated[int, Field(ge=0, le=22)]
    max_zoom: Annotated[int, Field(ge=0, le=22)]
    archive_filename: Literal["basemap.pmtiles"]
    byte_size: Annotated[int, Field(gt=0, le=2_147_483_648)]
    format: Literal["pmtiles-v3"]
    tile_type: Literal["mvt"]
    attribution: Annotated[str, Field(min_length=1, max_length=2048)]
    data_source: Annotated[str, Field(min_length=1, max_length=240)]
    build_id: Annotated[str, Field(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def runtime_constraints(self) -> Self:
        for text in (self.display_name, self.attribution, self.data_source):
            if text.strip() != text or re.search(r"[\x00-\x1f\x7f]", text):
                raise ValueError("invalid map manifest text")
        if (
            self.min_zoom > self.max_zoom
            or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", self.build_id)
            or ".." in self.build_id
        ):
            raise ValueError("invalid map zoom/build identity")
        return self


class RoutingBounds(StrictModel):
    west: float
    south: float
    east: float
    north: float


class RoutingManifest(StrictModel):
    schema_version: Literal[2]
    pack_id: Identifier
    engine: Literal["valhalla"]
    engine_version: Literal["3.6.3"]
    access_modes: tuple[Literal["foot"], Literal["bicycle"]]
    bounds: RoutingBounds


def read_map(path: Path) -> MapManifest:
    if path.stat().st_size > 16_384:
        raise ValueError("map manifest exceeds runtime size limit")
    return MapManifest.model_validate_json(path.read_bytes())


def load_spec(root: Path, region_id: str) -> RegionSpec:
    spec = RegionSpec.model_validate_json(
        contained_path(root, f"offline-regions/{region_id}.json").read_bytes()
    )
    if spec.region_id != region_id:
        raise ValueError("region spec filename/ID mismatch")
    template = read_map(contained_path(root, spec.map.template))
    if template.pack_id != spec.map.pack_id or template.bounds != spec.bounds:
        raise ValueError("map template ID/bounds differ from region spec")
    # The existing builder intentionally builds these development zooms only.
    if (template.min_zoom, template.max_zoom) != (0, 15):
        raise ValueError("map builder requires template zooms 0..15")
    return spec


def validate_pmtiles(path: Path, manifest: MapManifest) -> None:
    try:
        size = validate_archive(path, manifest.model_dump(mode="json"))
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc
    if size != manifest.byte_size:
        raise ValueError("map manifest byte size differs from final archive")
    with path.open("rb") as stream:
        header = stream.read(127)
    # Check all four section ranges, including empty leaves, and non-empty tiles.
    ranges: list[tuple[int, int]] = []
    for position in (8, 24, 40, 56):
        offset, length = struct.unpack_from("<QQ", header, position)
        if length == 0 and position == 40:
            continue
        if length == 0 or offset < 127 or offset + length > size:
            raise ValueError("invalid PMTiles section range")
        if position == 8 and offset + length > 16_384:
            raise ValueError("PMTiles root directory exceeds first 16 KiB")
        ranges.append((offset, offset + length))
    # PMTiles v3 permits arbitrary section order (Planetiler puts metadata last).
    ordered_ranges = sorted(ranges)
    if any(
        left[1] > right[0]
        for left, right in zip(ordered_ranges, ordered_ranges[1:], strict=False)
    ):
        raise ValueError("overlapping PMTiles sections")
    if header[97] not in (1, 2) or header[98] not in (1, 2):
        raise ValueError("unsupported PMTiles compression")
    # Tile-count fields are informational; zero means unknown in PMTiles v3.


def validate_tar(path: Path) -> None:
    if path.stat().st_size % 512:
        raise ValueError("truncated Valhalla tar")
    tiles: list[tuple[int, int, int]] = []
    index: bytes | None = None
    names: set[str] = set()
    with tarfile.open(path, "r:") as archive:
        for entry in archive:
            name = entry.name.removeprefix("./").rstrip("/")
            contained_path(path.parent, name)
            if not entry.isfile() or entry.size <= 0:
                raise ValueError("unexpected Valhalla tar entry")
            if name in names or entry.offset_data + entry.size > path.stat().st_size:
                raise ValueError("duplicate/truncated Valhalla tile")
            if entry.uid or entry.gid or entry.mtime or entry.uname or entry.gname:
                raise ValueError("Valhalla tar is not normalized")
            names.add(name)
            if name == "index.bin":
                stream = archive.extractfile(entry)
                assert stream is not None
                index = stream.read()
            elif re.fullmatch(r"[0-3]/(?:[0-9]{3}/)*[0-9]{3}\.gph", name):
                level, tile = name[:-4].split("/", 1)
                tile_id = int(level) | (int(tile.replace("/", "")) << 3)
                tiles.append((entry.offset_data, tile_id, entry.size))
            else:
                raise ValueError("unexpected Valhalla tar entry")
    if (
        not tiles
        or index is None
        or len(index) != 16 * len(tiles)
        or tuple(struct.iter_unpack("<QLL", index)) != tuple(tiles)
    ):
        raise ValueError("missing/incorrect Valhalla tile index")


def validate_components(directory: Path, manifest: RegionalManifest) -> None:
    expected = {"manifest.json"}
    for component in manifest.components.ordered:
        for file in component.files:
            path = contained_path(directory, file.path)
            if not path.is_file() or path.stat().st_size != file.byte_size:
                raise ValueError(f"missing/incorrect size: {file.path}")
            if file_sha256(path) != file.sha256:
                raise ValueError(f"checksum mismatch: {file.path}")
            expected.add(file.path)
    actual: set[str] = set()
    for path in directory.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("non-regular distribution entry")
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
    if actual != expected:
        raise ValueError("distribution has missing or unexpected files")
    map_manifest = read_map(directory / "map/manifest.json")
    if map_manifest.pack_id != manifest.components.map.component_id or (
        map_manifest.bounds != manifest.bounds
    ):
        raise ValueError("map identity/bounds mismatch")
    validate_pmtiles(directory / "map/basemap.pmtiles", map_manifest)
    routing_path = directory / "routing/manifest.json"
    if routing_path.stat().st_size > 16_384:
        raise ValueError("routing manifest exceeds runtime size limit")
    routing = RoutingManifest.model_validate_json(routing_path.read_bytes())
    if (
        routing.pack_id != manifest.components.routing.component_id
        or tuple(routing.bounds.model_dump().values()) != manifest.bounds
    ):
        raise ValueError("routing identity/bounds mismatch")
    validate_tar(directory / "routing/valhalla_tiles.tar")
    pois = PoiIndexDocument.model_validate_json(
        gzip.decompress((directory / "pois/index.json.gz").read_bytes())
    )
    nature = NatureIndexDocument.model_validate_json(
        gzip.decompress((directory / "nature/index.json.gz").read_bytes())
    )
    for metadata in (pois.metadata, nature.metadata):
        if metadata.bounding_box != manifest.bounds or (
            metadata.source_basename != manifest.source.basename
            or metadata.source_size_bytes != manifest.source.byte_size
        ):
            raise ValueError("index bounds/source identity mismatch")


def verify_region(directory: Path) -> RegionalManifest:
    path = contained_path(directory, "manifest.json")
    manifest = RegionalManifest.model_validate_json(path.read_bytes())
    validate_components(directory, manifest)
    return manifest
