"""Portable synthetic golden results for future native/UI contract consumers."""

import json
from pathlib import Path

from sugarglider.analysis.elevation import (
    ElevationParameters,
    ElevationProfile,
    analyze_elevation,
)


def test_versioned_portable_contract() -> None:
    path = Path(__file__).parents[1] / "fixtures/elevation/contract-v1.json"
    cases = json.loads(path.read_text())
    for case in cases:
        profile = ElevationProfile.model_validate_json(json.dumps(case["input"]))
        parameters = ElevationParameters.model_validate_json(
            json.dumps(case["parameters"])
        )
        assert (
            analyze_elevation(profile, parameters).model_dump(mode="json")
            == (case["expected"])
        ), case["name"]
