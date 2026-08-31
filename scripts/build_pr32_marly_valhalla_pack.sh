#!/bin/sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OSM_PBF=${OSM_PBF:-$REPOSITORY_ROOT/data/osm/ile-de-france-latest.osm.pbf}
PACK_DIRECTORY=${PACK_DIRECTORY:-$REPOSITORY_ROOT/data/valhalla/marly-dev-v1}
VALHALLA_IMAGE=ghcr.io/valhalla/valhalla:3.6.3
UV_CACHE_DIR=${UV_CACHE_DIR:-/tmp/sugarglider-uv-cache}
export UV_CACHE_DIR

mkdir -p "$PACK_DIRECTORY"

uv run python \
    "$REPOSITORY_ROOT/scripts/extract_pr32_marly_pbf.py" \
    --input "$OSM_PBF" \
    --output "$PACK_DIRECTORY/marly.osm.pbf"

docker run --rm \
    --user "$(id -u):$(id -g)" \
    --volume "$PACK_DIRECTORY:/work" \
    "$VALHALLA_IMAGE" \
    sh -eu -c '
        valhalla_build_config \
            --mjolnir-tile-dir /work/tiles \
            --mjolnir-tile-extract /work/valhalla_tiles.tar \
            --mjolnir-concurrency 1 \
            --mjolnir-include-driving false \
            --mjolnir-include-bicycle false \
            --mjolnir-include-pedestrian true \
            --mjolnir-data-processing-use-admin-db false \
            --additional-data-elevation "" \
            -o /work/valhalla.json
        valhalla_build_tiles -c /work/valhalla.json /work/marly.osm.pbf
        valhalla_build_extract -c /work/valhalla.json
    '

uv run python "$REPOSITORY_ROOT/scripts/normalize_pr32_valhalla_tar.py" \
    "$PACK_DIRECTORY/valhalla_tiles.tar"

sha256sum "$PACK_DIRECTORY/valhalla_tiles.tar"
stat -c '%n %s bytes' "$PACK_DIRECTORY/marly.osm.pbf" \
    "$PACK_DIRECTORY/valhalla_tiles.tar"
