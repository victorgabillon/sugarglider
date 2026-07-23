"""Focused current-schema tests for the Marly generation helper."""

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from sugarglider.planning.plan_summary import (
    PlanSummaryError,
    prepare_candidate_request,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _result(*, repaired: bool = False) -> dict[str, Any]:
    details = {
        "construction": ("spur_closure_repair" if repaired else "point_to_point_direct")
    }
    if repaired:
        details.update(
            repeated_distance_improvement_m="1900.0",
            immediate_backtracking_improvement_m="1750.0",
        )
    return {
        "schema_version": 1,
        "kind": "auto_tour",
        "candidates": [
            {
                "id": "candidate-1",
                "rank": 1,
                "roles": ["harmonious"],
                "route": {
                    "summary": {"distance_m": 41_200.0},
                    "geometry": [[2.0, 48.0], [2.1, 48.1]],
                    "analysis": {
                        "spurs": {
                            "spur_count": 2,
                            "total_repeated_distance_m": 2400.0,
                        }
                    },
                },
                "diagnostics": {
                    "safety_eligible": True,
                    "details": details,
                },
                "reached_stops": [{}, {}],
                "approximated_stops": [{}],
                "dropped_stops": [{}, {}, {}],
            }
        ],
    }


def test_summary_uses_current_outcomes_and_tolerates_no_repair_provenance() -> None:
    summary, request = prepare_candidate_request(_result())

    assert "2 reached/1 approximated/3 dropped" in summary
    assert "spurs=2; spur_repeated=2400.0 m" in summary
    assert "construction=point_to_point_direct" in summary
    assert "repair_improvement" not in summary
    assert request["schema_version"] == 1
    candidate = request["candidate"]
    assert isinstance(candidate, dict)
    assert candidate["id"] == "candidate-1"


def test_repair_summary_prints_both_positive_improvements() -> None:
    summary, _request = prepare_candidate_request(_result(repaired=True))

    assert "construction=spur_closure_repair" in summary
    assert "1900.0 m repeated/1750.0 m immediate backtracking" in summary


def test_obsolete_selected_stops_shape_fails_clearly() -> None:
    document = _result()
    candidate = document["candidates"][0]
    candidate.pop("reached_stops")
    candidate["selected_stops"] = []

    with pytest.raises(PlanSummaryError, match="reached stops must be an array"):
        prepare_candidate_request(document)


def test_cli_returns_clear_error_for_invalid_schema(tmp_path: Path) -> None:
    source = tmp_path / "invalid.json"
    destination = tmp_path / "candidate.json"
    source.write_text('{"schema_version": 1, "candidates": []}', encoding="utf-8")

    completed = subprocess.run(
        (
            sys.executable,
            str(REPOSITORY_ROOT / "scripts/prepare_plan_gpx.py"),
            str(source),
            str(destination),
        ),
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "invalid canonical plan response:" in completed.stderr
    assert not destination.exists()


def test_shell_uses_fail_with_body_and_never_reads_selected_stops() -> None:
    shell = (REPOSITORY_ROOT / "scripts/generate_marly.sh").read_text(encoding="utf-8")

    assert shell.count("curl --fail-with-body") == 2
    assert "prepare_plan_gpx.py" in shell
    assert "selected_stops" not in shell
