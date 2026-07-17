#!/bin/sh
set -eu

API_URL=${API_URL:-http://localhost:8000}
JSON_OUTPUT=${1:-${JSON_OUTPUT:-/tmp/sugarglider-marly-all-pois.json}}
GPX_OUTPUT=${2:-${GPX_OUTPUT:-/tmp/sugarglider-marly-all-pois.gpx}}
REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
REQUEST_PATH="$REPOSITORY_ROOT/examples/marly/all-pois-generation-request.json"
START_TIME=$(python -c 'import time; print(time.monotonic())')

curl --fail --silent --show-error "$API_URL/ready" >/dev/null
curl --fail --silent --show-error \
    --header "Content-Type: application/json" \
    --data-binary "@$REQUEST_PATH" \
    --output "$JSON_OUTPUT" \
    "$API_URL/v1/routes/generate"

candidate_count=$(python - "$JSON_OUTPUT" <<'PY'
import json
import math
import sys

with open(sys.argv[1], encoding="utf-8") as response_file:
    response = json.load(response_file)

search = response["search"]
baseline = response["baseline"]
candidates = response["candidates"]
print(f"Search status: {search['status']}", file=sys.stderr)
print(
    f"Fixed-order baseline: {baseline['summary']['distance_m']:.1f} m",
    file=sys.stderr,
)
print(
    f"Best mandatory-order route: {search['best_order_distance_m']:.1f} m",
    file=sys.stderr,
)
print(
    "Repetition: "
    f"fixed={100 * search['fixed_order_repeated_share']:.1f}%, "
    f"optimized={100 * search['best_order_repeated_share']:.1f}%",
    file=sys.stderr,
)
print(
    "Immediate backtracking: "
    f"fixed={100 * search['fixed_order_backtrack_share']:.1f}%, "
    f"optimized={100 * search['best_order_backtrack_share']:.1f}%",
    file=sys.stderr,
)
print(
    "Evaluations: "
    f"{search['evaluated_candidate_count']}/{search['search_budget']} full, "
    f"orders={search['evaluated_order_count']} evaluated/"
    f"{search['successful_order_count']} successful/"
    f"{search['rejected_order_count']} rejected",
    file=sys.stderr,
)
standard_candidates = sorted(
    (
        candidate
        for candidate in candidates
        if candidate["construction"] != "alternative_leg_beam"
    ),
    key=lambda candidate: (
        not candidate["within_tolerance"],
        candidate["route"]["analysis"]["repetition"]["repeated_distance"]["share"],
        candidate["route"]["analysis"]["immediate_backtrack"]["share"],
        candidate["target_error_m"],
        candidate["signature"],
    ),
)
refined_candidates = sorted(
    (
        candidate
        for candidate in candidates
        if candidate["construction"] == "alternative_leg_beam"
    ),
    key=lambda candidate: (
        not candidate["within_tolerance"],
        candidate["route"]["analysis"]["repetition"]["repeated_distance"]["share"],
        candidate["route"]["analysis"]["immediate_backtrack"]["share"],
        candidate["score"]["total"],
        candidate["target_error_m"],
        candidate["signature"],
    ),
)
if standard_candidates:
    print(
        "Best standard candidate: "
        f"{standard_candidates[0]['route']['summary']['distance_m']:.1f} m",
        file=sys.stderr,
    )
if refined_candidates:
    print(
        "Best low-overlap candidate: "
        f"{refined_candidates[0]['route']['summary']['distance_m']:.1f} m",
        file=sys.stderr,
    )
else:
    print("Best low-overlap candidate: none", file=sys.stderr)
recommended = candidates[0] if candidates else None
standard_control = standard_candidates[0] if standard_candidates else None
best_total_repetition = refined_candidates[0] if refined_candidates else None
best_natural_improvement = (
    recommended
    if recommended is not None
    and recommended["construction"] == "alternative_leg_beam"
    else None
)

def candidate_label(candidate):
    if candidate is None:
        return "none"
    return f"candidate {candidate['rank']} ({candidate['construction']})"

print(f"Recommended: {candidate_label(recommended)}", file=sys.stderr)
print(f"Standard control: {candidate_label(standard_control)}", file=sys.stderr)
print(
    f"Best total-repetition candidate: {candidate_label(best_total_repetition)}",
    file=sys.stderr,
)
print(
    f"Best natural-improvement candidate: {candidate_label(best_natural_improvement)}",
    file=sys.stderr,
)
print(
    "Low-overlap repetition: "
    f"standard={100 * search['pre_low_overlap_repeated_share']:.1f}%, "
    f"refined={100 * search['best_low_overlap_repeated_share']:.1f}%",
    file=sys.stderr,
)
print(
    "Low-overlap immediate backtracking: "
    f"standard={100 * search['pre_low_overlap_backtrack_share']:.1f}%, "
    f"refined={100 * search['best_low_overlap_backtrack_share']:.1f}%",
    file=sys.stderr,
)
print(
    "Alternative legs: "
    f"{search['alternative_leg_request_count']}/"
    f"{search['low_overlap_request_budget']} requests, "
    f"{search['alternative_path_count']} paths, "
    f"{search['low_overlap_candidate_count']} beam candidates",
    file=sys.stderr,
)

for candidate in candidates:
    visits = candidate["required_point_order"]
    indices = [visit["original_index"] for visit in visits]
    if len(indices) != 23 or sorted(indices) != list(range(23)):
        raise SystemExit(f"candidate {candidate['rank']} has invalid mandatory indices")
    if indices[0] != 0:
        raise SystemExit(f"candidate {candidate['rank']} moved the fixed start")
    routing_points = candidate["routing_points"]
    optional_points = candidate["optional_points"]
    if len(routing_points) != len(indices) + len(optional_points):
        raise SystemExit(f"candidate {candidate['rank']} has invalid routing-point count")
    required_cursor = 0
    for routing_point in routing_points:
        if (
            required_cursor < len(visits)
            and routing_point == visits[required_cursor]["coordinate"]
        ):
            required_cursor += 1
    if required_cursor != len(visits):
        raise SystemExit(f"candidate {candidate['rank']} changed mandatory routing order")
    if any(routing_points.count(optional) != 1 for optional in optional_points):
        raise SystemExit(f"candidate {candidate['rank']} changed optional routing points")
    route = candidate["route"]
    snapped = route.get("snapped_points")
    if not isinstance(snapped, list) or len(snapped) != len(routing_points) + 1:
        raise SystemExit(f"candidate {candidate['rank']} has invalid snapped-point count")
    if math.hypot(
        snapped[0][0] - snapped[-1][0], snapped[0][1] - snapped[-1][1]
    ) > 0.001:
        raise SystemExit(f"candidate {candidate['rank']} does not close at the start")
    names = [visit["coordinate"].get("name") or str(indices[position]) for position, visit in enumerate(visits)]
    analysis = route["analysis"]
    repeated_distance = analysis["repetition"]["repeated_distance"]["distance_m"]
    repeated_share = analysis["repetition"]["repeated_distance"]["share"]
    backtrack_distance = analysis["immediate_backtrack"]["distance_m"]
    backtrack_share = analysis["immediate_backtrack"]["share"]
    non_immediate_repeated = max(repeated_distance - backtrack_distance, 0)
    print(
        f"Candidate {candidate['rank']}: "
        f"construction={candidate['construction']}, "
        f"{route['summary']['distance_m']:.1f} m, "
        f"error={candidate['target_error_m']:.1f} m, "
        f"repeated={repeated_distance:.1f} m/{100 * repeated_share:.1f}%, "
        f"backtrack={backtrack_distance:.1f} m/{100 * backtrack_share:.1f}%, "
        f"non-immediate-repeat={non_immediate_repeated:.1f} m, "
        f"paved={100 * analysis['paved']['share']:.1f}%, "
        f"trail-like={100 * analysis['trail_like']['share']:.1f}%, "
        f"major-road={100 * analysis['major_road']['share']:.1f}%",
        file=sys.stderr,
    )
    print(
        "  Visit order: "
        + " -> ".join(
            f"{index}:{name}" for index, name in zip(indices, names, strict=True)
        ),
        file=sys.stderr,
    )

print("Warnings: " + (", ".join(search["warnings"]) or "none"), file=sys.stderr)
print(len(candidates))
PY
)

echo "Generation JSON: $JSON_OUTPUT"
if [ "$candidate_count" -eq 0 ]; then
    echo "No candidate GPX generated." >&2
    exit 0
fi

curl --fail --silent --show-error \
    --header "Content-Type: application/json" \
    --data-binary "@$REQUEST_PATH" \
    --output "$GPX_OUTPUT" \
    "$API_URL/v1/routes/generate/gpx"

python - "$GPX_OUTPUT" <<'PY'
import sys
from xml.etree import ElementTree

root = ElementTree.parse(sys.argv[1]).getroot()
namespace = {"g": "http://www.topografix.com/GPX/1/1"}
tracks = root.findall("g:trk", namespace)
segments = root.findall("g:trk/g:trkseg", namespace)
points = root.findall("g:trk/g:trkseg/g:trkpt", namespace)
routes = root.findall("g:rte", namespace)
assert len(tracks) == 1, f"expected one track, found {len(tracks)}"
assert len(segments) == 1, f"expected one segment, found {len(segments)}"
assert len(points) > 1, f"expected multiple trackpoints, found {len(points)}"
assert not routes, f"expected no routes, found {len(routes)}"
PY

echo "Best GPX: $GPX_OUTPUT"
python - "$START_TIME" <<'PY'
import sys
import time

print(f"Runtime: {time.monotonic() - float(sys.argv[1]):.2f} s")
PY
