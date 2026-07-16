"""FastAPI application factory and production application instance."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from sugarglider.api.errors import install_error_handlers
from sugarglider.api.routes import router
from sugarglider.config import Settings
from sugarglider.generation.service import RouteGenerationService
from sugarglider.routing.graphhopper import GraphHopperClient
from sugarglider.routing.result import RouteResultFactory
from sugarglider.routing.service import RouteService


def create_app(
    service: RouteService | None = None,
    generation_service: RouteGenerationService | None = None,
) -> FastAPI:
    """Build an application, optionally injecting a service for tests."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if service is not None:
            app.state.route_service = service
            if generation_service is not None:
                app.state.generation_service = generation_service
            yield
            return
        settings = Settings()
        async with httpx.AsyncClient() as client:
            backend = GraphHopperClient(
                str(settings.graphhopper_url),
                settings.graphhopper_timeout_seconds,
                client,
            )
            result_factory = RouteResultFactory()
            app.state.route_service = RouteService(backend, result_factory)
            app.state.generation_service = RouteGenerationService(
                backend,
                result_factory,
                max_evaluations=settings.generation_max_evaluations,
                max_optional_snap_displacement_m=(
                    settings.generation_max_optional_snap_displacement_m
                ),
            )
            yield

    app = FastAPI(title="Sugarglider API", version="0.1.0", lifespan=lifespan)
    install_error_handlers(app)
    app.include_router(router)
    return app


app = create_app()
