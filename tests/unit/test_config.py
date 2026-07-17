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
    ],
)
def test_invalid_map_settings_are_rejected(field: str, value: str | float) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: value})
