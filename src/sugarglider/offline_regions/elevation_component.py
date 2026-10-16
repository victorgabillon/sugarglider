"""Private, deterministic V2 Skadi component; reuse PR84's bounded HGT probe."""

from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from sugarglider.offline_regions.elevation_feasibility import (
    HGT_RAW_BYTES,
    HGT_SAMPLES_PER_SIDE,
)
from sugarglider.offline_regions.elevation_hgt_probe import (
    probe_hgt_file,
    sha256_file,
    tile_from_filename,
)
from sugarglider.offline_regions.elevation_layout import elevation_paths
from sugarglider.offline_regions.models import (
    Identifier,
    RegionBounds,
    RelativePath,
    Sha256,
    StrictModel,
    canonical_json,
    contained_path,
)


class AcquiredTile(StrictModel):
    tile: Annotated[str, Field(pattern=r"^[NS][0-9]{2}[EW][0-9]{3}$")]
    path: str
    source_url: Annotated[str, Field(pattern=r"^https://[^\s?#]+$", max_length=2048)]
    acquired_at: Annotated[str, Field(min_length=10, max_length=80)]
    byte_size: Annotated[int, Field(gt=0, le=HGT_RAW_BYTES + 1_048_576)]
    sha256: Sha256
    last_modified: str | None
    origin: str


class ElevationInputs(StrictModel):
    publication_allowed: Literal[False]
    tiles: Annotated[tuple[AcquiredTile, ...], Field(min_length=1, max_length=16)]


class ElevationTile(StrictModel):
    path: RelativePath  # relative to elevation/, e.g. skadi/N48/N48E002.hgt.gz
    byte_size: Annotated[int, Field(gt=0, le=HGT_RAW_BYTES + 1_048_576)]
    sha256: Sha256
    source_url: str
    acquired_at: str
    decoded_bytes: Literal[25_934_402] = 25_934_402
    pixels_valid: Annotated[int, Field(gt=0)]
    pixels_void: Annotated[int, Field(ge=0)]
    pixels_invalid: Literal[0] = 0
    minimum_height_m: int
    maximum_height_m: int

    @model_validator(mode="after")
    def valid_tile(self) -> Self:
        tile = tile_from_filename(Path(self.path).name)
        if self.path != f"skadi/{tile.filename[:3]}/{tile.filename}":
            raise ValueError("incorrect Skadi path/tile identity")
        if self.pixels_valid + self.pixels_void != HGT_SAMPLES_PER_SIDE**2:
            raise ValueError("invalid elevation coverage counters")
        if not -16_384 <= self.minimum_height_m <= self.maximum_height_m <= 16_384:
            raise ValueError("invalid available elevation range")
        return self


class ElevationManifest(StrictModel):
    schema_version: Literal[1] = 1
    component_id: Identifier
    bounds: RegionBounds
    format: Literal["skadi-hgt-gzip-v1"] = "skadi-hgt-gzip-v1"
    publication_allowed: bool = False
    provenance_status: Literal["unresolved", "documented"] = "unresolved"
    vertical_datum: Literal["unresolved", "EGM96"] = "unresolved"
    tiles: Annotated[tuple[ElevationTile, ...], Field(min_length=1, max_length=16)]

    @model_validator(mode="after")
    def exact_coverage(self) -> Self:
        if (self.provenance_status, self.vertical_datum) not in (
            ("unresolved", "unresolved"),
            ("documented", "EGM96"),
        ) or (self.publication_allowed and self.provenance_status != "documented"):
            raise ValueError("publication requires documented EGM96 provenance")
        if tuple(f"elevation/{tile.path}" for tile in self.tiles) != elevation_paths(
            self.bounds
        ):
            raise ValueError("missing, duplicate, unordered or excess elevation tiles")
        return self


# Retained regional versions commonly reuse identical compressed terrain. Cache
# only proven coverage metadata, never rasters; every reuse still hashes the file.
# A separate verifier process necessarily starts with an empty cache.
_COVERAGE: OrderedDict[tuple[str, int, str], ElevationTile] = OrderedDict()
_COVERAGE_LOCK = Lock()


def _verified_tile(path: Path, source: ElevationTile | AcquiredTile) -> ElevationTile:
    if path.is_symlink() or path.resolve() != path.absolute():
        raise ValueError("symlink elevation source is forbidden")
    if path.stat().st_size != source.byte_size:
        raise ValueError("invalid elevation source size")
    key = (source.sha256, source.byte_size, path.name)
    with _COVERAGE_LOCK:
        cached = _COVERAGE.get(key)
        if cached is not None:
            _COVERAGE.move_to_end(key)
    if cached is not None:
        if sha256_file(path) != source.sha256:
            raise ValueError("HGT SHA-256 mismatch")
        return cached.model_copy(
            update={"source_url": source.source_url, "acquired_at": source.acquired_at}
        )
    probe = probe_hgt_file(path, source.sha256)
    if (
        probe.compressed_bytes != source.byte_size
        or probe.pixels_invalid
        or not probe.pixels_valid
    ):
        raise ValueError("invalid elevation source size/coverage")
    assert probe.min_height_m is not None and probe.max_height_m is not None
    verified = ElevationTile(
        path=f"skadi/{probe.tile.filename[:3]}/{probe.tile.filename}",
        byte_size=probe.compressed_bytes,
        sha256=probe.source_sha256,
        source_url=source.source_url,
        acquired_at=source.acquired_at,
        pixels_valid=probe.pixels_valid,
        pixels_void=probe.pixels_void,
        minimum_height_m=probe.min_height_m,
        maximum_height_m=probe.max_height_m,
    )
    with _COVERAGE_LOCK:
        _COVERAGE[key] = verified
        _COVERAGE.move_to_end(key)
        while len(_COVERAGE) > 16:
            _COVERAGE.popitem(last=False)
    return verified


def build_elevation(
    directory: Path,
    component_id: str,
    bounds: tuple[float, float, float, float],
    sources: Path,
) -> ElevationManifest:
    if sources.stat().st_size > 64 * 1024:
        raise ValueError("elevation source pins exceed limit")
    pins = ElevationInputs.model_validate_json(sources.read_bytes())
    inputs = {
        f"elevation/skadi/{tile.tile[:3]}/{tile.tile}.hgt.gz": tile
        for tile in pins.tiles
    }
    if len(inputs) != len(pins.tiles):
        raise ValueError("duplicate elevation source pins")
    directory.mkdir()  # Fresh staging only, never replace an immutable component.
    tiles = []
    for relative in elevation_paths(bounds):
        source = inputs.get(relative)
        if source is None:
            raise ValueError("required elevation source pin missing")
        path = Path(source.path)
        if (
            path.name != f"{source.tile}.hgt.gz"
            or path.is_symlink()
            or path.resolve() != path.absolute()
            or path.stat().st_size != source.byte_size
        ):
            raise ValueError("unsafe/mismatched elevation source")
        target = contained_path(directory, relative.removeprefix("elevation/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        with path.open("rb") as original, target.open("xb") as output:
            copied = 0
            while chunk := original.read(min(64 * 1024, source.byte_size - copied + 1)):
                copied += len(chunk)
                if copied > source.byte_size:
                    raise ValueError("elevation source grew during copy")
                output.write(chunk)
            if copied != source.byte_size:
                raise ValueError("elevation source changed during copy")
        tiles.append(_verified_tile(target, source))
    manifest = ElevationManifest(
        component_id=component_id, bounds=bounds, tiles=tuple(tiles)
    )
    (directory / "manifest.json").write_bytes(
        canonical_json(manifest.model_dump(mode="json"))
    )
    return manifest


def verify_elevation(directory: Path) -> ElevationManifest:
    path = contained_path(directory, "manifest.json")
    if path.stat().st_size > 64 * 1024:
        raise ValueError("elevation manifest exceeds limit")
    manifest = ElevationManifest.model_validate_json(path.read_bytes())
    for tile in manifest.tiles:
        if _verified_tile(contained_path(directory, tile.path), tile) != tile:
            raise ValueError("elevation coverage metadata mismatch")
    return manifest
