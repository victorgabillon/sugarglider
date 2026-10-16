"""Explicit offline terrain acquisition/conversion commands; never publishes data."""

import argparse
from pathlib import Path

from sugarglider.offline_regions.terrain_source import TerrainSources, acquire_sources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("acquire", "convert", "rebuild"))
    parser.add_argument("--pins", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--previous-region", type=Path)
    parser.add_argument("--pbf", type=Path)
    parser.add_argument("--elevation-pins", type=Path)
    args = parser.parse_args()
    if args.command == "rebuild":
        from sugarglider.offline_regions.terrain_rebuild import rebuild_terrain_region

        if (
            args.previous_region is None
            or args.pbf is None
            or args.elevation_pins is None
        ):
            parser.error(
                "rebuild requires explicit prior region, PBF and derived elevation pins"
            )
        rebuild_terrain_region(
            Path(__file__).resolve().parents[3],
            args.previous_region,
            args.pbf,
            args.elevation_pins,
            args.output,
        )
        return
    if args.pins is None:
        parser.error("acquire/convert requires --pins")
    if args.pins.stat().st_size > 32_768:
        parser.error("source pins exceed limit")
    pins = TerrainSources.model_validate_json(args.pins.read_bytes())
    if args.command == "acquire":
        acquire_sources(pins, args.output)
    else:
        from sugarglider.offline_regions.terrain_conversion import convert_sources

        if args.source is None:
            parser.error("conversion requires explicit --source")
        convert_sources(pins, args.source, args.output)


if __name__ == "__main__":
    main()
