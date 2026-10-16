"""Fresh DEM-enriched graph, reusing verified unaffected OSM components."""

import os
import shutil
from pathlib import Path

from sugarglider.offline_regions.build import (
    make_manifest,
    run_command,
    source_identity,
    toolchain,
)
from sugarglider.offline_regions.elevation_component import build_elevation
from sugarglider.offline_regions.models import canonical_json
from sugarglider.offline_regions.validation import load_spec, verify_region


def rebuild_terrain_region(
    root: Path, previous: Path, pbf: Path, pins: Path, output: Path
) -> Path:
    """Never update an old directory; fail leaves uncommitted new staging only.

    Map/POIs/Nature retain their exact immutable verified bytes. The graph is
    always rebuilt from the exact same pinned PBF and the new verified HGT.
    """
    old = verify_region(previous)
    spec = load_spec(root, old.region_id)
    identity = source_identity(pbf, spec, old.source.source_url)
    if identity != old.source or spec.bounds != old.bounds:
        raise ValueError("OSM source/spec differ from immutable prior region")
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    output.mkdir()
    for name in ("map", "pois", "nature"):
        shutil.copytree(previous / name, output / name)
    build_elevation(
        output / "elevation", spec.elevation.component_id, spec.bounds, pins
    )
    environment = dict(os.environ)
    environment["OSM_PBF"] = str(pbf.absolute())
    environment["SUGARGLIDER_DEM_DIR"] = str(output.absolute() / "elevation/skadi")
    run_command(
        (
            "sh",
            str(root / "scripts/build_pr33_valhalla_pack.sh"),
            spec.routing.pack_id,
            *(str(v) for v in spec.bounds),
            str(output.absolute() / "routing"),
        ),
        environment,
    )
    if source_identity(pbf, spec, old.source.source_url) != identity:
        raise ValueError("OSM source changed during rebuild")
    manifest = make_manifest(output, spec, identity, toolchain())
    if (
        manifest.components.routing.files[1].sha256
        == old.components.routing.files[1].sha256
    ):
        raise ValueError(
            "terrain rebuild produced identical graph; investigate enrichment"
        )
    (output / "manifest.json").write_bytes(
        canonical_json(manifest.model_dump(mode="json"))
    )
    verify_region(output)
    record = {
        "schema_version": 1,
        "region_id": manifest.region_id,
        "private_build_id": manifest.build_id,
        "graph_sha256": manifest.components.routing.files[1].sha256,
        "source_pbf_sha256": manifest.source.sha256,
        "valhalla_image": manifest.tools.valhalla_image,
        "enrichment": "valhalla_build_tiles; additional_data.elevation; network=none",
        "dem_tiles": [
            f.model_dump(mode="json") for f in manifest.components.elevation.files[1:]
        ],
        "command": [
            "sh",
            "scripts/build_pr33_valhalla_pack.sh",
            spec.routing.pack_id,
            *(str(v) for v in spec.bounds),
            "NEW_OUTPUT_DIRECTORY",
        ],
    }
    (output.parent / (output.name + "-graph-build.json")).write_bytes(
        canonical_json(record)
    )
    if verify_region(previous) != old:
        raise ValueError("immutable old region changed")
    return output
