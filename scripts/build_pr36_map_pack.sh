#!/bin/sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$REPOSITORY_ROOT/scripts/offline_build_resources.sh"
PROTOMAPS_REVISION=3ea8293a28131c3dc63f1bb20827bdb8a76df06f
PROTOMAPS_ARCHIVE_SHA256=7b8e71f18627754af756923f6613a9008b5f1ff82377fff4e617157d053fc807
PROTOMAPS_ARCHIVE_URL="https://codeload.github.com/protomaps/basemaps/tar.gz/$PROTOMAPS_REVISION"
BUILD_IMAGE="maven:3.9.13-eclipse-temurin-21-alpine@sha256:194053d8f204a39710e564b49ba4d22188159fd29f073b8da1715aac61503132"
MAP_PACK_ROOT="$REPOSITORY_ROOT/data/map-packs"
TOOL_CACHE="$MAP_PACK_ROOT/.tool-cache"
MAVEN_CACHE="$MAP_PACK_ROOT/.m2"
SUPPORT_DATA="$MAP_PACK_ROOT/.protomaps-data"

usage() {
    echo "Usage: $0 REGION /absolute/or/relative/source.osm.pbf [NEW_OUTPUT_DIRECTORY]" >&2
    exit 2
}

[ "$#" -eq 2 ] || [ "$#" -eq 3 ] || usage
REGION=$1
PBF_INPUT=$2
REQUESTED_OUTPUT=${3:-}
# The strict region specification owns bounds; its template must agree exactly.
MAP_CONFIG=$(cd "$REPOSITORY_ROOT" && uv run python -m sugarglider.offline_regions \
    map-config --region "$REGION")
PACK_ID=$(printf '%s\n' "$MAP_CONFIG" | sed -n '1p')
BOUNDS=$(printf '%s\n' "$MAP_CONFIG" | sed -n '2p')
TEMPLATE=$(printf '%s\n' "$MAP_CONFIG" | sed -n '3p')

[ -f "$PBF_INPUT" ] || {
    echo "OSM PBF input does not exist: $PBF_INPUT" >&2
    exit 1
}
case "$PBF_INPUT" in
    *.osm.pbf) ;;
    *)
        echo "OSM input must end in .osm.pbf" >&2
        exit 1
        ;;
esac
PBF_INPUT=$(CDPATH= cd -- "$(dirname -- "$PBF_INPUT")" && pwd)/$(basename -- "$PBF_INPUT")

FINAL_OUTPUT=${REQUESTED_OUTPUT:-$MAP_PACK_ROOT/$PACK_ID}
[ ! -e "$FINAL_OUTPUT" ] && [ ! -L "$FINAL_OUTPUT" ] || {
    echo "Output already exists; remove it explicitly before rebuilding: $FINAL_OUTPUT" >&2
    exit 1
}

mkdir -p "$TOOL_CACHE" "$MAVEN_CACHE" "$SUPPORT_DATA/sources"
SOURCE_ARCHIVE="$TOOL_CACHE/protomaps-basemaps-$PROTOMAPS_REVISION.tar.gz"
if [ ! -f "$SOURCE_ARCHIVE" ]; then
    PARTIAL_SOURCE_ARCHIVE="$SOURCE_ARCHIVE.partial"
    curl --location --fail --show-error --output "$PARTIAL_SOURCE_ARCHIVE" \
        "$PROTOMAPS_ARCHIVE_URL"
    printf '%s  %s\n' "$PROTOMAPS_ARCHIVE_SHA256" "$PARTIAL_SOURCE_ARCHIVE" \
        | sha256sum --check --status || {
        echo "Downloaded Protomaps source checksum mismatch" >&2
        exit 1
    }
    mv "$PARTIAL_SOURCE_ARCHIVE" "$SOURCE_ARCHIVE"
fi
printf '%s  %s\n' "$PROTOMAPS_ARCHIVE_SHA256" "$SOURCE_ARCHIVE" | sha256sum --check --status || {
    echo "Pinned Protomaps source checksum mismatch: $SOURCE_ARCHIVE" >&2
    exit 1
}

BUILD_ROOT="$MAP_PACK_ROOT"
if [ -n "$REQUESTED_OUTPUT" ]; then
    BUILD_ROOT=$(dirname -- "$REQUESTED_OUTPUT")
fi
BUILD_DIRECTORY=$(mktemp -d "$BUILD_ROOT/.build-$REGION.XXXXXX")
cleanup() {
    rm -rf "$BUILD_DIRECTORY"
}
trap cleanup EXIT HUP INT TERM

tar -xzf "$SOURCE_ARCHIVE" -C "$BUILD_DIRECTORY"
SOURCE_DIRECTORY="$BUILD_DIRECTORY/basemaps-$PROTOMAPS_REVISION"
STAGING_OUTPUT="$BUILD_DIRECTORY/output"
mkdir -p "$STAGING_OUTPUT" "$BUILD_DIRECTORY/planetiler-tmp"

docker run --rm \
    --label io.github.victorgabillon.sugarglider.build=offline-region \
    --memory "${SUGARGLIDER_BUILD_MEMORY_MB}m" \
    --memory-swap "${SUGARGLIDER_BUILD_MEMORY_MB}m" \
    --cpus "$SUGARGLIDER_BUILD_CPUS" \
    --user "$(id -u):$(id -g)" \
    --env "MAVEN_OPTS=-Xmx${SUGARGLIDER_BUILD_JAVA_HEAP_MB}m -Duser.home=/tmp/pr36-home" \
    --volume "$SOURCE_DIRECTORY:/source" \
    --volume "$MAVEN_CACHE:/tmp/pr36-home/.m2" \
    "$BUILD_IMAGE" \
    mvn --file /source/tiles/pom.xml --batch-mode --no-transfer-progress \
        -DskipTests package

docker run --rm \
    --label io.github.victorgabillon.sugarglider.build=offline-region \
    --memory "${SUGARGLIDER_BUILD_MEMORY_MB}m" \
    --memory-swap "${SUGARGLIDER_BUILD_MEMORY_MB}m" \
    --cpus "$SUGARGLIDER_BUILD_CPUS" \
    --user "$(id -u):$(id -g)" \
    --workdir /work \
    --volume "$SOURCE_DIRECTORY:/source:ro" \
    --volume "$SUPPORT_DATA:/work/data" \
    --volume "$BUILD_DIRECTORY/planetiler-tmp:/work/data/tmp" \
    --volume "$STAGING_OUTPUT:/output" \
    --volume "$PBF_INPUT:/work/data/sources/pr36-input.osm.pbf:ro" \
    "$BUILD_IMAGE" \
    java "-Xmx${SUGARGLIDER_BUILD_JAVA_HEAP_MB}m" \
        -jar /source/tiles/target/protomaps-basemap-HEAD-with-deps.jar \
        --area=pr36-input \
        --bounds="$BOUNDS" \
        --maxzoom=15 \
        --output=/output/basemap.pmtiles \
        --download \
        --force

uv run python "$REPOSITORY_ROOT/scripts/write_pr36_map_pack_manifest.py" \
    --template "$TEMPLATE" \
    --archive "$STAGING_OUTPUT/basemap.pmtiles" \
    --source-pbf "$PBF_INPUT" \
    --output "$STAGING_OUTPUT/manifest.json"

mv "$STAGING_OUTPUT" "$FINAL_OUTPUT"
echo "Built $PACK_ID in $FINAL_OUTPUT"
