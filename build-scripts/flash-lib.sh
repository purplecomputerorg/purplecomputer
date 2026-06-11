#!/usr/bin/env bash
# Shared helpers for flash-to-usb.sh and flash-all.sh.
# Sourced, not executed.

# Global safety cap: reject anything larger regardless of per-entry max.
MAX_SIZE_GB=256

# Convert lsblk SIZE string (e.g. "14.5G", "5.5T", "512M") to integer GB.
parse_size_to_gb() {
    local num unit
    num=$(echo "$1" | sed 's/[^0-9.]//g')
    unit=$(echo "$1" | sed 's/[0-9.]//g')
    case "$unit" in
        T) awk -v n="$num" 'BEGIN { printf "%.0f", n * 1024 }' ;;
        G) awk -v n="$num" 'BEGIN { printf "%.0f", n }' ;;
        *) echo 0 ;;
    esac
}

# Test whether a whitelist rule matches a drive.
# Rule formats:
#   <serial>                                   exact serial match
#   model:<VENDOR>/<MODEL> [max=NG] [min=NG]   match any drive of that vendor+model in size range
rule_matches() {
    local rule="$1" vendor="$2" model="$3" serial="$4" size_gb="$5"
    local rule_max=$MAX_SIZE_GB rule_min=0

    if [[ "$rule" == model:* ]]; then
        local spec="${rule#model:}"
        while [[ "$spec" =~ ^(.*[^[:space:]])[[:space:]]+(max|min)=([0-9]+)G?$ ]]; do
            spec="${BASH_REMATCH[1]}"
            if [[ "${BASH_REMATCH[2]}" == max ]]; then
                rule_max="${BASH_REMATCH[3]}"
            else
                rule_min="${BASH_REMATCH[3]}"
            fi
        done
        [[ "$vendor" != "${spec%%/*}" ]] && return 1
        [[ "$model" != "${spec#*/}" ]] && return 1
    else
        [[ "$serial" != "$rule" ]] && return 1
    fi

    [[ $size_gb -gt $rule_max ]] && return 1
    [[ $size_gb -lt $rule_min ]] && return 1
    [[ $size_gb -gt $MAX_SIZE_GB ]] && return 1
    return 0
}

# Load whitelist entries from $CONFIG_FILE into the WHITELIST array.
# Exits with an error if the file is missing or empty.
load_whitelist() {
    if [[ ! -f "$CONFIG_FILE" ]]; then
        echo "[ERROR] Config file not found: $CONFIG_FILE" >&2
        exit 1
    fi
    WHITELIST=()
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        line=$(echo "$line" | xargs)
        [[ -n "$line" ]] && WHITELIST+=("$line")
    done < "$CONFIG_FILE"
    if [[ ${#WHITELIST[@]} -eq 0 ]]; then
        echo "[ERROR] No drive serials found in $CONFIG_FILE" >&2
        exit 1
    fi
}

# Populate FOUND_DRIVES with "dev|size|model|serial" entries for every
# plugged-in USB drive that matches a whitelist rule.
find_whitelisted_drives() {
    FOUND_DRIVES=()
    while IFS= read -r line; do
        eval "$line"
        [[ "$TRAN" != "usb" ]] && continue
        [[ -z "$SERIAL" ]] && continue
        local vendor size_gb
        vendor=$(echo "$VENDOR" | xargs)
        size_gb=$(parse_size_to_gb "$SIZE")
        for rule in "${WHITELIST[@]}"; do
            if rule_matches "$rule" "$vendor" "$MODEL" "$SERIAL" "$size_gb"; then
                FOUND_DRIVES+=("/dev/$NAME|$SIZE|$MODEL|$SERIAL")
                break
            fi
        done
    done < <(lsblk -d -n -o NAME,SIZE,TRAN,VENDOR,MODEL,SERIAL -P 2>/dev/null)
}

# Verify the ISO matches its build-time .sha256 sidecar, echoing the verified
# hash on success. Returns 1 on mismatch; warns but succeeds when no sidecar
# exists (e.g. a hand-specified ISO). This guards the highest-blast-radius
# mistake: flashing many drives from a truncated or wrong-build ISO, which
# passes every per-drive readback yet is wrong on every stick.
verify_iso_checksum() {
    local iso="$1" sidecar="$1.sha256" expected actual
    actual="$(sha256sum "$iso" | awk '{print $1}')"
    if [[ ! -f "$sidecar" ]]; then
        echo "[WARN] No checksum sidecar ($sidecar); skipping ISO identity check." >&2
        echo "$actual"
        return 0
    fi
    expected="$(awk '{print $1}' "$sidecar")"
    if [[ "$actual" != "$expected" ]]; then
        echo "[ERROR] ISO does not match its build checksum (corrupt or wrong build)." >&2
        echo "[ERROR]   expected: $expected" >&2
        echo "[ERROR]   actual:   $actual" >&2
        return 1
    fi
    echo "$actual"
}

# Append-only QA record of every drive flashed, for shipping traceability.
# Lives next to .flash-drives.conf (gitignored).
manifest_path() { echo "$PROJECT_DIR/flash-manifest.csv"; }

# Create the header if the manifest doesn't exist yet. Call once from the
# top-level invocation, before any parallel children, to avoid a header race.
init_manifest() {
    local m; m="$(manifest_path)"
    [[ -f "$m" ]] || echo "timestamp,status,serial,model,size,iso,sha256,device" > "$m"
}

# Append one CSV row per drive. A single-line O_APPEND write stays under the
# 4KB PIPE_BUF atomicity limit, so parallel flash-all children append safely
# without locking. Model is quoted since it can contain spaces.
record_manifest() {
    local status="$1" device="$2" serial="$3" model="$4" size="$5" iso="$6" sha="$7"
    printf '%s,%s,%s,"%s",%s,%s,%s,%s\n' \
        "$(date -Iseconds)" "$status" "$serial" "$model" "$size" "$iso" "$sha" "$device" \
        >> "$(manifest_path)"
}

# Resolve the most recent ISO in $OUTPUT_DIR. Pass "debug" for .debug.iso.
find_latest_iso() {
    [[ -d "$OUTPUT_DIR" ]] || return 0
    if [[ "${1:-}" == debug ]]; then
        ls -t "$OUTPUT_DIR"/purple-*.debug.iso 2>/dev/null | head -1
    else
        ls -t "$OUTPUT_DIR"/purple-*.iso 2>/dev/null | grep -v '\.debug\.iso$' | head -1
    fi
}
