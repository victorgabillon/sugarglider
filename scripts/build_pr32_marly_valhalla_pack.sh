#!/bin/sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

exec "$REPOSITORY_ROOT/scripts/build_pr33_valhalla_pack.sh" \
    marly-dev-v1 2.00 48.80 2.16 48.94
