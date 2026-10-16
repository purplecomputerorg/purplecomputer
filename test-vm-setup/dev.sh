#!/bin/bash
# Pull the latest code and run Purple in dev mode. Pass a repo path to override the default.
set -e

cd "${1:-$HOME/purplecomputer}"
git pull
just run-dev
