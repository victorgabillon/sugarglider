"""Build and verify an *unpublished* checksum-pinned elevation research candidate.

This format is NOT a regional distribution manifest or an Android installable
component. Sources are always supplied locally; this module never downloads.
"""

import argparse
import json
import re
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

from sugarglider.offline_regions.elevation_feasibility import skadi_tiles_for_bounds
from sugarglider.offline_regions.elevation_hgt_probe import probe_hgt_file
from sugarglider.offline_regions.models import canonical_json
from sugarglider.offline_regions.validation import load_spec

CANDIDATE_FORMAT = "sugarglider-unpublished-elevation-research-v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _check_source_note(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 160
        or value.strip() != value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"invalid {label}")
    return value


def _read_pins(path: Path, expected_paths: list[str]) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("pins must be an existing regular file")
    if path.stat().st_size > 64 * 1024:
        raise ValueError("pin file exceeds 64 KiB")
    payload: object = json.loads(path.read_bytes())
    if not isinstance(payload, dict) or set(payload) != {
        "dataset",
        "acquired_on",
        "sources",
    }:
        raise ValueError("invalid source pin document")
    _check_source_note(payload["dataset"], "dataset")
    acquired_on = payload["acquired_on"]
    if not isinstance(acquired_on, str):
        raise ValueError("invalid acquisition date")
    try:
        if date.fromisoformat(acquired_on).isoformat() != acquired_on:
            raise ValueError("invalid acquisition date")
    except ValueError as error:
        raise ValueError("invalid acquisition date") from error
    sources = payload["sources"]
    if not isinstance(sources, list) or len(sources) != len(expected_paths):
        raise ValueError("pins must name exactly the required tiles")
    names: list[str] = []
    for source in sources:
        if not isinstance(source, dict) or set(source) != {
            "path",
            "sha256",
            "source_url",
        }:
            raise ValueError("invalid tile pin")
        tile_path = source["path"]
        digest = source["sha256"]
        url = source["source_url"]
        if (
            not isinstance(tile_path, str)
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
            or not isinstance(url, str)
            or not url.startswith("https://")
            or not url.endswith("/" + tile_path)
        ):
            raise ValueError("invalid tile pin path, checksum or source URL")
        names.append(tile_path)
    if names != expected_paths:
        raise ValueError("pins must list all required tiles in canonical order")
    return payload


def _tile_record(
    path: Path, tile_path: str, digest: str, source_url: str
) -> dict[str, object]:
    probe = probe_hgt_file(path, digest)
    return {
        "path": tile_path,
        "source_url": source_url,
        "sha256": probe.source_sha256,
        "compressed_bytes": probe.compressed_bytes,
        "decoded_bytes": len(probe.data),
        "pixels_valid": probe.pixels_valid,
        "pixels_void": probe.pixels_void,
        "pixels_invalid": probe.pixels_invalid,
        "min_height_m": probe.min_height_m,
        "max_height_m": probe.max_height_m,
    }


def _expected_paths(root: Path, region_id: str) -> tuple[list[str], list[float]]:
    spec = load_spec(root, region_id)
    return (
        [tile.path for tile in skadi_tiles_for_bounds(spec.bounds)],
        list(spec.bounds),
    )


def verify_candidate(root: Path, region_id: str, output: Path) -> dict[str, object]:
    """Reject any missing, extra, corrupt or misidentified staged tile."""
    if output.is_symlink() or not output.is_dir():
        raise ValueError("candidate directory missing or symbolic link")
    expected, bounds = _expected_paths(root, region_id)
    manifest_path = output / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("candidate manifest missing or symbolic link")
    if manifest_path.stat().st_size > 64 * 1024:
        raise ValueError("candidate manifest exceeds 64 KiB")
    manifest: object = json.loads(manifest_path.read_bytes())
    if not isinstance(manifest, dict) or set(manifest) != {
        "format",
        "schema_version",
        "region_id",
        "bounds",
        "dataset",
        "acquired_on",
        "publication_allowed",
        "tiles",
    }:
        raise ValueError("invalid candidate manifest")
    if (
        manifest["format"] != CANDIDATE_FORMAT
        or type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
        or manifest["region_id"] != region_id
        or manifest["bounds"] != bounds
        or manifest["publication_allowed"] is not False
    ):
        raise ValueError("candidate identity or unpublished policy mismatch")
    _check_source_note(manifest["dataset"], "dataset")
    acquired_on = manifest["acquired_on"]
    if not isinstance(acquired_on, str):
        raise ValueError("invalid acquisition date")
    try:
        if date.fromisoformat(acquired_on).isoformat() != acquired_on:
            raise ValueError("invalid acquisition date")
    except ValueError as error:
        raise ValueError("invalid acquisition date") from error
    entries = manifest["tiles"]
    if not isinstance(entries, list) or len(entries) != len(expected):
        raise ValueError("incorrect number of candidate tiles")
    allowed_files = {"manifest.json", *expected}
    found: set[str] = set()
    for path in output.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("candidate contains symbolic or unusual entry")
        if path.is_file():
            found.add(path.relative_to(output).as_posix())
    if found != allowed_files:
        raise ValueError("candidate contains missing or extra files")
    for expected_path, entry in zip(expected, entries, strict=True):
        if not isinstance(entry, dict):
            raise ValueError("invalid candidate tile metadata")
        digest = entry.get("sha256")
        url = entry.get("source_url")
        if (
            entry.get("path") != expected_path
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
            or not isinstance(url, str)
            or not url.startswith("https://")
            or not url.endswith("/" + expected_path)
        ):
            raise ValueError("invalid candidate tile identity")
        checked = _tile_record(output / expected_path, expected_path, digest, url)
        if entry != checked:
            raise ValueError("candidate tile statistics or metadata mismatch")
    return manifest


def build_candidate(
    root: Path,
    region_id: str,
    input_directory: Path,
    pins_path: Path,
    output: Path,
) -> dict[str, object]:
    """Stage and independently validate before atomically exposing a candidate.

    Existing files are not overwritten. Input tile bytes are copied after
    preflight and reverified in the staging tree, detecting source mutations.
    """
    expected, bounds = _expected_paths(root, region_id)
    pins = _read_pins(pins_path, expected)
    if (
        input_directory.is_symlink()
        or not input_directory.is_dir()
        or output.exists()
        or output.is_symlink()
    ):
        raise ValueError("source directory missing or candidate output already exists")
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise ValueError("candidate parent must be an existing real directory")
    sources = pins["sources"]
    assert isinstance(sources, list)
    for record in sources:
        assert isinstance(record, dict)
        name = record["path"]
        source = input_directory / name
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"required source tile missing or symbolic: {name}")
        digest = record["sha256"]
        assert isinstance(digest, str)
        probe_hgt_file(source, digest)
    with tempfile.TemporaryDirectory(
        dir=output.parent, prefix=f".{output.name}.staging-"
    ) as temporary:
        candidate = Path(temporary) / "candidate"
        candidate.mkdir()
        records: list[dict[str, object]] = []
        for record in sources:
            assert isinstance(record, dict)
            name = record["path"]
            digest = record["sha256"]
            url = record["source_url"]
            assert isinstance(name, str)
            assert isinstance(digest, str)
            assert isinstance(url, str)
            source = input_directory / name
            target = candidate / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            records.append(_tile_record(target, name, digest, url))
        manifest: dict[str, object] = {
            "format": CANDIDATE_FORMAT,
            "schema_version": 1,
            "region_id": region_id,
            "bounds": bounds,
            "dataset": pins["dataset"],
            "acquired_on": pins["acquired_on"],
            "publication_allowed": False,
            "tiles": records,
        }
        (candidate / "manifest.json").write_bytes(canonical_json(manifest))
        verify_candidate(root, region_id, candidate)
        if output.exists() or output.is_symlink():
            raise FileExistsError("candidate output appeared during staging")
        candidate.rename(output)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        subparser = subcommands.add_parser(name)
        subparser.add_argument("--region", required=True)
        subparser.add_argument("--output", type=Path, required=True)
        if name == "build":
            subparser.add_argument("--input-dir", type=Path, required=True)
            subparser.add_argument("--pins", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    try:
        if args.command == "build":
            report = build_candidate(
                root, args.region, args.input_dir, args.pins, args.output
            )
        else:
            report = verify_candidate(root, args.region, args.output)
    except (OSError, ValueError, json.JSONDecodeError, EOFError) as error:
        print(f"elevation-candidate: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
