"""Sequential, fail-closed regional build orchestration above existing builders."""

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Protocol

import osmium

from sugarglider.offline_regions.elevation_component import build_elevation
from sugarglider.offline_regions.elevation_layout import elevation_paths
from sugarglider.offline_regions.map_manifest import file_sha256
from sugarglider.offline_regions.models import (
    Component,
    Components,
    FileDescriptor,
    FileFormat,
    RegionalManifest,
    RegionSpec,
    SourceIdentity,
    Toolchain,
    build_identity,
    canonical_json,
    contained_path,
)
from sugarglider.offline_regions.validation import load_spec, verify_region
from sugarglider.osm_build_bounds import require_header_coverage


class CommandRunner(Protocol):
    def __call__(
        self, arguments: Sequence[str], environment: Mapping[str, str]
    ) -> None: ...


def run_command(arguments: Sequence[str], environment: Mapping[str, str]) -> None:
    subprocess.run(arguments, env=dict(environment), check=True)


def source_identity(source: Path, spec: RegionSpec, url: str | None) -> SourceIdentity:
    if not source.is_file() or not source.name.endswith(".osm.pbf"):
        raise ValueError("an explicit existing .osm.pbf source is required")
    header = osmium.FileProcessor(source).header.box()
    bounds = require_header_coverage(header, spec.bounds)
    return SourceIdentity(
        basename=source.name,
        byte_size=source.stat().st_size,
        sha256=file_sha256(source),
        header_bounds=bounds,
        source_url=url,
    )


def toolchain() -> Toolchain:
    return Toolchain(
        python_version=platform.python_version(),
        osmium_version=version("osmium"),
        shapely_version=version("shapely"),
    )


def build_components(
    root: Path,
    spec: RegionSpec,
    source: Path,
    directory: Path,
    runner: CommandRunner = run_command,
    *,
    elevation_sources: Path | None = None,
    partition_nature: bool = False,
) -> None:
    if elevation_sources is None:
        raise ValueError("V2 build requires explicit verified elevation source pins")
    build_elevation(
        directory / "elevation",
        spec.elevation.component_id,
        spec.bounds,
        elevation_sources,
    )
    environment = dict(os.environ)
    # Never allow the legacy routing script to choose its implicit source.
    environment["OSM_PBF"] = str(source)
    environment["SUGARGLIDER_DEM_DIR"] = str(directory / "elevation/skadi")
    runner(
        (
            "sh",
            str(root / "scripts/build_pr36_map_pack.sh"),
            spec.region_id,
            str(source),
            str(directory / "map"),
        ),
        environment,
    )
    runner(
        (
            "sh",
            str(root / "scripts/build_pr33_valhalla_pack.sh"),
            spec.routing.pack_id,
            *(str(value) for value in spec.bounds),
            str(directory / "routing"),
        ),
        environment,
    )
    # OSM parsing and geometry construction retain large native/Python heaps.
    # A fresh process per index releases those heaps before the next phase and
    # final verification, while inheriting the caller's resource limits.
    for component in ("pois", "nature"):
        index_directory = directory / (
            "nature-source" if component == "nature" and partition_nature else component
        )
        runner(
            (
                sys.executable,
                "-m",
                f"sugarglider.{component}.build",
                "--osm-pbf",
                str(source),
                "--output",
                str(index_directory / "index.json.gz"),
                "--bounds",
                *(str(value) for value in spec.bounds),
            ),
            environment,
        )
        if component == "nature" and partition_nature:
            runner(
                (
                    sys.executable,
                    "-m",
                    "sugarglider.offline_regions.nature_partitions",
                    "--source",
                    str(index_directory / "index.json.gz"),
                    "--output",
                    str(directory / "nature"),
                    "--source-sha256",
                    file_sha256(source),
                ),
                environment,
            )
            # Only this fresh build's temporary monolithic index is removed.
            shutil.rmtree(index_directory)


type ComponentBuilder = Callable[[Path, RegionSpec, Path, Path], None]


def describe_components(directory: Path, spec: RegionSpec) -> Components:
    # Fixed schema descriptors, never paths supplied by command output.
    layouts: tuple[tuple[tuple[str, FileFormat], ...], ...] = (
        (
            ("map/manifest.json", "map-manifest-v1"),
            ("map/basemap.pmtiles", "pmtiles-v3-mvt"),
        ),
        (
            ("routing/manifest.json", "routing-manifest-v2"),
            ("routing/valhalla_tiles.tar", "valhalla-3.9.1-elevation-tar"),
        ),
        (("pois/index.json.gz", "poi-index-v2-gzip-json"),),
        (("nature/index.json.gz", "nature-index-v1-gzip-json"),),
        (
            ("elevation/manifest.json", "elevation-manifest-v1"),
            *((path, "skadi-hgt-gzip-v1") for path in elevation_paths(spec.bounds)),
        ),
    )
    if (directory / "nature/partitions.json").is_file():
        from sugarglider.offline_regions.nature_partitions import NaturePartitions

        parts = NaturePartitions.model_validate_json(
            (directory / "nature/partitions.json").read_bytes()
        )
        layouts = (
            *layouts[:3],
            (
                ("nature/partitions.json", "nature-partitions-v1-json"),
                *(
                    (part.path, "nature-index-v1-gzip-json")
                    for part in parts.partitions
                ),
            ),
            layouts[4],
        )
    components: list[Component] = []
    for identity, layout in zip(spec.component_ids, layouts, strict=True):
        files = tuple(
            FileDescriptor(
                path=path,
                format=format_name,
                byte_size=contained_path(directory, path).stat().st_size,
                sha256=file_sha256(contained_path(directory, path)),
            )
            for path, format_name in layout
        )
        components.append(Component(component_id=identity, files=files))
    return Components(
        map=components[0],
        routing=components[1],
        pois=components[2],
        nature=components[3],
        elevation=components[4],
    )


def make_manifest(
    directory: Path,
    spec: RegionSpec,
    source: SourceIdentity,
    tools: Toolchain,
) -> RegionalManifest:
    payload = {
        "schema_version": 2,
        "publication_allowed": False,
        "region_id": spec.region_id,
        "display_name": spec.display_name,
        "bounds": spec.bounds,
        "source": source.model_dump(mode="json"),
        "tools": tools.model_dump(mode="json"),
        "components": describe_components(directory, spec).model_dump(mode="json"),
    }
    payload["build_id"] = build_identity(payload)
    return RegionalManifest.model_validate_json(canonical_json(payload))


def build_region(
    root: Path,
    region_id: str,
    source: Path,
    *,
    source_url: str | None = None,
    builder: ComponentBuilder = build_components,
    elevation_sources: Path | None = None,
    partition_nature: bool = False,
) -> Path:
    """Publish a new regional directory only after every component verifies.

    The configured coverage and source identity bind all component builders to
    one input. A private staging directory contains partial work, and the final
    rename exposes only a verified manifest/component set. Existing outputs
    are refused so a failed rebuild cannot damage a distributable region.
    """
    spec = load_spec(root, region_id)
    output_root = contained_path(root, "data/offline-regions")
    output = contained_path(root, f"data/offline-regions/{spec.region_id}")
    if output.exists():
        raise FileExistsError(f"regional output already exists: {output}")
    source = source.resolve(strict=True)
    identity = source_identity(source, spec, source_url)
    output_root.mkdir(parents=True, exist_ok=True)
    # Exclusive cooperative build lock; no replacement or removal of old output.
    lock = output_root / f".{spec.region_id}.lock"
    lock.mkdir()
    try:
        if output.exists() or output.is_symlink():
            raise FileExistsError(f"regional output already exists: {output}")
        with tempfile.TemporaryDirectory(
            prefix=f".{spec.region_id}.build-", dir=output_root
        ) as temporary:
            staging = Path(temporary) / "region"
            staging.mkdir()
            if builder is build_components:
                build_components(
                    root,
                    spec,
                    source,
                    staging,
                    elevation_sources=elevation_sources,
                    partition_nature=partition_nature,
                )
            else:
                builder(root, spec, source, staging)
            if source_identity(source, spec, source_url) != identity:
                raise ValueError("source changed during build")
            manifest = make_manifest(staging, spec, identity, toolchain())
            (staging / "manifest.json").write_bytes(
                canonical_json(manifest.model_dump(mode="json"))
            )
            verify_region(staging)
            if output.exists() or output.is_symlink():
                raise FileExistsError(f"regional output already exists: {output}")
            staging.rename(output)
    finally:
        lock.rmdir()
    return output
