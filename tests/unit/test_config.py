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
