"""Map neutral submitted-candidate validation to reversal's public failure."""

from sugarglider.planning.models import PlanRequest
from sugarglider.planning.result import PlanCandidate
from sugarglider.planning.submitted_candidate import (
    SubmittedCandidateInvalidError,
    validate_submitted_candidate,
)


class ReverseSourceInvalidError(ValueError):
    """The posted source request and candidate do not form a trusted pair."""


def validate_reverse_source(request: PlanRequest, candidate: PlanCandidate) -> None:
    """Preserve the reversal-specific error contract over neutral validation."""
    try:
        validate_submitted_candidate(request, candidate)
    except SubmittedCandidateInvalidError as exc:
        raise ReverseSourceInvalidError(
            str(exc).replace("submitted", "source")
        ) from exc
