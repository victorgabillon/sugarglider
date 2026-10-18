"""Explicit offline terrain acquisition/conversion commands; never publishes data."""

import argparse
from pathlib import Path

from pydantic import TypeAdapter

from sugarglider.offline_regions.terrain_source import (
    IGNSources,
    TerrainSources,
    acquire_sources,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("acquire", "prepare", "convert", "rebuild"))
    parser.add_argument("--pins", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--previous-region", type=Path)
    parser.add_argument("--pbf", type=Path)
    parser.add_argument("--elevation-pins", type=Path)
    parser.add_argument("--bounds", type=float, nargs=4, metavar=("W", "S", "E", "N"))
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
        parser.error("acquire/prepare/convert requires --pins")
    if args.pins.stat().st_size > 32_768:
        parser.error("source pins exceed limit")
    pins: TerrainSources | IGNSources = TypeAdapter(
        TerrainSources | IGNSources
    ).validate_json(args.pins.read_bytes())
    if args.command == "acquire":
        acquire_sources(pins, args.output)
    elif args.command == "prepare":
        from sugarglider.offline_regions.terrain_ign import prepare_ign

        if not isinstance(pins, IGNSources) or args.source is None:
            parser.error("prepare requires IGN pins and an explicit original source")
        prepare_ign(pins, args.source, args.output)
    else:
        from sugarglider.offline_regions.terrain_conversion import convert_sources

        if args.source is None:
            parser.error("conversion requires explicit --source")
        bounds = (
            None
            if args.bounds is None
            else (args.bounds[0], args.bounds[1], args.bounds[2], args.bounds[3])
        )
        convert_sources(pins, args.source, args.output, bounds)


if __name__ == "__main__":
    main()
