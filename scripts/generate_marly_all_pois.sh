#!/bin/sh
set -eu

API_URL=${API_URL:-http://localhost:8000}
JSON_OUTPUT=${1:-${JSON_OUTPUT:-/tmp/sugarglider-marly-all-pois.json}}
GPX_OUTPUT=${2:-${GPX_OUTPUT:-/tmp/sugarglider-marly-all-pois.gpx}}
REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
REQUEST_PATH="$REPOSITORY_ROOT/examples/marly/all-pois-generation-request.json"

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

for candidate in candidates:
    visits = candidate["required_point_order"]
    indices = [visit["original_index"] for visit in visits]
    if len(indices) != 23 or sorted(indices) != list(range(23)):
        raise SystemExit(f"candidate {candidate['rank']} has invalid mandatory indices")
    if indices[0] != 0:
        raise SystemExit(f"candidate {candidate['rank']} moved the fixed start")
    route = candidate["route"]
    snapped = route.get("snapped_points")
    if not isinstance(snapped, list) or len(snapped) <= len(indices):
        raise SystemExit(f"candidate {candidate['rank']} lacks a closed snapped route")
    if math.hypot(
        snapped[0][0] - snapped[-1][0], snapped[0][1] - snapped[-1][1]
    ) > 0.001:
        raise SystemExit(f"candidate {candidate['rank']} does not close at the start")
    names = [visit["coordinate"].get("name") or str(indices[position]) for position, visit in enumerate(visits)]
    analysis = route["analysis"]
    print(
        f"Candidate {candidate['rank']}: "
        f"{route['summary']['distance_m']:.1f} m, "
        f"error={candidate['target_error_m']:.1f} m, "
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
