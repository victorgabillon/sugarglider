#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
URL="${SUGARGLIDER_URL:-http://localhost:8000/}"
READY_URL="${SUGARGLIDER_READY_URL:-http://localhost:8000/ready}"
MAX_ATTEMPTS="${SUGARGLIDER_READY_ATTEMPTS:-120}"

cd "$REPO_ROOT"

echo "Repository: $REPO_ROOT"
echo "Branch: $(git branch --show-current 2>/dev/null || echo unknown)"
echo
echo "Building and starting Sugarglider..."

docker compose up -d --build

echo
echo "Waiting for the API..."

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    if curl -fsS "$READY_URL" >/dev/null 2>&1; then
        echo "Sugarglider is ready: $URL"
        break
    fi

    if [ "$attempt" -eq "$MAX_ATTEMPTS" ]; then
        echo "Sugarglider did not become ready."
        echo
        docker compose ps
        echo
        docker compose logs --tail=250 api graphhopper
        exit 1
    fi

    sleep 2
done

# Prefer an explicitly selected browser.
case "${1:-}" in
    --firefox)
        exec firefox "$URL"
        ;;
    --chrome)
        PROFILE="/tmp/sugarglider-chrome-profile"
        rm -rf "$PROFILE"

        if command -v google-chrome >/dev/null 2>&1; then
            exec google-chrome \
                --user-data-dir="$PROFILE" \
                --disable-extensions \
                "$URL"
        fi

        if command -v google-chrome-stable >/dev/null 2>&1; then
            exec google-chrome-stable \
                --user-data-dir="$PROFILE" \
                --disable-extensions \
                "$URL"
        fi

        echo "Chrome was not found."
        exit 1
        ;;
    "")
        if command -v firefox >/dev/null 2>&1; then
            exec firefox "$URL"
        fi

        exec xdg-open "$URL"
        ;;
    *)
        echo "Usage: $0 [--firefox|--chrome]"
        exit 2
        ;;
esac
