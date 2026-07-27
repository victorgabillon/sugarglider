"""Neutral submitted-candidate trust validation."""

import pytest

from sugarglider.planning.direction.traversal import build_plan_traversal
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.models import PLAN_REQUEST_ADAPTER, PlanRequest
from sugarglider.planning.result import PlanCandidate
from sugarglider.planning.submitted_candidate import (
    SubmittedCandidateInvalidError,
    validate_submitted_candidate,
)


def test_neutral_validation_rejects_missing_or_incorrect_exact_anchor_identity(
    saved_route_source_request: PlanRequest,
    saved_route_candidate: PlanCandidate,
) -> None:
    document = saved_route_source_request.model_dump(mode="json")
    document["waypoints"] = [
        {
            "id": "exact-middle",
            "name": "Exact middle",
            "coordinate": {"lat": 48.87, "lon": 2.1},
            "constraint_strength": "exact",
        }
    ]
    request = PLAN_REQUEST_ADAPTER.validate_python(document)
    traversal = build_plan_traversal(
        request,
        CandidateDraft(
            route=saved_route_candidate.route,
            routing_points=(),
            topology=request.topology,
            construction="submitted_candidate_test",
            search_family="submitted_candidate",
        ),
    )
    candidate = saved_route_candidate.model_copy(update={"traversal": traversal})
    validate_submitted_candidate(request, candidate)

    exact = next(
        anchor for anchor in traversal.anchors if anchor.kind == "exact_waypoint"
    )
    incorrect = exact.model_copy(update={"id": "exact/wrong-identity"})
    tampered_traversal = traversal.model_copy(
        update={
            "anchors": tuple(
                incorrect if anchor is exact else anchor for anchor in traversal.anchors
            )
        }
    )
    with pytest.raises(SubmittedCandidateInvalidError, match="traversal|exact"):
        validate_submitted_candidate(
            request,
            candidate.model_copy(update={"traversal": tampered_traversal}),
        )
