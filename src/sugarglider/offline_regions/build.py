"""Sequential, fail-closed regional build orchestration above existing builders."""

import os
import platform
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Protocol

import osmium

from sugarglider.nature.build import build_nature_index
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
from sugarglider.pois.build import build_poi_index


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
) -> None:
    environment = dict(os.environ)
    # Never allow the legacy routing script to choose its implicit source.
    environment["OSM_PBF"] = str(source)
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
    build_poi_index(source, directory / "pois/index.json.gz", bounds=spec.bounds)
    build_nature_index(source, directory / "nature/index.json.gz", bounds=spec.bounds)


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
            ("routing/valhalla_tiles.tar", "valhalla-3.6.3-tar"),
        ),
        (("pois/index.json.gz", "poi-index-v2-gzip-json"),),
        (("nature/index.json.gz", "nature-index-v1-gzip-json"),),
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
    )


def make_manifest(
    directory: Path,
    spec: RegionSpec,
    source: SourceIdentity,
    tools: Toolchain,
) -> RegionalManifest:
    payload = {
        "schema_version": 1,
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
) -> Path:
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
