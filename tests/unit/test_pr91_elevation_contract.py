"""Synthetic portable runtime and exact geometry identity contracts."""

import hashlib
import json
import struct
from pathlib import Path

from sugarglider.analysis.elevation import (
    ElevationParameters,
    ElevationProfile,
    analyze_elevation,
)
from sugarglider.offline_regions.native_height_experiment import (
    ResearchRoute,
    sample_routed_geometry,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/elevation"


def test_native_runtime_fixtures_are_the_unchanged_python_reference() -> None:
    for case in json.loads((FIXTURES / "runtime-v1.json").read_bytes()):
        profile = ElevationProfile.model_validate_json(json.dumps(case["input"]))
        policy = ElevationParameters.model_validate_json(json.dumps(case["parameters"]))
        assert (
            analyze_elevation(profile, policy).model_dump(mode="json")
            == case["expected"]
        )


def test_portable_sampling_and_binary_geometry_fingerprints() -> None:
    for case in json.loads((FIXTURES / "sampling-v1.json").read_bytes()):
        geometry = case["geometry"]
        payload = b"sugarglider-route-geometry-v1\0" + struct.pack(">I", len(geometry))
        for longitude, latitude in geometry:
            payload += struct.pack(
                ">dd", float(longitude) or 0.0, float(latitude) or 0.0
            )
        assert hashlib.sha256(payload).hexdigest() == case["geometry_sha256"]
        route = ResearchRoute.model_validate_json(
            json.dumps(
                dict(
                    routing_profile="hike",
                    distance_m=case["distance_m"],
                    geometry=geometry,
                )
            )
        )
        samples = sample_routed_geometry(
            route, spacing_m=max(50, route.distance_m / 2047)
        )
        assert [[p.distance_m, p.lat, p.lon] for p in samples] == case["samples"]
