#!/bin/sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$REPOSITORY_ROOT/data/valhalla"
# OSM_PBF and a verified SUGARGLIDER_DEM_DIR are mandatory; outputs are fresh.

"$REPOSITORY_ROOT/scripts/build_pr33_valhalla_pack.sh" \
    marly-dev-v2 2.00 48.80 2.16 48.94 "$REPOSITORY_ROOT/data/valhalla/marly-dev-v2"
"$REPOSITORY_ROOT/scripts/build_pr33_valhalla_pack.sh" \
    paris-dev-v2 2.25 48.80 2.42 48.92 "$REPOSITORY_ROOT/data/valhalla/paris-dev-v2"
