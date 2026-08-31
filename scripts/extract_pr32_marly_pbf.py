#!/usr/bin/env python3
"""Create the bounded PR32 OSM routing extract from the local regional PBF."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import osmium

WEST = 2.00
SOUTH = 48.80
EAST = 2.16
NORTH = 48.94


class MarlyExtractHandler(osmium.SimpleHandler):
    """Select graph ways intersecting the buffered PR32 development bounds."""

    def __init__(self, writer: osmium.BackReferenceWriter) -> None:
        super().__init__()
        self._writer = writer
        self._way_ids: set[int] = set()

    def way(self, way: Any) -> None:
        if any(
            node.location.valid()
            and WEST <= node.location.lon <= EAST
            and SOUTH <= node.location.lat <= NORTH
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path: Path = args.input
    output_path: Path = args.output
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
        handler = MarlyExtractHandler(writer)
        handler.apply_file(input_path, locations=True)


if __name__ == "__main__":
    main()
