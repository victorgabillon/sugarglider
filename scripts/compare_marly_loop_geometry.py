"""Compare bounded Marly generation with loop geometry off and preferred."""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from sugarglider.domain.generation import GeneratedCandidate, RouteGenerationResult

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REQUEST_PATH = (
    REPOSITORY_ROOT / "examples/marly/all-pois-generation-request.json"
)
GPX_NAMESPACE = {"g": "http://www.topografix.com/GPX/1/1"}
type HigherPriorityKey = tuple[int, float, float, float]


@dataclass(frozen=True)
class TimedResult:
    result: RouteGenerationResult
    elapsed_s: float


def _post_json(url: str, payload: object, *, timeout: float = 900) -> bytes:
    request = Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        return cast(bytes, response.read())


def _generate(api_url: str, payload: dict[str, object]) -> TimedResult:
    started = time.perf_counter()
    response = _post_json(
        f"{api_url.rstrip('/')}/v1/routes/generate",
        payload,
    )
    return TimedResult(
        result=RouteGenerationResult.model_validate_json(response),
        elapsed_s=time.perf_counter() - started,
    )


def _geometry_penalty(candidate: GeneratedCandidate) -> float | None:
    geometry = candidate.route.analysis.loop_geometry
    return geometry.penalty_breakdown.total if geometry is not None else None


def _best_geometry(
    candidates: tuple[GeneratedCandidate, ...],
) -> GeneratedCandidate | None:
    known = tuple(
        candidate
        for candidate in candidates
        if _geometry_penalty(candidate) is not None
    )
    return min(
        known,
        key=lambda candidate: (_geometry_penalty(candidate), candidate.signature),
        default=None,
    )


def _higher_priority_key(
    candidate: GeneratedCandidate, *, low_overlap: bool
) -> HigherPriorityKey:
    tolerance_class = 0 if candidate.within_tolerance else 1
    outside_distance_pressure = (
        candidate.score.distance_error_ratio if not candidate.within_tolerance else 0.0
    )
    repetition = candidate.route.analysis.repetition.repeated_distance.share
    backtracking = candidate.route.analysis.immediate_backtrack.share
    if low_overlap:
        return (
            tolerance_class,
            outside_distance_pressure,
            repetition,
            backtracking,
        )
    return (
        tolerance_class,
        outside_distance_pressure,
        backtracking,
        repetition,
    )


def _preference_contract(
    control: GeneratedCandidate,
    preferred: GeneratedCandidate,
    *,
    low_overlap: bool,
) -> tuple[bool, bool, str]:
    """Return contract validity, promotion acceptance, and exact decision reason."""
    if preferred.signature == control.signature:
        return True, False, "retained the exact Off control"
    control_higher = _higher_priority_key(control, low_overlap=low_overlap)
    preferred_higher = _higher_priority_key(preferred, low_overlap=low_overlap)
    if preferred_higher < control_higher:
        return True, True, "replaced control: higher-priority tuple improved"
    if preferred_higher > control_higher:
        return False, False, "invalid replacement: higher-priority tuple regressed"
    control_penalty = _geometry_penalty(control)
    preferred_penalty = _geometry_penalty(preferred)
    if preferred_penalty is None:
        return False, False, "invalid replacement: preferred shape is not evaluated"
    if control_penalty is None or preferred_penalty < control_penalty:
        return (
            True,
            True,
            "replaced control: equal higher-priority tuple and lower shape penalty",
        )
    return (
        False,
        False,
        "invalid replacement: equal higher-priority tuple without lower shape penalty",
    )


def _candidate_report(label: str, candidate: GeneratedCandidate | None) -> None:
    if candidate is None:
        print(f"  {label}: none")
        return
    analysis = candidate.route.analysis
    geometry = analysis.loop_geometry
    nature = analysis.nature
    if geometry is None:
        print(
            f"  {label}: signature={candidate.signature}; loop geometry=not evaluated"
        )
        return
    print(
        f"  {label}: signature={candidate.signature}; "
        f"construction={candidate.construction}; "
        f"distance={candidate.route.summary.distance_m:.1f} m; "
        f"target error={candidate.target_error_m:.1f} m; "
        f"backtracking={analysis.immediate_backtrack.share:.6f}; "
        f"repetition={analysis.repetition.repeated_distance.share:.6f}; "
        f"shape penalty={geometry.penalty_breakdown.total:.6f}; "
        f"compactness={geometry.compactness:.6f}; "
        f"sector balance={geometry.sector_balance:.6f}; "
        f"near parallel={geometry.near_parallel.share:.6f}; "
        f"self crossings={geometry.self_crossing_count}; "
        f"elongation={geometry.elongation:.6f}; "
        f"nature score={nature.nature_score if nature is not None else 'not evaluated'}"
    )


def _result_report(preference: str, timed: TimedResult) -> None:
    result = timed.result
    search = result.search
    recommended = result.candidates[0] if result.candidates else None
    best_geometry = _best_geometry(result.candidates)
    base_evaluated = (
        search.evaluated_candidate_count - search.loop_geometry_extra_evaluated_count
    )
    print(f"\nLoop geometry {preference}")
    _candidate_report("recommended", recommended)
    if best_geometry is recommended:
        print("  best returned geometry: same as recommended")
    else:
        _candidate_report("best returned geometry", best_geometry)
    print(
        "  GraphHopper accounting: "
        f"base budget={search.base_search_budget}; "
        f"geometry extra budget={search.loop_geometry_extra_evaluation_budget}; "
        f"base evaluations={base_evaluated}; "
        f"extra evaluations={search.loop_geometry_extra_evaluated_count}; "
        f"extra successes={search.loop_geometry_extra_successful_count}; "
        f"extra rejections={search.loop_geometry_extra_rejected_count}; "
        f"total evaluations={search.evaluated_candidate_count}/{search.search_budget}; "
        f"round-trip calls={search.round_trip_proposal_count}; "
        f"derived proposal sequences={search.derived_proposal_sequence_count}; "
        f"alternative-leg calls={search.alternative_leg_request_count}/"
        f"{search.low_overlap_request_budget}; "
        f"alternative paths={search.alternative_path_count}"
    )
    print(
        "  Summary geometry: "
        f"recommended={search.recommended_loop_geometry_penalty}; "
        f"best available={search.best_available_loop_geometry_penalty}"
    )
    print(f"  Runtime: {timed.elapsed_s:.3f} s")
    print("  Warnings: " + (", ".join(search.warnings) or "none"))


def _export_gpx(api_url: str, preference: str, candidate: GeneratedCandidate) -> Path:
    path = Path(f"/tmp/sugarglider-marly-loop-{preference}.gpx")
    payload = candidate.route.model_dump(mode="json")
    path.write_bytes(
        _post_json(
            f"{api_url.rstrip('/')}/v1/routes/gpx/from-result",
            payload,
        )
    )
    root = ElementTree.parse(path).getroot()
    if len(root.findall("g:trk", GPX_NAMESPACE)) != 1:
        raise ValueError(f"{path} must contain exactly one GPX track")
    if len(root.findall("g:trk/g:trkseg", GPX_NAMESPACE)) != 1:
        raise ValueError(f"{path} must contain exactly one GPX track segment")
    if root.findall("g:rte", GPX_NAMESPACE):
        raise ValueError(f"{path} must not contain a GPX route")
    if root.findall(".//g:extensions", GPX_NAMESPACE):
        raise ValueError(f"{path} must not contain analysis extensions")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare loop-shape off/prefer generation with every other Marly "
            "request field unchanged and both bounded lanes explicit."
        )
    )
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--request", type=Path, default=DEFAULT_REQUEST_PATH)
    arguments = parser.parse_args()

    base_payload: dict[str, object] = json.loads(
        arguments.request.read_text(encoding="utf-8")
    )
    results: dict[str, TimedResult] = {}
    for preference in ("off", "prefer"):
        payload = {**base_payload, "loop_geometry_preference": preference}
        results[preference] = _generate(arguments.api_url, payload)
        Path(f"/tmp/sugarglider-marly-loop-{preference}.json").write_text(
            results[preference].result.model_dump_json(indent=2),
            encoding="utf-8",
        )

    off_search = results["off"].result.search
    prefer_search = results["prefer"].result.search
    accounting_errors: list[str] = []
    if off_search.base_search_budget != prefer_search.base_search_budget:
        accounting_errors.append("Off and Prefer base budgets differ")
    if off_search.loop_geometry_extra_evaluation_budget != 0:
        accounting_errors.append("Off unexpectedly exposes a geometry extra budget")
    if any(
        (
            off_search.loop_geometry_extra_evaluated_count,
            off_search.loop_geometry_extra_successful_count,
            off_search.loop_geometry_extra_rejected_count,
        )
    ):
        accounting_errors.append("Off unexpectedly used geometry extra accounting")
    if prefer_search.search_budget != (
        prefer_search.base_search_budget
        + prefer_search.loop_geometry_extra_evaluation_budget
    ):
        accounting_errors.append("Prefer total budget is not base plus geometry extra")
    off_base_evaluated = (
        off_search.evaluated_candidate_count
        - off_search.loop_geometry_extra_evaluated_count
    )
    prefer_base_evaluated = (
        prefer_search.evaluated_candidate_count
        - prefer_search.loop_geometry_extra_evaluated_count
    )
    if off_base_evaluated != prefer_base_evaluated:
        accounting_errors.append("Prefer primary evaluations do not match Off")
    if off_search.round_trip_proposal_count != prefer_search.round_trip_proposal_count:
        accounting_errors.append("balanced derivation changed round-trip call count")
    if (
        prefer_search.loop_geometry_extra_evaluated_count
        > prefer_search.loop_geometry_extra_evaluation_budget
    ):
        accounting_errors.append("Prefer exceeded its geometry extra budget")
    if prefer_search.loop_geometry_extra_evaluated_count != (
        prefer_search.loop_geometry_extra_successful_count
        + prefer_search.loop_geometry_extra_rejected_count
    ):
        accounting_errors.append("Prefer extra outcomes do not sum to evaluations")
    for label, search in (("Off", off_search), ("Prefer", prefer_search)):
        if search.evaluated_candidate_count > search.search_budget:
            accounting_errors.append(f"{label} exceeded its total evaluation budget")
    if (
        off_search.low_overlap_request_budget
        != prefer_search.low_overlap_request_budget
    ):
        accounting_errors.append("Off and Prefer low-overlap budgets differ")

    for preference in ("off", "prefer"):
        _result_report(preference, results[preference])
        candidates = results[preference].result.candidates
        if candidates:
            output = _export_gpx(arguments.api_url, preference, candidates[0])
            print(f"  Selected-candidate GPX: {output}")

    off_candidates = results["off"].result.candidates
    prefer_candidates = results["prefer"].result.candidates
    if not off_candidates or not prefer_candidates:
        print(
            "\nComparison contract: FAIL — one mode returned no candidate",
            file=sys.stderr,
        )
        return 1
    control = off_candidates[0]
    preferred = prefer_candidates[0]
    low_overlap = base_payload.get("path_selection_mode") == "low_overlap"
    control_higher = _higher_priority_key(control, low_overlap=low_overlap)
    preferred_higher = _higher_priority_key(preferred, low_overlap=low_overlap)
    valid, promotion_accepted, reason = _preference_contract(
        control,
        preferred,
        low_overlap=low_overlap,
    )
    control_retained = any(
        candidate.signature == control.signature for candidate in prefer_candidates
    )
    print("\nPreference contract")
    print(f"  Control signature: {control.signature}")
    print(f"  Preferred signature: {preferred.signature}")
    print(f"  Higher-priority order: {'low-overlap' if low_overlap else 'ordinary'}")
    print(f"  Control higher-priority tuple: {control_higher}")
    print(f"  Preferred higher-priority tuple: {preferred_higher}")
    comparison = (
        "better"
        if preferred_higher < control_higher
        else "worse"
        if preferred_higher > control_higher
        else "equal"
    )
    print(f"  Higher-priority comparison: {comparison}")
    print(f"  Geometry promotion accepted: {'yes' if promotion_accepted else 'no'}")
    retained_label = "yes" if control_retained else "no"
    print(f"  Control retained in Prefer candidates: {retained_label}")
    print(f"  Decision reason: {reason}")
    if not control_retained:
        accounting_errors.append("Prefer candidate list dropped the Off control")
    if accounting_errors:
        for error in accounting_errors:
            print(f"  Accounting error: {error}", file=sys.stderr)
    if not valid or accounting_errors:
        print("Comparison contract: FAIL", file=sys.stderr)
        return 1
    print("Comparison contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
