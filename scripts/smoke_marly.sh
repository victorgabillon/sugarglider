#!/bin/sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec "$REPOSITORY_ROOT/scripts/generate_marly.sh" \
    "${JSON_OUTPUT:-/tmp/sugarglider-marly-smoke.json}" \
    "${1:-${GPX_OUTPUT:-/tmp/sugarglider-marly-smoke.gpx}}"
