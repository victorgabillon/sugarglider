"""Allowlisted SQLite backups: no live positions or replay payloads are copied."""

import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sugarglider.outings.sqlite_repository import SQLiteOutingRepository
from sugarglider.saved_routes.sqlite_repository import SQLiteSavedRouteRepository
from sugarglider.social_server.settings import SocialSettings

_FILES = ("saved-routes.sqlite3", "outings.sqlite3")


class BackupError(Exception):
    """A backup cannot be created or verified; no private error detail is public."""


def create_backup(data_directory: Path, destination: Path) -> Path:
    """Publish a complete pair; each database uses its own consistent read view."""
    data_directory = data_directory.resolve()
    destination = destination.resolve()
    if data_directory == destination or destination.is_relative_to(data_directory):
        raise BackupError("backups must be outside the live data directory")
    now = datetime.now(UTC)
    identity = f"sugarglider-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    temporary = destination / f".{identity}.partial"
    final = destination / identity
    try:
        destination.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary.mkdir(mode=0o700)
        SQLiteSavedRouteRepository(temporary / _FILES[0]).initialize()
        SQLiteOutingRepository(temporary / _FILES[1]).initialize()
        for name in _FILES:
            _copy_public_tables(data_directory / name, temporary / name, now)
        manifest = {
            "schema_version": 1,
            "created_at_utc": now.isoformat(),
            "live_positions_included": False,
            "live_events_included": False,
            "files": {
                name: {
                    "sha256": _sha256(temporary / name),
                    "size_bytes": (temporary / name).stat().st_size,
                }
                for name in _FILES
            },
        }
        manifest_path = temporary / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        for path in temporary.iterdir():
            path.chmod(0o600)
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
        verify_backup(temporary)
        _fsync_directory(temporary)
        temporary.rename(final)
        _fsync_directory(destination)
        return final
    except Exception as exc:
        if temporary.is_dir():
            shutil.rmtree(temporary)
        raise BackupError("backup failed") from exc


def _copy_public_tables(source: Path, target: Path, now: datetime) -> None:
    tables = (
        ("saved_routes",)
        if source.name == _FILES[0]
        else ("outings", "outing_participants")
    )
    cutoff = now.isoformat().replace("+00:00", "Z")
    with (
        closing(sqlite3.connect(_uri(source, "ro"), uri=True)) as reader,
        closing(sqlite3.connect(target)) as writer,
    ):
        writer.execute("PRAGMA journal_mode = DELETE")
        writer.execute("PRAGMA foreign_keys = ON")
        reader.execute("BEGIN DEFERRED")
        try:
            with writer:
                for table in tables:
                    source_columns = tuple(
                        row[1] for row in reader.execute(f"PRAGMA table_info({table})")
                    )
                    target_columns = tuple(
                        row[1] for row in writer.execute(f"PRAGMA table_info({table})")
                    )
                    if source_columns != target_columns or not source_columns:
                        raise BackupError("unsupported database schema")
                    condition = (
                        "outing_id IN (SELECT id FROM outings WHERE expires_at_utc > ?)"
                        if table == "outing_participants"
                        else "expires_at_utc > ?"
                    )
                    rows = reader.execute(
                        f"SELECT * FROM {table} WHERE {condition}", (cutoff,)
                    )
                    placeholders = ",".join("?" for _ in source_columns)
                    while batch := rows.fetchmany(1):
                        writer.executemany(
                            f"INSERT INTO {table} VALUES ({placeholders})", batch
                        )
        finally:
            reader.rollback()


def verify_backup(directory: Path) -> None:
    """Validate hashes, SQLite consistency and absent live data before restore."""
    try:
        if directory.is_symlink() or set(path.name for path in directory.iterdir()) != {
            *_FILES,
            "manifest.json",
        }:
            raise BackupError("unexpected backup files")
        manifest_path = directory / "manifest.json"
        if manifest_path.is_symlink() or manifest_path.stat().st_size > 8192:
            raise BackupError("invalid backup manifest")
        manifest = json.loads(manifest_path.read_text())
        if (
            manifest["schema_version"] != 1
            or manifest["live_positions_included"] is not False
            or manifest["live_events_included"] is not False
            or set(manifest["files"]) != set(_FILES)
        ):
            raise BackupError("invalid backup manifest")
        for name in _FILES:
            path = directory / name
            metadata = manifest["files"][name]
            if (
                path.is_symlink()
                or path.stat().st_size != metadata["size_bytes"]
                or _sha256(path) != metadata["sha256"]
            ):
                raise BackupError("backup checksum mismatch")
            with closing(
                sqlite3.connect(_uri(path.resolve(), "ro"), uri=True)
            ) as connection:
                if (
                    connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]
                    or connection.execute("PRAGMA foreign_key_check").fetchall()
                ):
                    raise BackupError("backup database invalid")
                if name == "outings.sqlite3":
                    for table in ("outing_live_positions", "outing_live_events"):
                        if connection.execute(
                            f"SELECT 1 FROM {table} LIMIT 1"
                        ).fetchone():
                            raise BackupError("live data in backup")
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        raise BackupError("backup verification failed") from exc


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prune_backups(directory: Path, *, retain_days: int = 7) -> int:
    """Remove only verified, completed backups with our exact generated names."""
    if not 1 <= retain_days <= 7 or directory.is_symlink():
        raise BackupError("invalid backup retention")
    cutoff = datetime.now(UTC) - timedelta(days=retain_days)
    removed = 0
    try:
        for path in sorted(directory.iterdir()):
            match = re.fullmatch(r"sugarglider-(\d{8}T\d{6}Z)-[0-9a-f]{8}", path.name)
            if match is None or path.is_symlink() or not path.is_dir():
                continue
            created = datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            if created >= cutoff:
                continue
            verify_backup(path)
            shutil.rmtree(path)
            removed += 1
        _fsync_directory(directory)
        return removed
    except (OSError, ValueError) as exc:
        raise BackupError("backup retention failed") from exc


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def storage_ready(settings: SocialSettings) -> bool:
    """Probe existing tables and write locks without creating missing databases."""
    try:
        if (
            shutil.disk_usage(settings.data_directory).free
            < settings.minimum_free_bytes
        ):
            return False
        for name, table in (
            ("saved-routes.sqlite3", "saved_routes"),
            ("outings.sqlite3", "outings"),
        ):
            path = settings.data_directory / name
            with closing(
                sqlite3.connect(_uri(path, "rw"), uri=True, timeout=1)
            ) as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
                finally:
                    connection.rollback()
        return True
    except (OSError, sqlite3.Error):
        return False


def _uri(path: Path, mode: str) -> str:
    return f"{path.as_uri()}?mode={mode}"
