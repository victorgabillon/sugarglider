#!/usr/bin/env bash
set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
graph_cache="$repository_root/data/graph-cache"
backup_root="$repository_root/data/graph-cache-backups"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)

docker compose -f "$repository_root/docker-compose.yml" stop graphhopper
if [[ -d "$graph_cache" ]] && [[ -n $(find "$graph_cache" -mindepth 1 -maxdepth 1 ! -name '.gitkeep' -print -quit) ]]; then
  mkdir -p "$backup_root"
  backup="$backup_root/graph-cache-$timestamp"
  mkdir "$backup"
  find "$graph_cache" -mindepth 1 -maxdepth 1 ! -name '.gitkeep' \
    -exec mv --target-directory="$backup" -- {} +
  printf 'Previous graph cache moved to %s\n' "$backup"
fi
mkdir -p "$graph_cache"
docker compose -f "$repository_root/docker-compose.yml" up \
  --build --detach --wait --wait-timeout 3600 graphhopper
