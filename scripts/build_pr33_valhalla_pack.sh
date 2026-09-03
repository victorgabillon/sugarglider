#!/bin/sh
set -eu

if [ "$#" -ne 5 ]; then
    echo "Usage: $0 PACK_ID WEST SOUTH EAST NORTH" >&2
    exit 2
fi

PACK_ID=$1
WEST=$2
SOUTH=$3
EAST=$4
NORTH=$5
case "$PACK_ID" in
    ""|[!a-z0-9]*|*[!a-z0-9._-]*)
        echo "Invalid routing-pack ID: $PACK_ID" >&2
        exit 2
        ;;
esac

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OSM_PBF=${OSM_PBF:-$REPOSITORY_ROOT/data/osm/ile-de-france-latest.osm.pbf}
PACK_DIRECTORY=$REPOSITORY_ROOT/data/valhalla/$PACK_ID
VALHALLA_IMAGE=ghcr.io/valhalla/valhalla:3.6.3
UV_CACHE_DIR=${UV_CACHE_DIR:-/tmp/sugarglider-uv-cache}
export UV_CACHE_DIR

mkdir -p "$REPOSITORY_ROOT/data/valhalla"
BUILD_DIRECTORY=$(mktemp -d "$REPOSITORY_ROOT/data/valhalla/.${PACK_ID}.build.XXXXXX")
trap 'rm -rf "$BUILD_DIRECTORY"' EXIT HUP INT TERM
REGION_PBF=$BUILD_DIRECTORY/$PACK_ID.osm.pbf

uv run python "$REPOSITORY_ROOT/scripts/extract_pr33_regional_pbf.py" \
    --input "$OSM_PBF" \
    --output "$REGION_PBF" \
    --west "$WEST" \
    --south "$SOUTH" \
    --east "$EAST" \
    --north "$NORTH"

docker run --rm \
    --user "$(id -u):$(id -g)" \
    --volume "$BUILD_DIRECTORY:/work" \
    "$VALHALLA_IMAGE" \
    sh -eu -c "
        valhalla_build_config \\
            --mjolnir-tile-dir /work/tiles \\
            --mjolnir-tile-extract /work/valhalla_tiles.tar \\
            --mjolnir-concurrency 1 \\
            --mjolnir-include-driving false \\
            --mjolnir-include-bicycle true \\
            --mjolnir-include-pedestrian true \\
            --mjolnir-data-processing-use-admin-db false \\
            --additional-data-elevation \"\" \\
            -o /work/valhalla.json
        valhalla_build_tiles -c /work/valhalla.json /work/$PACK_ID.osm.pbf
        valhalla_build_extract -c /work/valhalla.json
    "

uv run python "$REPOSITORY_ROOT/scripts/normalize_pr32_valhalla_tar.py" \
    "$BUILD_DIRECTORY/valhalla_tiles.tar"

uv run python "$REPOSITORY_ROOT/scripts/write_pr33_routing_pack_manifest.py" \
    --output "$BUILD_DIRECTORY/manifest.json" \
    --pack-id "$PACK_ID" \
    --west "$WEST" \
    --south "$SOUTH" \
    --east "$EAST" \
    --north "$NORTH"

if [ -L "$PACK_DIRECTORY" ]; then
    echo "Refusing symbolic-link routing-pack directory: $PACK_DIRECTORY" >&2
    exit 1
fi
mkdir -p "$PACK_DIRECTORY"

# Publish only after the clean staging build has completed.
cp "$REGION_PBF" "$PACK_DIRECTORY/$PACK_ID.osm.pbf"
cp "$BUILD_DIRECTORY/manifest.json" "$PACK_DIRECTORY/manifest.json"
cp "$BUILD_DIRECTORY/valhalla_tiles.tar" "$PACK_DIRECTORY/valhalla_tiles.tar"

# Remove only fixed, known PR32 work outputs after successful publication.
rm -f -- "$PACK_DIRECTORY/valhalla.json"
rm -rf -- "$PACK_DIRECTORY/tiles"
if [ "$PACK_ID" = "marly-dev-v1" ]; then
    rm -f -- "$PACK_DIRECTORY/marly.osm.pbf"
fi

sha256sum "$PACK_DIRECTORY/manifest.json" "$PACK_DIRECTORY/valhalla_tiles.tar"
stat -c '%n %s bytes' "$PACK_DIRECTORY/$PACK_ID.osm.pbf" \
    "$PACK_DIRECTORY/manifest.json" \
    "$PACK_DIRECTORY/valhalla_tiles.tar"
