#!/usr/bin/env bash
# Which commit is the public download, and is it the one you expect?
#
# Usage:
#   ./release-check.sh            # show the live version and its commit
#   ./release-check.sh abc1234    # also fail unless the download is that commit
#
# Reads the live /download.iso redirect and latest.json from the files host.
# Only needs R2_CUSTOM_DOMAIN from .env.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -a
source "$SCRIPT_DIR/.env"
set +a
HOST="https://${R2_CUSTOM_DOMAIN:?R2_CUSTOM_DOMAIN missing from build-scripts/.env}"

LATEST=$(curl -fsS "$HOST/latest.json")
VERSION=$(jq -r .version <<<"$LATEST")
SERVED=$(curl -fsSI "$HOST/download.iso" | sed -n 's#^location:.*/releases/\([^/]*\)/standard.iso.*#\1#Ip')
COMMIT=$(jq -r '.commit // empty' <<<"$LATEST")
# Releases before latest.json recorded the commit: the release tag is the record
[ -n "$COMMIT" ] || COMMIT=$(git -C "$SCRIPT_DIR" rev-parse --verify -q "refs/tags/${VERSION}^{commit}" || true)

echo "Download: $VERSION, released $(jq -r .released <<<"$LATEST")"
echo "Commit:   ${COMMIT:-unknown (no commit recorded and no $VERSION tag)}"

if [ "$SERVED" != "$VERSION" ]; then
    echo "✗ /download.iso redirects to ${SERVED:-nothing}, not $VERSION"
    exit 1
fi
[ -n "${1:-}" ] || exit 0
if [ -z "$COMMIT" ]; then
    RELEASED=$(jq -r .released <<<"$LATEST")
    if [ "$(git -C "$SCRIPT_DIR" log -1 --format=%ct "$1")" -gt "$(date -d "$RELEASED" +%s)" ]; then
        echo "✗ The download predates $1 (released $RELEASED, $1 committed $(git -C "$SCRIPT_DIR" log -1 --format=%cs "$1")): nothing has shipped since"
    else
        echo "✗ Cannot check $1: the commit for $VERSION is unknown"
    fi
    exit 1
fi
if [ "$(git -C "$SCRIPT_DIR" rev-parse --verify "${1}^{commit}")" = "$(git -C "$SCRIPT_DIR" rev-parse --verify "${COMMIT}^{commit}")" ]; then
    echo "✓ The download is $1"
else
    echo "✗ The download is ${COMMIT:0:7}, not $1"
    exit 1
fi
