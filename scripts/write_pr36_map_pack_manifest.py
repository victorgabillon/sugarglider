#!/usr/bin/env python3
"""Validate a built PMTiles archive and write its strict PR36 manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Final

MANIFEST_FIELDS: Final = frozenset(
    {
        "archive_filename",
        "attribution",
        "bounds",
        "build_id",
        "byte_size",
        "data_source",
        "display_name",
        "format",
        "max_zoom",
        "min_zoom",
        "pack_id",
        "schema_version",
        "tile_type",
    }
)
PMTILES_HEADER_BYTES: Final = 127
PMTILES_MAGIC: Final = b"PMTiles"
PMTILES_SPEC_VERSION: Final = 3
MVT_TILE_TYPE: Final = 1
MAXIMUM_MAP_PACK_BYTES: Final = 2_147_483_648
PROTOMAPS_SOURCE_REVISION: Final = "3ea8293a28131c3dc63f1bb20827bdb8a76df06f"


@dataclass(frozen=True)
class CliArguments:
    template: Path
    archive: Path
    source_pbf: Path
    output: Path


def parse_args() -> CliArguments:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--source-pbf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    values = parser.parse_args()
    return CliArguments(
        template=values.template,
        archive=values.archive,
        source_pbf=values.source_pbf,
        output=values.output,
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_template(path: Path) -> dict[str, object]:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        raise SystemExit("Map-pack template must be a JSON object")
    template = {str(key): value for key, value in raw.items()}
    if set(template) != MANIFEST_FIELDS:
        raise SystemExit("Map-pack template fields do not match schema v1")
    if (
        template["schema_version"] != 1
        or template["format"] != "pmtiles-v3"
        or template["tile_type"] != "mvt"
        or template["archive_filename"] != "basemap.pmtiles"
    ):
        raise SystemExit("Map-pack template format is not PR36 PMTiles v3 MVT")
    validate_bounds(template["bounds"])
    validate_zoom(template["min_zoom"], template["max_zoom"])
    return template


def validate_archive(path: Path, template: dict[str, object]) -> int:
    byte_size = path.stat().st_size
    if byte_size < PMTILES_HEADER_BYTES or byte_size > MAXIMUM_MAP_PACK_BYTES:
        raise SystemExit("PMTiles archive size is outside the PR36 limit")
    with path.open("rb") as stream:
        header = stream.read(PMTILES_HEADER_BYTES)
    if header[:7] != PMTILES_MAGIC or header[7] != PMTILES_SPEC_VERSION:
        raise SystemExit("Archive is not PMTiles v3")
    if header[99] != MVT_TILE_TYPE:
        raise SystemExit("Archive does not contain MVT vector tiles")
    min_zoom = header[100]
    max_zoom = header[101]
    if min_zoom != template["min_zoom"] or max_zoom != template["max_zoom"]:
        raise SystemExit("Archive zoom range differs from its template")
    raw_bounds = struct.unpack_from("<iiii", header, 102)
    archive_bounds = tuple(value / 10_000_000 for value in raw_bounds)
    template_bounds = validated_bounds(template["bounds"])
    if any(
        not math.isclose(actual, expected, abs_tol=0.0000001)
        for actual, expected in zip(archive_bounds, template_bounds, strict=True)
    ):
        raise SystemExit("Archive bounds differ from its template")
    return byte_size


def validated_bounds(value: object) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise SystemExit("Map-pack bounds must contain four numbers")
    if any(
        isinstance(item, bool) or not isinstance(item, (int, float)) for item in value
    ):
        raise SystemExit("Map-pack bounds must contain four numbers")
    west, south, east, north = (float(item) for item in value)
    if not (
        all(math.isfinite(item) for item in (west, south, east, north))
        and -180 <= west < east <= 180
        and -85.051129 <= south < north <= 85.051129
    ):
        raise SystemExit("Map-pack bounds are invalid")
    return west, south, east, north


def validate_bounds(value: object) -> None:
    validated_bounds(value)


def validate_zoom(minimum: object, maximum: object) -> None:
    if (
        isinstance(minimum, bool)
        or not isinstance(minimum, int)
        or isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or not 0 <= minimum <= maximum <= 22
    ):
        raise SystemExit("Map-pack zoom range is invalid")


def write_manifest(args: CliArguments) -> None:
    template = load_template(args.template)
    byte_size = validate_archive(args.archive, template)
    pbf_digest = file_sha256(args.source_pbf)
    archive_digest = file_sha256(args.archive)
    template["byte_size"] = byte_size
    template["build_id"] = (
        f"protomaps-{PROTOMAPS_SOURCE_REVISION[:12]}-pbf-{pbf_digest[:16]}"
        f"-pmtiles-{archive_digest[:16]}"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    temporary.write_text(
        json.dumps(template, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)


def main() -> None:
    args = parse_args()
    for path in (args.template, args.archive, args.source_pbf):
        if not path.is_file():
            raise SystemExit(f"Required input does not exist: {path}")
    write_manifest(args)


if __name__ == "__main__":
    main()
