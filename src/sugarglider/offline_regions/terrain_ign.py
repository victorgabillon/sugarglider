"""Offline IGN point-grid preparation and bounded sampling; no vertical shift.

RGE ALTI nodes are at integer multiples of 5 m, not at ASC pixel corners.
Department deliveries may duplicate a 5 km granule. Conflicting available
nodes are rejected; a void is never replaced by another elevation product.
"""

import math
import shutil
import subprocess
import tarfile
from collections import OrderedDict
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Annotated, Any

from pydantic import Field

from sugarglider.offline_regions.elevation_hgt_probe import sha256_file
from sugarglider.offline_regions.models import (
    RelativePath,
    Sha256,
    StrictModel,
    canonical_json,
    contained_path,
)
from sugarglider.offline_regions.terrain_source import IGNSources, verify_source

MAX_OPEN_DATASETS = 32


class PreparedGrid(StrictModel):
    path: RelativePath
    source_archive_sha256: Sha256
    original_ascii_sha256: Sha256
    sha256: Sha256


class PreparedIGN(StrictModel):
    sources: IGNSources
    grids: Annotated[tuple[PreparedGrid, ...], Field(min_length=1, max_length=40_000)]


def extract_delivery(stream: IO[bytes], output: Path) -> None:
    """Consume a TAR stream, never its links, devices or extraction methods."""
    total = 0
    with tarfile.open(fileobj=stream, mode="r|") as archive:
        for index, entry in enumerate(archive):
            if index >= 10_000 or len(entry.name) > 1024:
                raise ValueError("oversized IGN archive index")
            target = contained_path(output, entry.name.rstrip("/"))
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not entry.isfile() or not 0 < entry.size <= 100_000_000:
                raise ValueError("invalid IGN archive entry")
            total += entry.size
            if total > 8_000_000_000:
                raise ValueError("expanded IGN archive exceeds budget")
            if shutil.disk_usage(output).free < entry.size + 128 * 1024**2:
                raise ValueError("insufficient disk for IGN extraction")
            target.parent.mkdir(parents=True, exist_ok=True)
            original = archive.extractfile(entry)
            if original is None:
                raise ValueError("missing IGN archive payload")
            with original, target.open("xb") as destination:
                shutil.copyfileobj(original, destination, length=65_536)


def prepare_ign(pins: IGNSources, originals: Path, output: Path) -> None:
    """Verify original archives, decode once, prepare lossless random-read grids.

    Requires libarchive's bsdtar only on the offline build host. Data is streamed
    through our bounded TAR reader; bsdtar never writes to the filesystem.
    """
    import rasterio  # type: ignore[import-untyped]

    for pin in pins.files:
        verify_source(originals, pin)
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    if (
        shutil.disk_usage(output.parent).free
        < sum(pin.byte_size * 15 for pin in pins.files) + 256 * 1024**2
    ):
        raise ValueError("insufficient disk for IGN preparation")
    output.mkdir()
    records = []
    with rasterio.Env(GDAL_CACHEMAX=32 * 1024**2):
        for pin in pins.files:
            delivery = output / pin.filename.removesuffix(".7z")
            delivery.mkdir()
            with subprocess.Popen(
                [
                    "bsdtar",
                    "-cf",
                    "-",
                    "--format=ustar",
                    "@" + str(verify_source(originals, pin).absolute()),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            ) as process:
                assert process.stdout is not None
                try:
                    extract_delivery(process.stdout, delivery)
                except BaseException:
                    process.terminate()
                    raise
                if process.wait() != 0:
                    raise ValueError("libarchive could not decode IGN delivery")
            for path in sorted(delivery.rglob("*.asc")):
                # One 1000 x 1000 float32 granule (4 MB) at a time.
                target = path.with_suffix(".tif")
                with rasterio.open(path) as dataset:
                    validate_grid(dataset)
                    with rasterio.open(
                        target,
                        "w",
                        driver="GTiff",
                        width=1000,
                        height=1000,
                        count=1,
                        dtype="float32",
                        crs="EPSG:2154",
                        transform=dataset.transform,
                        nodata=dataset.nodata,
                        tiled=True,
                        blockxsize=256,
                        blockysize=256,
                        compress="DEFLATE",
                        predictor=3,
                    ) as converted:
                        converted.write(dataset.read(1), 1)
                records.append(
                    {
                        "path": target.relative_to(output).as_posix(),
                        "source_archive_sha256": pin.sha256,
                        "original_ascii_sha256": sha256_file(path),
                        "sha256": sha256_file(target),
                    }
                )
    if not records:
        raise ValueError("IGN delivery has no terrain granules")
    (output / "prepared.json").write_bytes(
        canonical_json(
            {
                "sources": pins.model_dump(mode="json"),
                "grids": records,
            }
        )
    )


def validate_grid(dataset: Any) -> tuple[int, int]:
    """Validate the actual node lattice, including IGN's half-pixel header."""
    transform = dataset.transform
    x, y = transform @ (0.5, 0.5)
    if (
        (dataset.width, dataset.height, dataset.count) != (1000, 1000, 1)
        or tuple(transform)[:2] != (5.0, 0.0)
        or transform.d != 0
        or transform.e != -5.0
        or dataset.nodata != -99999.0
        or abs(x / 5000 - round(x / 5000)) > 1e-9
        or abs(y / 5000 - round(y / 5000)) > 1e-9
        or dataset.crs is not None
        and dataset.crs.to_epsg() != 2154
    ):
        raise ValueError("unexpected RGE ALTI 5 m node grid")
    return round(x / 5000), round(y / 5000) - 1


def bilinear_weights(x: float, y: float) -> tuple[tuple[int, int, float], ...]:
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("non-finite projected coordinate")
    a, b = x / 5, y / 5
    # Stabilize exact nodes against inverse-projection floating-point error.
    if abs(a - round(a)) < 1e-9:
        a = float(round(a))
    if abs(b - round(b)) < 1e-9:
        b = float(round(b))
    ix, iy = math.floor(a), math.floor(b)
    dx, dy = a - ix, b - iy
    return tuple(
        (ix + i, iy + j, wx * wy)
        for i, wx in ((0, 1 - dx), (1, dx))
        for j, wy in ((0, 1 - dy), (1, dy))
        if wx * wy > 0
    )


class IGNSampler:
    """A verified mosaic, 32 MB GDAL cache and at most 32 open datasets.

    Uses vectorized point-grid interpolation, not GDAL's nodata-renormalizing
    resampler. Every positive-weight node must be available.
    """

    def __init__(self, pins: IGNSources, prepared: Path) -> None:
        import rasterio

        record_path = contained_path(prepared, "prepared.json")
        if record_path.stat().st_size > 16 * 1024**2:
            raise ValueError("oversized IGN preparation index")
        record = PreparedIGN.model_validate_json(record_path.read_bytes())
        if record.sources != pins:
            raise ValueError("prepared IGN source identity mismatch")
        self.grids: dict[tuple[int, int], list[Path]] = {}
        self.cache: OrderedDict[Path, Any] = OrderedDict()
        source_hashes = {pin.sha256 for pin in pins.files}
        paths: set[str] = set()
        identical: set[tuple[tuple[int, int], str]] = set()
        for grid in record.grids:
            if grid.path in paths or grid.source_archive_sha256 not in source_hashes:
                raise ValueError("invalid prepared IGN source association")
            paths.add(grid.path)
            path = contained_path(prepared, grid.path)
            if sha256_file(path) != grid.sha256:
                raise ValueError("prepared IGN grid hash mismatch")
            with rasterio.open(path) as dataset:
                key = validate_grid(dataset)
            # Verify every input, then avoid reopening byte-identical duplicates.
            # Different deliveries at the same location still require agreement.
            identity = (key, grid.sha256)
            if identity in identical:
                continue
            identical.add(identity)
            self.grids.setdefault(key, []).append(path)

    def close(self) -> None:
        for dataset in self.cache.values():
            dataset.close()
        self.cache.clear()

    def _dataset(self, path: Path) -> Any:
        import rasterio

        dataset = self.cache.pop(path, None)
        if dataset is None:
            dataset = rasterio.open(path)
        self.cache[path] = dataset
        while len(self.cache) > MAX_OPEN_DATASETS:
            self.cache.popitem(last=False)[1].close()
        return dataset

    def sample(self, xs: Sequence[float], ys: Sequence[float]) -> list[float | None]:
        import numpy as np
        from rasterio.windows import Window  # type: ignore[import-untyped]

        if len(xs) != len(ys) or len(xs) > 100_000:
            raise ValueError("invalid IGN sampling batch")
        x, y = (
            np.asarray(xs, dtype=np.float64) / 5,
            np.asarray(ys, dtype=np.float64) / 5,
        )
        if (
            not np.isfinite(x).all()
            or not np.isfinite(y).all()
            or (np.abs(x) > 2e8).any()
            or (np.abs(y) > 2e8).any()
        ):
            raise ValueError("invalid projected IGN coordinates")
        x = np.where(np.abs(x - np.rint(x)) < 1e-9, np.rint(x), x)
        y = np.where(np.abs(y - np.rint(y)) < 1e-9, np.rint(y), y)
        ix, iy = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
        dx, dy = x - ix, y - iy
        result = np.zeros(len(xs), dtype=np.float64)
        valid = np.ones(len(xs), dtype=bool)
        for i, wx in ((0, 1 - dx), (1, dx)):
            for j, wy in ((0, 1 - dy), (1, dy)):
                weight = wx * wy
                nx, ny = ix + i, iy + j
                gx, gy = nx // 1000, (ny - 1) // 1000
                # Lossless pair encoding; bounded coordinates fit signed 32 bits.
                keys = (gx << 32) | (gy & 0xFFFFFFFF)
                for key in np.unique(keys[weight > 0]):
                    indices = np.flatnonzero((keys == key) & (weight > 0))
                    xx, yy = int(gx[indices[0]]), int(gy[indices[0]])
                    paths = self.grids.get((xx, yy), [])
                    if not paths:
                        valid[indices] = False
                        continue
                    cols, rows = nx[indices] % 1000, 999 - ((ny[indices] - 1) % 1000)
                    left, top = int(cols.min()), int(rows.min())
                    width, height = (
                        int(cols.max()) - left + 1,
                        int(rows.max()) - top + 1,
                    )
                    values = np.full(len(indices), np.nan)
                    for path in paths:
                        data = self._dataset(path).read(
                            1, window=Window(left, top, width, height)
                        )
                        nodes = data[rows - top, cols - left].astype(np.float64)
                        present = nodes != -99999.0
                        if (
                            (~np.isfinite(nodes) | (np.abs(nodes) > 16384)) & present
                        ).any():
                            raise ValueError("invalid IGN terrain node")
                        overlap = present & np.isfinite(values)
                        if (np.abs(values[overlap] - nodes[overlap]) > 1e-5).any():
                            raise ValueError(
                                "conflicting IGN departmental terrain nodes"
                            )
                        values[present] = nodes[present]
                    available = np.isfinite(values)
                    valid[indices[~available]] = False
                    result[indices[available]] += (
                        values[available] * weight[indices[available]]
                    )
        return [float(value) if valid[i] else None for i, value in enumerate(result)]


@contextmanager
def ign_sampler(pins: IGNSources, prepared: Path) -> Iterator[IGNSampler]:
    import rasterio

    with rasterio.Env(GDAL_CACHEMAX=32 * 1024**2):
        sampler = IGNSampler(pins, prepared)
        try:
            yield sampler
        finally:
            sampler.close()
