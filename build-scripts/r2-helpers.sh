#!/usr/bin/env bash
# Shared helpers for R2 upload scripts.
# Source this file, don't run it directly.

GREEN='\033[0;32m'
NC='\033[0m'

R2_HELPERS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load .env and set up R2 credentials. Exits on missing required vars.
r2_init() {
    local env_file="$R2_HELPERS_DIR/.env"
    if [ ! -f "$env_file" ]; then
        echo "Missing $env_file (need R2 credentials)"
        exit 1
    fi
    set -a
    source "$env_file"
    set +a

    local missing=()
    [ -z "${R2_BUCKET:-}" ] && missing+=("R2_BUCKET")
    [ -z "${R2_ACCOUNT_ID:-}" ] && missing+=("R2_ACCOUNT_ID")
    [ -z "${R2_ACCESS_KEY_ID:-}" ] && missing+=("R2_ACCESS_KEY_ID")
    [ -z "${R2_SECRET_ACCESS_KEY:-}" ] && missing+=("R2_SECRET_ACCESS_KEY")

    if [ ${#missing[@]} -gt 0 ]; then
        echo "Missing required values in .env: ${missing[*]}"
        exit 1
    fi

    R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
    export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
}

# Upload a file to R2. Args: local_path r2_key content_type
r2_upload() {
    local local_path="$1" r2_key="$2" content_type="$3"
    aws s3 cp "$local_path" "s3://${R2_BUCKET}/${r2_key}" \
        --endpoint-url "$R2_ENDPOINT" \
        --content-type "$content_type" \
        --no-progress
}

# Extract and upload PDFs from cards/purple.pdf
upload_pdfs() {
    just python - <<'EOF'
import fitz
doc = fitz.open("cards/purple.pdf")
install = fitz.open()
install.insert_pdf(doc, from_page=0, to_page=1)
install.save("cards/purple-installation.pdf")
print("Extracted pages 1-2 → cards/purple-installation.pdf")
guide = fitz.open()
guide.insert_pdf(doc, from_page=2, to_page=2)
guide.save("cards/purple-guide.pdf")
print("Extracted page 3 → cards/purple-guide.pdf")
EOF

    local cards_dir="$R2_HELPERS_DIR/../cards"
    r2_upload "$cards_dir/purple-installation.pdf" "purple-installation.pdf" "application/pdf"
    r2_upload "$cards_dir/purple-guide.pdf" "purple-guide.pdf" "application/pdf"
    echo -e "${GREEN}Uploaded${NC} purple-installation.pdf + purple-guide.pdf"
}

# Purge Cloudflare cache for given URL paths (e.g. "/" "/index.html" "/foo.pdf").
# Requires CF_API_TOKEN, CF_ZONE_ID, R2_CUSTOM_DOMAIN in env. Skips gracefully if missing.
purge_cache() {
    if [ -z "${CF_API_TOKEN:-}" ] || [ -z "${CF_ZONE_ID:-}" ] || [ -z "${R2_CUSTOM_DOMAIN:-}" ]; then
        echo "Skipping cache purge (CF_API_TOKEN, CF_ZONE_ID, or R2_CUSTOM_DOMAIN not set)"
        return
    fi

    # Build JSON array of full URLs
    local urls=""
    for path in "$@"; do
        [ -n "$urls" ] && urls+=","
        urls+="\"https://${R2_CUSTOM_DOMAIN}${path}\""
    done

    echo "Purging Cloudflare cache..."
    local result
    result=$(curl -s -X POST \
        "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/purge_cache" \
        -H "Authorization: Bearer $CF_API_TOKEN" \
        -H "Content-Type: application/json" \
        --data "{\"files\":[${urls}]}")

    if echo "$result" | jq -e '.success == true' > /dev/null 2>&1; then
        echo -e "${GREEN}Cache purged${NC}"
    else
        echo "Warning: cache purge failed (files uploaded, but old versions may be served briefly)"
        echo "$result" | jq '.errors' 2>/dev/null || echo "$result"
    fi
}
