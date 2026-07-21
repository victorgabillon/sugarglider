"""One-shot offline migration is strict, deterministic, and idempotent."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from sugarglider.planning.models import PLAN_REQUEST_ADAPTER

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "migrate_plan_json.py"


def _migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migrate_plan_json", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_checked_in_examples_are_canonical_and_idempotent() -> None:
    migrate = _migration_module().migrate_document
    for path in sorted((ROOT / "examples" / "marly").glob("*.json")):
        source = json.loads(path.read_text(encoding="utf-8"))
        canonical = PLAN_REQUEST_ADAPTER.validate_python(source)
        migrated, assumptions = migrate(source)
        assert migrated == canonical.model_dump(mode="json")
        assert assumptions == ("input is already canonical",)


def test_known_legacy_waypoint_shape_migrates_with_explicit_assumptions() -> None:
    migrated, assumptions = _migration_module().migrate_document(
        {
            "name": "Old route",
            "points": [
                {"lat": 48.87, "lon": 2.09, "name": "Start"},
                {"lat": 48.88, "lon": 2.10, "name": "Inside"},
            ],
            "close_loop": True,
            "target_distance_m": 10_000,
            "tolerance_m": 1_000,
        }
    )
    assert migrated["kind"] == "waypoint_route"
    assert migrated["topology"] == "loop"
    assert migrated["start"]["name"] == "Start"
    assert len(assumptions) == 2


def test_ambiguous_legacy_input_is_rejected() -> None:
    module = _migration_module()
    with pytest.raises(module.MigrationError, match="topology is ambiguous"):
        module.migrate_document(
            {
                "name": "Ambiguous",
                "points": [
                    {"lat": 48.87, "lon": 2.09},
                    {"lat": 48.88, "lon": 2.10},
                ],
                "target_distance_m": 10_000,
            }
        )


@pytest.mark.parametrize("name", ["Marly ordered-anchor example", "Anything else"])
def test_missing_target_never_depends_on_document_name(name: str) -> None:
    module = _migration_module()
    source = {
        "name": name,
        "points": [
            {"lat": 48.87, "lon": 2.09},
            {"lat": 48.88, "lon": 2.10},
        ],
        "close_loop": False,
    }
    with pytest.raises(module.MigrationError, match="--target-distance-m"):
        module.migrate_document(source)


def test_direct_open_route_migrates_with_explicit_target_override() -> None:
    migrated, assumptions = _migration_module().migrate_document(
        {
            "name": "Direct",
            "points": [
                {"lat": 48.87, "lon": 2.09},
                {"lat": 48.88, "lon": 2.10},
            ],
            "close_loop": False,
        },
        target_distance_m=5_000,
    )
    assert migrated["waypoints"] == []
    assert migrated["topology"] == "point_to_point"
    assert "used target distance override 5000 m" in assumptions
