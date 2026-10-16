"""Synthetic end-to-end PR88 evidence → analysis and rejection regressions."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

from sugarglider.analysis.elevation import analyze_elevation
from sugarglider.offline_regions.elevation_analysis import (
    NativeHeightDocument,
    bind_native_profile,
    load_native_profile,
    main,
    read_evidence,
    verify_csv,
)
from sugarglider.offline_regions.native_height_experiment import (
    MAX_INPUT_BYTES,
    HeightPlan,
    NativeResearchResult,
    ResearchRoute,
    sample_routed_geometry,
)


@pytest.fixture
def evidence() -> tuple[
    NativeHeightDocument, HeightPlan, ResearchRoute, NativeResearchResult
]:
    # Duplicate and revisited vertices, and a non-nominal final interval.
    route = ResearchRoute(
        routing_profile="gravel_bike",
        distance_m=153,
        geometry=((2.0, 48.0), (2.0, 48.0), (2.01, 48.0), (2.0, 48.0)),
    )
    points = sample_routed_geometry(route)
    plan = HeightPlan(
        routing_profile=route.routing_profile,
        route_distance_m=route.distance_m,
        geometry_sha256=hashlib.sha256(
            json.dumps(route.geometry, separators=(",", ":")).encode()
        ).hexdigest(),
        source_sha256="a" * 64,
        spacing_m=50,
        maximum_samples=2_048,
        points=points,
    )
    heights = (100.0, 110.0, 105.0, None, 100.0)
    document = NativeHeightDocument.model_validate_json(
        json.dumps(
            {
                "format": "sugarglider-native-height-research-v1",
                "publication_allowed": False,
                "routing_profile": route.routing_profile,
                "geometry_sha256": plan.geometry_sha256,
                "source_sha256": plan.source_sha256,
                "route_distance_m": 153,
                "spacing_m": 50,
                "sample_count": 5,
                "available_count": 4,
                "unavailable_count": 1,
                "maximum_absolute_error_m": 0,
                "samples": [
                    {
                        **point.model_dump(),
                        "height_m": height,
                        "python_height_m": height,
                        "absolute_error_m": 0 if height is not None else None,
                    }
                    for point, height in zip(points, heights, strict=True)
                ],
            }
        )
    )
    native = NativeResearchResult(
        source_sha256=plan.source_sha256,
        input_sha256=hashlib.sha256(plan.model_dump_json().encode()).hexdigest(),
        heights=heights,
    )
    return document, plan, route, native


def test_bound_evidence_keeps_progress_identity_and_unknowns(
    evidence: tuple[
        NativeHeightDocument, HeightPlan, ResearchRoute, NativeResearchResult
    ],
) -> None:
    document, plan, route, native = evidence
    originals = [item.model_dump_json() for item in evidence]
    source = bind_native_profile(*evidence, plan_sha256=native.input_sha256)
    result = analyze_elevation(source)
    assert result.coverage == "partial"
    assert result.total_ascent_m is None
    assert [point.distance_m for point in result.samples] == [0, 50, 100, 150, 153]
    assert [point.height_m for point in result.samples] == list(native.heights)
    assert result.geometry_sha256 == plan.geometry_sha256
    assert result.source_sha256 == document.source_sha256
    assert result.routing_profile == route.routing_profile
    assert [item.model_dump_json() for item in evidence] == originals


@pytest.mark.parametrize(
    "field,value",
    [
        ("geometry_sha256", "c" * 64),
        ("source_sha256", "c" * 64),
        ("route_distance_m", 154),
        ("routing_profile", "hike"),
        ("spacing_m", 51),
    ],
)
def test_mismatched_profile_identity_is_rejected(
    evidence: tuple[
        NativeHeightDocument, HeightPlan, ResearchRoute, NativeResearchResult
    ],
    field: str,
    value: object,
) -> None:
    document, plan, route, native = evidence
    data = document.model_dump(mode="json")
    data[field] = value
    changed = NativeHeightDocument.model_validate_json(json.dumps(data))
    with pytest.raises(ValueError, match="identity mismatch"):
        bind_native_profile(
            changed, plan, route, native, plan_sha256=native.input_sha256
        )


@pytest.mark.parametrize(
    "field,value",
    [("distance_m", 49.0), ("lat", 48.01), ("edge_index", 0), ("edge_fraction", 0.5)],
)
def test_tampered_sample_coordinates_or_progress_are_rejected(
    evidence: tuple[
        NativeHeightDocument, HeightPlan, ResearchRoute, NativeResearchResult
    ],
    field: str,
    value: object,
) -> None:
    document, plan, route, native = evidence
    data = document.model_dump(mode="json")
    data["samples"][1][field] = value
    changed = NativeHeightDocument.model_validate_json(json.dumps(data))
    with pytest.raises(ValueError, match="position/height mismatch"):
        bind_native_profile(
            changed, plan, route, native, plan_sha256=native.input_sha256
        )


def test_plan_native_height_and_byte_identity_tampering_are_rejected(
    evidence: tuple[
        NativeHeightDocument, HeightPlan, ResearchRoute, NativeResearchResult
    ],
) -> None:
    document, plan, route, native = evidence
    with pytest.raises(ValueError, match="identity mismatch"):
        bind_native_profile(*evidence, plan_sha256="f" * 64)
    changed_native = NativeResearchResult(
        source_sha256=native.source_sha256,
        input_sha256=native.input_sha256,
        heights=(101.0, *native.heights[1:]),
    )
    with pytest.raises(ValueError, match="position/height mismatch"):
        bind_native_profile(
            document, plan, route, changed_native, plan_sha256=native.input_sha256
        )
    data = plan.model_dump(mode="json")
    data["points"][1]["distance_m"] = 49
    changed_plan = HeightPlan.model_validate_json(json.dumps(data))
    with pytest.raises(ValueError, match="normalized routed geometry"):
        bind_native_profile(
            document, changed_plan, route, native, plan_sha256=native.input_sha256
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"available_count": 5},
        {"sample_count": 4},
        {"unavailable_count": 0},
        {"maximum_absolute_error_m": 0.001},
    ],
)
def test_malformed_native_summaries_are_rejected(
    evidence: tuple[
        NativeHeightDocument, HeightPlan, ResearchRoute, NativeResearchResult
    ],
    updates: dict[str, object],
) -> None:
    data = evidence[0].model_dump(mode="json")
    data.update(updates)
    with pytest.raises(ValueError):
        NativeHeightDocument.model_validate_json(json.dumps(data))


def test_csv_is_cross_checked_without_rounding(
    evidence: tuple[
        NativeHeightDocument, HeightPlan, ResearchRoute, NativeResearchResult
    ],
) -> None:
    document = evidence[0]
    fields = list(document.samples[0].model_dump())
    csv = ",".join(fields) + "\n"
    csv += "\n".join(
        ",".join(
            "" if value is None else str(value)
            for value in sample.model_dump().values()
        )
        for sample in document.samples
    )
    verify_csv(document, csv.encode())
    for changed in [
        csv.replace("153.0", "152.9"),
        csv + "\n" + csv.splitlines()[-1],
        "\n".join(csv.splitlines()[:-1]),
        csv.replace("height_m,", "bad,"),
    ]:
        with pytest.raises(ValueError):
            verify_csv(document, changed.encode())


def test_file_and_cli_integration(
    evidence: tuple[
        NativeHeightDocument, HeightPlan, ResearchRoute, NativeResearchResult
    ],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    flags = ("--profile", "--plan", "--route", "--native-result")
    arguments = ["elevation-analysis"]
    paths = []
    for flag, model in zip(flags, evidence, strict=True):
        path = tmp_path / f"{flag[2:]}.json"
        path.write_text(model.model_dump_json())
        paths.append(path)
        arguments.extend([flag, str(path)])
    source = load_native_profile(
        profile=paths[0],
        plan=paths[1],
        route=paths[2],
        native_result=paths[3],
        csv_path=None,
    )
    assert source.samples[-1].distance_m == 153
    monkeypatch.setattr(sys, "argv", arguments)
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["coverage"] == "partial"
    assert result["total_ascent_m"] is None
    assert result["algorithm_version"] == "distance-box-v1"
    # Even whitespace changes break the native request's exact-byte binding.
    paths[1].write_bytes(paths[1].read_bytes() + b"\n")
    assert main() == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "identity mismatch" in output.err


def test_file_reads_are_bounded(tmp_path: Path) -> None:
    path = tmp_path / "oversize.json"
    path.write_bytes(b" " * (MAX_INPUT_BYTES + 1))
    with pytest.raises(ValueError, match="byte limit"):
        read_evidence(path)
