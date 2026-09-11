"""Production region inputs and resource admission, without Docker or map data."""

import os
import subprocess
from pathlib import Path

import pytest

from sugarglider.offline_regions.validation import load_spec

ROOT = Path(__file__).resolve().parents[2]


def test_ile_de_france_uses_one_matching_region_and_map_contract() -> None:
    spec = load_spec(ROOT, "ile-de-france")
    assert spec.display_name == "Île-de-France"
    assert spec.bounds == (1.445097, 48.11918, 3.560409, 49.24271)
    assert spec.routing.access_modes == ("foot", "bicycle")
    assert len(set(spec.component_ids)) == 4
    assert not any("dev" in identity for identity in spec.component_ids)


@pytest.mark.parametrize(
    ("memory", "cpus", "heap"),
    [("3072", "2", "2304"), ("512", "1", "384"), ("32768", "16", "24576")],
)
def test_resource_limits_preserve_explicit_bounds(
    memory: str, cpus: str, heap: str
) -> None:
    result = subprocess.run(
        (
            "sh",
            "-c",
            '. "$1"\n'
            'printf "%s|%s|%s" "$SUGARGLIDER_BUILD_MEMORY_MB" '
            '"$SUGARGLIDER_BUILD_CPUS" "$SUGARGLIDER_BUILD_JAVA_HEAP_MB"',
            "check",
            str(ROOT / "scripts/offline_build_resources.sh"),
        ),
        env={
            **os.environ,
            "SUGARGLIDER_BUILD_MEMORY_MB": memory,
            "SUGARGLIDER_BUILD_CPUS": cpus,
        },
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == f"{memory}|{cpus}|{heap}"


@pytest.mark.parametrize(
    ("memory", "cpus"),
    [
        ("511", "2"),
        ("32769", "2"),
        ("3072", "0"),
        ("3072", "17"),
        ("99999999999999999999999999", "2"),
        ("3072", "1.5"),
        ("03", "2"),
        ("1000:1", "2"),
        ("$(false)", "2"),
    ],
)
@pytest.mark.parametrize("builder", ["map", "routing"])
def test_invalid_resource_configuration_stops_before_tools(
    memory: str, cpus: str, builder: str
) -> None:
    arguments = (
        ("scripts/build_pr36_map_pack.sh", "ile-de-france", "/no-source.osm.pbf")
        if builder == "map"
        else (
            "scripts/build_pr33_valhalla_pack.sh",
            "ile-de-france-v1",
            "1",
            "48",
            "3",
            "49",
        )
    )
    result = subprocess.run(
        ("sh", *arguments),
        cwd=ROOT,
        env={
            **os.environ,
            "SUGARGLIDER_BUILD_MEMORY_MB": memory,
            "SUGARGLIDER_BUILD_CPUS": cpus,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "Build " in result.stderr
