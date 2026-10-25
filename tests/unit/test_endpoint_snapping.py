"""Canonical endpoint intent survives storage and cannot weaken native bounds."""

import json
from math import degrees
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from sugarglider.planning.models import PLAN_REQUEST_ADAPTER, EndpointSnapPolicy
from sugarglider.planning.pipeline import PlanService
from sugarglider.planning.result import PlanCandidate
from sugarglider.planning.validation import (
    CandidateEvaluationError,
    validate_search_candidate,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def request_payload() -> dict[str, Any]:
    fixture = cast(
        dict[str, Any],
        json.loads((FIXTURES / "pr41_local_candidates.json").read_text()),
    )
    return cast(dict[str, Any], fixture["cases"][0]["request"])


def test_absent_policy_keeps_existing_serialized_request() -> None:
    request = PLAN_REQUEST_ADAPTER.validate_python(request_payload())
    assert request.endpoint_snap_policy is None
    assert "endpoint_snap_policy" not in request.model_dump(mode="json")


@pytest.mark.parametrize("mode", ["near", "exact"])
def test_explicit_policy_round_trips_without_changing_coordinates(mode: str) -> None:
    payload = request_payload()
    payload["endpoint_snap_policy"] = {"start": mode, "end": "exact"}
    request = PLAN_REQUEST_ADAPTER.validate_python(payload)
    restored = PLAN_REQUEST_ADAPTER.validate_json(request.model_dump_json())
    assert restored == request
    assert restored.start.model_dump(mode="json") == payload["start"]
    assert restored.endpoint_snap_policy is not None
    assert restored.endpoint_snap_policy.start == mode
    assert restored.endpoint_snap_policy.end == "exact"


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"start": "near"},
        {"start": "near", "end": "unlimited"},
        {"start": "near", "end": "near", "maximum_m": 10000},
    ],
)
def test_policy_rejects_missing_fields_and_unlimited_bypass(value: object) -> None:
    with pytest.raises(ValidationError):
        EndpointSnapPolicy.model_validate(value)


@pytest.mark.parametrize("mode,maximum", [("near", 150.0), ("exact", 25.0)])
@pytest.mark.parametrize("offset", [-0.1, 0.0, 0.1])
def test_snapshot_trust_boundary_enforces_explicit_policy(
    mode: str, maximum: float, offset: float
) -> None:
    fixture = cast(
        dict[str, Any], json.loads((FIXTURES / "pr41_local_gpx.json").read_text())
    )
    candidate = PlanCandidate.model_validate(fixture["candidate"])
    first, last = candidate.route.geometry[0], candidate.route.geometry[-1]
    payload = request_payload()
    payload.update(
        routing_profile=candidate.routing_profile,
        topology="point_to_point",
        start={
            "lat": first[1] - degrees((maximum + offset) / 6371008.8),
            "lon": first[0],
            "name": "Requested Start",
        },
        end={"lat": last[1], "lon": last[0], "name": "End"},
        waypoints=[],
        endpoint_snap_policy={"start": mode, "end": "exact"},
    )
    request = PLAN_REQUEST_ADAPTER.validate_python(payload)
    if offset > 0:
        with pytest.raises(CandidateEvaluationError, match="endpoint snap policy"):
            validate_search_candidate(request, candidate)
    else:
        assert validate_search_candidate(request, candidate) is candidate


@pytest.mark.asyncio
async def test_development_server_does_not_ignore_native_near_policy() -> None:
    payload = request_payload()
    payload["endpoint_snap_policy"] = {"start": "near", "end": "exact"}
    # No producer is configured: rejection must precede every routing dispatch.
    service = object.__new__(PlanService)
    with pytest.raises(ValueError, match="on-device planner"):
        await service.generate(PLAN_REQUEST_ADAPTER.validate_python(payload))
