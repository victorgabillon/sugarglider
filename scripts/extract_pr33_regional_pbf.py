#!/usr/bin/env python3
"""Create one bounded OSM routing extract from a local regional PBF."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import osmium


@dataclass(frozen=True)
class Bounds:
    west: float
    south: float
    east: float
    north: float

    def is_valid(self) -> bool:
        return (
            all(math.isfinite(value) for value in vars(self).values())
            and -180 <= self.west < self.east <= 180
            and -90 <= self.south < self.north <= 90
        )


class RegionalExtractHandler(osmium.SimpleHandler):
    """Select graph ways intersecting the configured development bounds."""

    def __init__(
        self,
        writer: osmium.BackReferenceWriter,
        bounds: Bounds,
    ) -> None:
        super().__init__()
        self._writer = writer
        self._bounds = bounds
        self._way_ids: set[int] = set()

    def way(self, way: Any) -> None:
        bounds = self._bounds
        if any(
            node.location.valid()
            and bounds.west <= node.location.lon <= bounds.east
            and bounds.south <= node.location.lat <= bounds.north
            for node in way.nodes
        ):
            self._way_ids.add(int(way.id))
            self._writer.add_way(way)

    def relation(self, relation: Any) -> None:
        if relation.tags.get("type") != "restriction":
            return
        if any(
            member.type == "w" and int(member.ref) in self._way_ids
            for member in relation.members
        ):
            self._writer.add_relation(relation)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--west", type=float, required=True)
    parser.add_argument("--south", type=float, required=True)
    parser.add_argument("--east", type=float, required=True)
    parser.add_argument("--north", type=float, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path: Path = args.input
    output_path: Path = args.output
    bounds = Bounds(args.west, args.south, args.east, args.north)
    if not bounds.is_valid():
        raise SystemExit("Invalid regional bounds")
    if not input_path.is_file():
        raise SystemExit(f"OSM input does not exist: {input_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with osmium.BackReferenceWriter(
        output_path,
        input_path,
        overwrite=True,
        remove_tags=False,
        relation_depth=1,
    ) as writer:
        RegionalExtractHandler(writer, bounds).apply_file(input_path, locations=True)


if __name__ == "__main__":
    main()
