"""V2 component and source isolation, exclusively synthetic HGT inputs."""

import json
from pathlib import Path

import pytest
from elevation_test_support import synthetic_sources, write_synthetic_elevation

from sugarglider.offline_regions.elevation_component import (
    build_elevation,
    verify_elevation,
)
from sugarglider.offline_regions.elevation_layout import elevation_paths
from sugarglider.offline_regions.models import (
    RegionalManifest,
    build_identity,
    canonical_json,
)

BOUNDS = (2.0, 48.8, 2.16, 48.94)


def test_v2_inclusive_coverage_and_order_is_bounded() -> None:
    assert elevation_paths((1.445097, 48.38, 2.25, 49.1)) == (
        "elevation/skadi/N48/N48E001.hgt.gz",
        "elevation/skadi/N48/N48E002.hgt.gz",
        "elevation/skadi/N49/N49E001.hgt.gz",
        "elevation/skadi/N49/N49E002.hgt.gz",
    )
    assert len(elevation_paths((1.1, 48.1, 2.0, 49.0))) == 4
    with pytest.raises(ValueError, match="budget"):
        elevation_paths((-10.0, 10.0, 10.0, 30.0))
    with pytest.raises(ValueError):
        elevation_paths((179.0, 1.0, 180.0, 2.0))


def test_sources_build_genuine_gzip_component_with_truthful_coverage(
    tmp_path: Path,
) -> None:
    pins = synthetic_sources(tmp_path, BOUNDS)
    manifest = build_elevation(
        tmp_path / "elevation", "synthetic-elevation", BOUNDS, pins
    )
    assert verify_elevation(tmp_path / "elevation") == manifest
    assert manifest.publication_allowed is False
    assert manifest.tiles[0].pixels_valid == 3601**2
    assert manifest.tiles[0].pixels_void == 0
    assert manifest.tiles[0].minimum_height_m == manifest.tiles[0].maximum_height_m == 0
    before = (tmp_path / "elevation/manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        build_elevation(tmp_path / "elevation", "synthetic-elevation", BOUNDS, pins)
    assert (tmp_path / "elevation/manifest.json").read_bytes() == before


@pytest.mark.parametrize(
    "problem", ["missing", "digest", "size", "tile", "symlink", "duplicates"]
)
def test_missing_corrupt_or_mismatched_sources_fail(
    tmp_path: Path, problem: str
) -> None:
    pins = synthetic_sources(tmp_path, BOUNDS)
    value = json.loads(pins.read_bytes())
    source = Path(value["tiles"][0]["path"])
    if problem == "missing":
        source.unlink()
    elif problem == "digest":
        value["tiles"][0]["sha256"] = "f" * 64
    elif problem == "size":
        value["tiles"][0]["byte_size"] += 1
    elif problem == "tile":
        value["tiles"][0]["tile"] = "N48E001"
    elif problem == "symlink":
        original = source.with_name("retained.hgt.gz")
        source.rename(original)
        source.symlink_to(original)
    else:
        value["tiles"].append(value["tiles"][0])
    pins.write_bytes(canonical_json(value))
    with pytest.raises((ValueError, OSError)):
        build_elevation(tmp_path / "elevation", "synthetic-elevation", BOUNDS, pins)


def test_component_counter_tampering_and_symlink_escape_are_rejected(
    tmp_path: Path,
) -> None:
    root = tmp_path / "elevation"
    write_synthetic_elevation(root, "synthetic", BOUNDS)
    path = root / "manifest.json"
    original = path.read_bytes()
    value = json.loads(original)
    value["tiles"][0]["maximum_height_m"] = 1
    path.write_bytes(canonical_json(value))
    with pytest.raises(ValueError, match="coverage metadata"):
        verify_elevation(root)
    path.write_bytes(original)
    tile = root / value["tiles"][0]["path"]
    retained = tmp_path / tile.name
    tile.rename(retained)
    tile.symlink_to(retained)
    with pytest.raises(ValueError, match="symbolic"):
        verify_elevation(root)
    assert retained.is_file()


@pytest.mark.parametrize("kind", ["map", "routing", "pois", "nature", "elevation"])
def test_every_v2_component_is_mandatory(kind: str) -> None:
    path = Path(__file__).parents[1] / "fixtures/pr40_regional_data.json"
    manifest = json.loads(path.read_bytes())["manifest"]
    manifest["components"].pop(kind)
    manifest["build_id"] = build_identity(
        {key: value for key, value in manifest.items() if key != "build_id"}
    )
    with pytest.raises(ValueError):
        RegionalManifest.model_validate_json(json.dumps(manifest))


def test_v1_is_rejected_without_a_migration_or_dual_parser() -> None:
    path = Path(__file__).parents[1] / "fixtures/pr40_regional_data.json"
    manifest = json.loads(path.read_bytes())["manifest"]
    manifest["schema_version"] = 1
    with pytest.raises(ValueError):
        RegionalManifest.model_validate_json(json.dumps(manifest))


@pytest.mark.parametrize(
    "vector",
    json.loads(
        (
            Path(__file__).parents[1] / "fixtures/v2_manifest_identity_vectors.json"
        ).read_bytes()
    ),
    ids=lambda vector: str(vector["name"]),
)
def test_cross_language_identity_vectors(vector: dict[str, object]) -> None:
    manifest = RegionalManifest.model_validate_json(json.dumps(vector["manifest"]))
    assert manifest.build_id == build_identity(
        manifest.model_dump(exclude={"build_id"})
    )
    assert canonical_json({"value": -0.0}) == canonical_json({"value": 0.0})


@pytest.mark.parametrize("value", [0, 1, "false", True, None])
def test_publication_flag_is_strict_and_never_enables_redistribution(
    value: object,
) -> None:
    manifest = json.loads(
        (Path(__file__).parents[1] / "fixtures/pr40_regional_data.json").read_bytes()
    )["manifest"]
    manifest["publication_allowed"] = value
    with pytest.raises(ValueError):
        RegionalManifest.model_validate_json(json.dumps(manifest))


@pytest.mark.parametrize(
    "path",
    [
        ("publication_allowed",),
        ("schema_version",),
        ("tools", "valhalla_image"),
        ("source", "source_url"),
    ],
)
def test_wire_fields_cannot_be_filled_by_constructor_defaults(
    path: tuple[str, ...],
) -> None:
    manifest = json.loads(
        (Path(__file__).parents[1] / "fixtures/pr40_regional_data.json").read_bytes()
    )["manifest"]
    target = manifest
    for key in path[:-1]:
        target = target[key]
    target.pop(path[-1])
    manifest["build_id"] = build_identity(
        {key: value for key, value in manifest.items() if key != "build_id"}
    )
    with pytest.raises(ValueError, match="explicit"):
        RegionalManifest.model_validate_json(json.dumps(manifest))


def test_reverification_hashes_reused_bytes_and_detects_same_size_corruption(
    tmp_path: Path,
) -> None:
    root = tmp_path / "elevation"
    write_synthetic_elevation(root, "synthetic", BOUNDS)
    manifest = verify_elevation(root)
    tile = root / manifest.tiles[0].path
    contents = bytearray(tile.read_bytes())
    contents[-1] ^= 1
    tile.write_bytes(contents)
    with pytest.raises(ValueError, match="SHA-256"):
        verify_elevation(root)
