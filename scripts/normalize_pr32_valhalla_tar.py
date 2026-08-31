#!/usr/bin/env python3
"""Normalize TAR metadata in place without changing Valhalla tile offsets."""

from __future__ import annotations

import argparse
from pathlib import Path

BLOCK_SIZE = 512


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    return parser.parse_args()


def octal_field(value: int, length: int) -> bytes:
    encoded = f"{value:0{length - 1}o}".encode("ascii") + b"\0"
    if len(encoded) != length:
        raise ValueError("value does not fit TAR field")
    return encoded


def normalized_header(block: bytes) -> bytes:
    if len(block) != BLOCK_SIZE:
        raise ValueError("truncated TAR header")
    header = bytearray(block)
    header[108:116] = octal_field(0, 8)
    header[116:124] = octal_field(0, 8)
    header[136:148] = octal_field(0, 12)
    header[265:297] = bytes(32)
    header[297:329] = bytes(32)
    header[148:156] = b"        "
    checksum = sum(header)
    header[148:156] = f"{checksum:06o}\0 ".encode("ascii")
    return bytes(header)


def parse_size(header: bytes) -> int:
    raw = header[124:136].rstrip(b"\0 ") or b"0"
    return int(raw, 8)


def normalize_archive(path: Path) -> None:
    payload = bytearray(path.read_bytes())
    if len(payload) % BLOCK_SIZE != 0:
        raise ValueError("TAR length is not block aligned")
    offset = 0
    while offset < len(payload):
        block = bytes(payload[offset : offset + BLOCK_SIZE])
        if block == bytes(BLOCK_SIZE):
            break
        size = parse_size(block)
        if block[156:157] in {b"x", b"g"} and size > 0:
            canonical_pax_data = b"11 mtime=0\n"
            allocated_size = BLOCK_SIZE * ((size + BLOCK_SIZE - 1) // BLOCK_SIZE)
            if len(canonical_pax_data) > allocated_size:
                raise ValueError("PAX metadata exceeds its allocated TAR blocks")
            pax_header = bytearray(block)
            pax_header[124:136] = octal_field(len(canonical_pax_data), 12)
            payload[offset : offset + BLOCK_SIZE] = normalized_header(pax_header)
            data_start = offset + BLOCK_SIZE
            data_end = data_start + allocated_size
            payload[data_start:data_end] = canonical_pax_data + bytes(
                allocated_size - len(canonical_pax_data),
            )
        else:
            payload[offset : offset + BLOCK_SIZE] = normalized_header(block)
        data_blocks = (size + BLOCK_SIZE - 1) // BLOCK_SIZE
        offset += BLOCK_SIZE * (data_blocks + 1)
    path.write_bytes(payload)


def main() -> None:
    args = parse_args()
    normalize_archive(args.archive)


if __name__ == "__main__":
    main()
