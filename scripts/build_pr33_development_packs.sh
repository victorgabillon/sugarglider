#!/bin/sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

"$REPOSITORY_ROOT/scripts/build_pr33_valhalla_pack.sh" \
    marly-dev-v1 2.00 48.80 2.16 48.94
"$REPOSITORY_ROOT/scripts/build_pr33_valhalla_pack.sh" \
    paris-dev-v1 2.25 48.80 2.42 48.92
