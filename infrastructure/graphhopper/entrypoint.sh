#!/bin/sh
set -eu

PBF_PATH=/data/osm/ile-de-france-latest.osm.pbf
if [ ! -s "$PBF_PATH" ]; then
    echo "GraphHopper cannot start: missing or empty PBF at $PBF_PATH" >&2
    echo "Run 'make download-osm' before starting Docker Compose." >&2
    exit 1
fi

# Intentional word splitting lets JAVA_OPTS contain multiple JVM flags.
# shellcheck disable=SC2086
exec java ${JAVA_OPTS:-} -jar /opt/graphhopper-web.jar server /opt/graphhopper/config.yml

