"""Standard-library SQLite persistence for durable outing live state."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from sugarglider.outings.live_models import (
    SQLITE_SIGNED_INTEGER_MAX,
    LiveEventType,
    OutingLiveEvent,
    ParticipantLivePosition,
    PositionClearReason,
)
from sugarglider.outings.live_repository import (
    OutingLiveAuthorizationContextError,
    OutingLiveEventRecord,
    OutingLiveEventWindow,
    OutingLiveMutationResult,
    OutingLivePositionRecord,
    OutingLiveRepositoryError,
    OutingLiveSequenceConflictError,
    OutingLiveSnapshotRecord,
    OutingLiveStreamStateRecord,
    OutingParticipantAuthorizationRecord,
    OutingParticipantRemovalResult,
)
from sugarglider.outings.repository import OutingRepositoryError
from sugarglider.outings.sqlite_repository import _format_timestamp, _parse_timestamp


class SQLiteOutingLiveRepository:
    """Use short-lived configured connections to the shared outing database."""

    def __init__(
        self,
        database_path: Path,
        *,
        stream_read_hook: Callable[[], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._database_path = database_path
        self._stream_read_hook = stream_read_hook
        self._clock = clock or (lambda: datetime.now(UTC))

    def get_participant_authorization(
        self, slug: str, participant_public_id: str
    ) -> OutingParticipantAuthorizationRecord | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    """
                    SELECT o.id AS outing_id, o.expires_at_utc,
                           p.id AS participant_row_id,
                           p.public_id AS participant_public_id,
                           p.participant_token_hash, p.join_order
                    FROM outings AS o
                    JOIN outing_participants AS p ON p.outing_id = o.id
                    WHERE o.public_slug = ? AND p.public_id = ?
                    """,
                    (slug, participant_public_id),
                ).fetchone()
        except (OverflowError, sqlite3.Error) as exc:
            raise OutingLiveRepositoryError("live authorization lookup failed") from exc
        return None if row is None else _authorization_record(row)

    def get_live_snapshot(self, slug: str) -> OutingLiveSnapshotRecord | None:
        state = self.get_live_stream_state(slug)
        return None if state is None else state.snapshot

    def get_live_stream_state(self, slug: str) -> OutingLiveStreamStateRecord | None:
        try:
            with self._connection() as connection:
                connection.isolation_level = None
                connection.execute("BEGIN DEFERRED")
                try:
                    outing = connection.execute(
                        """
                        SELECT id, public_slug, expires_at_utc
                        FROM outings
                        WHERE public_slug = ?
                        """,
                        (slug,),
                    ).fetchone()
                    if outing is None:
                        connection.commit()
                        return None
                    outing_id = str(outing["id"])
                    positions = connection.execute(
                        """
                        SELECT lp.participant_row_id, lp.outing_id,
                               lp.participant_public_id, lp.client_sequence,
                               lp.latitude, lp.longitude, lp.accuracy_m,
                               lp.altitude_m, lp.speed_m_s, lp.heading_deg,
                               lp.captured_at_utc, lp.received_at_utc,
                               p.join_order
                        FROM outing_live_positions AS lp
                        JOIN outing_participants AS p
                          ON p.id = lp.participant_row_id
                        WHERE lp.outing_id = ?
                        ORDER BY p.join_order ASC
                        """,
                        (outing_id,),
                    ).fetchall()
                    if self._stream_read_hook is not None:
                        self._stream_read_hook()
                    cursor_row = connection.execute(
                        """
                        SELECT live_event_cursor
                        FROM outings
                        WHERE id = ?
                        """,
                        (outing_id,),
                    ).fetchone()
                    oldest_row = connection.execute(
                        """
                        SELECT MIN(event_id) AS oldest_event_id
                        FROM outing_live_events
                        WHERE outing_id = ?
                        """,
                        (outing_id,),
                    ).fetchone()
                    if cursor_row is None or oldest_row is None:
                        raise OutingLiveRepositoryError("live stream state disappeared")
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
        except (OverflowError, sqlite3.Error) as exc:
            raise OutingLiveRepositoryError("live stream state lookup failed") from exc
        try:
            oldest = oldest_row["oldest_event_id"]
            return OutingLiveStreamStateRecord(
                snapshot=OutingLiveSnapshotRecord(
                    outing_id=str(outing["id"]),
                    public_slug=str(outing["public_slug"]),
                    outing_expires_at_utc=_parse_timestamp(
                        str(outing["expires_at_utc"])
                    ),
                    cursor=int(cursor_row["live_event_cursor"]),
                    positions=tuple(_position_record(row) for row in positions),
                ),
                oldest_retained_event_id=(None if oldest is None else int(oldest)),
            )
        except (OutingRepositoryError, TypeError, ValueError) as exc:
            raise OutingLiveRepositoryError("live stream state is invalid") from exc

    def upsert_live_position(
        self,
        authorization: OutingParticipantAuthorizationRecord,
        record: OutingLivePositionRecord,
        position: ParticipantLivePosition,
        *,
        occurred_at: datetime,
        retention_cutoff: datetime,
        maximum_event_count: int,
    ) -> OutingLiveMutationResult:
        if (
            record.participant_row_id != authorization.participant_row_id
            or record.outing_id != authorization.outing_id
            or record.participant_public_id != authorization.participant_public_id
            or position.participant_id != authorization.participant_public_id
        ):
            raise OutingLiveRepositoryError("live update context is inconsistent")
        try:
            with self._write_connection() as connection:
                self._verify_authorization_context(
                    connection,
                    authorization,
                )
                current_row = connection.execute(
                    """
                    SELECT lp.participant_row_id, lp.outing_id,
                           lp.participant_public_id, lp.client_sequence,
                           lp.latitude, lp.longitude, lp.accuracy_m,
                           lp.altitude_m, lp.speed_m_s, lp.heading_deg,
                           lp.captured_at_utc, lp.received_at_utc,
                           p.join_order
                    FROM outing_live_positions AS lp
                    JOIN outing_participants AS p
                      ON p.id = lp.participant_row_id
                    WHERE lp.participant_row_id = ?
                    """,
                    (authorization.participant_row_id,),
                ).fetchone()
                if current_row is not None:
                    current = _position_record(current_row)
                    if record.client_sequence < current.client_sequence:
                        raise OutingLiveSequenceConflictError
                    if record.client_sequence == current.client_sequence:
                        if not _same_client_payload(current, record):
                            raise OutingLiveSequenceConflictError
                        connection.commit()
                        return OutingLiveMutationResult(
                            position_record=current,
                            event=None,
                        )
                connection.execute(
                    """
                    INSERT INTO outing_live_positions (
                        participant_row_id, outing_id, participant_public_id,
                        client_sequence, latitude, longitude, accuracy_m,
                        altitude_m, speed_m_s, heading_deg, captured_at_utc,
                        received_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(participant_row_id) DO UPDATE SET
                        client_sequence = excluded.client_sequence,
                        latitude = excluded.latitude,
                        longitude = excluded.longitude,
                        accuracy_m = excluded.accuracy_m,
                        altitude_m = excluded.altitude_m,
                        speed_m_s = excluded.speed_m_s,
                        heading_deg = excluded.heading_deg,
                        captured_at_utc = excluded.captured_at_utc,
                        received_at_utc = excluded.received_at_utc
                    """,
                    _position_values(record),
                )
                event = self._append_event(
                    connection,
                    authorization.outing_id,
                    "position_updated",
                    authorization.participant_public_id,
                    occurred_at,
                    position=position,
                )
                self._prune_events(
                    connection,
                    authorization.outing_id,
                    retention_cutoff,
                    maximum_event_count,
                )
                connection.commit()
                return OutingLiveMutationResult(
                    position_record=record,
                    event=event,
                )
        except OutingLiveSequenceConflictError:
            raise
        except OutingLiveRepositoryError:
            raise
        except (OverflowError, OutingRepositoryError, sqlite3.Error) as exc:
            raise OutingLiveRepositoryError("live position update failed") from exc

    def clear_live_position(
        self,
        authorization: OutingParticipantAuthorizationRecord,
        reason: PositionClearReason,
        *,
        occurred_at: datetime,
        retention_cutoff: datetime,
        maximum_event_count: int,
    ) -> OutingLiveMutationResult:
        try:
            with self._write_connection() as connection:
                self._verify_authorization_context(
                    connection,
                    authorization,
                )
                cursor = connection.execute(
                    """
                    DELETE FROM outing_live_positions
                    WHERE participant_row_id = ?
                    """,
                    (authorization.participant_row_id,),
                )
                event = (
                    self._append_event(
                        connection,
                        authorization.outing_id,
                        "position_cleared",
                        authorization.participant_public_id,
                        occurred_at,
                        clear_reason=reason,
                    )
                    if cursor.rowcount == 1
                    else None
                )
                if event is not None:
                    self._prune_events(
                        connection,
                        authorization.outing_id,
                        retention_cutoff,
                        maximum_event_count,
                    )
                connection.commit()
                return OutingLiveMutationResult(position_record=None, event=event)
        except OutingLiveRepositoryError:
            raise
        except (OverflowError, OutingRepositoryError, sqlite3.Error) as exc:
            raise OutingLiveRepositoryError("live position clear failed") from exc

    def delete_participant_with_live_cleanup(
        self,
        authorization: OutingParticipantAuthorizationRecord,
        *,
        occurred_at: datetime,
        retention_cutoff: datetime,
        maximum_event_count: int,
    ) -> OutingParticipantRemovalResult:
        try:
            with self._write_connection() as connection:
                self._verify_authorization_context(
                    connection,
                    authorization,
                )
                connection.execute(
                    """
                    DELETE FROM outing_live_positions
                    WHERE participant_row_id = ?
                    """,
                    (authorization.participant_row_id,),
                )
                event = self._append_event(
                    connection,
                    authorization.outing_id,
                    "position_cleared",
                    authorization.participant_public_id,
                    occurred_at,
                    clear_reason="participant_left",
                )
                removed = (
                    connection.execute(
                        """
                    DELETE FROM outing_participants
                    WHERE id = ? AND outing_id = ? AND public_id = ?
                    """,
                        (
                            authorization.participant_row_id,
                            authorization.outing_id,
                            authorization.participant_public_id,
                        ),
                    ).rowcount
                    == 1
                )
                if not removed:
                    raise OutingLiveRepositoryError(
                        "live participant removal context disappeared"
                    )
                self._prune_events(
                    connection,
                    authorization.outing_id,
                    retention_cutoff,
                    maximum_event_count,
                )
                connection.commit()
                return OutingParticipantRemovalResult(removed=True, event=event)
        except OutingLiveRepositoryError:
            raise
        except (OverflowError, OutingRepositoryError, sqlite3.Error) as exc:
            raise OutingLiveRepositoryError("live participant removal failed") from exc

    def expire_live_positions(
        self,
        *,
        slug: str | None,
        expiration_cutoff: datetime,
        occurred_at: datetime,
        retention_cutoff: datetime,
        maximum_event_count: int,
    ) -> tuple[OutingLiveEvent, ...]:
        try:
            with self._write_connection() as connection:
                parameters: tuple[str, ...]
                slug_join = ""
                if slug is None:
                    parameters = (_format_timestamp(expiration_cutoff),)
                else:
                    slug_join = "AND o.public_slug = ?"
                    parameters = (_format_timestamp(expiration_cutoff), slug)
                rows = connection.execute(
                    f"""
                    SELECT lp.participant_row_id, lp.outing_id,
                           lp.participant_public_id
                    FROM outing_live_positions AS lp
                    JOIN outings AS o ON o.id = lp.outing_id
                    WHERE lp.received_at_utc <= ? {slug_join}
                    ORDER BY lp.outing_id ASC, lp.participant_public_id ASC
                    """,
                    parameters,
                ).fetchall()
                events: list[OutingLiveEvent] = []
                touched_outings: set[str] = set()
                for row in rows:
                    outing_id = str(row["outing_id"])
                    participant_id = str(row["participant_public_id"])
                    deleted = connection.execute(
                        """
                        DELETE FROM outing_live_positions
                        WHERE participant_row_id = ? AND received_at_utc <= ?
                        """,
                        (
                            str(row["participant_row_id"]),
                            _format_timestamp(expiration_cutoff),
                        ),
                    ).rowcount
                    if deleted == 1:
                        events.append(
                            self._append_event(
                                connection,
                                outing_id,
                                "position_cleared",
                                participant_id,
                                occurred_at,
                                clear_reason="expired",
                            )
                        )
                        touched_outings.add(outing_id)
                for outing_id in touched_outings:
                    self._prune_events(
                        connection,
                        outing_id,
                        retention_cutoff,
                        maximum_event_count,
                    )
                connection.commit()
                return tuple(events)
        except OutingLiveRepositoryError:
            raise
        except (OverflowError, OutingRepositoryError, sqlite3.Error) as exc:
            raise OutingLiveRepositoryError("live position expiry failed") from exc

    def get_live_event_window(self, slug: str) -> OutingLiveEventWindow | None:
        state = self.get_live_stream_state(slug)
        if state is None:
            return None
        return OutingLiveEventWindow(
            outing_id=state.snapshot.outing_id,
            current_cursor=state.snapshot.cursor,
            oldest_retained_event_id=state.oldest_retained_event_id,
        )

    def get_live_events_after(
        self, slug: str, event_id: int, *, limit: int
    ) -> tuple[OutingLiveEventRecord, ...] | None:
        try:
            with self._connection() as connection:
                outing = connection.execute(
                    "SELECT id FROM outings WHERE public_slug = ?",
                    (slug,),
                ).fetchone()
                if outing is None:
                    return None
                outing_id = str(outing["id"])
                rows = connection.execute(
                    """
                    SELECT outing_id, event_id, event_type,
                           participant_public_id, payload_json, created_at_utc
                    FROM outing_live_events
                    WHERE outing_id = ? AND event_id > ?
                    ORDER BY event_id ASC
                    LIMIT ?
                    """,
                    (outing_id, event_id, limit),
                ).fetchall()
        except (OverflowError, sqlite3.Error) as exc:
            raise OutingLiveRepositoryError("live event replay lookup failed") from exc
        return tuple(_event_record(row) for row in rows)

    def purge_live_events(self, cutoff: datetime) -> int:
        try:
            with self._connection() as connection, connection:
                cursor = connection.execute(
                    """
                    DELETE FROM outing_live_events
                    WHERE created_at_utc < ?
                    """,
                    (_format_timestamp(cutoff),),
                )
                return max(0, cursor.rowcount)
        except (OverflowError, OutingRepositoryError, sqlite3.Error) as exc:
            raise OutingLiveRepositoryError("live event purge failed") from exc

    def delete_expired_outing(self, slug: str, now: datetime) -> bool:
        try:
            with self._write_connection() as connection:
                cursor = connection.execute(
                    """
                    DELETE FROM outings
                    WHERE public_slug = ? AND expires_at_utc <= ?
                    """,
                    (slug, _format_timestamp(now)),
                )
                connection.commit()
                return cursor.rowcount == 1
        except (OverflowError, OutingRepositoryError, sqlite3.Error) as exc:
            raise OutingLiveRepositoryError("live outing expiry failed") from exc

    def _verify_authorization_context(
        self,
        connection: sqlite3.Connection,
        authorization: OutingParticipantAuthorizationRecord,
    ) -> None:
        row = connection.execute(
            """
            SELECT o.expires_at_utc
            FROM outings AS o
            JOIN outing_participants AS p ON p.outing_id = o.id
            WHERE o.id = ? AND p.id = ? AND p.public_id = ?
            """,
            (
                authorization.outing_id,
                authorization.participant_row_id,
                authorization.participant_public_id,
            ),
        ).fetchone()
        if row is None:
            raise OutingLiveAuthorizationContextError
        now_text = _format_timestamp(self._clock())
        now = _parse_timestamp(now_text)
        if _parse_timestamp(str(row["expires_at_utc"])) <= now:
            connection.execute(
                """
                DELETE FROM outings
                WHERE id = ? AND expires_at_utc <= ?
                """,
                (authorization.outing_id, now_text),
            )
            connection.commit()
            raise OutingLiveAuthorizationContextError

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        outing_id: str,
        event_type: LiveEventType,
        participant_id: str,
        occurred_at: datetime,
        *,
        position: ParticipantLivePosition | None = None,
        clear_reason: PositionClearReason | None = None,
    ) -> OutingLiveEvent:
        incremented = connection.execute(
            """
            UPDATE outings
            SET live_event_cursor = live_event_cursor + 1
            WHERE id = ? AND live_event_cursor < ?
            """,
            (outing_id, SQLITE_SIGNED_INTEGER_MAX),
        )
        if incremented.rowcount != 1:
            raise OutingLiveRepositoryError("live event cursor increment failed")
        row = connection.execute(
            """
            SELECT live_event_cursor
            FROM outings
            WHERE id = ?
            """,
            (outing_id,),
        ).fetchone()
        if row is None:
            raise OutingLiveRepositoryError("live event ID allocation failed")
        event = OutingLiveEvent(
            event_id=int(row["live_event_cursor"]),
            event_type=event_type,
            participant_id=participant_id,
            occurred_at=occurred_at,
            position=position,
            clear_reason=clear_reason,
        )
        connection.execute(
            """
            INSERT INTO outing_live_events (
                outing_id, event_id, event_type, participant_public_id,
                payload_json, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                outing_id,
                event.event_id,
                event.event_type,
                participant_id,
                event.model_dump_json(),
                _format_timestamp(occurred_at),
            ),
        )
        return event

    @staticmethod
    def _prune_events(
        connection: sqlite3.Connection,
        outing_id: str,
        retention_cutoff: datetime,
        maximum_event_count: int,
    ) -> None:
        connection.execute(
            """
            DELETE FROM outing_live_events
            WHERE outing_id = ? AND created_at_utc < ?
            """,
            (outing_id, _format_timestamp(retention_cutoff)),
        )
        connection.execute(
            """
            DELETE FROM outing_live_events
            WHERE outing_id = ? AND event_id NOT IN (
                SELECT event_id
                FROM outing_live_events
                WHERE outing_id = ?
                ORDER BY event_id DESC
                LIMIT ?
            )
            """,
            (outing_id, outing_id, maximum_event_count),
        )

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


def _authorization_record(
    row: sqlite3.Row,
) -> OutingParticipantAuthorizationRecord:
    try:
        return OutingParticipantAuthorizationRecord(
            outing_id=str(row["outing_id"]),
            participant_row_id=str(row["participant_row_id"]),
            participant_public_id=str(row["participant_public_id"]),
            participant_token_hash=bytes(row["participant_token_hash"]),
            outing_expires_at_utc=_parse_timestamp(str(row["expires_at_utc"])),
            participant_join_order=int(row["join_order"]),
        )
    except (OutingRepositoryError, TypeError, ValueError) as exc:
        raise OutingLiveRepositoryError("live authorization record is invalid") from exc


def _position_record(row: sqlite3.Row) -> OutingLivePositionRecord:
    try:
        return OutingLivePositionRecord(
            participant_row_id=str(row["participant_row_id"]),
            outing_id=str(row["outing_id"]),
            participant_public_id=str(row["participant_public_id"]),
            client_sequence=int(row["client_sequence"]),
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            accuracy_m=float(row["accuracy_m"]),
            altitude_m=_optional_float(row["altitude_m"]),
            speed_m_s=_optional_float(row["speed_m_s"]),
            heading_deg=_optional_float(row["heading_deg"]),
            captured_at_utc=_parse_timestamp(str(row["captured_at_utc"])),
            received_at_utc=_parse_timestamp(str(row["received_at_utc"])),
            participant_join_order=int(row["join_order"]),
        )
    except (OutingRepositoryError, TypeError, ValueError) as exc:
        raise OutingLiveRepositoryError("live position record is invalid") from exc


def _event_record(row: sqlite3.Row) -> OutingLiveEventRecord:
    try:
        event = OutingLiveEvent.model_validate_json(str(row["payload_json"]))
        if (
            event.event_id != int(row["event_id"])
            or event.event_type != str(row["event_type"])
            or event.participant_id != str(row["participant_public_id"])
            or event.occurred_at != _parse_timestamp(str(row["created_at_utc"]))
        ):
            raise ValueError("live event columns are inconsistent")
        return OutingLiveEventRecord(outing_id=str(row["outing_id"]), event=event)
    except (OutingRepositoryError, ValidationError, TypeError, ValueError) as exc:
        raise OutingLiveRepositoryError("live event record is invalid") from exc


def _position_values(record: OutingLivePositionRecord) -> tuple[object, ...]:
    return (
        record.participant_row_id,
        record.outing_id,
        record.participant_public_id,
        record.client_sequence,
        record.latitude,
        record.longitude,
        record.accuracy_m,
        record.altitude_m,
        record.speed_m_s,
        record.heading_deg,
        _format_timestamp(record.captured_at_utc),
        _format_timestamp(record.received_at_utc),
    )


def _same_client_payload(
    current: OutingLivePositionRecord,
    incoming: OutingLivePositionRecord,
) -> bool:
    return (
        current.client_sequence == incoming.client_sequence
        and current.latitude == incoming.latitude
        and current.longitude == incoming.longitude
        and current.accuracy_m == incoming.accuracy_m
        and current.altitude_m == incoming.altitude_m
        and current.speed_m_s == incoming.speed_m_s
        and current.heading_deg == incoming.heading_deg
        and current.captured_at_utc == incoming.captured_at_utc
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError("live optional number is invalid")
    return float(value)
