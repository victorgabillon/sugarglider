"""Synthetic 3601-grid HGT tests; no source DEM or network is involved."""

import gzip
import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

from sugarglider.offline_regions.elevation_feasibility import (
    HGT_RAW_BYTES,
    HGT_SAMPLES_PER_SIDE,
    SkadiTile,
)
from sugarglider.offline_regions.elevation_hgt_probe import (
    HGT_NO_DATA,
    main,
    probe_hgt_file,
    tile_from_filename,
)


def fixture_tile(
    path: Path,
    *,
    height: int = 100,
    overrides: dict[tuple[int, int], int] | None = None,
    slope: bool = False,
) -> tuple[Path, str]:
    by_row: dict[int, list[tuple[int, int]]] = {}
    for (row, column), value in (overrides or {}).items():
        by_row.setdefault(row, []).append((column, value))
    with path.open("wb") as output:
        with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as stream:
            for row_number in range(HGT_SAMPLES_PER_SIDE):
                value = HGT_SAMPLES_PER_SIDE - 1 - row_number if slope else height
                row = bytearray(struct.pack(">h", value) * HGT_SAMPLES_PER_SIDE)
                for column, override in by_row.get(row_number, []):
                    struct.pack_into(">h", row, column * 2, override)
                stream.write(row)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def level_tile(tmp_path: Path) -> tuple[Path, str]:
    return fixture_tile(tmp_path / "N48E001.hgt.gz")


def test_canonical_names() -> None:
    assert tile_from_filename("N48E001.hgt.gz") == SkadiTile(48, 1)
    assert tile_from_filename("S02W001.hgt.gz") == SkadiTile(-2, -1)
    for name in (
        "s00E000.hgt.gz",
        "S00E001.hgt.gz",
        "N48E180.hgt.gz",
        "N90E001.hgt.gz",
        "../N48E001.hgt.gz",
        "N48E001.hgt",
        "N48E001.hgt.gz.bak",
    ):
        with pytest.raises(ValueError):
            tile_from_filename(name)


def test_valid_grid_statistics_and_sampling(level_tile: tuple[Path, str]) -> None:
    path, sha256 = level_tile
    result = probe_hgt_file(path, sha256)
    assert result.report() == {
        "tile": "N48E001.hgt.gz",
        "sha256": sha256,
        "compressed_bytes": path.stat().st_size,
        "decoded_bytes": HGT_RAW_BYTES,
        "pixels_valid": HGT_SAMPLES_PER_SIDE**2,
        "pixels_void": 0,
        "pixels_invalid": 0,
        "min_height_m": 100,
        "max_height_m": 100,
    }
    assert result.sample(latitude=48.5, longitude=1.5) == 100.0
    assert result.sample(latitude=48.0, longitude=1.0) == 100.0
    assert result.sample(latitude=48.999, longitude=1.999) == 100.0
    assert result.sample(latitude=49.0, longitude=1.5) is None
    assert result.sample(latitude=48.5, longitude=2.0) is None
    assert result.sample(latitude=float("nan"), longitude=1.5) is None


def test_void_and_invalid_values_remain_unavailable(tmp_path: Path) -> None:
    path, pin = fixture_tile(
        tmp_path / "N48E001.hgt.gz",
        overrides={(1800, 1800): HGT_NO_DATA, (1700, 1700): 20000},
    )
    probe = probe_hgt_file(path, pin)
    assert probe.pixels_void == 1
    assert probe.pixels_invalid == 1
    assert probe.pixels_valid == HGT_SAMPLES_PER_SIDE**2 - 2
    assert probe.min_height_m == probe.max_height_m == 100
    assert probe.sample(latitude=48.5, longitude=1.5) is None
    assert probe.sample(latitude=48.5001, longitude=1.5001) == pytest.approx(100.0)


def test_south_to_north_gradient_orientation(tmp_path: Path) -> None:
    path, pin = fixture_tile(tmp_path / "N48E001.hgt.gz", slope=True)
    probe = probe_hgt_file(path, pin)
    assert probe.sample(latitude=48.25, longitude=1.25) == pytest.approx(900.0)
    assert probe.sample(latitude=48.75, longitude=1.75) == pytest.approx(2700.0)
    assert probe.min_height_m == 0
    assert probe.max_height_m == 3600


def test_sha256_pin_enforced_before_decode(level_tile: tuple[Path, str]) -> None:
    path, pin = level_tile
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        probe_hgt_file(path, "0" * 64 if pin != "0" * 64 else "f" * 64)
    with pytest.raises(ValueError, match="64 lowercase"):
        probe_hgt_file(path, pin.upper())


def test_short_and_oversized_grid_rejected(tmp_path: Path) -> None:
    path = tmp_path / "N48E001.hgt.gz"
    for raw in (b"short", b"\x00" * (HGT_RAW_BYTES + 1)):
        path.write_bytes(gzip.compress(raw, mtime=0))
        pin = hashlib.sha256(path.read_bytes()).hexdigest()
        with pytest.raises(ValueError, match="decoded grid"):
            probe_hgt_file(path, pin)


def test_corrupt_gzip_detected(tmp_path: Path) -> None:
    path = tmp_path / "N48E001.hgt.gz"
    path.write_bytes(b"not a gzip file")
    pin = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(OSError):
        probe_hgt_file(path, pin)


def test_cli_output_and_no_side_effects(
    level_tile: tuple[Path, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path, pin = level_tile
    before = sorted(tmp_path.iterdir())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "elevation-hgt-probe",
            "--tile",
            str(path),
            "--sha256",
            pin,
            "--latitude",
            "48.5",
            "--longitude",
            "1.5",
        ],
    )
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["sample"]["height_m"] == 100.0
    assert result["pixels_valid"] == HGT_SAMPLES_PER_SIDE**2
    assert sorted(tmp_path.iterdir()) == before
