"""Standard-library SQLite persistence for shared outings."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from sugarglider.outings.models import AVATAR_KEY_ADAPTER
from sugarglider.outings.repository import (
    OutingAggregateRecord,
    OutingCapacityReachedError,
    OutingParticipantRecord,
    OutingRecord,
    OutingRepositoryError,
    OutingSlugCollisionError,
    ParticipantIdCollisionError,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outings (
    id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL,
    public_slug TEXT NOT NULL UNIQUE,
    owner_token_hash BLOB NOT NULL,
    join_token_hash BLOB NOT NULL,
    title TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    expires_at_utc TEXT NOT NULL,
    max_participants INTEGER NOT NULL,
    live_event_cursor INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_outings_public_slug ON outings(public_slug);
CREATE INDEX IF NOT EXISTS idx_outings_expires_at_utc ON outings(expires_at_utc);

CREATE TABLE IF NOT EXISTS outing_participants (
    id TEXT PRIMARY KEY,
    outing_id TEXT NOT NULL,
    public_id TEXT NOT NULL,
    participant_token_hash BLOB NOT NULL,
    display_name TEXT NOT NULL,
    avatar_key TEXT NOT NULL DEFAULT 'blue',
    source_request_json TEXT NOT NULL,
    candidate_json TEXT NOT NULL,
    joined_at_utc TEXT NOT NULL,
    join_order INTEGER NOT NULL,
    FOREIGN KEY (outing_id) REFERENCES outings(id) ON DELETE CASCADE,
    UNIQUE (outing_id, public_id),
    UNIQUE (outing_id, join_order)
);
CREATE INDEX IF NOT EXISTS idx_outing_participants_outing_id
    ON outing_participants(outing_id);
CREATE INDEX IF NOT EXISTS idx_outing_participants_outing_public_id
    ON outing_participants(outing_id, public_id);
CREATE INDEX IF NOT EXISTS idx_outing_participants_outing_join_order
    ON outing_participants(outing_id, join_order);

CREATE TABLE IF NOT EXISTS outing_live_positions (
    participant_row_id TEXT PRIMARY KEY,
    outing_id TEXT NOT NULL,
    participant_public_id TEXT NOT NULL,
    client_sequence INTEGER NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    accuracy_m REAL NOT NULL,
    altitude_m REAL,
    speed_m_s REAL,
    heading_deg REAL,
    captured_at_utc TEXT NOT NULL,
    received_at_utc TEXT NOT NULL,
    FOREIGN KEY (participant_row_id)
        REFERENCES outing_participants(id) ON DELETE CASCADE,
    FOREIGN KEY (outing_id) REFERENCES outings(id) ON DELETE CASCADE,
    UNIQUE (outing_id, participant_public_id)
);
CREATE INDEX IF NOT EXISTS idx_outing_live_positions_outing_id
    ON outing_live_positions(outing_id);
CREATE INDEX IF NOT EXISTS idx_outing_live_positions_received_at_utc
    ON outing_live_positions(received_at_utc);

CREATE TABLE IF NOT EXISTS outing_live_events (
    outing_id TEXT NOT NULL,
    event_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    participant_public_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY (outing_id, event_id),
    FOREIGN KEY (outing_id) REFERENCES outings(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_outing_live_events_outing_event_id
    ON outing_live_events(outing_id, event_id);
CREATE INDEX IF NOT EXISTS idx_outing_live_events_created_at_utc
    ON outing_live_events(created_at_utc);
"""


class SQLiteOutingRepository:
    """Use one short-lived configured connection per repository operation."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        try:
            self._database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with self._connection() as connection:
                connection.executescript(_SCHEMA)
                connection.isolation_level = None
                connection.execute("BEGIN IMMEDIATE")
                try:
                    outing_columns = {
                        str(row["name"])
                        for row in connection.execute("PRAGMA table_info(outings)")
                    }
                    if "live_event_cursor" not in outing_columns:
                        connection.execute(
                            """
                            ALTER TABLE outings
                            ADD COLUMN live_event_cursor INTEGER NOT NULL DEFAULT 0
                            """
                        )
                        connection.execute(
                            """
                            UPDATE outings
                            SET live_event_cursor = COALESCE(
                                (
                                    SELECT MAX(event_id)
                                    FROM outing_live_events
                                    WHERE outing_live_events.outing_id = outings.id
                                ),
                                0
                            )
                            """
                        )
                    participant_columns = {
                        str(row["name"])
                        for row in connection.execute(
                            "PRAGMA table_info(outing_participants)"
                        )
                    }
                    if "avatar_key" not in participant_columns:
                        connection.execute(
                            """
                            ALTER TABLE outing_participants
                            ADD COLUMN avatar_key TEXT NOT NULL DEFAULT 'blue'
                            """
                        )
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
        except (OSError, sqlite3.Error) as exc:
            raise OutingRepositoryError("outing initialization failed") from exc

    def create(
        self,
        outing: OutingRecord,
        initial_participant: OutingParticipantRecord,
    ) -> None:
        if initial_participant.outing_id != outing.id:
            raise OutingRepositoryError(
                "initial participant does not belong to the new outing"
            )
        if initial_participant.join_order != 0:
            raise OutingRepositoryError("initial participant join order must be zero")
        try:
            with self._write_connection() as connection:
                self._insert_outing(connection, outing)
                self._insert_participant(connection, initial_participant)
                connection.commit()
        except sqlite3.IntegrityError as exc:
            if self.get_by_slug(outing.public_slug) is not None:
                raise OutingSlugCollisionError from exc
            raise OutingRepositoryError("outing create failed") from exc
        except sqlite3.Error as exc:
            raise OutingRepositoryError("outing create failed") from exc

    def get_by_slug(self, slug: str) -> OutingAggregateRecord | None:
        try:
            with self._connection() as connection:
                outing_row = connection.execute(
                    """
                    SELECT id, schema_version, public_slug, owner_token_hash,
                           join_token_hash, title, created_at_utc,
                           expires_at_utc, max_participants
                    FROM outings
                    WHERE public_slug = ?
                    """,
                    (slug,),
                ).fetchone()
                if outing_row is None:
                    return None
                participant_rows = connection.execute(
                    """
                    SELECT id, outing_id, public_id, participant_token_hash,
                           display_name, avatar_key, source_request_json,
                           candidate_json,
                           joined_at_utc, join_order
                    FROM outing_participants
                    WHERE outing_id = ?
                    ORDER BY join_order ASC
                    """,
                    (str(outing_row["id"]),),
                ).fetchall()
        except sqlite3.Error as exc:
            raise OutingRepositoryError("outing lookup failed") from exc
        return OutingAggregateRecord(
            outing=_outing_record(outing_row),
            participants=tuple(_participant_record(row) for row in participant_rows),
        )

    def add_participant(
        self,
        outing_id: str,
        participant: OutingParticipantRecord,
        *,
        maximum_participants: int,
    ) -> OutingParticipantRecord:
        if participant.outing_id != outing_id:
            raise OutingRepositoryError(
                "participant does not belong to the target outing"
            )
        try:
            with self._write_connection() as connection:
                count_row = connection.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM outing_participants
                    WHERE outing_id = ?
                    """,
                    (outing_id,),
                ).fetchone()
                if count_row is None or int(count_row["count"]) >= maximum_participants:
                    raise OutingCapacityReachedError
                order_row = connection.execute(
                    """
                    SELECT COALESCE(MAX(join_order), -1) + 1 AS next_join_order
                    FROM outing_participants
                    WHERE outing_id = ?
                    """,
                    (outing_id,),
                ).fetchone()
                if order_row is None:
                    raise OutingRepositoryError("outing join-order allocation failed")
                persisted = replace(
                    participant,
                    join_order=int(order_row["next_join_order"]),
                )
                self._insert_participant(connection, persisted)
                connection.commit()
                return persisted
        except OutingCapacityReachedError:
            raise
        except sqlite3.IntegrityError as exc:
            if self._participant_exists(outing_id, participant.public_id):
                raise ParticipantIdCollisionError from exc
            raise OutingRepositoryError("outing participant insert failed") from exc
        except sqlite3.Error as exc:
            raise OutingRepositoryError("outing participant insert failed") from exc

    def delete_participant(self, outing_id: str, participant_id: str) -> bool:
        try:
            with self._connection() as connection, connection:
                cursor = connection.execute(
                    """
                    DELETE FROM outing_participants
                    WHERE outing_id = ? AND public_id = ?
                    """,
                    (outing_id, participant_id),
                )
                return cursor.rowcount == 1
        except sqlite3.Error as exc:
            raise OutingRepositoryError("outing participant delete failed") from exc

    def delete_outing_by_id(self, outing_id: str) -> bool:
        try:
            with self._connection() as connection, connection:
                cursor = connection.execute(
                    "DELETE FROM outings WHERE id = ?",
                    (outing_id,),
                )
                return cursor.rowcount == 1
        except sqlite3.Error as exc:
            raise OutingRepositoryError("outing delete failed") from exc

    def purge_expired(self, now: datetime) -> int:
        try:
            with self._connection() as connection, connection:
                cursor = connection.execute(
                    "DELETE FROM outings WHERE expires_at_utc <= ?",
                    (_format_timestamp(now),),
                )
                return max(0, cursor.rowcount)
        except sqlite3.Error as exc:
            raise OutingRepositoryError("outing expiry purge failed") from exc

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self._database_path, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
        finally:
            if connection is not None:
                connection.close()

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection:
            connection.isolation_level = None
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _insert_outing(
        connection: sqlite3.Connection,
        outing: OutingRecord,
    ) -> None:
        connection.execute(
            """
            INSERT INTO outings (
                id, schema_version, public_slug, owner_token_hash,
                join_token_hash, title, created_at_utc, expires_at_utc,
                max_participants
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outing.id,
                outing.schema_version,
                outing.public_slug,
                outing.owner_token_hash,
                outing.join_token_hash,
                outing.title,
                _format_timestamp(outing.created_at_utc),
                _format_timestamp(outing.expires_at_utc),
                outing.max_participants,
            ),
        )

    @staticmethod
    def _insert_participant(
        connection: sqlite3.Connection,
        participant: OutingParticipantRecord,
    ) -> None:
        connection.execute(
            """
            INSERT INTO outing_participants (
                id, outing_id, public_id, participant_token_hash,
                display_name, avatar_key, source_request_json,
                candidate_json, joined_at_utc, join_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                participant.id,
                participant.outing_id,
                participant.public_id,
                participant.participant_token_hash,
                participant.display_name,
                participant.avatar_key,
                participant.source_request_json,
                participant.candidate_json,
                _format_timestamp(participant.joined_at_utc),
                participant.join_order,
            ),
        )

    def _participant_exists(self, outing_id: str, public_id: str) -> bool:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    """
                    SELECT 1 FROM outing_participants
                    WHERE outing_id = ? AND public_id = ?
                    """,
                    (outing_id, public_id),
                ).fetchone()
                return row is not None
        except sqlite3.Error as exc:
            raise OutingRepositoryError("outing participant lookup failed") from exc


def _outing_record(row: sqlite3.Row) -> OutingRecord:
    try:
        return OutingRecord(
            id=str(row["id"]),
            schema_version=int(row["schema_version"]),
            public_slug=str(row["public_slug"]),
            owner_token_hash=bytes(row["owner_token_hash"]),
            join_token_hash=bytes(row["join_token_hash"]),
            title=str(row["title"]),
            created_at_utc=_parse_timestamp(str(row["created_at_utc"])),
            expires_at_utc=_parse_timestamp(str(row["expires_at_utc"])),
            max_participants=int(row["max_participants"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise OutingRepositoryError("outing record is invalid") from exc


def _participant_record(row: sqlite3.Row) -> OutingParticipantRecord:
    try:
        return OutingParticipantRecord(
            id=str(row["id"]),
            outing_id=str(row["outing_id"]),
            public_id=str(row["public_id"]),
            participant_token_hash=bytes(row["participant_token_hash"]),
            display_name=str(row["display_name"]),
            avatar_key=AVATAR_KEY_ADAPTER.validate_python(row["avatar_key"]),
            source_request_json=str(row["source_request_json"]),
            candidate_json=str(row["candidate_json"]),
            joined_at_utc=_parse_timestamp(str(row["joined_at_utc"])),
            join_order=int(row["join_order"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise OutingRepositoryError("outing participant record is invalid") from exc


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise OutingRepositoryError("outing timestamp is naive")
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OutingRepositoryError("outing timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OutingRepositoryError("outing timestamp is naive")
    return parsed.astimezone(UTC)
