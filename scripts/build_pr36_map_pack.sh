#!/bin/sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PROTOMAPS_REVISION=3ea8293a28131c3dc63f1bb20827bdb8a76df06f
PROTOMAPS_ARCHIVE_SHA256=7b8e71f18627754af756923f6613a9008b5f1ff82377fff4e617157d053fc807
PROTOMAPS_ARCHIVE_URL="https://codeload.github.com/protomaps/basemaps/tar.gz/$PROTOMAPS_REVISION"
BUILD_IMAGE="maven:3.9.13-eclipse-temurin-21-alpine@sha256:194053d8f204a39710e564b49ba4d22188159fd29f073b8da1715aac61503132"
MAP_PACK_ROOT="$REPOSITORY_ROOT/data/map-packs"
TOOL_CACHE="$MAP_PACK_ROOT/.tool-cache"
MAVEN_CACHE="$MAP_PACK_ROOT/.m2"
SUPPORT_DATA="$MAP_PACK_ROOT/.protomaps-data"

usage() {
    echo "Usage: $0 marly|paris /absolute/or/relative/source.osm.pbf" >&2
    exit 2
}

[ "$#" -eq 2 ] || usage
REGION=$1
PBF_INPUT=$2

case "$REGION" in
    marly)
        PACK_ID=marly-map-dev-v1
        BOUNDS=2.0,48.8,2.16,48.94
        ;;
    paris)
        PACK_ID=paris-map-dev-v1
        BOUNDS=2.25,48.8,2.42,48.92
        ;;
    *) usage ;;
esac

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

TEMPLATE="$REPOSITORY_ROOT/map-packs/$PACK_ID.template.json"
FINAL_OUTPUT="$MAP_PACK_ROOT/$PACK_ID"
[ ! -e "$FINAL_OUTPUT" ] || {
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

BUILD_DIRECTORY=$(mktemp -d "$MAP_PACK_ROOT/.build-$REGION.XXXXXX")
cleanup() {
    rm -rf "$BUILD_DIRECTORY"
}
trap cleanup EXIT HUP INT TERM

tar -xzf "$SOURCE_ARCHIVE" -C "$BUILD_DIRECTORY"
SOURCE_DIRECTORY="$BUILD_DIRECTORY/basemaps-$PROTOMAPS_REVISION"
STAGING_OUTPUT="$BUILD_DIRECTORY/output"
mkdir -p "$STAGING_OUTPUT"

docker run --rm \
    --user "$(id -u):$(id -g)" \
    --env HOME=/tmp/pr36-home \
    --volume "$SOURCE_DIRECTORY:/source" \
    --volume "$MAVEN_CACHE:/tmp/pr36-home/.m2" \
    "$BUILD_IMAGE" \
    mvn --file /source/tiles/pom.xml --batch-mode --no-transfer-progress \
        -DskipTests package

docker run --rm \
    --user "$(id -u):$(id -g)" \
    --workdir /work \
    --volume "$SOURCE_DIRECTORY:/source:ro" \
    --volume "$SUPPORT_DATA:/work/data" \
    --volume "$STAGING_OUTPUT:/output" \
    --volume "$PBF_INPUT:/work/data/sources/pr36-input.osm.pbf:ro" \
    "$BUILD_IMAGE" \
    java -jar /source/tiles/target/protomaps-basemap-HEAD-with-deps.jar \
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
