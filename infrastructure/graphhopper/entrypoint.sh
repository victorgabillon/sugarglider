#!/bin/sh
set -eu

PBF_PATH=/data/osm/ile-de-france-latest.osm.pbf
GRAPH_PATH=/data/graph-cache
FINGERPRINT_PATH="$GRAPH_PATH/.sugarglider-import-fingerprint"
if [ ! -s "$PBF_PATH" ]; then
    echo "GraphHopper cannot start: missing or empty PBF at $PBF_PATH" >&2
    echo "Run 'make download-osm' before starting Docker Compose." >&2
    exit 1
fi

EXPECTED_FINGERPRINT=$(cat /opt/graphhopper/import-fingerprint)
if [ -d "$GRAPH_PATH" ] && [ "$(find "$GRAPH_PATH" -mindepth 1 -maxdepth 1 ! -name '.gitkeep' ! -name '.sugarglider-import-fingerprint' -print -quit)" ]; then
    if [ ! -f "$FINGERPRINT_PATH" ]; then
        echo "GraphHopper cache predates PR15 profile fingerprinting." >&2
        echo "Run 'make rebuild-graph' to preserve it as a backup and import a compatible graph." >&2
        exit 1
    fi
    CACHED_FINGERPRINT=$(cat "$FINGERPRINT_PATH")
    if [ "$CACHED_FINGERPRINT" != "$EXPECTED_FINGERPRINT" ]; then
        echo "GraphHopper cache is incompatible with the packaged profiles." >&2
        echo "Run 'make rebuild-graph' to preserve it as a backup and import a compatible graph." >&2
        exit 1
    fi
fi
mkdir -p "$GRAPH_PATH"
printf '%s\n' "$EXPECTED_FINGERPRINT" > "$FINGERPRINT_PATH"

# Intentional word splitting lets JAVA_OPTS contain multiple JVM flags.
# shellcheck disable=SC2086
exec java ${JAVA_OPTS:-} -jar /opt/graphhopper-web.jar server /opt/graphhopper/config.yml
