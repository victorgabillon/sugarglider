"""Shared persistence startup; no routing or regional-data initialization."""

import logging

from sugarglider.config import Settings
from sugarglider.outings.errors import OutingStorageError
from sugarglider.outings.live_repository import OutingLiveRepositoryError
from sugarglider.outings.live_service import (
    OutingLiveOperations,
    OutingLiveService,
    UnavailableOutingLiveService,
)
from sugarglider.outings.live_sqlite_repository import SQLiteOutingLiveRepository
from sugarglider.outings.repository import OutingRepositoryError
from sugarglider.outings.service import (
    OutingOperations,
    OutingService,
    UnavailableOutingService,
)
from sugarglider.outings.sqlite_repository import SQLiteOutingRepository
from sugarglider.saved_routes.errors import SavedRouteStorageError
from sugarglider.saved_routes.repository import SavedRouteRepositoryError
from sugarglider.saved_routes.service import (
    SavedRouteOperations,
    SavedRouteService,
    UnavailableSavedRouteService,
)
from sugarglider.saved_routes.sqlite_repository import SQLiteSavedRouteRepository

logger = logging.getLogger(__name__)


def create_saved_route_service(settings: Settings) -> SavedRouteOperations:
    path = settings.saved_route_database_path
    if path is None:
        return UnavailableSavedRouteService()
    try:
        repository = SQLiteSavedRouteRepository(path)
        repository.initialize()
        service = SavedRouteService(
            repository,
            ttl_days=settings.saved_route_ttl_days,
            maximum_snapshot_bytes=settings.saved_route_max_snapshot_bytes,
        )
        service.purge_expired()
        return service
    except (SavedRouteRepositoryError, SavedRouteStorageError):
        logger.warning("Saved-route persistence is unavailable")
        return UnavailableSavedRouteService()


def create_outing_services(
    settings: Settings,
) -> tuple[OutingOperations, OutingLiveOperations]:
    path = settings.outing_database_path
    if path is None:
        return UnavailableOutingService(), UnavailableOutingLiveService()
    try:
        repository = SQLiteOutingRepository(path)
        repository.initialize()
        live_repository = SQLiteOutingLiveRepository(path)
        service = OutingService(
            repository,
            ttl_days=settings.outing_ttl_days,
            max_participants=settings.outing_max_participants,
            maximum_route_snapshot_bytes=(settings.outing_max_route_snapshot_bytes),
            live_repository=live_repository,
            live_event_retention_seconds=(settings.outing_live_event_retention_seconds),
            live_maximum_events_per_outing=(settings.outing_live_max_events_per_outing),
        )
        service.purge_expired()
        live_service = OutingLiveService(
            live_repository,
            stale_after_seconds=settings.outing_live_stale_after_seconds,
            expire_after_seconds=settings.outing_live_expire_after_seconds,
            maximum_update_age_seconds=(settings.outing_live_max_update_age_seconds),
            future_tolerance_seconds=(settings.outing_live_future_tolerance_seconds),
            event_retention_seconds=(settings.outing_live_event_retention_seconds),
            maximum_events_per_outing=(settings.outing_live_max_events_per_outing),
            keepalive_seconds=settings.outing_live_sse_keepalive_seconds,
        )
        live_service.startup_cleanup()
        return service, live_service
    except (
        OutingLiveRepositoryError,
        OutingRepositoryError,
        OutingStorageError,
    ):
        logger.warning("Outing persistence is unavailable")
        return UnavailableOutingService(), UnavailableOutingLiveService()
