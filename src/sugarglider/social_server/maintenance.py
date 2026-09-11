"""Off-request retention cleanup and real SQLite readiness checks."""

from datetime import UTC, datetime

from sugarglider.outings.live_service import OutingLiveOperations
from sugarglider.outings.sqlite_repository import SQLiteOutingRepository
from sugarglider.saved_routes.sqlite_repository import SQLiteSavedRouteRepository
from sugarglider.social_server.settings import SocialSettings


def cleanup(settings: SocialSettings, live: OutingLiveOperations) -> None:
    now = datetime.now(UTC)
    SQLiteSavedRouteRepository(
        settings.data_directory / "saved-routes.sqlite3"
    ).purge_expired(now)
    SQLiteOutingRepository(settings.data_directory / "outings.sqlite3").purge_expired(
        now
    )
    live.startup_cleanup()
