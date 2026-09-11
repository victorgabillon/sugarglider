"""Repository CLI: build, verify, or resolve the existing map builder's region."""

import argparse
import subprocess
import sys
from pathlib import Path

from sugarglider.offline_regions.build import build_region
from sugarglider.offline_regions.models import contained_path
from sugarglider.offline_regions.validation import load_spec, verify_region


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify", "map-config"))
    parser.add_argument("--region", required=True)
    parser.add_argument("--pbf", type=Path)
    parser.add_argument("--source-url")
    values = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    try:
        spec = load_spec(root, values.region)
        if values.command == "map-config":
            print(spec.map.pack_id)
            print(",".join(str(value) for value in spec.bounds))
            print(contained_path(root, spec.map.template))
            return 0
        if values.command == "build":
            if values.pbf is None:
                parser.error("build requires an explicit --pbf")
            directory = build_region(
                root, spec.region_id, values.pbf, source_url=values.source_url
            )
        else:
            directory = contained_path(root, f"data/offline-regions/{spec.region_id}")
        manifest = verify_region(directory)
        if (
            manifest.region_id != spec.region_id
            or manifest.bounds != spec.bounds
            or tuple(
                component.component_id for component in manifest.components.ordered
            )
            != spec.component_ids
        ):
            raise ValueError("published region differs from configured spec")
        print(f"Verified {manifest.region_id}: {directory}")
        print(f"Source SHA-256: {manifest.source.sha256}")
        for component in manifest.components.ordered:
            print(component.component_id)
            for file in component.files:
                print(f"  {file.path}: {file.byte_size} bytes sha256={file.sha256}")
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"offline-region: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
