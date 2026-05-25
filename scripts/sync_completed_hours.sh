#!/usr/bin/env bash
# Stage completed UTC-hour Parquet files and sync them with rclone.

set -euo pipefail

DATA_DIR="${DATA_DIR:-data}"
STAGE_DIR="${STAGE_DIR:-/tmp/binance_collector_completed_hours}"
FORCE_CURRENT="${FORCE_CURRENT:-0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURRENT_HOUR="$(date -u +%Y%m%d%H)"

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"

while IFS= read -r -d '' file; do
    name="$(basename "$file")"
    [[ "$name" == *.tmp ]] && continue
    hour="${name%.parquet}"
    hour="${hour##*_}"
    if [ "$FORCE_CURRENT" != "1" ] && [ "$hour" -ge "$CURRENT_HOUR" ]; then
        continue
    fi

    rel="${file#"$DATA_DIR"/}"
    mkdir -p "$STAGE_DIR/$(dirname "$rel")"
    cp -p "$file" "$STAGE_DIR/$rel"
done < <(find "$DATA_DIR" -type f -name "*.parquet" -print0)

"$SCRIPT_DIR/sync_pikpak.sh" "$STAGE_DIR"
