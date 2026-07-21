"""FastAPI application factory and production application instance."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from sugarglider.analysis.loop_geometry import LoopGeometryRouteAnalyzer
from sugarglider.analysis.route import RouteAnalyzer
from sugarglider.api.errors import install_error_handlers
from sugarglider.api.routes import router
from sugarglider.config import Settings
from sugarglider.nature.analysis import NatureRouteAnalyzer
from sugarglider.nature.errors import NatureIndexError, NatureIndexMissingError
from sugarglider.nature.index import (
    NatureIndex,
    available_nature_status,
    load_nature_index,
    unavailable_nature_status,
)
from sugarglider.nature.models import NatureIndexStatus
from sugarglider.planning.alternative_legs import LowOverlapSettings
from sugarglider.planning.auto_tour.discovered_pois import TourPoiSettings
from sugarglider.planning.auto_tour.service import AutoTourPlanner, AutoTourService
from sugarglider.planning.auto_tour.state import AutoTourSettings
from sugarglider.planning.pipeline import PlanService
from sugarglider.planning.waypoint.service import WaypointPlanner
from sugarglider.pois.errors import PoiIndexError, PoiIndexMissingError
from sugarglider.pois.index import (
    PoiIndex,
    available_poi_status,
    load_poi_index,
    unavailable_poi_status,
)
from sugarglider.pois.models import PoiIndexStatus
from sugarglider.routing.graphhopper import GraphHopperClient
from sugarglider.routing.result import RouteResultFactory
from sugarglider.routing.service import RouteService
from sugarglider.web.models import UiConfig
from sugarglider.web.routes import STATIC_DIRECTORY
from sugarglider.web.routes import router as web_router

logger = logging.getLogger(__name__)


def create_app(
    service: RouteService | None = None,
    settings: Settings | None = None,
    plan_service: PlanService | None = None,
) -> FastAPI:
    """Build an application, optionally injecting a service for tests."""

    runtime_settings = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nature_index, nature_status = _load_nature(runtime_settings)
        poi_index, poi_status = _load_pois(runtime_settings)
        nature_analyzer = (
            NatureRouteAnalyzer(
                nature_index,
                water_buffer_m=runtime_settings.nature_water_buffer_m,
            )
            if nature_index is not None
            else None
        )
        ui_config = UiConfig(
            tile_url_template=runtime_settings.map_tile_url,
            tile_attribution=runtime_settings.map_attribution,
            initial_center=(
                runtime_settings.map_initial_lon,
                runtime_settings.map_initial_lat,
            ),
            initial_zoom=runtime_settings.map_initial_zoom,
            max_required_points=30,
            nature_index_available=nature_status.available,
            nature_water_buffer_m=runtime_settings.nature_water_buffer_m,
            nature_preference_values=("off", "prefer"),
            loop_geometry_preference_values=("off", "prefer"),
            poi_index_available=poi_status.available,
            poi_default_limit=runtime_settings.poi_default_limit,
            poi_max_limit=runtime_settings.poi_max_limit,
            auto_tour_scenic_corridor_radius_m=(
                runtime_settings.auto_tour_scenic_corridor_radius_m
            ),
            auto_tour_water_corridor_radius_m=(
                runtime_settings.auto_tour_water_corridor_radius_m
            ),
        )
        app.state.ui_config = ui_config
        app.state.nature_index = nature_index
        app.state.nature_analyzer = nature_analyzer
        app.state.nature_status = nature_status
        app.state.poi_index = poi_index
        app.state.poi_status = poi_status
        app.state.poi_default_limit = runtime_settings.poi_default_limit
        app.state.poi_max_limit = runtime_settings.poi_max_limit
        if service is not None:
            app.state.route_service = service
            if plan_service is not None:
                app.state.plan_service = plan_service
            yield
            return
        async with httpx.AsyncClient() as client:
            backend = GraphHopperClient(
                str(runtime_settings.graphhopper_url),
                runtime_settings.graphhopper_timeout_seconds,
                client,
            )
            result_factory = RouteResultFactory(
                RouteAnalyzer(
                    nature_analyzer=nature_analyzer,
                    loop_geometry_analyzer=LoopGeometryRouteAnalyzer(),
                )
            )
            structural_result_factory = RouteResultFactory(RouteAnalyzer())
            app.state.route_service = RouteService(backend, result_factory)
            auto_tour_search = AutoTourService(
                backend,
                result_factory,
                poi_index=poi_index,
                settings=AutoTourSettings(
                    max_snap_displacement_m=(
                        runtime_settings.generation_max_optional_snap_displacement_m
                    ),
                    poi=TourPoiSettings(
                        scenic_corridor_radius_m=(
                            runtime_settings.auto_tour_scenic_corridor_radius_m
                        ),
                        verified_water_corridor_radius_m=(
                            runtime_settings.auto_tour_water_corridor_radius_m
                        ),
                        include_broad_attractions=(
                            runtime_settings.auto_tour_include_broad_attractions
                        ),
                    ),
                ),
                nature_index_available=nature_status.available,
                structural_result_factory=structural_result_factory,
                low_overlap_settings=LowOverlapSettings(
                    max_paths=runtime_settings.low_overlap_max_paths,
                    max_weight_factor=(runtime_settings.low_overlap_max_weight_factor),
                    max_share_factor=runtime_settings.low_overlap_max_share_factor,
                    beam_width=min(12, runtime_settings.low_overlap_beam_width),
                    max_leg_requests=min(
                        24, runtime_settings.low_overlap_max_leg_requests
                    ),
                    source_count=min(2, runtime_settings.low_overlap_source_count),
                ),
            )
            app.state.plan_service = PlanService(
                auto_tour=AutoTourPlanner(auto_tour_search),
                waypoint=WaypointPlanner(
                    backend,
                    result_factory,
                    max_evaluations=runtime_settings.generation_max_evaluations,
                    structural_result_factory=structural_result_factory,
                ),
            )
            yield

    app = FastAPI(title="Sugarglider API", version="0.1.0", lifespan=lifespan)
    install_error_handlers(app)
    app.include_router(web_router)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")
    return app


def _load_nature(settings: Settings) -> tuple[NatureIndex | None, NatureIndexStatus]:
    path = settings.nature_index_path
    if path is None:
        return None, unavailable_nature_status(
            None,
            water_buffer_m=settings.nature_water_buffer_m,
            warnings=("nature_index_unavailable",),
        )
    try:
        index = load_nature_index(path)
    except NatureIndexMissingError:
        log = logger.warning if settings.nature_missing_index_warning else logger.info
        log("Nature index %s is unavailable; nature analysis is disabled", path.name)
        return None, unavailable_nature_status(
            path,
            water_buffer_m=settings.nature_water_buffer_m,
            warnings=("nature_index_unavailable",),
        )
    except NatureIndexError:
        logger.warning(
            "Nature index %s is invalid; nature analysis is disabled",
            path.name,
            exc_info=True,
        )
        return None, unavailable_nature_status(
            path,
            water_buffer_m=settings.nature_water_buffer_m,
            warnings=("nature_index_invalid",),
        )
    return index, available_nature_status(
        index,
        path,
        water_buffer_m=settings.nature_water_buffer_m,
    )


def _load_pois(settings: Settings) -> tuple[PoiIndex | None, PoiIndexStatus]:
    path = settings.poi_index_path
    if path is None:
        return None, unavailable_poi_status(
            None,
            warnings=("poi_index_unavailable",),
        )
    try:
        index = load_poi_index(path)
    except PoiIndexMissingError:
        log = logger.warning if settings.poi_missing_index_warning else logger.info
        log("POI index %s is unavailable; place discovery is disabled", path.name)
        return None, unavailable_poi_status(
            path,
            warnings=("poi_index_unavailable",),
        )
    except PoiIndexError:
        logger.warning(
            "POI index %s is invalid; place discovery is disabled",
            path.name,
        )
        return None, unavailable_poi_status(
            path,
            warnings=("poi_index_invalid",),
        )
    return index, available_poi_status(index, path)


app = create_app()
