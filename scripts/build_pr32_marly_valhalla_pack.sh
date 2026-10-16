#!/bin/sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

mkdir -p "$REPOSITORY_ROOT/data/valhalla"
exec "$REPOSITORY_ROOT/scripts/build_pr33_valhalla_pack.sh" \
    marly-dev-v2 2.00 48.80 2.16 48.94 "$REPOSITORY_ROOT/data/valhalla/marly-dev-v2"
