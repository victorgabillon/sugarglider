"""Read-only Skadi elevation tile coverage probe for a future offline region format.

This module neither downloads terrain data nor modifies any regional build.
"""

import argparse
import json
from dataclasses import dataclass
from math import ceil, floor
from pathlib import Path

from sugarglider.offline_regions.validation import load_spec
from sugarglider.osm_build_bounds import Bounds, validate_bounds

# Valhalla 3.6.3 Skadi uses a 3601 x 3601 big-endian signed-int16 HGT grid.
# This is a *raw decoded-size estimate*, not a prediction of compressed transfer
# size or runtime peak memory. Availability and source rights are not established.
HGT_SAMPLES_PER_SIDE = 3601
HGT_RAW_BYTES = HGT_SAMPLES_PER_SIDE**2 * 2
SKADI_SOURCE = "https://elevation-tiles-prod.s3.us-east-1.amazonaws.com"


@dataclass(frozen=True, order=True)
class SkadiTile:
    """Southwest integer-degree corner of a one-degree HGT tile."""

    south: int
    west: int

    @property
    def filename(self) -> str:
        latitude = "N" if self.south >= 0 else "S"
        longitude = "E" if self.west >= 0 else "W"
        return f"{latitude}{abs(self.south):02d}{longitude}{abs(self.west):03d}.hgt.gz"

    @property
    def path(self) -> str:
        latitude_dir = self.filename[:3]
        return f"skadi/{latitude_dir}/{self.filename}"

    @property
    def candidate_url(self) -> str:
        return f"{SKADI_SOURCE}/{self.path}"


def skadi_tiles_for_bounds(bounds: Bounds) -> tuple[SkadiTile, ...]:
    """Plan tile coverage for an existing non-dateline regional rectangle.

    Integer upper bounds share their border with the last included tile,
    so they do not require fetching an entire additional one-degree tile.
    This plans nominal spatial coverage, not the availability of valid DEM.
    """
    west, south, east, north = validate_bounds(bounds)
    return tuple(
        SkadiTile(latitude, longitude)
        for latitude in range(floor(south), ceil(north))
        for longitude in range(floor(west), ceil(east))
    )


def elevation_feasibility_plan(region_id: str, bounds: Bounds) -> dict[str, object]:
    """Construct a deterministic, informational estimate; perform no I/O."""
    tiles = skadi_tiles_for_bounds(bounds)
    return {
        "region_id": region_id,
        "source_candidate": "Tilezen/Mapzen Skadi (not selected for publication)",
        "format_candidate": "3601x3601 signed int16 big-endian HGT gzip",
        "tile_count": len(tiles),
        "total_raw_bytes": len(tiles) * HGT_RAW_BYTES,
        "tiles": [
            {"path": tile.path, "candidate_url": tile.candidate_url} for tile in tiles
        ],
        "limits": (
            "Nominal coverage only; downloaded sizes, valid heights, license "
            "clearance and Android memory are not verified."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--region", required=True, help="Existing region specification ID"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    spec = load_spec(root, args.region)
    print(json.dumps(elevation_feasibility_plan(spec.region_id, spec.bounds), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
