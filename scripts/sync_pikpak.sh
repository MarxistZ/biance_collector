#!/usr/bin/env bash
# Sync selected collector files to a PikPak rclone remote.

set -euo pipefail

REMOTE="${PIKPAK_REMOTE:-pikpak:binance_collector}"
SOURCE="${1:-data}"

if ! command -v rclone >/dev/null 2>&1; then
    echo "rclone not found" >&2
    exit 1
fi

rclone copy "$SOURCE" "$REMOTE" \
    --exclude "*.tmp" \
    --transfers "${RCLONE_TRANSFERS:-4}" \
    --checkers "${RCLONE_CHECKERS:-8}" \
    --stats 30s
