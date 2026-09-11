"""One public UI configuration builder for reference and social deployments."""

from sugarglider.config import Settings
from sugarglider.web.models import UiConfig


def build_ui_config(
    settings: Settings,
    *,
    nature_available: bool,
    poi_available: bool,
    saved_routes_available: bool,
    outings_available: bool,
    live_available: bool,
) -> UiConfig:
    return UiConfig(
        tile_url_template=settings.map_tile_url,
        tile_attribution=settings.map_attribution,
        initial_center=(
            settings.map_initial_lon,
            settings.map_initial_lat,
        ),
        initial_zoom=settings.map_initial_zoom,
        max_required_points=30,
        nature_index_available=nature_available,
        nature_water_buffer_m=settings.nature_water_buffer_m,
        nature_preference_values=("off", "prefer"),
        loop_geometry_preference_values=("off", "prefer"),
        poi_index_available=poi_available,
        poi_default_limit=settings.poi_default_limit,
        poi_max_limit=settings.poi_max_limit,
        saved_routes_available=saved_routes_available,
        outings_available=outings_available,
        outing_max_participants=settings.outing_max_participants,
        outing_live_positions_available=live_available,
        outing_live_stale_after_seconds=(settings.outing_live_stale_after_seconds),
        outing_live_expire_after_seconds=(settings.outing_live_expire_after_seconds),
        auto_tour_scenic_corridor_radius_m=(
            settings.auto_tour_scenic_corridor_radius_m
        ),
        auto_tour_water_corridor_radius_m=(settings.auto_tour_water_corridor_radius_m),
    )
