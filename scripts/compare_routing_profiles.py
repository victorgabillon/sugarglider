#!/usr/bin/env python3
"""Submit the six canonical PR15 examples to the canonical planning API."""

import argparse
import json
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIRECTORY = REPOSITORY_ROOT / "examples" / "profiles"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    return parser.parse_args()


def result_summary(
    path: Path, payload: dict[str, Any], elapsed_s: float
) -> dict[str, Any]:
    candidates = payload.get("candidates")
    first = candidates[0] if isinstance(candidates, list) and candidates else {}
    route = first.get("route", {}) if isinstance(first, dict) else {}
    summary = route.get("summary", {}) if isinstance(route, dict) else {}
    diagnostics = payload.get("search_diagnostics", {})
    return {
        "example": path.name,
        "routing_profile": payload.get("routing_profile"),
        "candidate_count": len(candidates) if isinstance(candidates, list) else 0,
        "recommended_distance_m": summary.get("distance_m"),
        "elapsed_s": round(elapsed_s, 3),
        "cache": diagnostics.get("cache") if isinstance(diagnostics, dict) else None,
    }


def main() -> int:
    args = parse_args()
    paths = sorted(EXAMPLES_DIRECTORY.glob("*.json"))
    results: list[dict[str, Any]] = []
    with httpx.Client(base_url=args.base_url, timeout=args.timeout_seconds) as client:
        for path in paths:
            request = json.loads(path.read_text(encoding="utf-8"))
            started = perf_counter()
            response = client.post("/v2/plans/generate", json=request)
            elapsed_s = perf_counter() - started
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError("canonical planning API returned a non-object")
            results.append(result_summary(path, payload, elapsed_s))
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
