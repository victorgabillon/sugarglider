#!/bin/sh
set -eu

API_URL=${API_URL:-http://localhost:8000}
JSON_OUTPUT=${1:-${JSON_OUTPUT:-/tmp/sugarglider-marly-plan.json}}
GPX_OUTPUT=${2:-${GPX_OUTPUT:-/tmp/sugarglider-marly-plan.gpx}}
REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
REQUEST_PATH=${REQUEST_PATH:-$REPOSITORY_ROOT/examples/marly/generation-request.json}
CANDIDATE_REQUEST=$(mktemp)
trap 'rm -f "$CANDIDATE_REQUEST"' EXIT HUP INT TERM

curl --fail --silent --show-error "$API_URL/ready" >/dev/null
curl --fail --silent --show-error \
    --header "Content-Type: application/json" \
    --data-binary "@$REQUEST_PATH" \
    --output "$JSON_OUTPUT" \
    "$API_URL/v2/plans/generate"

python - "$JSON_OUTPUT" "$CANDIDATE_REQUEST" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    result = json.load(stream)
assert result["schema_version"] == 1
candidates = result["candidates"]
if not candidates:
    raise SystemExit("canonical plan returned no candidate")
candidate = candidates[0]
assert candidate["rank"] == 1
assert len(candidate["route"]["geometry"]) > 1
assert candidate["diagnostics"]["safety_eligible"]
print(
    f"{result['kind']} candidate {candidate['id']}: "
    f"{candidate['route']['summary']['distance_m']:.1f} m; "
    f"roles={','.join(candidate['roles'])}; "
    f"selected={len(candidate['selected_stops'])}; "
    f"dropped={len(candidate['dropped_stops'])}"
)
with open(sys.argv[2], "w", encoding="utf-8") as stream:
    json.dump(
        {"schema_version": 1, "candidate": candidate},
        stream,
        ensure_ascii=False,
        separators=(",", ":"),
    )
PY

curl --fail --silent --show-error \
    --header "Content-Type: application/json" \
    --data-binary "@$CANDIDATE_REQUEST" \
    --output "$GPX_OUTPUT" \
    "$API_URL/v2/plans/gpx"

python - "$GPX_OUTPUT" <<'PY'
import sys
from xml.etree import ElementTree

root = ElementTree.parse(sys.argv[1]).getroot()
namespace = {"g": "http://www.topografix.com/GPX/1/1"}
assert len(root.findall("g:trk", namespace)) == 1
assert len(root.findall("g:trk/g:trkseg", namespace)) == 1
assert len(root.findall("g:trk/g:trkseg/g:trkpt", namespace)) > 1
assert root.findall("g:rte", namespace) == []
PY

echo "Plan JSON: $JSON_OUTPUT"
echo "Candidate GPX: $GPX_OUTPUT"
