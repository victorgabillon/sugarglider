"""PR39 real tiny OSM geometry plus injected map/routing builds; no services."""

import gzip
import hashlib
import io
import json
import shutil
import struct
import subprocess
import sys
import tarfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import osmium
import pytest
from pydantic import ValidationError

from sugarglider.nature.build import build_nature_index
from sugarglider.nature.models import NatureIndexDocument
from sugarglider.offline_regions.build import (
    build_components,
    build_region,
    make_manifest,
    source_identity,
    toolchain,
)
from sugarglider.offline_regions.map_manifest import MANIFEST_FIELDS
from sugarglider.offline_regions.models import (
    Components,
    FileDescriptor,
    RegionSpec,
    canonical_json,
    contained_path,
)
from sugarglider.offline_regions.validation import (
    MapManifest,
    RoutingManifest,
    load_spec,
    read_map,
    validate_pmtiles,
    verify_region,
)
from sugarglider.pois.build import build_poi_index
from sugarglider.pois.models import PoiIndexDocument

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/pr39_region.osm"


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    for folder in ("offline-regions", "map-packs"):
        shutil.copytree(ROOT / folder, tmp_path / folder)
    return tmp_path


@pytest.fixture
def pbf(tmp_path: Path) -> Path:
    source = tmp_path / "tiny.osm.pbf"
    processor = osmium.FileProcessor(FIXTURE)
    with osmium.SimpleWriter(source, header=processor.header) as writer:
        for entity in processor:
            writer.add(entity)
    return source


def fake_components(
    root: Path, spec: RegionSpec, source: Path, directory: Path
) -> None:
    for name in ("map", "routing"):
        (directory / name).mkdir()
    header = bytearray(127)
    header[:8] = b"PMTiles\x03"
    for position, offset, length in (
        (8, 127, 1),
        (24, 128, 2),
        (40, 130, 0),
        (56, 130, 1),
    ):
        struct.pack_into("<QQ", header, position, offset, length)
    for position in (72, 80, 88):
        struct.pack_into("<Q", header, position, 1)
    header[97:102] = bytes((1, 1, 1, 0, 15))
    struct.pack_into(
        "<iiii", header, 102, *(round(v * 10_000_000) for v in spec.bounds)
    )
    archive = bytes(header) + b"\x00{}\x00"
    (directory / "map/basemap.pmtiles").write_bytes(archive)
    template = json.loads((root / spec.map.template).read_bytes())
    template.update(byte_size=len(archive))
    (directory / "map/manifest.json").write_bytes(canonical_json(template))
    routing = {
        "schema_version": 2,
        "pack_id": spec.routing.pack_id,
        "engine": "valhalla",
        "engine_version": "3.6.3",
        "access_modes": ["foot", "bicycle"],
        "bounds": dict(
            zip(("west", "south", "east", "north"), spec.bounds, strict=True)
        ),
    }
    (directory / "routing/manifest.json").write_bytes(canonical_json(routing))
    with tarfile.open(
        directory / "routing/valhalla_tiles.tar", "w", format=tarfile.USTAR_FORMAT
    ) as tar:
        for name, data in (
            ("index.bin", struct.pack("<QLL", 1536, 2, 4)),
            ("2/000/000.gph", b"tile"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    build_poi_index(source, directory / "pois/index.json.gz", bounds=spec.bounds)
    build_nature_index(source, directory / "nature/index.json.gz", bounds=spec.bounds)


@pytest.mark.parametrize(
    "region,bounds,ids",
    [
        ("marly", (2.0, 48.8, 2.16, 48.94), ("marly-map-dev-v1", "marly-dev-v1")),
        ("paris", (2.25, 48.8, 2.42, 48.92), ("paris-map-dev-v1", "paris-dev-v1")),
    ],
)
def test_specs_match_existing_templates(
    region: str, bounds: tuple[float, ...], ids: tuple[str, str]
) -> None:
    spec = load_spec(ROOT, region)
    assert spec.bounds == bounds
    assert spec.component_ids[:2] == ids
    assert set(MapManifest.model_fields) == MANIFEST_FIELDS
    assert set(RoutingManifest.model_fields) == {
        "schema_version",
        "pack_id",
        "engine",
        "engine_version",
        "access_modes",
        "bounds",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("extra", 1),
        ("region_id", "../bad"),
        ("region_id", "marly..v1"),
        ("region_id", "Marly"),
        ("bounds", [2, 49, 1, 50]),
        ("bounds", [True, 48, 3, 49]),
        ("bounds", [2, 48, "3", 49]),
        ("bounds", [2, 48, float("inf"), 49]),
        ("bounds", [2, -86, 3, 49]),
        ("schema_version", 2),
        ("schema_version", True),
        ("schema_version", 1.0),
    ],
)
def test_strict_spec_rejections(field: str, value: object) -> None:
    payload = json.loads((ROOT / "offline-regions/marly.json").read_bytes())
    payload[field] = value
    with pytest.raises(ValidationError):
        RegionSpec.model_validate_json(json.dumps(payload))


def test_nested_fields_duplicate_ids_and_template_mismatch(repository: Path) -> None:
    path = repository / "offline-regions/marly.json"
    original = json.loads(path.read_bytes())
    for patch in ({"extra": True}, {"component_id": "marly-dev-v1"}):
        changed = json.loads(json.dumps(original))
        changed["pois"].update(patch)
        with pytest.raises(ValidationError):
            RegionSpec.model_validate_json(json.dumps(changed))
    original["bounds"][0] = 1.99
    path.write_bytes(canonical_json(original))
    with pytest.raises(ValueError, match="template"):
        load_spec(repository, "marly")


@pytest.mark.parametrize(
    "path",
    [
        "../x",
        "/tmp/x",
        "map/../x",
        "map//x",
        "map/./x",
        "C:\\x",
        "map/x\\y",
        "map/x/",
        "",
    ],
)
def test_unsafe_paths(path: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        contained_path(tmp_path, path)
    with pytest.raises(ValidationError):
        FileDescriptor(path=path, byte_size=1, sha256="0" * 64, format="pmtiles-v3-mvt")


def test_symlink_paths_and_output_parent_rejected(repository: Path, pbf: Path) -> None:
    (repository / "link").symlink_to(repository, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic"):
        contained_path(repository, "link/file")
    (repository / "data").symlink_to(repository, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic"):
        build_region(repository, "marly", pbf, builder=fake_components)


def test_geometry_preserves_nodes_ways_polygons_relations_holes_and_approaches(
    pbf: Path, tmp_path: Path
) -> None:
    bounds = load_spec(ROOT, "marly").bounds
    poi_path, nature_path = tmp_path / "pois.gz", tmp_path / "nature.gz"
    build_poi_index(pbf, poi_path, bounds=bounds)
    build_nature_index(pbf, nature_path, bounds=bounds)
    pois = PoiIndexDocument.model_validate_json(gzip.decompress(poi_path.read_bytes()))
    nature = NatureIndexDocument.model_validate_json(
        gzip.decompress(nature_path.read_bytes())
    )
    assert {f.id for f in pois.features} == {
        "node/1",
        "way/20",
        "way/21",
        "relation/30",
    }
    assert {f.feature_id for f in nature.features} == {"way/21", "relation/30"}
    assert next(f for f in pois.features if f.id == "way/21").approach_candidates
    relation = next(f for f in nature.features if f.feature_id == "relation/30")
    assert relation.geometry.type == "Polygon"
    assert len(relation.geometry.coordinates) == 2
    assert pois.metadata.bounding_box == nature.metadata.bounding_box == bounds
    before = poi_path.read_bytes(), nature_path.read_bytes()
    build_poi_index(pbf, poi_path, bounds=bounds)
    build_nature_index(pbf, nature_path, bounds=bounds)
    assert before == (poi_path.read_bytes(), nature_path.read_bytes())
    # Retain the complete polygon even if all outer vertices are outside a tiny region.
    tiny = (2.061, 48.881, 2.062, 48.882)
    build_nature_index(pbf, nature_path, bounds=tiny)
    retained = NatureIndexDocument.model_validate_json(
        gzip.decompress(nature_path.read_bytes())
    )
    assert {f.feature_id for f in retained.features} == {"way/21", "relation/30"}
    assert retained.features == nature.features


def test_source_provenance_and_coverage(pbf: Path, tmp_path: Path) -> None:
    spec = load_spec(ROOT, "marly")
    identity = source_identity(pbf, spec, "https://example.test/source.osm.pbf")
    assert identity.sha256 == hashlib.sha256(pbf.read_bytes()).hexdigest()
    assert identity.byte_size == pbf.stat().st_size
    assert identity.basename == "tiny.osm.pbf"
    assert identity.header_bounds == (1.0, 48.0, 4.0, 50.0)
    for bounds in (None, osmium.osm.Box(3.0, 49.0, 4.0, 50.0)):
        output = tmp_path / ("missing.osm.pbf" if bounds is None else "wrong.osm.pbf")
        header = osmium.io.Header()
        if bounds is not None:
            header.add_box(bounds)
        with osmium.SimpleWriter(output, header=header):
            pass
        with pytest.raises(ValueError, match="cover"):
            source_identity(output, spec, None)


def test_atomic_publication_deterministic_manifest_and_hashes(
    repository: Path, pbf: Path
) -> None:
    output = build_region(repository, "marly", pbf, builder=fake_components)
    manifest = verify_region(output)
    assert set(Components.model_fields) == {"map", "routing", "pois", "nature"}
    for component in manifest.components.ordered:
        for file in component.files:
            data = (output / file.path).read_bytes()
            assert file.byte_size == len(data)
            assert file.sha256 == hashlib.sha256(data).hexdigest()
    assert not tuple(output.rglob("*.pbf"))
    assert list(output.parent.iterdir()) == [output]
    rebuilt = make_manifest(
        output, load_spec(repository, "marly"), manifest.source, manifest.tools
    )
    assert rebuilt == manifest
    assert (
        canonical_json(rebuilt.model_dump(mode="json"))
        == (output / "manifest.json").read_bytes()
    )
    before = (output / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        build_region(repository, "marly", pbf, builder=fake_components)
    assert (output / "manifest.json").read_bytes() == before


@pytest.mark.parametrize(
    "problem",
    [
        "failure",
        "missing",
        "corrupt-map",
        "corrupt-tar",
        "corrupt-pois",
        "wrong-bounds",
        "extra-source",
        "symlink",
    ],
)
def test_failed_build_never_publishes_and_cleans_staging(
    repository: Path, pbf: Path, problem: str
) -> None:
    def broken(root: Path, spec: RegionSpec, source: Path, directory: Path) -> None:
        if problem == "failure":
            raise RuntimeError("builder failed")
        fake_components(root, spec, source, directory)
        if problem == "missing":
            (directory / "nature/index.json.gz").unlink()
        elif problem == "corrupt-map":
            (directory / "map/basemap.pmtiles").write_bytes(b"corrupt")
        elif problem == "corrupt-tar":
            (directory / "routing/valhalla_tiles.tar").write_bytes(b"corrupt")
        elif problem == "corrupt-pois":
            (directory / "pois/index.json.gz").write_bytes(
                gzip.compress(b"{}", mtime=0)
            )
        elif problem == "wrong-bounds":
            path = directory / "routing/manifest.json"
            value = json.loads(path.read_bytes())
            value["bounds"]["west"] = 1.0
            path.write_bytes(canonical_json(value))
        elif problem == "extra-source":
            (directory / "source.osm.pbf").write_bytes(b"not downloadable")
        elif problem == "symlink":
            (directory / "extra").symlink_to(source)

    with pytest.raises((ValueError, OSError, RuntimeError)):
        build_region(repository, "marly", pbf, builder=broken)
    assert not tuple((repository / "data/offline-regions").iterdir())


def test_verifier_rejects_tampering_and_extra_components(
    repository: Path, pbf: Path
) -> None:
    output = build_region(repository, "marly", pbf, builder=fake_components)
    path = output / "map/basemap.pmtiles"
    data = path.read_bytes()
    path.write_bytes(data[:-1] + b"x")
    with pytest.raises(ValueError, match="checksum"):
        verify_region(output)
    path.write_bytes(data)
    manifest_path = output / "manifest.json"
    payload = json.loads(manifest_path.read_bytes())
    payload["components"]["other"] = payload["components"]["pois"]
    manifest_path.write_bytes(canonical_json(payload))
    with pytest.raises(ValidationError):
        verify_region(output)


def test_url_is_not_content_identity_and_source_change_aborts(
    repository: Path, pbf: Path
) -> None:
    spec = load_spec(repository, "marly")
    staging = repository / "components"
    staging.mkdir()
    fake_components(repository, spec, pbf, staging)
    identity = source_identity(pbf, spec, None)
    first = make_manifest(staging, spec, identity, toolchain())
    located = identity.model_copy(update={"source_url": "https://example.test/moved"})
    assert make_manifest(staging, spec, located, toolchain()).build_id == first.build_id

    def changing(root: Path, config: RegionSpec, source: Path, output: Path) -> None:
        fake_components(root, config, source, output)
        with source.open("ab") as stream:
            stream.write(b"changed input")

    with pytest.raises((ValueError, RuntimeError)):
        build_region(repository, "marly", pbf, builder=changing)
    assert not tuple((repository / "data/offline-regions").iterdir())


def test_existing_lock_and_broken_symlink_are_never_removed(
    repository: Path, pbf: Path
) -> None:
    parent = repository / "data/offline-regions"
    parent.mkdir(parents=True)
    lock = parent / ".marly.lock"
    lock.mkdir()
    with pytest.raises(FileExistsError):
        build_region(repository, "marly", pbf, builder=fake_components)
    assert lock.is_dir()
    (parent / "marly").symlink_to(parent / "absent")
    with pytest.raises(ValueError, match="symbolic"):
        build_region(repository, "marly", pbf, builder=fake_components)
    assert (parent / "marly").is_symlink() and lock.is_dir()


@pytest.mark.parametrize(
    "counts",
    [(0, 1, 1), (1, 0, 1), (1, 1, 0), (0, 0, 0), (1, 1, 1)],
    ids=[
        "unknown-addressed",
        "unknown-entries",
        "unknown-contents",
        "all-unknown",
        "known",
    ],
)
def test_pmtiles_counts_may_be_unknown(
    repository: Path, pbf: Path, counts: tuple[int, int, int]
) -> None:
    directory = repository / "components"
    directory.mkdir()
    fake_components(repository, load_spec(repository, "marly"), pbf, directory)
    archive = directory / "map/basemap.pmtiles"
    manifest = read_map(directory / "map/manifest.json")
    validate_pmtiles(archive, manifest)
    data = bytearray(archive.read_bytes())
    struct.pack_into("<QQQ", data, 72, *counts)
    archive.write_bytes(data)
    validate_pmtiles(archive, manifest)


def test_pmtiles_metadata_after_tiles_is_valid_but_overlap_and_overrun_are_not(
    repository: Path, pbf: Path
) -> None:
    directory = repository / "components"
    directory.mkdir()
    fake_components(repository, load_spec(repository, "marly"), pbf, directory)
    archive = directory / "map/basemap.pmtiles"
    header = bytearray(archive.read_bytes()[:127])
    struct.pack_into("<QQ", header, 24, 129, 2)  # metadata after tile data
    struct.pack_into("<QQ", header, 56, 128, 1)
    archive.write_bytes(header + b"\x00\x00{}")
    manifest = read_map(directory / "map/manifest.json")
    validate_pmtiles(archive, manifest)
    for offset in (128, 131):  # overlap with tile data, then exceed file length
        changed = bytearray(header)
        struct.pack_into("<QQ", changed, 24, offset, 2)
        archive.write_bytes(changed + b"\x00\x00{}")
        with pytest.raises(ValueError, match="PMTiles"):
            validate_pmtiles(archive, manifest)


def test_command_runner_receives_explicit_source_and_isolated_destinations(
    repository: Path, pbf: Path
) -> None:
    calls: list[tuple[Sequence[str], Mapping[str, str]]] = []

    def runner(arguments: Sequence[str], environment: Mapping[str, str]) -> None:
        calls.append((arguments, environment))
        if arguments[0] == sys.executable:
            subprocess.run(
                arguments, env=dict(environment), check=True, capture_output=True
            )

    output = repository / "staging"
    output.mkdir()
    build_components(repository, load_spec(repository, "marly"), pbf, output, runner)
    assert len(calls) == 4
    assert calls[0][0][-2:] == (str(pbf), str(output / "map"))
    assert calls[1][0][-1] == str(output / "routing")
    assert calls[1][1]["OSM_PBF"] == str(pbf)
    spec = load_spec(repository, "marly")
    for call, component in zip(calls[2:], ("pois", "nature"), strict=True):
        assert call[0] == (
            sys.executable,
            "-m",
            f"sugarglider.{component}.build",
            "--osm-pbf",
            str(pbf),
            "--output",
            str(output / component / "index.json.gz"),
            "--bounds",
            *(str(value) for value in spec.bounds),
        )
    # Real isolated tiny-fixture builds must preserve the in-process bytes.
    expected = repository / "expected"
    expected.mkdir()
    fake_components(repository, spec, pbf, expected)
    for component in ("pois", "nature"):
        assert (output / component / "index.json.gz").read_bytes() == (
            expected / component / "index.json.gz"
        ).read_bytes()


@pytest.mark.parametrize("failed_component", ["pois", "nature"])
def test_isolated_index_failure_aborts_publication_and_following_phases(
    repository: Path, pbf: Path, failed_component: str
) -> None:
    modules: list[str] = []

    def runner(arguments: Sequence[str], environment: Mapping[str, str]) -> None:
        if arguments[0] == sys.executable:
            modules.append(arguments[2])
            if arguments[2] == f"sugarglider.{failed_component}.build":
                raise subprocess.CalledProcessError(1, arguments)

    def builder(root: Path, spec: RegionSpec, source: Path, directory: Path) -> None:
        build_components(root, spec, source, directory, runner)

    with pytest.raises(subprocess.CalledProcessError):
        build_region(repository, "marly", pbf, builder=builder)
    assert modules == (
        ["sugarglider.pois.build"]
        if failed_component == "pois"
        else ["sugarglider.pois.build", "sugarglider.nature.build"]
    )
    assert list((repository / "data/offline-regions").iterdir()) == []


def test_make_cli_ignore_and_runtime_isolation() -> None:
    makefile = (ROOT / "Makefile").read_text()
    assert 'offline_regions build --region "$(REGION)" --pbf "$(PBF_INPUT)"' in makefile
    assert "offline-region-verify:" in makefile
    assert "data/offline-regions/" in (ROOT / ".gitignore").read_text()
    map_builder = (ROOT / "scripts/build_pr36_map_pack.sh").read_text()
    routing_builder = (ROOT / "scripts/build_pr33_valhalla_pack.sh").read_text()
    assert 'BUILD_ROOT=$(dirname -- "$REQUESTED_OUTPUT")' in map_builder
    assert 'BUILD_ROOT=$(dirname -- "$ISOLATED_OUTPUT")' in routing_builder
    assert '"$BUILD_DIRECTORY/planetiler-tmp:/work/data/tmp"' in map_builder
    provenance = toolchain()
    for pin in (
        provenance.protomaps_revision,
        provenance.protomaps_archive_sha256,
        provenance.map_build_image,
    ):
        assert pin in map_builder
    assert provenance.valhalla_image in routing_builder
    worker = (ROOT / "src/sugarglider/web/static/service-worker.js").read_text()
    assert "const SHELL_CACHE = `${SHELL_CACHE_PREFIX}v47`;" in worker
    assert "offline_regions" not in worker
    for folder in (ROOT / "src/sugarglider/web", ROOT / "src/sugarglider/planning"):
        for path in folder.rglob("*.py"):
            assert "offline_regions" not in path.read_text()
    result = subprocess.run(
        (
            sys.executable,
            "-m",
            "sugarglider.offline_regions",
            "build",
            "--region",
            "marly",
        ),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0 and "explicit --pbf" in result.stderr
    ignored = subprocess.run(
        ("git", "check-ignore", "data/offline-regions/marly/manifest.json"),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "data/offline-regions/marly/manifest.json" in ignored.stdout
    assert toolchain().pipeline_version == 1


@pytest.mark.parametrize(
    "value",
    [
        "http://packs.example/",
        "https://user@packs.example/",
        "https://packs.example/?token=secret",
        "https://packs.example/#private",
        "https://packs.example",
        "https://packs.example/a/../",
        "https://packs.example//",
        "https://packs.example/%2e/",
        "https://packs.example:65536/",
    ],
)
def test_static_distribution_rejects_noncanonical_hosts(value: str) -> None:
    from sugarglider.offline_regions.distribution import distribution_base_url

    with pytest.raises(ValueError):
        distribution_base_url(value)


def test_static_distribution_preserves_exact_bytes_and_is_deterministic(
    repository: Path, pbf: Path, tmp_path: Path
) -> None:
    import zipfile

    from sugarglider.offline_regions.distribution import prepare_distribution
    from sugarglider.offline_regions.unpack_distribution import unpack_distribution

    source = build_region(repository, "marly", pbf, builder=fake_components)
    manifest = verify_region(source)
    arguments = {
        "base_url": "https://packs.example/app/",
        "description": "Tiny <fixture>",
    }
    first = prepare_distribution(
        source,
        tmp_path / "distribution-one",
        base_url=arguments["base_url"],
        description=arguments["description"],
    )
    second = prepare_distribution(
        source,
        tmp_path / "distribution-two",
        base_url=arguments["base_url"],
        description=arguments["description"],
    )
    relative = f"regions/{manifest.region_id}/{manifest.build_id}"
    assert verify_region(first / "site" / relative) == manifest
    for path in source.rglob("*"):
        if path.is_file():
            assert (
                path.read_bytes()
                == (first / "site" / relative / path.relative_to(source)).read_bytes()
            )
    catalog = json.loads((first / "site/catalog.json").read_bytes())
    assert catalog["regions"][0]["manifest_url"] == (
        f"https://packs.example/app/{relative}/manifest.json"
    )
    assert catalog["regions"][0]["download_bytes"] == sum(
        file.byte_size
        for component in manifest.components.ordered
        for file in component.files
    )
    assert "Tiny &lt;fixture&gt;" in (first / "site/index.html").read_text()
    assert "OpenStreetMap contributors" in (first / "site/README.txt").read_text()
    assert (
        "https://opendatacommons.org/licenses/odbl/1-0/"
        in (first / "site/README.txt").read_text()
    )
    archive = first / "sugarglider-regions-static.zip"
    assert archive.read_bytes() == (second / archive.name).read_bytes()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            assert not member.filename.startswith("/") and ".." not in member.filename
            assert not member.filename.endswith(".pbf")
            assert (
                bundle.read(member) == (first / "site" / member.filename).read_bytes()
            )
    report = json.loads((first / "report.json").read_bytes())
    assert report["publication"] == "not published"
    assert report["archive_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    deployed = unpack_distribution(
        archive, tmp_path / "extracted-site", report["archive_sha256"]
    )
    assert verify_region(deployed / relative) == manifest
    with pytest.raises(ValueError, match="checksum"):
        unpack_distribution(archive, tmp_path / "bad-digest", "0" * 64)
    assert not (tmp_path / "bad-digest").exists()
    with pytest.raises(FileExistsError):
        prepare_distribution(
            source,
            first,
            base_url=arguments["base_url"],
            description=arguments["description"],
        )
    assert archive.read_bytes() == (second / archive.name).read_bytes()


def test_static_distribution_rejects_corruption_and_preserves_source(
    repository: Path, pbf: Path, tmp_path: Path
) -> None:
    from sugarglider.offline_regions.distribution import prepare_distribution

    source = build_region(repository, "marly", pbf, builder=fake_components)
    arguments = {"base_url": "https://packs.example/", "description": "Fixture"}
    with pytest.raises(ValueError, match="outside the source"):
        prepare_distribution(
            source,
            source / "output",
            base_url=arguments["base_url"],
            description=arguments["description"],
        )
    output = tmp_path / "corrupt-output"
    (source / "routing/valhalla_tiles.tar").write_bytes(b"invalid")
    with pytest.raises(ValueError):
        prepare_distribution(
            source,
            output,
            base_url=arguments["base_url"],
            description=arguments["description"],
        )
    assert not output.exists()
    assert (source / "routing/valhalla_tiles.tar").read_bytes() == b"invalid"


@pytest.mark.parametrize(
    "name,mode",
    [
        ("../escape", 0o100644),
        ("/absolute", 0o100644),
        (".env", 0o100644),
        ("README.txt", 0o120777),
    ],
)
def test_static_unpack_rejects_unsafe_entries_before_output(
    name: str, mode: int, tmp_path: Path
) -> None:
    import zipfile

    from sugarglider.offline_regions.unpack_distribution import unpack_distribution

    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        member = zipfile.ZipInfo(name)
        member.external_attr = mode << 16
        bundle.writestr(member, b"outside")
    output = tmp_path / "unpacked"
    with pytest.raises(ValueError):
        unpack_distribution(
            archive, output, hashlib.sha256(archive.read_bytes()).hexdigest()
        )
    assert not output.exists()
    assert not (tmp_path / "escape").exists()


def test_static_update_retains_previous_immutable_downloads(
    repository: Path, pbf: Path, tmp_path: Path
) -> None:
    from sugarglider.offline_regions.distribution import prepare_distribution
    from sugarglider.offline_regions.models import build_identity

    source = build_region(repository, "marly", pbf, builder=fake_components)
    current = verify_region(source)
    previous = tmp_path / "previous-region"
    shutil.copytree(source, previous)
    value = json.loads((previous / "manifest.json").read_bytes())
    value["display_name"] = "Previous offering"
    del value["build_id"]
    value["build_id"] = build_identity(value)
    (previous / "manifest.json").write_bytes(canonical_json(value))
    old = verify_region(previous)
    output = prepare_distribution(
        source,
        tmp_path / "retained-site",
        base_url="https://packs.example/",
        description="Current offering",
        retain_directory=previous,
    )
    for version in (current, old):
        assert (
            verify_region(
                output / "site/regions" / version.region_id / version.build_id
            )
            == version
        )
    catalog = json.loads((output / "site/catalog.json").read_bytes())
    assert [row["build_id"] for row in catalog["regions"]] == [current.build_id]
    assert json.loads((output / "report.json").read_bytes())["retained_build_ids"] == [
        old.build_id
    ]
