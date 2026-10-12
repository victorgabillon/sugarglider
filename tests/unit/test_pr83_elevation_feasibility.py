"""The PR83 elevation coverage spike is deterministic and cannot publish data."""

import json
import sys
from pathlib import Path

import pytest

from sugarglider.offline_regions.elevation_feasibility import (
    HGT_RAW_BYTES,
    SkadiTile,
    elevation_feasibility_plan,
    main,
    skadi_tiles_for_bounds,
)
from sugarglider.offline_regions.validation import load_spec

ROOT = Path(__file__).resolve().parents[2]


def test_yvelines_tile_plan_uses_real_spec() -> None:
    spec = load_spec(ROOT, "yvelines-ouest-parisien")
    plan = elevation_feasibility_plan(spec.region_id, spec.bounds)
    assert plan["region_id"] == "yvelines-ouest-parisien"
    assert plan["tile_count"] == 4
    assert plan["total_raw_bytes"] == 103_737_608
    assert plan["tiles"] == [
        {
            "path": f"skadi/N{latitude}/N{latitude}E{longitude}.hgt.gz",
            "candidate_url": (
                "https://elevation-tiles-prod.s3.us-east-1.amazonaws.com"
                f"/skadi/N{latitude}/N{latitude}E{longitude}.hgt.gz"
            ),
        }
        for latitude in ("48", "49")
        for longitude in ("001", "002")
    ]


def test_exact_integer_upper_bounds_require_neighbor_tiles() -> None:
    assert [t.path for t in skadi_tiles_for_bounds((2.0, 48.0, 3.0, 49.0))] == [
        "skadi/N48/N48E002.hgt.gz",
        "skadi/N48/N48E003.hgt.gz",
        "skadi/N49/N49E002.hgt.gz",
        "skadi/N49/N49E003.hgt.gz",
    ]


def test_negative_and_zero_degree_tile_naming() -> None:
    assert [t.path for t in skadi_tiles_for_bounds((-0.75, -1.25, 0.1, 0.2))] == [
        f"skadi/{latitude}/{latitude}{longitude}.hgt.gz"
        for latitude in ("S02", "S01", "N00")
        for longitude in ("W001", "E000")
    ]
    assert SkadiTile(0, 0).filename == "N00E000.hgt.gz"
    assert HGT_RAW_BYTES == 25_934_402


@pytest.mark.parametrize(
    "bounds",
    [
        (2.0, 49.0, 1.0, 50.0),
        (2.0, 49.0, 3.0, 49.0),
        (2.0, 49.0, 3.0, float("inf")),
        (float("nan"), 49.0, 3.0, 50.0),
        (179.0, 49.0, 181.0, 50.0),
        (2.0, -86.0, 3.0, 49.0),
    ],
)
def test_invalid_regions_are_rejected(
    bounds: tuple[float, float, float, float],
) -> None:
    with pytest.raises(ValueError, match="invalid regional bounds"):
        skadi_tiles_for_bounds(bounds)


def test_cli_is_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["elevation-feasibility", "--region", "yvelines-ouest-parisien"]
    )
    assert main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["tile_count"] == 4
    assert "not verified" in output["limits"]
    assert list(tmp_path.iterdir()) == []


def test_skadi_cannot_cover_inclusive_east_180_endpoint() -> None:
    with pytest.raises(ValueError, match="180-degree east edge"):
        skadi_tiles_for_bounds((179.0, 48.0, 180.0, 49.0))
