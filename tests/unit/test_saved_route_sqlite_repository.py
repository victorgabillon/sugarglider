"""Focused standard-library SQLite saved-route repository tests."""

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sugarglider.saved_routes.repository import (
    SavedRouteRecord,
    SavedRouteSlugCollisionError,
)
from sugarglider.saved_routes.sqlite_repository import SQLiteSavedRouteRepository

NOW = datetime(2026, 7, 27, 12, tzinfo=UTC)


def _record(
    *,
    route_id: str = "route-1",
    slug: str = "abcdefghijklmnopqrstuv",
    created: datetime = NOW,
    expires: datetime = NOW + timedelta(days=90),
) -> SavedRouteRecord:
    return SavedRouteRecord(
        id=route_id,
        schema_version=1,
        public_slug=slug,
        owner_token_hash=b"x" * 32,
        source_request_json='{"name":"Forêt — 東京"}',
        candidate_json='{"name":"Candidat été"}',
        created_at_utc=created,
        expires_at_utc=expires,
    )


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "nested" / "saved-routes.sqlite3"


@pytest.fixture
def repository(database_path: Path) -> SQLiteSavedRouteRepository:
    value = SQLiteSavedRouteRepository(database_path)
    value.initialize()
    return value


def test_initialize_is_idempotent_and_creates_exact_schema(
    database_path: Path,
) -> None:
    repository = SQLiteSavedRouteRepository(database_path)
    repository.initialize()
    repository.initialize()

    with sqlite3.connect(database_path) as connection:
        tables = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = ? AND name NOT LIKE ?
            ORDER BY name
            """,
            ("table", "sqlite_%"),
        ).fetchall()
        columns = connection.execute("PRAGMA table_info(saved_routes)").fetchall()
        indexes = connection.execute("PRAGMA index_list(saved_routes)").fetchall()
    assert tables == [("saved_routes",)]
    assert [column[1] for column in columns] == [
        "id",
        "schema_version",
        "public_slug",
        "owner_token_hash",
        "source_request_json",
        "candidate_json",
        "created_at_utc",
        "expires_at_utc",
    ]
    index_names = {index[1] for index in indexes}
    assert "idx_saved_routes_public_slug" in index_names
    assert "idx_saved_routes_expires_at_utc" in index_names
    assert any(index[2] for index in indexes)


def test_connections_configure_wal_and_busy_timeout(
    repository: SQLiteSavedRouteRepository,
    database_path: Path,
) -> None:
    repository.create(_record())
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_create_retrieve_and_unicode_round_trip(
    repository: SQLiteSavedRouteRepository,
) -> None:
    expected = _record()
    repository.create(expected)
    assert repository.get_by_slug(expected.public_slug) == expected


def test_duplicate_slug_raises_typed_collision(
    repository: SQLiteSavedRouteRepository,
) -> None:
    repository.create(_record())
    with pytest.raises(SavedRouteSlugCollisionError):
        repository.create(_record(route_id="route-2"))


def test_delete_existing_and_absent(repository: SQLiteSavedRouteRepository) -> None:
    repository.create(_record())
    assert repository.delete_by_id("route-1")
    assert not repository.delete_by_id("route-1")
    assert repository.get_by_slug("abcdefghijklmnopqrstuv") is None


def test_purge_removes_only_expired_records(
    repository: SQLiteSavedRouteRepository,
) -> None:
    expired = _record(expires=NOW + timedelta(seconds=1))
    current = replace(
        _record(route_id="route-2", slug="zyxwvutsrqponmlkjihgfe"),
        expires_at_utc=NOW + timedelta(days=1),
    )
    repository.create(expired)
    repository.create(current)

    assert repository.purge_expired(NOW + timedelta(seconds=2)) == 1
    assert repository.get_by_slug(expired.public_slug) is None
    assert repository.get_by_slug(current.public_slug) == current


def test_database_is_created_only_at_injected_path(database_path: Path) -> None:
    repository = SQLiteSavedRouteRepository(database_path)
    repository.initialize()
    repository.create(_record())

    files = {
        path.relative_to(database_path.parents[1]).as_posix()
        for path in database_path.parents[1].rglob("*")
        if path.is_file()
    }
    assert "nested/saved-routes.sqlite3" in files
    assert not any(name.endswith(".json") for name in files)
    assert not any("abcdefghijklmnopqrstuv" in name for name in files)


def test_adapter_uses_bound_parameters_and_owns_all_sqlite_imports() -> None:
    source_path = (
        Path(__file__).resolve().parents[2]
        / "src/sugarglider/saved_routes/sqlite_repository.py"
    )
    source = source_path.read_text(encoding="utf-8")
    assert "VALUES (?, ?, ?, ?, ?, ?, ?, ?)" in source
    assert "WHERE public_slug = ?" in source
    assert "WHERE id = ?" in source
    assert "expires_at_utc <= ?" in source
    for path in source_path.parent.glob("*.py"):
        if path.name != "sqlite_repository.py":
            assert "import sqlite3" not in path.read_text(encoding="utf-8")
