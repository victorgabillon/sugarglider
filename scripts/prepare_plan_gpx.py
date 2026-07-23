"""Validate one canonical plan summary and prepare its selected-candidate GPX input."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sugarglider.planning.plan_summary import (
    PlanSummaryError,
    prepare_candidate_request,
)


def main(argv: Sequence[str] | None = None) -> int:
    args = tuple(argv if argv is not None else sys.argv[1:])
    if len(args) != 2:
        raise SystemExit(
            "usage: prepare_plan_gpx.py PLAN_RESULT.json CANDIDATE_REQUEST.json"
        )
    source, destination = map(Path, args)
    try:
        with source.open(encoding="utf-8") as stream:
            document: Any = json.load(stream)
        summary, request = prepare_candidate_request(document)
        with destination.open("w", encoding="utf-8") as stream:
            json.dump(request, stream, ensure_ascii=False, separators=(",", ":"))
    except (OSError, json.JSONDecodeError, PlanSummaryError) as exc:
        raise SystemExit(f"invalid canonical plan response: {exc}") from None
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
