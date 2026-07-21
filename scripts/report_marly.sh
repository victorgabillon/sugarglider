#!/bin/sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
JSON_OUTPUT=${1:-${OUTPUT_PATH:-/tmp/sugarglider-marly-report.json}}
GPX_OUTPUT=${GPX_OUTPUT:-/tmp/sugarglider-marly-report.gpx}
"$REPOSITORY_ROOT/scripts/generate_marly.sh" "$JSON_OUTPUT" "$GPX_OUTPUT"

python - "$JSON_OUTPUT" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    candidate = json.load(stream)["candidates"][0]
analysis = candidate["route"]["analysis"]
print(f"Distance: {candidate['route']['summary']['distance_m']:.1f} m")
print(f"Target error: {candidate['diagnostics']['target_error_m']:.1f} m")
print(f"Repeated: {100 * analysis['repetition']['repeated_distance']['share']:.1f}%")
print(f"Backtracking: {100 * analysis['immediate_backtrack']['share']:.1f}%")
print(f"Trail-like: {100 * analysis['trail_like']['share']:.1f}%")
PY
