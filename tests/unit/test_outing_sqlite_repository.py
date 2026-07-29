"""SQLite outing repository schema, atomicity, and ordering tests."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sugarglider.outings.repository import (
    OutingCapacityReachedError,
    OutingParticipantRecord,
    OutingRecord,
    OutingRepositoryError,
    OutingSlugCollisionError,
    ParticipantIdCollisionError,
)
from sugarglider.outings.sqlite_repository import SQLiteOutingRepository

NOW = datetime(2026, 7, 27, tzinfo=UTC)


def _outing(slug: str = "abcdefghijklmnopqrstuv") -> OutingRecord:
    return OutingRecord(
        id=f"internal-{slug}",
        schema_version=1,
        public_slug=slug,
        owner_token_hash=b"o" * 32,
        join_token_hash=b"j" * 32,
        title="Forêt & gravel",
        created_at_utc=NOW,
        expires_at_utc=NOW + timedelta(days=30),
        max_participants=2,
    )


def _participant(
    outing_id: str,
    public_id: str,
    order: int,
    *,
    display_name: str = "Élodie",
) -> OutingParticipantRecord:
    return OutingParticipantRecord(
        id=f"internal-{public_id}",
        outing_id=outing_id,
        public_id=public_id,
        participant_token_hash=b"p" * 32,
        display_name=display_name,
        source_request_json='{"kind":"independent"}',
        candidate_json='{"route":"exact"}',
        joined_at_utc=NOW + timedelta(seconds=order),
        join_order=order,
    )


def test_initialization_is_idempotent_and_has_exact_application_tables(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nested" / "outings.sqlite3"
    repository = SQLiteOutingRepository(path)
    repository.initialize()
    repository.initialize()
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        journal = connection.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        outing_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(outings)")
        }
        participant_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(outing_participants)")
        }
    assert tables == {
        "outings",
        "outing_participants",
        "outing_live_positions",
        "outing_live_events",
    }
    assert {
        "idx_outings_public_slug",
        "idx_outings_expires_at_utc",
        "idx_outing_participants_outing_id",
        "idx_outing_participants_outing_public_id",
        "idx_outing_participants_outing_join_order",
        "idx_outing_live_positions_outing_id",
        "idx_outing_live_positions_received_at_utc",
        "idx_outing_live_events_outing_event_id",
        "idx_outing_live_events_created_at_utc",
    } <= indexes
    assert journal == "wal"
    assert foreign_keys == 0  # Connections configure it per operation.
    assert outing_columns == {
        "id",
        "schema_version",
        "public_slug",
        "owner_token_hash",
        "join_token_hash",
        "title",
        "created_at_utc",
        "expires_at_utc",
        "max_participants",
        "live_event_cursor",
    }
    assert participant_columns == {
        "id",
        "outing_id",
        "public_id",
        "participant_token_hash",
        "display_name",
        "source_request_json",
        "candidate_json",
        "joined_at_utc",
        "join_order",
    }
    assert list(path.parent.glob("*.json")) == []

    with repository._connection() as configured:
        assert configured.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert configured.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError):
        configured.execute("SELECT 1")


def test_existing_pr23_two_table_database_is_migrated_without_row_changes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pr23.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE outings (
                id TEXT PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                public_slug TEXT NOT NULL UNIQUE,
                owner_token_hash BLOB NOT NULL,
                join_token_hash BLOB NOT NULL,
                title TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                expires_at_utc TEXT NOT NULL,
                max_participants INTEGER NOT NULL
            );
            CREATE TABLE outing_participants (
                id TEXT PRIMARY KEY,
                outing_id TEXT NOT NULL,
                public_id TEXT NOT NULL,
                participant_token_hash BLOB NOT NULL,
                display_name TEXT NOT NULL,
                source_request_json TEXT NOT NULL,
                candidate_json TEXT NOT NULL,
                joined_at_utc TEXT NOT NULL,
                join_order INTEGER NOT NULL,
                FOREIGN KEY (outing_id) REFERENCES outings(id) ON DELETE CASCADE,
                UNIQUE (outing_id, public_id),
                UNIQUE (outing_id, join_order)
            );
            """
        )
        connection.execute(
            """
            INSERT INTO outings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "outing-before-migration",
                1,
                "pr23_slug_12345678901",
                b"o" * 32,
                b"j" * 32,
                "Existing outing",
                "2026-07-27T00:00:00.000000Z",
                "2026-08-27T00:00:00.000000Z",
                8,
            ),
        )
        connection.execute(
            """
            INSERT INTO outing_participants VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "participant-before-migration",
                "outing-before-migration",
                "participant_1234567890",
                b"p" * 32,
                "Existing participant",
                '{"source":"unchanged"}',
                '{"candidate":"unchanged"}',
                "2026-07-27T00:00:00.000000Z",
                0,
            ),
        )
        before_outing = connection.execute("SELECT * FROM outings").fetchone()
        before_participant = connection.execute(
            "SELECT * FROM outing_participants"
        ).fetchone()

    repository = SQLiteOutingRepository(path)
    repository.initialize()
    repository.initialize()

    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(outings)")}
        migrated_outing = connection.execute(
            """
            SELECT id, schema_version, public_slug, owner_token_hash,
                   join_token_hash, title, created_at_utc, expires_at_utc,
                   max_participants
            FROM outings
            """
        ).fetchone()
        migrated_participant = connection.execute(
            "SELECT * FROM outing_participants"
        ).fetchone()
        cursor = connection.execute("SELECT live_event_cursor FROM outings").fetchone()
    assert before_outing == migrated_outing
    assert before_participant == migrated_participant
    assert "live_event_cursor" in columns
    assert cursor == (0,)


def test_create_round_trip_order_delete_and_cascade(tmp_path: Path) -> None:
    path = tmp_path / "outings.sqlite3"
    repository = SQLiteOutingRepository(path)
    repository.initialize()
    outing = _outing()
    first = _participant(outing.id, "participant_public_01", 0)
    second = _participant(
        outing.id,
        "participant_public_02",
        1,
        display_name="骑行者",
    )
    repository.create(outing, first)
    repository.add_participant(
        outing.id, second, maximum_participants=outing.max_participants
    )
    loaded = repository.get_by_slug(outing.public_slug)
    assert loaded is not None
    assert loaded.outing == outing
    assert loaded.participants == (first, second)
    assert repository.delete_participant(outing.id, second.public_id)
    assert not repository.delete_participant(outing.id, "missing-participant")
    assert repository.delete_outing_by_id(outing.id)
    with sqlite3.connect(path) as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) FROM outing_participants"
        ).fetchone()[0]
    assert remaining == 0


def test_duplicate_slug_is_typed_and_failed_initial_insert_rolls_back(
    tmp_path: Path,
) -> None:
    repository = SQLiteOutingRepository(tmp_path / "outings.sqlite3")
    repository.initialize()
    outing = _outing()
    repository.create(outing, _participant(outing.id, "participant_public_01", 0))
    with pytest.raises(OutingSlugCollisionError):
        repository.create(
            replace(outing, id="another-internal-id"),
            _participant("another-internal-id", "participant_public_02", 0),
        )
    broken = _outing("different_slug_value01")
    bad_participant = _participant("missing-outing", "participant_public_03", 0)
    with pytest.raises(OutingRepositoryError):
        repository.create(broken, bad_participant)
    assert repository.get_by_slug(broken.public_slug) is None

    mismatch = _outing("mismatch_outing_slug01")
    with pytest.raises(OutingRepositoryError):
        repository.create(
            mismatch,
            _participant("different-outing-id", "participant_public_04", 0),
        )
    assert repository.get_by_slug(mismatch.public_slug) is None

    invalid_order = _outing("invalid_order_slug_01")
    with pytest.raises(OutingRepositoryError):
        repository.create(
            invalid_order,
            _participant(invalid_order.id, "participant_public_05", 1),
        )
    assert repository.get_by_slug(invalid_order.public_slug) is None


def test_concurrent_capacity_is_transactionally_enforced(tmp_path: Path) -> None:
    repository = SQLiteOutingRepository(tmp_path / "outings.sqlite3")
    repository.initialize()
    outing = _outing()
    repository.create(outing, _participant(outing.id, "participant_public_01", 0))

    def add(public_id: str) -> bool:
        try:
            repository.add_participant(
                outing.id,
                _participant(outing.id, public_id, 1),
                maximum_participants=2,
            )
            return True
        except OutingCapacityReachedError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                add,
                ("participant_public_02", "participant_public_03"),
            )
        )
    assert sorted(results) == [False, True]
    loaded = repository.get_by_slug(outing.public_slug)
    assert loaded is not None
    assert len(loaded.participants) == 2


def test_two_concurrent_joins_below_capacity_receive_unique_database_orders(
    tmp_path: Path,
) -> None:
    repository = SQLiteOutingRepository(tmp_path / "outings.sqlite3")
    repository.initialize()
    outing = replace(_outing(), max_participants=4)
    repository.create(
        outing,
        _participant(outing.id, "participant_public_01", 0),
    )

    def add(public_id: str) -> OutingParticipantRecord:
        return repository.add_participant(
            outing.id,
            _participant(outing.id, public_id, 0),
            maximum_participants=4,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        inserted = tuple(
            executor.map(
                add,
                ("participant_public_02", "participant_public_03"),
            )
        )
    assert {participant.join_order for participant in inserted} == {1, 2}
    loaded = repository.get_by_slug(outing.public_slug)
    assert loaded is not None
    assert len(loaded.participants) == 3
    assert tuple(item.join_order for item in loaded.participants) == (0, 1, 2)


def test_public_participant_id_collision_is_typed(tmp_path: Path) -> None:
    repository = SQLiteOutingRepository(tmp_path / "outings.sqlite3")
    repository.initialize()
    outing = replace(_outing(), max_participants=4)
    first = _participant(outing.id, "participant_public_01", 0)
    repository.create(outing, first)
    duplicate = replace(
        _participant(outing.id, first.public_id, 0),
        id="different-internal-participant",
    )
    with pytest.raises(ParticipantIdCollisionError):
        repository.add_participant(
            outing.id,
            duplicate,
            maximum_participants=4,
        )


def test_add_participant_rejects_mismatched_outing_without_mutation(
    tmp_path: Path,
) -> None:
    repository = SQLiteOutingRepository(tmp_path / "outings.sqlite3")
    repository.initialize()
    first_outing = replace(
        _outing("first_outing_slug_001"),
        max_participants=4,
    )
    second_outing = replace(
        _outing("second_outing_slug_01"),
        max_participants=4,
    )
    repository.create(
        first_outing,
        _participant(first_outing.id, "participant_public_01", 0),
    )
    repository.create(
        second_outing,
        _participant(second_outing.id, "participant_public_02", 0),
    )
    first_before = repository.get_by_slug(first_outing.public_slug)
    second_before = repository.get_by_slug(second_outing.public_slug)

    with pytest.raises(
        OutingRepositoryError,
        match="participant does not belong to the target outing",
    ):
        repository.add_participant(
            first_outing.id,
            _participant(
                second_outing.id,
                "participant_public_03",
                99,
            ),
            maximum_participants=4,
        )

    assert repository.get_by_slug(first_outing.public_slug) == first_before
    assert repository.get_by_slug(second_outing.public_slug) == second_before


def test_corrupt_timestamp_fails_safely(tmp_path: Path) -> None:
    path = tmp_path / "outings.sqlite3"
    repository = SQLiteOutingRepository(path)
    repository.initialize()
    outing = _outing()
    repository.create(
        outing,
        _participant(outing.id, "participant_public_01", 0),
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE outings SET expires_at_utc = ? WHERE id = ?",
            ("not-a-timestamp", outing.id),
        )
    with pytest.raises(OutingRepositoryError):
        repository.get_by_slug(outing.public_slug)


def test_purge_expired_preserves_unexpired(tmp_path: Path) -> None:
    repository = SQLiteOutingRepository(tmp_path / "outings.sqlite3")
    repository.initialize()
    expired = _outing("expired_outing_slug_01")
    current = replace(
        _outing("current_outing_slug_01"),
        expires_at_utc=NOW + timedelta(days=31),
    )
    repository.create(expired, _participant(expired.id, "participant_public_01", 0))
    repository.create(current, _participant(current.id, "participant_public_02", 0))
    assert repository.purge_expired(NOW + timedelta(days=30)) == 1
    assert repository.get_by_slug(expired.public_slug) is None
    assert repository.get_by_slug(current.public_slug) is not None
