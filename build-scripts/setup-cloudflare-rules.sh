#!/usr/bin/env bash
# Set up Cloudflare cache and redirect rules for ISO downloads.
#
# Requires CF_API_TOKEN and CF_ZONE_ID in .env (or environment).
# CF_API_TOKEN needs "Zone.Cache Rules", "Zone.Dynamic Redirect", and "Zone.Transform Rules" permissions.
#
# What this creates:
#   Cache rules:
#     /releases/* : cache 1 day at edge
#     /download*  : bypass cache (so pointer updates take effect immediately)
#   URL rewrite rules:
#     /                          → /index.html  (invisible rewrite, URL stays /)
#   Redirect rules:
#     /download.iso              → /releases/{version}/standard.iso         (302)
#     /download-debug.iso        → /releases/{version}/debug.iso            (302)
#     /download.iso.sha256       → /releases/{version}/standard.iso.sha256  (302)
#     /download-debug.iso.sha256 → /releases/{version}/debug.iso.sha256     (302)
#
# Usage:
#   ./setup-cloudflare-rules.sh                    # just cache rules
#   ./setup-cloudflare-rules.sh v2026.03.30-1430   # cache + redirect rules

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Load .env
ENV_FILE="$SCRIPT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

# Validate
MISSING=()
[ -z "${CF_API_TOKEN:-}" ] && MISSING+=("CF_API_TOKEN")
[ -z "${CF_ZONE_ID:-}" ] && MISSING+=("CF_ZONE_ID")

if [ ${#MISSING[@]} -gt 0 ]; then
    log_error "Missing required values: ${MISSING[*]}"
    echo "  Add CF_API_TOKEN and CF_ZONE_ID to $ENV_FILE"
    exit 1
fi

CF_API="https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}"
VERSION="${1:-}"

# Helper: make an API call and check for success
cf_api() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"

    local args=(-s -X "$method"
        -H "Authorization: Bearer $CF_API_TOKEN"
        -H "Content-Type: application/json"
    )
    [ -n "$data" ] && args+=(--data "$data")

    local response
    response=$(curl "${args[@]}" "${CF_API}${endpoint}")

    if echo "$response" | jq -e '.success' > /dev/null 2>&1; then
        local success
        success=$(echo "$response" | jq -r '.success')
        if [ "$success" != "true" ]; then
            log_error "API call failed: $method $endpoint"
            echo "$response" | jq '.errors' 2>/dev/null || echo "$response"
            return 1
        fi
    fi

    echo "$response"
}

# Find existing ruleset for a phase, or return empty string
find_ruleset_id() {
    local phase="$1"
    local rulesets
    rulesets=$(cf_api GET "/rulesets")
    echo "$rulesets" | jq -r ".result[] | select(.phase == \"$phase\") | .id" | head -1
}

# ─── Cache Rules ──────────────────────────────────────────────

setup_cache_rules() {
    log_step "Setting up cache rules..."

    local rules
    rules=$(cat <<'ENDJSON'
{
  "name": "Purple Computer download cache rules",
  "kind": "zone",
  "phase": "http_request_cache_settings",
  "rules": [
    {
      "description": "Cache release ISOs aggressively (1 day edge TTL)",
      "expression": "starts_with(http.request.uri.path, \"/releases/\")",
      "action": "set_cache_settings",
      "action_parameters": {
        "cache": true,
        "edge_ttl": {
          "mode": "override_origin",
          "default": 86400
        },
        "browser_ttl": {
          "mode": "override_origin",
          "default": 3600
        }
      }
    },
    {
      "description": "Bypass cache for download pointers and latest.json",
      "expression": "starts_with(http.request.uri.path, \"/download\") or http.request.uri.path eq \"/latest.json\"",
      "action": "set_cache_settings",
      "action_parameters": {
        "cache": false
      }
    }
  ]
}
ENDJSON
)

    local existing_id
    existing_id=$(find_ruleset_id "http_request_cache_settings")

    if [ -n "$existing_id" ]; then
        log_info "Updating existing cache ruleset ($existing_id)..."
        cf_api PUT "/rulesets/$existing_id" "$rules" > /dev/null
    else
        log_info "Creating new cache ruleset..."
        cf_api POST "/rulesets" "$rules" > /dev/null
    fi

    log_info "Cache rules configured."
}

# ─── URL Rewrite Rules ───────────────────────────────────────

setup_rewrite_rules() {
    log_step "Setting up URL rewrite rules..."

    local rules
    rules=$(cat <<'ENDJSON'
{
  "name": "Purple Computer URL rewrites",
  "kind": "zone",
  "phase": "http_request_transform",
  "rules": [
    {
      "description": "Rewrite / to /index.html (browser URL stays clean)",
      "expression": "http.request.uri.path eq \"/\"",
      "action": "rewrite",
      "action_parameters": {
        "uri": {
          "path": {
            "value": "/index.html"
          }
        }
      }
    }
  ]
}
ENDJSON
)

    local existing_id
    existing_id=$(find_ruleset_id "http_request_transform")

    if [ -n "$existing_id" ]; then
        log_info "Updating existing rewrite ruleset ($existing_id)..."
        cf_api PUT "/rulesets/$existing_id" "$rules" > /dev/null
    else
        log_info "Creating new rewrite ruleset..."
        cf_api POST "/rulesets" "$rules" > /dev/null
    fi

    log_info "Rewrite rules configured."
}

# ─── Redirect Rules ──────────────────────────────────────────

setup_redirect_rules() {
    local version="$1"

    if [ -z "$version" ]; then
        log_info "No version specified, skipping redirect rules."
        echo "  Pass a version to set up redirects: ./setup-cloudflare-rules.sh v1.0"
        return
    fi

    log_step "Setting up redirect rules for $version..."

    # Get custom domain from .env, or ask
    if [ -z "${R2_CUSTOM_DOMAIN:-}" ]; then
        log_error "R2_CUSTOM_DOMAIN not set in .env (needed for redirect target URLs)"
        exit 1
    fi

    local base_url="https://${R2_CUSTOM_DOMAIN}"

    local rules
    rules=$(cat <<ENDJSON
{
  "name": "Purple Computer download redirects",
  "kind": "zone",
  "phase": "http_request_dynamic_redirect",
  "rules": [
    {
      "description": "Redirect /download.iso to current release",
      "expression": "http.request.uri.path eq \"/download.iso\"",
      "action": "redirect",
      "action_parameters": {
        "from_value": {
          "status_code": 302,
          "target_url": {
            "value": "${base_url}/releases/${version}/standard.iso"
          }
        }
      }
    },
    {
      "description": "Redirect /download-debug.iso to current debug release",
      "expression": "http.request.uri.path eq \"/download-debug.iso\"",
      "action": "redirect",
      "action_parameters": {
        "from_value": {
          "status_code": 302,
          "target_url": {
            "value": "${base_url}/releases/${version}/debug.iso"
          }
        }
      }
    },
    {
      "description": "Redirect /download.iso.sha256 to current release checksum",
      "expression": "http.request.uri.path eq \"/download.iso.sha256\"",
      "action": "redirect",
      "action_parameters": {
        "from_value": {
          "status_code": 302,
          "target_url": {
            "value": "${base_url}/releases/${version}/standard.iso.sha256"
          }
        }
      }
    },
    {
      "description": "Redirect /download-debug.iso.sha256 to current debug release checksum",
      "expression": "http.request.uri.path eq \"/download-debug.iso.sha256\"",
      "action": "redirect",
      "action_parameters": {
        "from_value": {
          "status_code": 302,
          "target_url": {
            "value": "${base_url}/releases/${version}/debug.iso.sha256"
          }
        }
      }
    }
  ]
}
ENDJSON
)

    local existing_id
    existing_id=$(find_ruleset_id "http_request_dynamic_redirect")

    if [ -n "$existing_id" ]; then
        log_info "Updating existing redirect ruleset ($existing_id)..."
        cf_api PUT "/rulesets/$existing_id" "$rules" > /dev/null
    else
        log_info "Creating new redirect ruleset..."
        cf_api POST "/rulesets" "$rules" > /dev/null
    fi

    log_info "Redirect rules configured:"
    log_info "  /download.iso              → /releases/${version}/standard.iso"
    log_info "  /download-debug.iso        → /releases/${version}/debug.iso"
    log_info "  /download.iso.sha256       → /releases/${version}/standard.iso.sha256"
    log_info "  /download-debug.iso.sha256 → /releases/${version}/debug.iso.sha256"
}

# ─── Main ─────────────────────────────────────────────────────

echo
echo "=========================================="
echo "  Cloudflare Rules Setup"
echo "=========================================="
echo

setup_cache_rules
echo
setup_rewrite_rules
echo
setup_redirect_rules "$VERSION"

echo
log_info "Done! Verify with: curl -sI https://\${R2_CUSTOM_DOMAIN}/download.iso | grep -i cf-cache-status"
echo
