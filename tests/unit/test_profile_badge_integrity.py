"""Decode the badges' PNG framing and image stream independently of pinned hashes."""

import struct
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BADGES = ("blue", "forest", "orange", "tomato", "mask", "olivier")
DIRECTORIES = (
    ROOT / "assets/brand/profile-badges",
    ROOT / "src/sugarglider/web/static/brand/profile-badges",
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _validate_badge_png(data: bytes) -> None:
    assert data.startswith(PNG_SIGNATURE), "Invalid PNG signature"
    offset = len(PNG_SIGNATURE)
    chunks: list[bytes] = []
    image_parts: list[bytes] = []
    channels = 0
    while offset < len(data):
        assert offset + 12 <= len(data), "Incomplete chunk header/CRC"
        length, kind = struct.unpack_from(">I4s", data, offset)
        end = offset + length + 12
        assert end <= len(data), "Chunk exceeds PNG bounds"
        payload = data[offset + 8 : end - 4]
        stored_crc = struct.unpack_from(">I", data, end - 4)[0]
        assert zlib.crc32(kind + payload) == stored_crc, "PNG chunk CRC mismatch"
        if not chunks:
            assert kind == b"IHDR" and length == 13, "Missing initial IHDR"
            width, height, depth, color, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", payload)
            )
            assert (width, height) == (512, 512), "Unexpected badge canvas"
            assert depth == 8 and color in (0, 2, 3, 4, 6), "Unsupported pixels"
            assert (compression, filtering, interlace) == (0, 0, 0)
            channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
        else:
            assert kind != b"IHDR", "Duplicate IHDR"
        if kind == b"IDAT":
            assert not image_parts or chunks[-1] == b"IDAT", "Nonconsecutive IDAT"
            image_parts.append(payload)
        chunks.append(kind)
        offset = end
        if kind == b"IEND":
            assert length == 0 and offset == len(data), "Invalid PNG ending"
            break
    assert chunks and chunks[-1] == b"IEND", "Missing complete IEND"
    assert image_parts, "Missing IDAT"
    row_size = 1 + 512 * channels
    expected_size = 512 * row_size
    decoder = zlib.decompressobj()
    # zlib verifies Adler-32; EOF rejects truncated streams even with fresh CRCs.
    raw = decoder.decompress(b"".join(image_parts), expected_size + 1)
    assert decoder.eof, "Incomplete or oversized image stream"
    assert not decoder.unused_data and not decoder.unconsumed_tail
    assert len(raw) == expected_size, "Incorrect decompressed image size"
    assert all(raw[row] <= 4 for row in range(0, len(raw), row_size)), (
        "Invalid PNG scanline filter"
    )


@pytest.mark.parametrize("directory", DIRECTORIES, ids=("canonical", "runtime"))
@pytest.mark.parametrize("badge", BADGES)
def test_profile_badge_png_integrity(directory: Path, badge: str) -> None:
    _validate_badge_png((directory / f"{badge}.png").read_bytes())


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload))
    )


@pytest.mark.parametrize(
    "damage",
    ("bounds", "crc", "checksum", "truncated_stream", "image_size", "filter", "iend"),
)
def test_integrity_check_rejects_damaged_pngs(damage: str) -> None:
    raw = bytes(512 * (1 + 512 * 4))
    if damage == "image_size":
        raw = raw[:-1]
    if damage == "filter":
        raw = b"\x05" + raw[1:]
    compressed = zlib.compress(raw)
    if damage == "checksum":
        compressed = compressed[:-1] + bytes((compressed[-1] ^ 1,))
    if damage == "truncated_stream":
        compressed = compressed[:-4]
    idat = _chunk(b"IDAT", compressed)
    if damage == "bounds":
        idat = struct.pack(">I", len(compressed) + 1866) + idat[4:]
    if damage == "crc":
        idat = idat[:-1] + bytes((idat[-1] ^ 1,))
    data = (
        PNG_SIGNATURE
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", 512, 512, 8, 6, 0, 0, 0))
        + idat
        + (b"" if damage == "iend" else _chunk(b"IEND", b""))
    )
    with pytest.raises((AssertionError, zlib.error)):
        _validate_badge_png(data)
