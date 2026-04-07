#!/bin/sh
# DevXOS auto-push: runs analysis and pushes to platform once per day.
# Runs in background to not block the commit.

DEVXOS_DIR="$HOME/.devxos"
STAMP_FILE="$DEVXOS_DIR/.last_push_$(basename "$(git rev-parse --show-toplevel)" 2>/dev/null | tr '/' '_')"
TODAY=$(date +%Y-%m-%d)

# Check if already pushed today
if [ -f "$STAMP_FILE" ]; then
    LAST_PUSH=$(cat "$STAMP_FILE" 2>/dev/null)
    if [ "$LAST_PUSH" = "$TODAY" ]; then
        exit 0
    fi
fi

# Check if devxos is available and authenticated
DEVXOS_BIN=""
for candidate in "$DEVXOS_DIR/bin/devxos" "$DEVXOS_DIR/venv/bin/devxos" "$(command -v devxos 2>/dev/null)"; do
    if [ -x "$candidate" ]; then
        DEVXOS_BIN="$candidate"
        break
    fi
done

if [ -z "$DEVXOS_BIN" ]; then
    exit 0
fi

# Check auth config exists
if [ ! -f "$DEVXOS_DIR/config.json" ]; then
    exit 0
fi

# Check token is configured
TOKEN=$(grep -o '"token"' "$DEVXOS_DIR/config.json" 2>/dev/null)
if [ -z "$TOKEN" ]; then
    exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -z "$REPO_ROOT" ]; then
    exit 0
fi

# Run in background so we don't block the commit
(
    mkdir -p "$DEVXOS_DIR"
    "$DEVXOS_BIN" "$REPO_ROOT" --push --quiet 2>/dev/null
    echo "$TODAY" > "$STAMP_FILE"
) &

exit 0
