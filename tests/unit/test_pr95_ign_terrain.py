"""Synthetic source/geometry/datum/byte contracts, without real terrain or services."""

import gzip
import hashlib
import io
import json
import shutil
import tarfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from elevation_test_support import synthetic_sources
from test_pr94_distribution_readiness import private_region as private_region

from sugarglider.offline_regions.elevation_component import (
    ElevationManifest,
    build_elevation,
    verify_elevation,
)
from sugarglider.offline_regions.models import canonical_json
from sugarglider.offline_regions.publication import release_manifests
from sugarglider.offline_regions.terrain_conversion import convert_tile, quantize_height
from sugarglider.offline_regions.terrain_ign import (
    bilinear_weights,
    extract_delivery,
    ign_sampler,
)
from sugarglider.offline_regions.terrain_source import (
    IGNArchive,
    IGNSources,
    verify_source,
)
from sugarglider.offline_regions.validation import verify_region


def ign_pins() -> IGNSources:
    filename = "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D078_2020-07-30.7z"
    return IGNSources(
        product="IGN-RGE-ALTI-5M",
        horizontal_crs="EPSG:2154",
        vertical_crs="EPSG:5720",
        surface="DTM",
        license_url="https://www.etalab.gouv.fr/licence-ouverte-open-licence/",
        files=(
            IGNArchive(
                filename=filename,
                url="https://data.geopf.fr/telechargement/download/RGEALTI/"
                + filename.removesuffix(".7z")
                + "/"
                + filename,
                byte_size=7,
                sha256=hashlib.sha256(b"fixture").hexdigest(),
                acquired_at="2026-01-01T00:00:00Z",
                last_modified=None,
                etag=None,
                version_id=None,
            ),
        ),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("vertical_crs", "EPSG:5773"),
        ("horizontal_crs", "EPSG:4326"),
        ("surface", "DSM"),
        ("product", "IGN-LIDAR-5M"),
        ("license_url", "https://unverified.test/"),
    ],
)
def test_source_semantics_are_explicit(field: str, value: str) -> None:
    pins = ign_pins().model_dump(mode="json")
    pins[field] = value
    with pytest.raises(ValueError):
        IGNSources.model_validate(pins)


@pytest.mark.parametrize(
    "field,value",
    [
        ("filename", "../terrain.7z"),
        ("filename", "RGEALTI_1M.7z"),
        ("url", "https://data.geopf.fr/another-archive.7z"),
        ("url", "https://user:secret@data.geopf.fr/terrain.7z"),
        ("sha256", "f" * 63),
        ("byte_size", 1_000_000_001),
        ("acquired_at", "unknown"),
        ("acquired_at", "2026-01-01T00:00:00"),
        ("filename", "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D078_2020-02-30.7z"),
    ],
)
def test_source_identity_rejects_ambiguity(field: str, value: object) -> None:
    pin = ign_pins().files[0].model_dump(mode="json")
    pin[field] = value
    with pytest.raises(ValueError):
        IGNArchive.model_validate(pin)


def test_source_bytes_and_department_uniqueness(tmp_path: Path) -> None:
    pins = ign_pins()
    path = tmp_path / pins.files[0].filename
    path.write_bytes(b"fixture")
    assert verify_source(tmp_path, pins.files[0]) == path
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        verify_source(tmp_path, pins.files[0])
    with pytest.raises(ValueError, match="duplicate"):
        IGNSources.model_validate({**pins.model_dump(), "files": pins.files * 2})


def test_acquisition_checks_disk_before_creating_output_or_using_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sugarglider.offline_regions import terrain_source

    monkeypatch.setattr(shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    target = tmp_path / "no-space"
    with pytest.raises(ValueError, match="insufficient disk"):
        terrain_source.acquire_sources(ign_pins(), target)
    assert not target.exists()


@pytest.mark.parametrize(
    "name,kind",
    [
        ("../escape", tarfile.REGTYPE),
        ("/absolute", tarfile.REGTYPE),
        ("link", tarfile.SYMTYPE),
        ("hardlink", tarfile.LNKTYPE),
        ("device", tarfile.CHRTYPE),
    ],
)
def test_archive_never_follows_paths_or_links(
    tmp_path: Path, name: str, kind: bytes
) -> None:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        entry = tarfile.TarInfo(name)
        entry.type = kind
        entry.size = 1
        archive.addfile(entry, io.BytesIO(b"x"))
    stream.seek(0)
    with pytest.raises((ValueError, OSError)):
        extract_delivery(stream, tmp_path)
    assert not list(tmp_path.iterdir())


def test_exact_nodes_and_boundary_neighbors() -> None:
    assert bilinear_weights(5000, 5000) == ((1000, 1000, 1.0),)
    weights = bilinear_weights(4997.5, 5002.5)
    assert len(weights) == 4 and sum(v[2] for v in weights) == 1
    assert {(ix // 1000, (iy - 1) // 1000) for ix, iy, _ in weights} == {
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    }
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            bilinear_weights(bad, 0)


def prepared_mosaic(
    tmp_path: Path, *, void: bool = False, conflict: bool = False
) -> Path:
    np = pytest.importorskip("numpy")
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import Affine  # type: ignore[import-untyped]

    records = []
    for name, x0 in (("west", 0), ("east", 5000)):
        path = tmp_path / (name + ".tif")
        xs = x0 + np.arange(1000) * 5
        ys = 5000 - np.arange(1000) * 5
        heights = (100 + xs[None, :] * 0.01 + ys[:, None] * 0.02).astype("float32")
        if void and name == "east":
            heights[0, 0] = -99999
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=1000,
            height=1000,
            count=1,
            dtype="float32",
            crs="EPSG:2154",
            nodata=-99999,
            transform=Affine(5, 0, x0 - 2.5, 0, -5, 5002.5),
        ) as dst:
            dst.write(heights, 1)
        records.append(
            {
                "path": path.name,
                "source_archive_sha256": ign_pins().files[0].sha256,
                "original_ascii_sha256": "a" * 64,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    if conflict:
        path = tmp_path / "duplicate.tif"
        with rasterio.open(tmp_path / "west.tif") as src:
            profile = src.profile
            heights = src.read(1) + 1
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(heights, 1)
        records.append(
            {
                "path": path.name,
                "source_archive_sha256": ign_pins().files[0].sha256,
                "original_ascii_sha256": "a" * 64,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    (tmp_path / "prepared.json").write_bytes(
        canonical_json(
            {
                "sources": ign_pins().model_dump(mode="json"),
                "grids": records,
            }
        )
    )
    return tmp_path


@pytest.mark.parametrize("cache_limit", [1, 32])
def test_projected_mosaic_strict_nodata_and_seams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cache_limit: int
) -> None:
    from sugarglider.offline_regions import terrain_ign

    monkeypatch.setattr(terrain_ign, "MAX_OPEN_DATASETS", cache_limit)
    prepared_mosaic(tmp_path, void=True)
    with ign_sampler(ign_pins(), tmp_path) as sampler:
        xs, ys = [4995, 4997.5, 5000, 5000, 10000], [5000, 5000, 5000, 4995, 5000]
        values = sampler.sample(xs, ys)
        assert values[0] == pytest.approx(249.95, abs=2e-5)
        assert values[1:3] == [None, None]
        assert values[3] == pytest.approx(249.9, abs=2e-5)
        assert values[4] is None
        assert len(sampler.cache) <= cache_limit
    assert not sampler.cache


def test_ambiguous_overlap_and_modified_preparation_fail(tmp_path: Path) -> None:
    prepared_mosaic(tmp_path, conflict=True)
    with ign_sampler(ign_pins(), tmp_path) as sampler:
        with pytest.raises(ValueError, match="conflicting"):
            sampler.sample([0], [5000])
    path = tmp_path / "east.tif"
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        with ign_sampler(ign_pins(), tmp_path):
            pass


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "foreign", "traversal"])
def test_prepared_index_rejects_incomplete_or_mismatched_sources(
    tmp_path: Path, mutation: str
) -> None:
    prepared_mosaic(tmp_path)
    path = tmp_path / "prepared.json"
    index = json.loads(path.read_bytes())
    if mutation == "missing":
        del index["grids"][0]["original_ascii_sha256"]
    elif mutation == "duplicate":
        index["grids"].append(index["grids"][0])
    elif mutation == "foreign":
        index["grids"][0]["source_archive_sha256"] = "f" * 64
    else:
        index["grids"][0]["path"] = "../outside.tif"
    path.write_bytes(canonical_json(index))
    with pytest.raises(ValueError):
        with ign_sampler(ign_pins(), tmp_path):
            pass


def test_identical_prepared_bytes_are_verified_but_opened_once(tmp_path: Path) -> None:
    prepared_mosaic(tmp_path)
    path = tmp_path / "prepared.json"
    index = json.loads(path.read_bytes())
    duplicate = {**index["grids"][0], "path": "identical.tif"}
    shutil.copyfile(tmp_path / "west.tif", tmp_path / duplicate["path"])
    index["grids"].append(duplicate)
    path.write_bytes(canonical_json(index))
    with ign_sampler(ign_pins(), tmp_path) as sampler:
        assert len(sampler.grids[0, 0]) == 1
    (tmp_path / duplicate["path"]).write_bytes(b"changed duplicate")
    with pytest.raises(ValueError, match="hash"):
        with ign_sampler(ign_pins(), tmp_path):
            pass


def test_lambert_origin_roundtrip_and_vertical_identity() -> None:
    pyproj = pytest.importorskip("pyproj")
    pyproj.network.set_network_enabled(False)
    forward = pyproj.Transformer.from_crs(
        4326, 2154, always_xy=True, allow_ballpark=False
    )
    inverse = pyproj.Transformer.from_crs(
        2154, 4326, always_xy=True, allow_ballpark=False
    )
    x, y, h = forward.transform(3, 46.5, 123.456, errcheck=True)
    assert (x, y, h) == pytest.approx((700000, 6600000, 123.456), abs=1e-6)
    assert inverse.transform(x, y, h, errcheck=True) == pytest.approx(
        (3, 46.5, 123.456), abs=1e-9
    )


def test_real_hgt_writer_is_repeatable_and_preserves_voids(tmp_path: Path) -> None:
    def row(latitude: float, west: int, count: int) -> list[float | None]:
        assert west == 2 and count == 3601
        return [None, -2.5, 2.5, *([100 + latitude - 48] * (count - 3))]

    for name in ("one", "two"):
        convert_tile(tmp_path / name, 48, 2, row, lambda _x, _y, h: h)
    first, second = (tmp_path / "one").read_bytes(), (tmp_path / "two").read_bytes()
    assert first == second
    assert first[4:8] == bytes(4)  # no wall-clock gzip timestamp
    decoded = gzip.decompress(first)
    assert len(decoded) == 3601 * 3601 * 2
    assert decoded[:6] == b"\x80\x00\xff\xfe\x00\x02"
    assert decoded[6:8] == (101).to_bytes(2, "big", signed=True)
    assert decoded[-2:] == (100).to_bytes(2, "big", signed=True)
    assert quantize_height(None) == -32768


def test_ign_component_binds_sources_and_cannot_be_relabelled_or_published(
    tmp_path: Path,
) -> None:
    pins_path = synthetic_sources(tmp_path, (2, 48.8, 2.16, 48.94))
    pins = json.loads(pins_path.read_bytes())
    pins["derivation"] = {
        "algorithm": "ign-rge-alti-5m-ign69-skadi-v1",
        "sources": ign_pins().model_dump(mode="json"),
        "prepared_sha256": "a" * 64,
        "transformation_sha256": "b" * 64,
    }
    pins_path.write_bytes(canonical_json(pins))
    directory = tmp_path / "elevation"
    manifest = build_elevation(
        directory, "ign-pilot", (2, 48.8, 2.16, 48.94), pins_path
    )
    assert verify_elevation(directory) == manifest
    assert manifest.vertical_datum == "IGN69" and not manifest.publication_allowed
    original = (directory / "manifest.json").read_bytes()
    for changes in (
        {"publication_allowed": True},
        {"vertical_datum": "EGM96"},
        {"derivation": None},
        {"provenance_status": "unresolved"},
    ):
        with pytest.raises(ValueError):
            ElevationManifest.model_validate({**manifest.model_dump(), **changes})
    # Even a fully documented IGN component cannot enter the Copernicus approval path.
    from unittest.mock import Mock

    with pytest.raises(ValueError, match="unresolved"):
        release_manifests(directory.parent, Mock(publication_allowed=False))
    assert (directory / "manifest.json").read_bytes() == original
    changed: dict[str, Any] = manifest.model_dump(mode="json")
    changed["derivation"]["sources"]["files"][0]["sha256"] = "c" * 64
    assert canonical_json(changed) != original


def test_rebuild_canonicalizes_relative_output_without_changing_old_region(
    tmp_path: Path, private_region: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sugarglider.offline_regions import terrain_rebuild

    old = verify_region(private_region)
    original = (private_region / "manifest.json").read_bytes()
    pins = synthetic_sources(tmp_path, old.bounds)
    called = []

    def synthetic_build(
        arguments: Sequence[str], environment: Mapping[str, str]
    ) -> None:
        # Reuse the existing synthetic validation fixture; no external graph build.
        destination = Path(arguments[-1])
        assert destination.is_absolute() and destination.resolve() == destination
        assert Path(environment["SUGARGLIDER_DEM_DIR"]).resolve() == Path(
            environment["SUGARGLIDER_DEM_DIR"]
        )
        shutil.copytree(private_region / "routing", destination)
        archive = destination / "valhalla_tiles.tar"
        data = bytearray(archive.read_bytes())
        data[1700] = 1  # Synthetic tile payload; retain its tested format/header.
        archive.write_bytes(data)
        called.append(destination)

    monkeypatch.setattr(terrain_rebuild, "run_command", synthetic_build)
    repository = tmp_path / "repository"
    monkeypatch.chdir(repository)
    result = terrain_rebuild.rebuild_terrain_region(
        repository,
        private_region,
        tmp_path / "tiny.osm.pbf",
        pins,
        Path("../rebuilt"),
    )
    assert result == (tmp_path / "rebuilt").resolve() and called
    assert verify_region(result).build_id != old.build_id
    assert (private_region / "manifest.json").read_bytes() == original


def test_original_source_identity_changes_regional_identity_even_for_equal_heights(
    tmp_path: Path, private_region: Path
) -> None:
    from sugarglider.offline_regions.build import make_manifest
    from sugarglider.offline_regions.validation import load_spec

    old = verify_region(private_region)
    spec = load_spec(tmp_path / "repository", old.region_id)
    pins_path = synthetic_sources(tmp_path, old.bounds)
    pins = json.loads(pins_path.read_bytes())
    pins["derivation"] = {
        "algorithm": "ign-rge-alti-5m-ign69-skadi-v1",
        "sources": ign_pins().model_dump(mode="json"),
        "prepared_sha256": "a" * 64,
        "transformation_sha256": "b" * 64,
    }
    builds = []
    for index in (0, 1):
        target = tmp_path / f"source-identity-{index}"
        target.mkdir()
        for component in ("map", "routing", "pois", "nature"):
            shutil.copytree(private_region / component, target / component)
        if index:
            # Synthetic provenance mutation, with deliberately identical HGT.
            pins["derivation"]["sources"]["files"][0]["sha256"] = "f" * 64
        pins_path.write_bytes(canonical_json(pins))
        build_elevation(
            target / "elevation", spec.elevation.component_id, old.bounds, pins_path
        )
        builds.append(make_manifest(target, spec, old.source, old.tools))
    first, second = builds
    assert first.components.elevation.files[1:] == second.components.elevation.files[1:]
    assert (
        first.components.routing == second.components.routing == old.components.routing
    )
    assert (
        first.components.elevation.files[0].sha256
        != second.components.elevation.files[0].sha256
    )
    assert first.build_id != second.build_id
