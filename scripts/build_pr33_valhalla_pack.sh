#!/bin/sh
# V2 only: explicit source, verified private DEM, fresh output directory.
set -eu
[ "$#" -eq 6 ] || { echo "Usage: $0 PACK_ID WEST SOUTH EAST NORTH NEW_OUTPUT_DIRECTORY" >&2; exit 2; }
PACK_ID=$1
WEST=$2
SOUTH=$3
EAST=$4
NORTH=$5
OUTPUT=$6
case "$PACK_ID" in ""|[!a-z0-9]*|*[!a-z0-9._-]*|*..*) exit 2;; esac
REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$REPOSITORY_ROOT/scripts/offline_build_resources.sh"
: "${OSM_PBF:?V2 build requires explicit OSM_PBF}"
: "${SUGARGLIDER_DEM_DIR:?V2 build requires verified regional DEM directory}"
[ -f "$OSM_PBF" ] && [ -d "$SUGARGLIDER_DEM_DIR" ]
[ ! -e "$OUTPUT" ] && [ ! -L "$OUTPUT" ] || { echo "Refusing immutable output replacement" >&2; exit 1; }
VALHALLA_IMAGE=ghcr.io/valhalla/valhalla:3.9.1@sha256:18cb42988e03c70dc4bc4ca095a259ec4db5e5df928be65956fc1c64c280b47a
BUILD_DIRECTORY=$(mktemp -d "$(dirname -- "$OUTPUT")/.${PACK_ID}.build.XXXXXX")
trap 'rm -rf "$BUILD_DIRECTORY"' EXIT HUP INT TERM
uv run --offline python "$REPOSITORY_ROOT/scripts/extract_pr33_regional_pbf.py" \
    --input "$OSM_PBF" --output "$BUILD_DIRECTORY/input.osm.pbf" \
    --west "$WEST" --south "$SOUTH" --east "$EAST" --north "$NORTH"
docker run --rm --network none --platform linux/amd64 --entrypoint /bin/sh \
    --label io.github.victorgabillon.sugarglider.build=offline-region \
    --memory "${SUGARGLIDER_BUILD_MEMORY_MB}m" --memory-swap "${SUGARGLIDER_BUILD_MEMORY_MB}m" \
    --cpus "$SUGARGLIDER_BUILD_CPUS" --user "$(id -u):$(id -g)" \
    --volume "$BUILD_DIRECTORY:/work" --volume "$SUGARGLIDER_DEM_DIR:/dem:ro" \
    "$VALHALLA_IMAGE" -eu -c '
        test "$(valhalla_build_tiles --version)" = 3.9.1
        valhalla_build_config --mjolnir-tile-dir /work/tiles \
            --mjolnir-tile-extract /work/valhalla_tiles.tar --mjolnir-concurrency 1 \
            --mjolnir-include-driving false --mjolnir-include-bicycle true \
            --mjolnir-include-pedestrian true --mjolnir-data-processing-use-admin-db false \
            --mjolnir-tile-url "" --additional-data-elevation /dem \
            --additional-data-elevation-url "" --additional-data-elevation-url-user-pw "" \
            --output /work/valhalla.json
        valhalla_build_tiles -c /work/valhalla.json /work/input.osm.pbf
        # build_tiles runs ElevationBuilder once because /dem is configured.
        # Do not run valhalla_add_elevation on this already enriched, finalized
        # graph: 3.9.1 rewrites it non-idempotently and can corrupt edge records.
        valhalla_build_extract -c /work/valhalla.json
        if [ -r /sys/fs/cgroup/memory.peak ]; then cat /sys/fs/cgroup/memory.peak; fi
    '
uv run --offline python "$REPOSITORY_ROOT/scripts/normalize_pr32_valhalla_tar.py" "$BUILD_DIRECTORY/valhalla_tiles.tar"
uv run --offline python "$REPOSITORY_ROOT/scripts/write_pr33_routing_pack_manifest.py" \
    --output "$BUILD_DIRECTORY/manifest.json" --pack-id "$PACK_ID" \
    --west "$WEST" --south "$SOUTH" --east "$EAST" --north "$NORTH"
mkdir "$BUILD_DIRECTORY/output"
mv "$BUILD_DIRECTORY/manifest.json" "$BUILD_DIRECTORY/valhalla_tiles.tar" "$BUILD_DIRECTORY/output/"
mv "$BUILD_DIRECTORY/output" "$OUTPUT"
