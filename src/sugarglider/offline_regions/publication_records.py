"""Bounded detached records; a record's presence never confers authority."""

import hashlib
from pathlib import Path


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def bounded_record(path: Path, maximum: int = 32_768) -> bytes:
    if (
        path.is_symlink()
        or path.resolve() != path.absolute()
        or not path.is_file()
        or not 0 < path.stat().st_size <= maximum
    ):
        raise ValueError("invalid or oversized terrain evidence record")
    with path.open("rb") as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise ValueError("terrain evidence record grew beyond limit")
    return value
