"""Canonical, bounded Skadi layout shared by build-time regional validation."""

import math

from sugarglider.offline_regions.elevation_feasibility import SkadiTile

MAX_REGIONAL_DEM_TILES = 16


def elevation_paths(bounds: tuple[float, float, float, float]) -> tuple[str, ...]:
    west, south, east, north = bounds
    if east >= 180:
        raise ValueError("Skadi cannot cover the inclusive 180 degree boundary")
    # Bounds are inclusive in regional planning. An integer north/east edge
    # belongs to the next tile in Valhalla's floor-based Skadi lookup.
    count = (math.floor(east) - math.floor(west) + 1) * (
        math.floor(north) - math.floor(south) + 1
    )
    if not 1 <= count <= MAX_REGIONAL_DEM_TILES:
        raise ValueError("regional elevation exceeds 16-tile budget")
    tiles = (
        SkadiTile(lat, lon)
        for lat in range(math.floor(south), math.floor(north) + 1)
        for lon in range(math.floor(west), math.floor(east) + 1)
    )
    return tuple(
        sorted(f"elevation/skadi/{tile.filename[:3]}/{tile.filename}" for tile in tiles)
    )
