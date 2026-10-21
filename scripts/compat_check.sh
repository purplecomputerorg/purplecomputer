#!/usr/bin/env bash
# Fetches the Purple builds people downloaded or were shipped (landing's /api/admin/purple-builds) and
# checks each against the packs Studio makes today: scripts/compat_check.py. Reads FLASH_LOG_URL and
# ADMIN_PASSWORD_PROD from build-scripts/.env, like record-flash.sh. Never prints the password.
#
# Usage: just compat-check [--quick]    --quick skips running today's rooms on each build
set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$ROOT/build-scripts/.env" ]] && source "$ROOT/build-scripts/.env"
if [[ -z "${FLASH_LOG_URL:-}" || -z "${ADMIN_PASSWORD_PROD:-}" ]]; then
    echo "compat-check: FLASH_LOG_URL and ADMIN_PASSWORD_PROD must be set in build-scripts/.env" >&2
    exit 1
fi

CF_HEADERS=()
[[ -n "${CF_ACCESS_CLIENT_ID:-}" ]] && CF_HEADERS+=(-H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID")
[[ -n "${CF_ACCESS_CLIENT_SECRET:-}" ]] && CF_HEADERS+=(-H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET")

builds="$(mktemp)"
trap 'rm -f "$builds"' EXIT
curl -fsS --max-time 20 -u ":$ADMIN_PASSWORD_PROD" "${CF_HEADERS[@]}" "${FLASH_LOG_URL%/flashes}/purple-builds" -o "$builds" \
    || { echo "compat-check: couldn't fetch the builds list (check the password, and that landing has /api/admin/purple-builds deployed)" >&2; exit 1; }
"$ROOT/.venv/bin/python" "$ROOT/scripts/compat_check.py" "$builds" "$@"
