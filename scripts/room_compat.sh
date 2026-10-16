#!/bin/sh
# Runs this checkout's room library and rooms on the Purple a release shipped (default
# release/2.x): a Studio change that would break rooms on Purple Keys already out there fails here.
set -eu
ref=${1:-release/2.x}
root=$(git rev-parse --show-toplevel)
tmp=$(mktemp -d)
trap 'git -C "$root" worktree remove --force "$tmp/purple" 2>/dev/null; rm -rf "$tmp"' EXIT
git -C "$root" worktree add --quiet --detach "$tmp/purple" "$ref"
cp "$root/tests/canvas/test_room_compat.py" "$tmp/purple/tests/canvas/"
cd "$tmp/purple"
PURPLE_ROOM_LIB="$root/purple_tui/roomkit/purple.py" \
PURPLE_ROOM_CORPUS="$root/tests/rooms:$root/studio/src/examples" \
    "$root/.venv/bin/python" -m pytest tests/canvas/test_room_compat.py -q -p no:cacheprovider
