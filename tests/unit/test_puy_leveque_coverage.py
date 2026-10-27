"""Bounded regional configuration and Copernicus halo admission, without data."""

import json
from pathlib import Path

import pytest

from sugarglider.offline_regions.elevation_layout import elevation_paths
from sugarglider.offline_regions.terrain_conversion import copernicus_targets
from sugarglider.offline_regions.terrain_source import TerrainSources
from sugarglider.offline_regions.validation import load_spec

ROOT = Path(__file__).resolve().parents[2]


def lot_sources() -> TerrainSources:
    return TerrainSources.model_validate_json(
        (ROOT / "offline-regions/sources/copernicus-2021-puy-leveque.json").read_bytes()
    )


def test_lot_spec_has_complete_five_component_identity_and_central_town() -> None:
    spec = load_spec(ROOT, "puy-leveque-vallee-lot")
    assert spec.bounds == (0.9, 44.3, 1.6, 44.75)
    west, south, east, north = spec.bounds
    assert west + 0.15 < 1.137 < east - 0.15
    assert south + 0.15 < 44.504 < north - 0.15
    assert len(set(spec.component_ids)) == 5
    assert spec.routing.engine_version == "3.9.1"
    assert elevation_paths(spec.bounds) == (
        "elevation/skadi/N44/N44E000.hgt.gz",
        "elevation/skadi/N44/N44E001.hgt.gz",
    )
    assert copernicus_targets(lot_sources(), spec.bounds) == ((44, 0), (44, 1))


def test_legacy_copernicus_layout_still_emits_the_same_four_tiles() -> None:
    pins = TerrainSources.model_validate_json(
        (ROOT / "offline-regions/sources/copernicus-2021-yvelines.json").read_bytes()
    )
    assert copernicus_targets(pins, None) == ((48, 1), (48, 2), (49, 1), (49, 2))


@pytest.mark.parametrize("removed", [0, 1, 3, 6, 7])
def test_missing_halo_or_geoid_is_rejected(removed: int) -> None:
    value = lot_sources().model_dump(mode="json")
    del value["files"][removed]
    with pytest.raises(ValueError, match="incomplete"):
        TerrainSources.model_validate_json(json.dumps(value))


@pytest.mark.parametrize("fault", ["duplicate", "wrong_url", "noncontiguous"])
def test_mismatched_source_sets_are_rejected(fault: str) -> None:
    value = lot_sources().model_dump(mode="json")
    if fault == "duplicate":
        value["files"][1] = value["files"][0]
    elif fault == "wrong_url":
        value["files"][0]["url"] = "https://example.org/unverified.tif"
    else:
        for row in value["files"]:
            row["filename"] = row["filename"].replace("N43", "N42")
            row["url"] = row["url"].replace("N43", "N42")
    with pytest.raises(ValueError, match="incomplete"):
        TerrainSources.model_validate_json(json.dumps(value))


@pytest.mark.parametrize(
    "bounds",
    [
        (0.9, 44.3, 2.0, 44.75),
        (0.9, 43.9, 1.48, 44.75),
        (1.0, 44.3, 1.48, 44.75),
        (0.9, 44.3, 1.48, 45.0),
        (0.9, float("nan"), 1.48, 44.75),
    ],
)
def test_uncovered_bounds_never_synthesize_a_halo(
    bounds: tuple[float, float, float, float],
) -> None:
    with pytest.raises(ValueError):
        copernicus_targets(lot_sources(), bounds)
