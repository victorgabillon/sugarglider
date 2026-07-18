"""Server-controlled low-overlap setting validation."""

import pytest
from pydantic import ValidationError

from sugarglider.config import Settings


def test_low_overlap_setting_defaults() -> None:
    settings = Settings()
    assert settings.low_overlap_max_paths == 3
    assert settings.low_overlap_max_weight_factor == 1.6
    assert settings.low_overlap_max_share_factor == 0.5
    assert settings.low_overlap_beam_width == 12
    assert settings.low_overlap_max_leg_requests == 48
    assert settings.low_overlap_source_count == 2


def test_map_setting_defaults() -> None:
    settings = Settings()
    assert settings.map_tile_url == "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    assert settings.map_attribution == "© OpenStreetMap contributors"
    assert settings.map_initial_lat == 48.87
    assert settings.map_initial_lon == 2.10
    assert settings.map_initial_zoom == 11.0


def test_nature_setting_defaults_and_environment_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = Settings()
    assert defaults.nature_index_path is not None
    assert defaults.nature_index_path.name == ("ile-de-france-nature-index.json.gz")
    assert defaults.nature_water_buffer_m == 100
    assert not defaults.nature_missing_index_warning
    monkeypatch.setenv("SUGARGLIDER_NATURE_INDEX_PATH", "/tmp/local.json.gz")
    monkeypatch.setenv("SUGARGLIDER_NATURE_WATER_BUFFER_M", "250")
    monkeypatch.setenv("SUGARGLIDER_NATURE_MISSING_INDEX_WARNING", "true")
    configured = Settings()
    assert configured.nature_index_path is not None
    assert configured.nature_index_path.name == "local.json.gz"
    assert configured.nature_water_buffer_m == 250
    assert configured.nature_missing_index_warning


def test_poi_setting_defaults_environment_aliases_and_limit_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = Settings()
    assert defaults.poi_index_path is not None
    assert defaults.poi_index_path.name == "ile-de-france-poi-index.json.gz"
    assert not defaults.poi_missing_index_warning
    assert defaults.poi_default_limit == 500
    assert defaults.poi_max_limit == 1000

    monkeypatch.setenv("SUGARGLIDER_POI_INDEX_PATH", "/tmp/local-pois.json.gz")
    monkeypatch.setenv("SUGARGLIDER_POI_MISSING_INDEX_WARNING", "true")
    monkeypatch.setenv("SUGARGLIDER_POI_DEFAULT_LIMIT", "12")
    monkeypatch.setenv("SUGARGLIDER_POI_MAX_LIMIT", "20")
    configured = Settings()
    assert configured.poi_index_path is not None
    assert configured.poi_index_path.name == "local-pois.json.gz"
    assert configured.poi_missing_index_warning
    assert configured.poi_default_limit == 12
    assert configured.poi_max_limit == 20

    with pytest.raises(ValidationError):
        Settings(poi_default_limit=21, poi_max_limit=20)


def test_auto_tour_corridor_defaults_aliases_and_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = Settings()
    assert defaults.auto_tour_scenic_corridor_radius_m == 600
    assert defaults.auto_tour_water_corridor_radius_m == 350
    assert not defaults.auto_tour_include_broad_attractions

    monkeypatch.setenv("SUGARGLIDER_AUTO_TOUR_SCENIC_CORRIDOR_RADIUS_M", "750")
    monkeypatch.setenv("SUGARGLIDER_AUTO_TOUR_WATER_CORRIDOR_RADIUS_M", "275")
    monkeypatch.setenv("SUGARGLIDER_AUTO_TOUR_INCLUDE_BROAD_ATTRACTIONS", "true")
    configured = Settings()
    assert configured.auto_tour_scenic_corridor_radius_m == 750
    assert configured.auto_tour_water_corridor_radius_m == 275
    assert configured.auto_tour_include_broad_attractions

    with pytest.raises(ValidationError):
        Settings(auto_tour_scenic_corridor_radius_m=49)
    with pytest.raises(ValidationError):
        Settings(auto_tour_water_corridor_radius_m=1_001)


def test_map_environment_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUGARGLIDER_MAP_TILE_URL", "https://map.example/{z}/{x}/{y}")
    monkeypatch.setenv("SUGARGLIDER_MAP_ATTRIBUTION", "Example attribution")
    monkeypatch.setenv("SUGARGLIDER_MAP_INITIAL_LAT", "41.2")
    monkeypatch.setenv("SUGARGLIDER_MAP_INITIAL_LON", "-3.4")
    monkeypatch.setenv("SUGARGLIDER_MAP_INITIAL_ZOOM", "7.5")
    settings = Settings()
    assert settings.map_tile_url == "https://map.example/{z}/{x}/{y}"
    assert settings.map_attribution == "Example attribution"
    assert settings.map_initial_lat == 41.2
    assert settings.map_initial_lon == -3.4
    assert settings.map_initial_zoom == 7.5


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("low_overlap_max_paths", 0),
        ("low_overlap_max_paths", 6),
        ("low_overlap_max_weight_factor", 0.9),
        ("low_overlap_max_weight_factor", 3.1),
        ("low_overlap_max_share_factor", -0.1),
        ("low_overlap_max_share_factor", 1.1),
        ("low_overlap_beam_width", 0),
        ("low_overlap_beam_width", 51),
        ("low_overlap_max_leg_requests", 0),
        ("low_overlap_source_count", 0),
        ("low_overlap_source_count", 4),
    ],
)
def test_invalid_low_overlap_settings_are_rejected(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("map_tile_url", ""),
        ("map_attribution", ""),
        ("map_initial_lat", -90.1),
        ("map_initial_lat", 90.1),
        ("map_initial_lon", -180.1),
        ("map_initial_lon", 180.1),
        ("map_initial_zoom", -0.1),
        ("map_initial_zoom", 22.1),
        ("nature_water_buffer_m", -0.1),
        ("nature_water_buffer_m", 1000.1),
    ],
)
def test_invalid_map_settings_are_rejected(field: str, value: str | float) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: value})
