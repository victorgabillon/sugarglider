#!/bin/sh
set -eu

API_URL=${API_URL:-http://localhost:8000}
OUTPUT_PATH=${1:-${OUTPUT_PATH:-/tmp/sugarglider-marly-analysis.json}}
REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

curl --fail --silent --show-error "$API_URL/ready" >/dev/null
curl --fail --silent --show-error \
    --header "Content-Type: application/json" \
    --data-binary "@$REPOSITORY_ROOT/examples/marly/request.json" \
    --output "$OUTPUT_PATH" \
    "$API_URL/v1/routes"

python - "$OUTPUT_PATH" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as response_file:
    response = json.load(response_file)

analysis = response.get("analysis")
if not isinstance(analysis, dict):
    raise SystemExit("response does not contain an analysis object")


def percentage(metric_name):
    metric = analysis.get(metric_name)
    if not isinstance(metric, dict) or not isinstance(metric.get("share"), (int, float)):
        raise SystemExit(f"analysis.{metric_name}.share is missing")
    return 100 * metric["share"]


route_distance = analysis.get("route_distance_m")
if not isinstance(route_distance, (int, float)):
    raise SystemExit("analysis.route_distance_m is missing")
repetition = analysis.get("repetition")
if not isinstance(repetition, dict):
    raise SystemExit("analysis.repetition is missing")
repeated = repetition.get("repeated_distance")
coverage = repetition.get("edge_id_coverage")
if not isinstance(repeated, dict) or not isinstance(coverage, dict):
    raise SystemExit("analysis repetition metrics are missing")
repeated_share = repeated.get("share")
coverage_share = coverage.get("share")
if not isinstance(repeated_share, (int, float)) or not isinstance(
    coverage_share, (int, float)
):
    raise SystemExit("analysis repetition shares are missing")

print(f"Route distance: {route_distance:.1f} m")
print(f"Paved: {percentage('paved'):.1f}%")
print(f"Unpaved: {percentage('unpaved'):.1f}%")
print(f"Unknown surface: {percentage('unknown_surface'):.1f}%")
print(f"Trail-like: {percentage('trail_like'):.1f}%")
print(f"Official hiking network: {percentage('official_hiking_network'):.1f}%")
print(f"Major road: {percentage('major_road'):.1f}%")
print(f"Car-accessible: {percentage('car_accessible'):.1f}%")
print(f"Repeated edge: {100 * repeated_share:.1f}%")
print(f"Edge-ID coverage: {100 * coverage_share:.1f}%")
warnings = analysis.get("warnings")
if not isinstance(warnings, list):
    raise SystemExit("analysis.warnings is missing")
print("Warnings: " + (", ".join(str(item) for item in warnings) or "none"))
PY

echo "Analysis JSON: $OUTPUT_PATH"
