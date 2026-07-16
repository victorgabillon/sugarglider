#!/bin/sh
set -eu

API_URL=${API_URL:-http://localhost:8000}
OUTPUT_PATH=${1:-${OUTPUT_PATH:-/tmp/sugarglider-marly.gpx}}
REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

curl --fail --silent --show-error "$API_URL/ready" >/dev/null
curl --fail --silent --show-error \
    --header "Content-Type: application/json" \
    --data-binary "@$REPOSITORY_ROOT/examples/marly/request.json" \
    --output "$OUTPUT_PATH" \
    "$API_URL/v1/routes/gpx"

python - "$OUTPUT_PATH" <<'PY'
import sys
from xml.etree import ElementTree

path = sys.argv[1]
root = ElementTree.parse(path).getroot()
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

echo "Generated GPX: $OUTPUT_PATH"

