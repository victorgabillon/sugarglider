#!/usr/bin/env python3
"""Write the minimal deterministic PR33 routing-pack manifest."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

PACK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pack-id", required=True)
    parser.add_argument("--west", type=float, required=True)
    parser.add_argument("--south", type=float, required=True)
    parser.add_argument("--east", type=float, required=True)
    parser.add_argument("--north", type=float, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not PACK_ID_PATTERN.fullmatch(args.pack_id):
        raise SystemExit("Invalid routing-pack ID")
    coordinates = (args.west, args.south, args.east, args.north)
    if not (
        all(math.isfinite(value) for value in coordinates)
        and -180 <= args.west < args.east <= 180
        and -90 <= args.south < args.north <= 90
    ):
        raise SystemExit("Invalid routing-pack bounds")
    manifest = {
        "schema_version": 1,
        "pack_id": args.pack_id,
        "engine": "valhalla",
        "engine_version": "3.6.3",
        "bounds": {
            "west": args.west,
            "south": args.south,
            "east": args.east,
            "north": args.north,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
