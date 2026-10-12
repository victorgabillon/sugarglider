"""Bounded read-only Skadi HGT gzip validation and sampling *prototype*.

Not an Android renderer or a production regional artifact format. The caller
supplies an explicitly checksum-pinned local tile. No network or write paths.
"""

import argparse
import gzip
import hashlib
import json
import math
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from sugarglider.offline_regions.elevation_feasibility import (
    HGT_RAW_BYTES,
    HGT_SAMPLES_PER_SIDE,
    SkadiTile,
)

# Valhalla 3.6.3 Skadi treats data outside this range as unavailable.
HGT_NO_DATA = -32768
HGT_MIN_USABLE = -16384
HGT_MAX_USABLE = 16384
# A gzip file should not exceed its decoded raw file by more than this margin.
# This is a prototype's input guard, not a future distribution size limit.
MAX_COMPRESSED_BYTES = HGT_RAW_BYTES + 1_048_576


def tile_from_filename(filename: str) -> SkadiTile:
    """Reject unsafe/noncanonical names, including unavailable east=180."""
    match = re.fullmatch(r"([NS])(\d{2})([EW])(\d{3})\.hgt\.gz", filename)
    if match is None:
        raise ValueError("expected canonical Skadi .hgt.gz filename")
    north_south, lat, east_west, lon = match.groups()
    south = int(lat) * (1 if north_south == "N" else -1)
    west = int(lon) * (1 if east_west == "E" else -1)
    tile = SkadiTile(south, west)
    if not (-90 <= south < 90 and -180 <= west < 180) or filename != tile.filename:
        raise ValueError("invalid Skadi tile coordinates")
    return tile


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def usable_height(value: int) -> bool:
    return HGT_MIN_USABLE <= value <= HGT_MAX_USABLE


@dataclass(frozen=True)
class HgtProbe:
    """Single validated local HGT tile; ~26 MiB of bounded decoded data."""

    tile: SkadiTile
    source_sha256: str
    compressed_bytes: int
    pixels_valid: int
    pixels_void: int
    pixels_invalid: int
    min_height_m: int | None
    max_height_m: int | None
    data: bytes

    def sample(self, *, latitude: float, longitude: float) -> float | None:
        """Bilinear sampling, renormalizing valid corner weights like Skadi.

        Coordinates belonging to another tile are *unavailable*, never clamped
        or interpolated across a missing tile boundary. No remote fallback.
        """
        if (
            not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or math.floor(latitude) != self.tile.south
            or math.floor(longitude) != self.tile.west
        ):
            return None
        scale = HGT_SAMPLES_PER_SIDE - 1
        u = (longitude - self.tile.west) * scale
        v = (1.0 - (latitude - self.tile.south)) * scale
        column, row = math.floor(u), math.floor(v)
        if not (0 <= column < HGT_SAMPLES_PER_SIDE and 0 <= row < HGT_SAMPLES_PER_SIDE):
            return None
        dx, dy = u - column, v - row
        next_column = min(column + 1, scale)
        next_row = min(row + 1, scale)
        corners = (
            (row, column, (1.0 - dx) * (1.0 - dy)),
            (row, next_column, dx * (1.0 - dy)),
            (next_row, column, (1.0 - dx) * dy),
            (next_row, next_column, dx * dy),
        )
        total_weight = 0.0
        weighted_height = 0.0
        for y, x, weight in corners:
            if weight == 0.0:
                continue
            value = struct.unpack_from(
                ">h", self.data, (y * HGT_SAMPLES_PER_SIDE + x) * 2
            )[0]
            if not usable_height(value):
                continue
            total_weight += weight
            weighted_height += value * weight
        return weighted_height / total_weight if total_weight > 0 else None

    def report(self) -> dict[str, str | int | None]:
        return {
            "tile": self.tile.filename,
            "sha256": self.source_sha256,
            "compressed_bytes": self.compressed_bytes,
            "decoded_bytes": len(self.data),
            "pixels_valid": self.pixels_valid,
            "pixels_void": self.pixels_void,
            "pixels_invalid": self.pixels_invalid,
            "min_height_m": self.min_height_m,
            "max_height_m": self.max_height_m,
        }


def probe_hgt_file(path: Path, expected_sha256: str) -> HgtProbe:
    """Verify explicit source pin, gzip integrity, decoded shape and coverage.

    Gzip reads are capped at exactly one tile plus a single extra byte, so
    corrupt/oversized compressed inputs cannot be decompressed without bound.
    """
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise ValueError("expected SHA-256 must be 64 lowercase hex characters")
    tile = tile_from_filename(path.name)
    size = path.stat().st_size
    if not (0 < size <= MAX_COMPRESSED_BYTES):
        raise ValueError("compressed HGT size outside allowed probe range")
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise ValueError("HGT SHA-256 mismatch")
    with gzip.open(path, "rb") as stream:
        raw = stream.read(HGT_RAW_BYTES + 1)
    if len(raw) != HGT_RAW_BYTES:
        raise ValueError("HGT decoded grid is not 3601x3601 signed int16")

    valid, void, invalid = 0, 0, 0
    lowest: int | None = None
    highest: int | None = None
    for (height,) in struct.iter_unpack(">h", raw):
        if height == HGT_NO_DATA:
            void += 1
        elif not usable_height(height):
            invalid += 1
        else:
            valid += 1
            if lowest is None or height < lowest:
                lowest = height
            if highest is None or height > highest:
                highest = height

    return HgtProbe(
        tile=tile,
        source_sha256=actual_sha256,
        compressed_bytes=size,
        pixels_valid=valid,
        pixels_void=void,
        pixels_invalid=invalid,
        min_height_m=lowest,
        max_height_m=highest,
        data=raw,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tile", type=Path, required=True)
    parser.add_argument("--sha256", required=True, help="Expected compressed file SHA-256")
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    args = parser.parse_args()
    if (args.latitude is None) != (args.longitude is None):
        parser.error("--latitude and --longitude must be supplied together")
    try:
        probe = probe_hgt_file(args.tile, args.sha256)
    except (OSError, ValueError, EOFError) as error:
        print(f"elevation-hgt-probe: {error}", file=sys.stderr)
        return 1
    report: dict[str, object] = probe.report()
    if args.latitude is not None and args.longitude is not None:
        report["sample"] = {
            "latitude": args.latitude,
            "longitude": args.longitude,
            "height_m": probe.sample(latitude=args.latitude, longitude=args.longitude),
        }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
