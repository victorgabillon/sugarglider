"""Production factory: immutable sharing, outings and latest positions only."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from sugarglider.api.errors import install_error_handlers
from sugarglider.api.outing_live import router as live_router
from sugarglider.api.outings import router as outings_router
from sugarglider.api.persistence import (
    create_outing_services,
    create_saved_route_service,
)
from sugarglider.api.projection import router as projection_router
from sugarglider.api.saved_routes import router as saved_routes_router
from sugarglider.nature.index import unavailable_nature_status
from sugarglider.outings.live_broker import OutingLiveBroker
from sugarglider.outings.live_service import OutingLiveOperations
from sugarglider.pois.index import unavailable_poi_status
from sugarglider.pois.models import PoiIndexStatus
from sugarglider.routing.profiles import (
    ROUTING_PROFILES,
    RoutingProfileCatalog,
    RoutingProfileStatus,
    public_profile,
)
from sugarglider.social_server.http import SocialHttpMiddleware
from sugarglider.social_server.maintenance import cleanup
from sugarglider.social_server.settings import SocialSettings
from sugarglider.social_server.sqlite_repository import storage_ready
from sugarglider.web.config import build_ui_config
from sugarglider.web.routes import STATIC_DIRECTORY
from sugarglider.web.routes import router as web_router

logger = logging.getLogger("sugarglider.social.lifecycle")


def create_social_app(settings: SocialSettings | None = None) -> FastAPI:
    settings = settings or SocialSettings()
    persistence = settings.persistence_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        saved = await run_in_threadpool(create_saved_route_service, persistence)
        outings, live = await run_in_threadpool(create_outing_services, persistence)
        app.state.saved_route_service = saved
        app.state.outing_service = outings
        app.state.outing_live_service = live
        app.state.outing_live_broker = OutingLiveBroker()
        app.state.nature_analyzer = None
        app.state.nature_status = unavailable_nature_status(
            None,
            water_buffer_m=100,
            warnings=("nature_index_unavailable",),
        )
        app.state.ui_config = build_ui_config(
            persistence,
            nature_available=False,
            poi_available=False,
            saved_routes_available=saved.available,
            outings_available=outings.available,
            live_available=live.available,
        )
        app.state.social_storage_available = (
            saved.available and outings.available and live.available
        )
        app.state.retention_healthy = app.state.social_storage_available
        task = asyncio.create_task(_retain(app, settings, live))
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(
        title="Sugarglider social service",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.router.redirect_slashes = False
    install_error_handlers(app)
    app.include_router(web_router)
    app.include_router(saved_routes_router)
    app.include_router(outings_router)
    app.include_router(live_router)
    # Shared-web route highlighting is a bounded display projection of supplied
    # geometry. It never routes, enriches nature, reranks or serves map tiles.
    app.include_router(projection_router)
    app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "social"}

    @app.get("/ready")
    async def ready(request: Request) -> JSONResponse:
        available = bool(
            request.app.state.social_storage_available
            and request.app.state.retention_healthy
            and await run_in_threadpool(storage_ready, settings)
        )
        return JSONResponse(
            {"status": "ok" if available else "unavailable", "service": "social"},
            status_code=200 if available else 503,
        )

    @app.get("/v2/routing-profiles", response_model=RoutingProfileCatalog)
    async def profile_metadata() -> RoutingProfileCatalog:
        return RoutingProfileCatalog(
            profiles=tuple(
                RoutingProfileStatus(
                    profile=public_profile(profile),
                    available=False,
                    warnings=("server_planning_disabled",),
                )
                for profile in ROUTING_PROFILES
            )
        )

    @app.get("/v1/pois/status", response_model=PoiIndexStatus)
    async def poi_status() -> PoiIndexStatus:
        return unavailable_poi_status(None, warnings=("poi_index_unavailable",))

    app.add_middleware(SocialHttpMiddleware, settings=settings)
    return app


async def _retain(
    app: FastAPI, settings: SocialSettings, live: OutingLiveOperations
) -> None:
    while True:
        await asyncio.sleep(settings.cleanup_interval_seconds)
        if not app.state.social_storage_available:
            continue
        try:
            await run_in_threadpool(cleanup, settings, live)
        except Exception:
            app.state.retention_healthy = False
            logger.error('{"event":"retention_cleanup","status":"failed"}')
        else:
            app.state.retention_healthy = True
