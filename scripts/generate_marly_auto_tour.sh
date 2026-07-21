#!/bin/sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
REQUEST_PATH=${REQUEST_PATH:-$REPOSITORY_ROOT/examples/marly/auto-tour-request.json}
export REQUEST_PATH
exec "$REPOSITORY_ROOT/scripts/generate_marly.sh" "$@"
