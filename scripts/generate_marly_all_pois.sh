#!/bin/sh
set -eu

API_URL=${API_URL:-http://localhost:8000}
PREFER_JSON_OUTPUT=${1:-${JSON_OUTPUT:-/tmp/sugarglider-marly-all-pois.json}}
GPX_OUTPUT=${2:-${GPX_OUTPUT:-/tmp/sugarglider-marly-all-pois.gpx}}
OFF_JSON_OUTPUT=${OFF_JSON_OUTPUT:-/tmp/sugarglider-marly-all-pois-off.json}
REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
REQUEST_PATH="$REPOSITORY_ROOT/examples/marly/all-pois-generation-request.json"
OFF_REQUEST=$(mktemp)
PREFER_REQUEST=$(mktemp)
SELECTED_ROUTE=$(mktemp)
START_TIME=$(python -c 'import time; print(time.monotonic())')

cleanup() {
    rm -f "$OFF_REQUEST" "$PREFER_REQUEST" "$SELECTED_ROUTE"
}
trap cleanup EXIT HUP INT TERM

curl --fail --silent --show-error "$API_URL/ready" >/dev/null
curl --fail --silent --show-error "$API_URL/v1/nature/status" \
    | python -m json.tool

python - "$REQUEST_PATH" "$OFF_REQUEST" "$PREFER_REQUEST" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    request = json.load(stream)
for preference, output_path in (("off", sys.argv[2]), ("prefer", sys.argv[3])):
    variant = {**request, "nature_preference": preference}
    with open(output_path, "w", encoding="utf-8") as output:
        json.dump(variant, output, ensure_ascii=False, separators=(",", ":"))
PY

for pair in "$OFF_REQUEST:$OFF_JSON_OUTPUT" "$PREFER_REQUEST:$PREFER_JSON_OUTPUT"; do
    request=${pair%%:*}
    output=${pair#*:}
    curl --fail --silent --show-error \
        --header "Content-Type: application/json" \
        --data-binary "@$request" \
        --output "$output" \
        "$API_URL/v1/routes/generate"
done

candidate_count=$(python - "$OFF_JSON_OUTPUT" "$PREFER_JSON_OUTPUT" "$SELECTED_ROUTE" <<'PY' | tee /dev/stderr | tail -n 1
import json
import math
import sys


def load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def nature_value(candidate, key):
    nature = candidate["route"]["analysis"].get("nature")
    if nature is None:
        return "not evaluated"
    metric = nature[key]
    return f"{metric['distance_m']:.1f} m/{100 * metric['share']:.1f}%"


def candidate_label(candidate):
    if candidate is None:
        return "none"
    return f"candidate {candidate['rank']} ({candidate['construction']})"


def validate_candidate(candidate):
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
    cursor = 0
    for routing_point in routing_points:
        if cursor < len(visits) and routing_point == visits[cursor]["coordinate"]:
            cursor += 1
    if cursor != len(visits):
        raise SystemExit(f"candidate {candidate['rank']} changed mandatory order")
    snapped = candidate["route"].get("snapped_points")
    if not isinstance(snapped, list) or len(snapped) != len(routing_points) + 1:
        raise SystemExit(f"candidate {candidate['rank']} has invalid snapped points")
    if math.hypot(snapped[0][0] - snapped[-1][0], snapped[0][1] - snapped[-1][1]) > 0.001:
        raise SystemExit(f"candidate {candidate['rank']} does not close at the start")


def print_candidate(prefix, candidate):
    route = candidate["route"]
    analysis = route["analysis"]
    repetition = analysis["repetition"]["repeated_distance"]
    backtrack = analysis["immediate_backtrack"]
    nature = analysis.get("nature")
    score = "not evaluated" if nature is None else f"{nature['nature_score']:.1f}/100"
    print(
        f"{prefix} candidate {candidate['rank']}: signature={candidate['signature']}, "
        f"construction={candidate['construction']}, distance={route['summary']['distance_m']:.1f} m, "
        f"error={candidate['target_error_m']:.1f} m, backtrack={100 * backtrack['share']:.1f}%, "
        f"repeated={100 * repetition['share']:.1f}%, nature={score}, "
        f"woodland={nature_value(candidate, 'woodland')}, "
        f"open-natural={nature_value(candidate, 'open_natural')}, "
        f"agriculture={nature_value(candidate, 'agriculture')}, "
        f"urban={nature_value(candidate, 'urban')}, "
        f"unknown={nature_value(candidate, 'unknown_landcover')}, "
        f"park/protected={nature_value(candidate, 'park_or_protected')}, "
        f"near-water={nature_value(candidate, 'near_water')}, "
        f"paved={100 * analysis['paved']['share']:.1f}%, "
        f"trail-like={100 * analysis['trail_like']['share']:.1f}%, "
        f"major-road={100 * analysis['major_road']['share']:.1f}%"
    )


off = load(sys.argv[1])
prefer = load(sys.argv[2])
for label, result in (("Off", off), ("Prefer", prefer)):
    search = result["search"]
    candidates = result["candidates"]
    print(f"\n{label} nature preference")
    print(
        f"Status={search['status']}; nature requested={search['nature_requested']}; "
        f"index available={search['nature_index_available']}; "
        f"features={search['nature_index_feature_count']}; "
        f"evaluations={search['evaluated_candidate_count']}/{search['search_budget']}; "
        f"alternative legs={search['alternative_leg_request_count']}/{search['low_overlap_request_budget']}"
    )
    for candidate in candidates:
        validate_candidate(candidate)
        print_candidate(label, candidate)
    recommended = candidates[0] if candidates else None
    scored = [candidate for candidate in candidates if candidate["route"]["analysis"].get("nature") is not None]
    highest = max(
        scored,
        key=lambda candidate: (candidate["route"]["analysis"]["nature"]["nature_score"], candidate["signature"]),
        default=None,
    )
    print(f"Recommended: {candidate_label(recommended)}")
    print(f"Highest-nature returned: {candidate_label(highest)}")
    print("Warnings: " + (", ".join(search["warnings"]) or "none"))

off_recommended = off["candidates"][0] if off["candidates"] else None
prefer_recommended = prefer["candidates"][0] if prefer["candidates"] else None
changed = (
    off_recommended is not None
    and prefer_recommended is not None
    and off_recommended["signature"] != prefer_recommended["signature"]
)
print(f"\nNature preference changed recommendation: {'yes' if changed else 'no'}")
if off_recommended and prefer_recommended:
    if off_recommended["within_tolerance"] and not prefer_recommended["within_tolerance"]:
        raise SystemExit("nature preference selected outside tolerance over in-tolerance")
if prefer_recommended is not None:
    with open(sys.argv[3], "w", encoding="utf-8") as output:
        json.dump(prefer_recommended["route"], output, ensure_ascii=False)
print(len(prefer["candidates"]))
PY
)

echo "Nature-off JSON: $OFF_JSON_OUTPUT"
echo "Nature-prefer JSON: $PREFER_JSON_OUTPUT"
if [ "$candidate_count" -eq 0 ]; then
    echo "No candidate GPX generated." >&2
    exit 0
fi

curl --fail --silent --show-error \
    --header "Content-Type: application/json" \
    --data-binary "@$SELECTED_ROUTE" \
    --output "$GPX_OUTPUT" \
    "$API_URL/v1/routes/gpx/from-result"

python - "$GPX_OUTPUT" <<'PY'
import sys
from xml.etree import ElementTree

root = ElementTree.parse(sys.argv[1]).getroot()
namespace = {"g": "http://www.topografix.com/GPX/1/1"}
assert len(root.findall("g:trk", namespace)) == 1
assert len(root.findall("g:trk/g:trkseg", namespace)) == 1
assert len(root.findall("g:trk/g:trkseg/g:trkpt", namespace)) > 1
assert not root.findall("g:rte", namespace)
assert not root.findall(".//g:extensions", namespace)
PY

echo "Selected prefer-mode GPX: $GPX_OUTPUT"
python - "$START_TIME" <<'PY'
import sys
import time

print(f"Comparison runtime: {time.monotonic() - float(sys.argv[1]):.2f} s")
PY
