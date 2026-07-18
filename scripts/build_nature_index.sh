#!/bin/sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OSM_PBF=${OSM_PBF:-$REPOSITORY_ROOT/data/osm/ile-de-france-latest.osm.pbf}
NATURE_INDEX=${NATURE_INDEX:-$REPOSITORY_ROOT/data/nature/ile-de-france-nature-index.json.gz}

exec uv run python -m sugarglider.nature.build \
    --osm-pbf "$OSM_PBF" \
    --output "$NATURE_INDEX"
