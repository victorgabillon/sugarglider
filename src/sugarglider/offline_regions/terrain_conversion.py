"""Copernicus 2021 COG point grids to EGM96 Skadi; optional offline build tools."""

import gzip
import math
import platform
import shutil
import zlib
from contextlib import ExitStack
from pathlib import Path
from typing import Protocol

from sugarglider.offline_regions.elevation_hgt_probe import probe_hgt_file, sha256_file
from sugarglider.offline_regions.models import canonical_json
from sugarglider.offline_regions.terrain_source import TerrainSources, verify_source

TRANSFORMATION = "cop-dem-cog-egm96-v1"


def geoid_pipeline(source: Path) -> str:
    geoid08 = source / "us_nga_egm08_25.tif"
    geoid96 = source / "us_nga_egm96_15.tif"
    return (
        "+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad "
        f"+step +inv +proj=vgridshift +grids={geoid08} "
        f"+step +proj=vgridshift +grids={geoid96} "
        "+step +proj=unitconvert +xy_in=rad +xy_out=deg"
    )


class TerrainRow(Protocol):
    def __call__(
        self, latitude: float, west: int, count: int
    ) -> list[float | None]: ...


class DatumShift(Protocol):
    def __call__(self, lon: float, lat: float, height: float) -> float: ...


def quantize_height(value: float | None) -> int:
    if value is None:
        return -32768
    if not math.isfinite(value) or not -16384 <= value <= 16384:
        raise ValueError("invalid transformed terrain height")
    return round(value)  # nearest integer, ties to even, max error 0.5 m


def convert_tile(
    path: Path, south: int, west: int, row: TerrainRow, shift: DatumShift
) -> None:
    """One row at a time; no extrapolation, terrain synthesis or zero filling."""
    import array

    path.parent.mkdir(parents=True, exist_ok=True)
    with (
        path.open("xb") as output,
        gzip.GzipFile(
            filename="", mode="wb", fileobj=output, compresslevel=9, mtime=0
        ) as compressed,
    ):
        for index in range(3601):
            latitude = south + (3600 - index) / 3600
            source = row(latitude, west, 3601)
            if len(source) != 3601:
                raise ValueError("incomplete source row")
            values = array.array(
                "h",
                (
                    quantize_height(
                        None if h is None else shift(west + j / 3600, latitude, h)
                    )
                    for j, h in enumerate(source)
                ),
            )
            if __import__("sys").byteorder == "little":
                values.byteswap()
            compressed.write(values.tobytes())


def convert_sources(pins: TerrainSources, source: Path, output: Path) -> None:
    """Full nine-tile halo is mandatory: COGs removed east/south shared samples."""
    import numpy as np
    import pyproj
    import rasterio  # type: ignore[import-untyped]
    from rasterio.windows import Window  # type: ignore[import-untyped]

    names = {
        f"Copernicus_DSM_COG_10_N{lat}_00_E{lon:03}_00_DEM.tif": (lat, lon)
        for lat in (47, 48, 49)
        for lon in (1, 2, 3)
    }
    required = {*names, "us_nga_egm08_25.tif", "us_nga_egm96_15.tif"}
    if {p.filename for p in pins.files} != required or len(pins.files) != 11:
        raise ValueError("incomplete or duplicate source/vertical-grid set")
    for pin in pins.files:
        verify_source(source, pin)
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    if shutil.disk_usage(output.parent).free < 4 * 26_982_978 + 65_536:
        raise ValueError("insufficient disk for bounded terrain conversion")
    output.mkdir()
    # H96 = H08 + N08 - N96. No optional grids, network or ballpark operation.
    pyproj.network.set_network_enabled(False)  # type: ignore[attr-defined]
    pipeline = geoid_pipeline(source)
    transformer = pyproj.Transformer.from_pipeline(pipeline)
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(GDAL_CACHEMAX=32 * 1024 * 1024))
        rasters = {}
        for name, (lat, lon) in names.items():
            dataset = stack.enter_context(rasterio.open(source / name))
            transform = dataset.transform
            expected = (
                1 / 3600,
                0,
                lon - 0.5 / 3600,
                0,
                -1 / 3600,
                lat + 1 + 0.5 / 3600,
            )
            if (
                dataset.width != 3600
                or dataset.height != 3600
                or dataset.count != 1
                or dataset.crs.to_epsg() != 4326
                or dataset.dtypes != ("float32",)
                or dataset.tags().get("AREA_OR_POINT") != "Point"
                or any(
                    abs(a - b) > 1e-11
                    for a, b in zip(tuple(transform)[:6], expected, strict=True)
                )
            ):
                raise ValueError("unexpected Copernicus point-grid metadata")
            rasters[lat, lon] = dataset

        def read_row(latitude: float, west: int, count: int) -> list[float | None]:
            lat = math.ceil(latitude) - 1  # integer latitude belongs to its south tile
            index = round((lat + 1 - latitude) * 3600)
            base = rasters[lat, west].read(
                1, window=Window(0, index, 3600, 1), masked=True
            )
            edge = rasters[lat, west + 1].read(
                1, window=Window(0, index, 1, 1), masked=True
            )
            values = [*base[0], *edge[0]]
            if len(values) != count:
                raise ValueError("incomplete source raster coverage")
            return [None if np.ma.is_masked(v) else float(v) for v in values]

        def shift(lon: float, lat: float, height: float) -> float:
            _, _, result = transformer.transform(lon, lat, height, errcheck=True)
            return float(result)

        results = []
        for lat in (48, 49):
            for lon in (1, 2):
                name = f"N{lat}E{lon:03}.hgt.gz"
                target = output / f"N{lat}" / name
                convert_tile(target, lat, lon, read_row, shift)
                probe = probe_hgt_file(target, sha256_file(target))
                results.append(
                    {
                        "path": f"N{lat}/{name}",
                        "sha256": probe.source_sha256,
                        "byte_size": target.stat().st_size,
                        "probe": probe.report(),
                    }
                )
    (output / "transformation.json").write_bytes(
        canonical_json(
            {
                "algorithm": TRANSFORMATION,
                "product": pins.product,
                "release": pins.release,
                "input_vertical_crs": pins.vertical_crs,
                "output_vertical_crs": "EPSG:5773",
                "sources": pins.model_dump(mode="json"),
                "pipeline": pipeline,
                "rounding": "nearest integer ties to even; <=0.5 m",
                "nodata": -32768,
                "python": platform.python_version(),
                "numpy": np.__version__,
                "rasterio": rasterio.__version__,
                "gdal": rasterio.__gdal_version__,
                "pyproj": pyproj.__version__,
                "proj": pyproj.proj_version_str,
                "zlib": zlib.ZLIB_VERSION,
                "tiles": results,
            }
        )
    )

    from sugarglider.offline_regions.elevation_component import (
        AcquiredTile,
        ElevationInputs,
    )

    originals = {pin.filename: pin for pin in pins.files}
    acquired = []
    for lat in (48, 49):
        for lon in (1, 2):
            name = f"N{lat}E{lon:03}"
            path = output.absolute() / f"N{lat}/{name}.hgt.gz"
            original = originals[
                f"Copernicus_DSM_COG_10_N{lat}_00_E{lon:03}_00_DEM.tif"
            ]
            acquired.append(
                AcquiredTile(
                    tile=name,
                    path=str(path),
                    source_url=original.url,
                    acquired_at=original.acquired_at,
                    byte_size=path.stat().st_size,
                    sha256=sha256_file(path),
                    last_modified=None,
                    origin=TRANSFORMATION
                    + "; acquisition time refers to pinned source",
                )
            )
    (output / "elevation-inputs.json").write_bytes(
        canonical_json(
            ElevationInputs(
                publication_allowed=False, tiles=tuple(acquired)
            ).model_dump(mode="json")
        )
    )
