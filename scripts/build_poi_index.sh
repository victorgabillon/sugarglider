#!/bin/sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OSM_PBF=${OSM_PBF:-$REPOSITORY_ROOT/data/osm/ile-de-france-latest.osm.pbf}
POI_INDEX=${POI_INDEX:-$REPOSITORY_ROOT/data/pois/ile-de-france-poi-index.json.gz}

if [ -x /usr/bin/time ]; then
    exec /usr/bin/time -f 'Peak RSS: %M KiB' \
        uv run python -m sugarglider.pois.build \
        --osm-pbf "$OSM_PBF" \
        --output "$POI_INDEX"
fi

exec uv run python -m sugarglider.pois.build \
    --osm-pbf "$OSM_PBF" \
    --output "$POI_INDEX"
