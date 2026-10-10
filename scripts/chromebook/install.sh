#!/bin/bash
# Stage 1: installs Purple under /usr/local/purple on a Developer Mode Chromebook.
# Writes files there and nowhere else: no partition, kernel or ChromeOS change.
# Run as root from the stick: sudo bash, then bash install.sh
# Design: guides/chromebook-dev-mode-plan.md
set -u -o pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
LOGS=("$SRC/install.log" /usr/local/purple/install.log)
. "$SRC/common.sh"

inventory
log "=== install ==="
install_app
echo "$SRC" > "$DEST/stick-path"
rm -rf /usr/local/purple-probe
sync
log "=== installed $(date) ==="
echo
echo "Start Purple:   bash $DEST/purple-run.sh"
echo "Leave Purple:   hold Ctrl+\\ for 3 seconds. ChromeOS comes back in about 10 seconds."
echo "Logs land in $DEST/logs and, while the stick is mounted, in $SRC/logs"
