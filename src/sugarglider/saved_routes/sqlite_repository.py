"""Standard-library SQLite adapter for saved-route persistence."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sugarglider.saved_routes.repository import (
    SavedRouteRecord,
    SavedRouteRepositoryError,
    SavedRouteSlugCollisionError,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_routes (
    id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL,
    public_slug TEXT NOT NULL UNIQUE,
    owner_token_hash BLOB NOT NULL,
    source_request_json TEXT NOT NULL,
    candidate_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    expires_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saved_routes_public_slug
    ON saved_routes(public_slug);
CREATE INDEX IF NOT EXISTS idx_saved_routes_expires_at_utc
    ON saved_routes(expires_at_utc);
"""


class SQLiteSavedRouteRepository:
    """Use one configured short-lived SQLite connection per operation."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        try:
            self._database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with self._connection() as connection:
                connection.executescript(_SCHEMA)
        except (OSError, sqlite3.Error) as exc:
            raise SavedRouteRepositoryError(
                "saved-route initialization failed"
            ) from exc

    def create(self, record: SavedRouteRecord) -> None:
        try:
            with self._connection() as connection, connection:
                connection.execute(
                    """
                    INSERT INTO saved_routes (
                        id, schema_version, public_slug, owner_token_hash,
                        source_request_json, candidate_json, created_at_utc,
                        expires_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.schema_version,
                        record.public_slug,
                        record.owner_token_hash,
                        record.source_request_json,
                        record.candidate_json,
                        _format_timestamp(record.created_at_utc),
                        _format_timestamp(record.expires_at_utc),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if self.get_by_slug(record.public_slug) is not None:
                raise SavedRouteSlugCollisionError from exc
            raise SavedRouteRepositoryError("saved-route insert failed") from exc
        except sqlite3.Error as exc:
            raise SavedRouteRepositoryError("saved-route insert failed") from exc

    def get_by_slug(self, slug: str) -> SavedRouteRecord | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    """
                    SELECT id, schema_version, public_slug, owner_token_hash,
                           source_request_json, candidate_json, created_at_utc,
                           expires_at_utc
                    FROM saved_routes
                    WHERE public_slug = ?
                    """,
                    (slug,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise SavedRouteRepositoryError("saved-route lookup failed") from exc
        return None if row is None else _record(row)

    def delete_by_id(self, route_id: str) -> bool:
        try:
            with self._connection() as connection, connection:
                cursor = connection.execute(
                    "DELETE FROM saved_routes WHERE id = ?",
                    (route_id,),
                )
                return cursor.rowcount == 1
        except sqlite3.Error as exc:
            raise SavedRouteRepositoryError("saved-route delete failed") from exc

    def purge_expired(self, now: datetime) -> int:
        try:
            with self._connection() as connection, connection:
                cursor = connection.execute(
                    "DELETE FROM saved_routes WHERE expires_at_utc <= ?",
                    (_format_timestamp(now),),
                )
                return max(0, cursor.rowcount)
        except sqlite3.Error as exc:
            raise SavedRouteRepositoryError("saved-route expiry purge failed") from exc

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self._database_path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
        finally:
            if connection is not None:
                connection.close()


def _record(row: sqlite3.Row) -> SavedRouteRecord:
    try:
        return SavedRouteRecord(
            id=str(row["id"]),
            schema_version=int(row["schema_version"]),
            public_slug=str(row["public_slug"]),
            owner_token_hash=bytes(row["owner_token_hash"]),
            source_request_json=str(row["source_request_json"]),
            candidate_json=str(row["candidate_json"]),
            created_at_utc=_parse_timestamp(str(row["created_at_utc"])),
            expires_at_utc=_parse_timestamp(str(row["expires_at_utc"])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SavedRouteRepositoryError("saved-route record is invalid") from exc


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SavedRouteRepositoryError("saved-route timestamp is naive")
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("saved-route timestamp is naive")
    return parsed.astimezone(UTC)
