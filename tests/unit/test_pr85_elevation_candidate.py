"""Unpublished Skadi candidate staging stays immutable and source-pinned."""

import gzip
import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

from sugarglider.offline_regions.elevation_candidate import (
    CANDIDATE_FORMAT,
    build_candidate,
    main,
    verify_candidate,
)
from sugarglider.offline_regions.elevation_feasibility import HGT_SAMPLES_PER_SIDE
from sugarglider.offline_regions.models import canonical_json

ROOT = Path(__file__).resolve().parents[2]
TILE = "skadi/N48/N48E002.hgt.gz"


@pytest.fixture
def pinned_source(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    source_dir = tmp_path / "source"
    source_tile = source_dir / TILE
    source_tile.parent.mkdir(parents=True)
    # Full-size HGT synthetic fixture; no downloaded third-party data.
    with source_tile.open("wb") as destination:
        with gzip.GzipFile(fileobj=destination, mode="wb", filename="", mtime=0) as gz:
            row = struct.pack(">h", 137) * HGT_SAMPLES_PER_SIDE
            for _ in range(HGT_SAMPLES_PER_SIDE):
                gz.write(row)
    digest = hashlib.sha256(source_tile.read_bytes()).hexdigest()
    pins = {
        "dataset": "Synthetic unit-test terrain (no external DEM)",
        "acquired_on": "2026-10-13",
        "sources": [
            {
                "path": TILE,
                "sha256": digest,
                "source_url": (
                    "https://example.invalid/synthetic/skadi/N48/N48E002.hgt.gz"
                ),
            }
        ],
    }
    pins_path = tmp_path / "pins.json"
    pins_path.write_bytes(canonical_json(pins))
    return source_dir, pins_path, source_tile, digest


def test_candidate_is_atomic_reproducible_and_unpublished(
    pinned_source: tuple[Path, Path, Path, str], tmp_path: Path
) -> None:
    directory, pins, source, digest = pinned_source
    original = source.read_bytes()
    first = tmp_path / "candidate-one"
    second = tmp_path / "candidate-two"
    report = build_candidate(ROOT, "marly", directory, pins, first)
    assert report["publication_allowed"] is False
    assert report["format"] == CANDIDATE_FORMAT
    assert report["bounds"] == [2.0, 48.8, 2.16, 48.94]
    assert report["region_id"] == "marly"
    assert report["tiles"] == [
        {
            "path": TILE,
            "source_url": "https://example.invalid/synthetic/" + TILE,
            "sha256": digest,
            "compressed_bytes": len(original),
            "decoded_bytes": 25_934_402,
            "pixels_valid": HGT_SAMPLES_PER_SIDE**2,
            "pixels_void": 0,
            "pixels_invalid": 0,
            "min_height_m": 137,
            "max_height_m": 137,
        }
    ]
    assert source.read_bytes() == original
    assert (first / TILE).read_bytes() == original
    assert verify_candidate(ROOT, "marly", first) == report
    build_candidate(ROOT, "marly", directory, pins, second)
    assert (first / "manifest.json").read_bytes() == (
        second / "manifest.json"
    ).read_bytes()


def test_missing_or_mismatched_source_fails_closed(
    pinned_source: tuple[Path, Path, Path, str], tmp_path: Path
) -> None:
    directory, pins, source, _ = pinned_source
    output = tmp_path / "candidate"
    payload = json.loads(pins.read_bytes())
    payload["sources"][0]["sha256"] = "0" * 64
    pins.write_bytes(canonical_json(payload))
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        build_candidate(ROOT, "marly", directory, pins, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".candidate.staging-*"))

    source.unlink()
    with pytest.raises(ValueError, match="missing"):
        build_candidate(ROOT, "marly", directory, pins, output)
    assert not output.exists()


def test_pin_inventory_must_match_expected_region(
    pinned_source: tuple[Path, Path, Path, str], tmp_path: Path
) -> None:
    directory, pins, _, _ = pinned_source
    output = tmp_path / "candidate"
    for altered in (
        {"sources": []},
        {"sources": [{"path": "skadi/N48/N48E001.hgt.gz"}]},
        {"dataset": ""},
        {"acquired_on": "not-a-date"},
    ):
        payload = json.loads(pins.read_bytes())
        payload.update(altered)
        bad_pins = tmp_path / "bad-pins.json"
        bad_pins.write_bytes(canonical_json(payload))
        with pytest.raises(ValueError):
            build_candidate(ROOT, "marly", directory, bad_pins, output)
        assert not output.exists()


def test_existing_output_and_symbolic_source_are_rejected(
    pinned_source: tuple[Path, Path, Path, str], tmp_path: Path
) -> None:
    directory, pins, source, _ = pinned_source
    output = tmp_path / "candidate"
    output.mkdir()
    (output / "keep.txt").write_text("protected")
    with pytest.raises(ValueError, match="exists"):
        build_candidate(ROOT, "marly", directory, pins, output)
    assert (output / "keep.txt").read_text() == "protected"
    output.rmdir() if not list(output.iterdir()) else None

    target = tmp_path / "unchanged.hgt.gz"
    source.rename(target)
    source.symlink_to(target)
    with pytest.raises(ValueError, match="symbolic"):
        build_candidate(ROOT, "marly", directory, pins, tmp_path / "fresh")
    assert target.is_file()


def test_verifier_rejects_corruption_extra_files_and_policy_change(
    pinned_source: tuple[Path, Path, Path, str], tmp_path: Path
) -> None:
    directory, pins, _, _ = pinned_source
    target = tmp_path / "candidate"
    build_candidate(ROOT, "marly", directory, pins, target)
    extra = target / "skadi" / "unexpected.txt"
    extra.write_text("unexpected")
    with pytest.raises(ValueError, match="extra"):
        verify_candidate(ROOT, "marly", target)
    extra.unlink()

    manifest_path = target / "manifest.json"
    original_manifest = manifest_path.read_bytes()
    manifest = json.loads(original_manifest)
    manifest["publication_allowed"] = True
    manifest_path.write_bytes(canonical_json(manifest))
    with pytest.raises(ValueError, match="policy"):
        verify_candidate(ROOT, "marly", target)
    manifest_path.write_bytes(original_manifest)

    tile_path = target / TILE
    tile_path.write_bytes(tile_path.read_bytes() + b"extra")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_candidate(ROOT, "marly", target)


def test_cli_build_verify_do_not_download(
    pinned_source: tuple[Path, Path, Path, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory, pins, _, _ = pinned_source
    output = tmp_path / "candidate"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "elevation-candidate",
            "build",
            "--region",
            "marly",
            "--input-dir",
            str(directory),
            "--pins",
            str(pins),
            "--output",
            str(output),
        ],
    )
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["publication_allowed"] is False
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "elevation-candidate",
            "verify",
            "--region",
            "marly",
            "--output",
            str(output),
        ],
    )
    before = (output / "manifest.json").read_bytes()
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["tiles"][0]["path"] == TILE
    assert (output / "manifest.json").read_bytes() == before
