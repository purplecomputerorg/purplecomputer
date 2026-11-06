#!/bin/bash
# Pull the latest code, refresh Example Rooms, and run Purple in dev mode. Pass a repo path to override the default.
set -e

# From the console, start X first and rerun this inside its terminal.
[ -n "$DISPLAY" ] || exec startx-purple -e "$0" "$@"

cd "${1:-$HOME/purplecomputer}"
git pull
just example-rooms
PURPLE_FAKE_PRINTER=1 just run-dev  # Print shows the page on screen instead of printing
