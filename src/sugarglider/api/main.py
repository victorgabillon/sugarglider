"""FastAPI application factory and production application instance."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from sugarglider.api.errors import install_error_handlers
from sugarglider.api.routes import router
from sugarglider.config import Settings
from sugarglider.generation.low_overlap import LowOverlapSettings
from sugarglider.generation.service import RouteGenerationService
from sugarglider.routing.graphhopper import GraphHopperClient
from sugarglider.routing.result import RouteResultFactory
from sugarglider.routing.service import RouteService
from sugarglider.web.models import UiConfig
from sugarglider.web.routes import STATIC_DIRECTORY
from sugarglider.web.routes import router as web_router


def create_app(
    service: RouteService | None = None,
    generation_service: RouteGenerationService | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    """Build an application, optionally injecting a service for tests."""

    runtime_settings = settings if settings is not None else Settings()
    ui_config = UiConfig(
        tile_url_template=runtime_settings.map_tile_url,
        tile_attribution=runtime_settings.map_attribution,
        initial_center=(
            runtime_settings.map_initial_lon,
            runtime_settings.map_initial_lat,
        ),
        initial_zoom=runtime_settings.map_initial_zoom,
        max_required_points=30,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.ui_config = ui_config
        if service is not None:
            app.state.route_service = service
            if generation_service is not None:
                app.state.generation_service = generation_service
            yield
            return
        async with httpx.AsyncClient() as client:
            backend = GraphHopperClient(
                str(runtime_settings.graphhopper_url),
                runtime_settings.graphhopper_timeout_seconds,
                client,
            )
            result_factory = RouteResultFactory()
            app.state.route_service = RouteService(backend, result_factory)
            app.state.generation_service = RouteGenerationService(
                backend,
                result_factory,
                max_evaluations=runtime_settings.generation_max_evaluations,
                max_optional_snap_displacement_m=(
                    runtime_settings.generation_max_optional_snap_displacement_m
                ),
                low_overlap_settings=LowOverlapSettings(
                    max_paths=runtime_settings.low_overlap_max_paths,
                    max_weight_factor=runtime_settings.low_overlap_max_weight_factor,
                    max_share_factor=runtime_settings.low_overlap_max_share_factor,
                    beam_width=runtime_settings.low_overlap_beam_width,
                    max_leg_requests=runtime_settings.low_overlap_max_leg_requests,
                    source_count=runtime_settings.low_overlap_source_count,
                ),
            )
            yield

    app = FastAPI(title="Sugarglider API", version="0.1.0", lifespan=lifespan)
    install_error_handlers(app)
    app.include_router(web_router)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")
    return app


app = create_app()
