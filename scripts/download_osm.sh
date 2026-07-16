#!/bin/sh
set -eu

DEFAULT_URL=https://download.geofabrik.de/europe/france/ile-de-france-latest.osm.pbf
SOURCE_URL=${OSM_PBF_URL:-$DEFAULT_URL}
REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DESTINATION="$REPOSITORY_ROOT/data/osm/ile-de-france-latest.osm.pbf"
TEMPORARY="$DESTINATION.part.$$"

mkdir -p "$(dirname -- "$DESTINATION")"
if [ -s "$DESTINATION" ] && [ "${FORCE:-0}" != "1" ]; then
    echo "OSM PBF already exists: $DESTINATION"
    exit 0
fi

trap 'rm -f "$TEMPORARY"' EXIT HUP INT TERM
echo "Downloading OSM PBF from: $SOURCE_URL"
echo "Destination: $DESTINATION"
curl --fail --location --retry 3 --retry-delay 2 \
    --output "$TEMPORARY" "$SOURCE_URL"
if [ ! -s "$TEMPORARY" ]; then
    echo "Downloaded OSM PBF is empty" >&2
    exit 1
fi
mv -f "$TEMPORARY" "$DESTINATION"
trap - EXIT HUP INT TERM
echo "OSM PBF ready: $DESTINATION"

