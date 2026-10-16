"""Synthetic zero-height HGT fixtures; no downloaded map or terrain data."""

import gzip
import hashlib
from functools import lru_cache
from pathlib import Path

from sugarglider.offline_regions.elevation_component import (
    ElevationManifest,
    ElevationTile,
)
from sugarglider.offline_regions.elevation_feasibility import (
    HGT_RAW_BYTES,
    HGT_SAMPLES_PER_SIDE,
)
from sugarglider.offline_regions.elevation_layout import elevation_paths
from sugarglider.offline_regions.models import canonical_json


@lru_cache(maxsize=1)
def synthetic_hgt() -> bytes:
    return gzip.compress(bytes(HGT_RAW_BYTES), mtime=0)


def synthetic_sources(root: Path, bounds: tuple[float, float, float, float]) -> Path:
    raw = synthetic_hgt()
    digest = hashlib.sha256(raw).hexdigest()
    rows = []
    for relative in elevation_paths(bounds):
        path = root / "synthetic-dem" / relative.removeprefix("elevation/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        rows.append(
            {
                "tile": path.name.removesuffix(".hgt.gz"),
                "path": str(path),
                "source_url": "https://example.test/synthetic/" + path.name,
                "acquired_at": "2026-10-15T00:00:00Z",
                "byte_size": len(raw),
                "sha256": digest,
                "last_modified": None,
                "origin": "synthetic unit fixture",
            }
        )
    source = root / "synthetic-dem-pins.json"
    source.write_bytes(canonical_json({"publication_allowed": False, "tiles": rows}))
    return source


def write_synthetic_elevation(
    directory: Path, component_id: str, bounds: tuple[float, float, float, float]
) -> None:
    directory.mkdir()
    data = synthetic_hgt()
    tiles = []
    for relative in elevation_paths(bounds):
        path = relative.removeprefix("elevation/")
        output = directory / path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        tiles.append(
            ElevationTile(
                path=path,
                byte_size=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                source_url="https://example.test/synthetic/" + output.name,
                acquired_at="2026-10-15T00:00:00Z",
                pixels_valid=HGT_SAMPLES_PER_SIDE**2,
                pixels_void=0,
                minimum_height_m=0,
                maximum_height_m=0,
            )
        )
    manifest = ElevationManifest(
        component_id=component_id, bounds=bounds, tiles=tuple(tiles)
    )
    (directory / "manifest.json").write_bytes(
        canonical_json(manifest.model_dump(mode="json"))
    )
