#!/bin/sh
set -eu

API_URL=${API_URL:-http://localhost:8000}
JSON_OUTPUT=${1:-${JSON_OUTPUT:-/tmp/sugarglider-marly-generation.json}}
GPX_OUTPUT=${2:-${GPX_OUTPUT:-/tmp/sugarglider-marly-41km.gpx}}
REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
REQUEST_PATH="$REPOSITORY_ROOT/examples/marly/generation-request.json"

curl --fail --silent --show-error "$API_URL/ready" >/dev/null
curl --fail --silent --show-error \
    --header "Content-Type: application/json" \
    --data-binary "@$REQUEST_PATH" \
    --output "$JSON_OUTPUT" \
    "$API_URL/v1/routes/generate"

candidate_count=$(python - "$JSON_OUTPUT" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as response_file:
    response = json.load(response_file)

search = response.get("search")
baseline = response.get("baseline")
candidates = response.get("candidates")
if not isinstance(search, dict) or not isinstance(baseline, dict):
    raise SystemExit("generation response is missing search or baseline")
if not isinstance(candidates, list):
    raise SystemExit("generation response is missing candidates")

summary = baseline.get("summary")
if not isinstance(summary, dict):
    raise SystemExit("generation baseline is missing summary")

print(f"Search status: {search['status']}", file=sys.stderr)
print(f"Baseline distance: {summary['distance_m']:.1f} m", file=sys.stderr)
print(
    f"Target: {search['target_distance_m']:.1f} m "
    f"± {search['tolerance_m']:.1f} m",
    file=sys.stderr,
)
print(
    "Evaluations: "
    f"{search['evaluated_candidate_count']}/{search['search_budget']} full, "
    f"{search['successful_candidate_count']} successful, "
    f"{search['rejected_candidate_count']} rejected, "
    f"{search['round_trip_proposal_count']} proposals",
    file=sys.stderr,
)
for candidate in candidates:
    route = candidate["route"]
    analysis = route["analysis"]
    print(
        f"Candidate {candidate['rank']}: "
        f"{route['summary']['distance_m']:.1f} m, "
        f"error {candidate['target_error_m']:.1f} m, "
        f"within tolerance={candidate['within_tolerance']}, "
        f"score={candidate['score']['total']:.4f}, "
        f"repeated={100 * analysis['repetition']['repeated_distance']['share']:.1f}%, "
        f"paved={100 * analysis['paved']['share']:.1f}%, "
        f"trail-like={100 * analysis['trail_like']['share']:.1f}%, "
        f"major-road={100 * analysis['major_road']['share']:.1f}%",
        file=sys.stderr,
    )
warnings = search.get("warnings")
if not isinstance(warnings, list):
    raise SystemExit("generation search is missing warnings")
print("Warnings: " + (", ".join(warnings) or "none"), file=sys.stderr)
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
