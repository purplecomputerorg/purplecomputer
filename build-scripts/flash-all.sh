#!/usr/bin/env bash
# Flash PurpleOS ISO to ALL whitelisted USB drives in parallel.
# Each drive runs its own pipeline (flash with retries, boot-settle,
# re-verify, eject) as an independent job, so one slow or failing drive never
# holds up the batch. One udev gate is shared across children; per-drive logs
# stream to /tmp.

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/flash-lib.sh"
CONFIG_FILE="$PROJECT_DIR/.flash-drives.conf"
FLASH_SCRIPT="$SCRIPT_DIR/flash-to-usb.sh"

usage() {
    cat <<EOF
Usage: $0 [--debug] [--yes] [iso-path]
       $0 --corrupt [scenario...]

Flash an ISO to every whitelisted USB drive currently plugged in, in parallel.

With --corrupt, flash the corrupt-test scenario ISOs (made by 'just
corrupt-test-iso all') instead: one scenario per drive, then an interactive
unplug phase tells you which stick got which scenario as you pull each one.
Positional args select scenarios (default: ${CORRUPT_SCENARIOS[*]}).
Corrupt mode never boot-settles: these drives are for one throwaway test.

Options:
  --debug       Use the newest build's debug ISO
  --no-backup   Use the newest build's standard ISO (no backup image copy)
  --corrupt     Flash corrupt-test scenario ISOs, one per drive
  --yes         Skip the confirmation prompt
  --retries <n> Automatic re-flashes for a drive that fails verification,
                each preceded by a power-cycle of its hub port (default 1)
  --no-reverify Skip the post-settle re-read that confirms the image is still
                intact before the drive is ejected
  --no-settle   Skip the post-flash QEMU boot-settle (faster, but the first
                live boot on each drive will be slow)
  --ref <c>     Use an old commit's archived build (made by 'just build --ref <c>')
  --help        Show this help
EOF
}

SKIP_CONFIRM=false
SKIP_SETTLE=false
CORRUPT_MODE=false
ISO_KIND=""
MAX_ATTEMPTS=2
REVERIFY=true
POSITIONAL=()
while [[ -n "${1:-}" ]]; do
    case "$1" in
        --help|-h)    usage; exit 0 ;;
        --retries)    MAX_ATTEMPTS=$(( ${2:-1} + 1 )); shift 2 ;;
        --no-reverify) REVERIFY=false; shift ;;
        --debug|-d)   ISO_KIND=debug; shift ;;
        --no-backup)  ISO_KIND=standard; shift ;;
        --corrupt)    CORRUPT_MODE=true; shift ;;
        --yes|-y)     SKIP_CONFIRM=true; shift ;;
        --no-settle)  SKIP_SETTLE=true; shift ;;
        --ref)        OUTPUT_DIR="$(archive_dir_for_ref "$2")/output" || { log_error "Cannot resolve git commit '$2'"; exit 1; }; shift 2 ;;
        *)            POSITIONAL+=("$1"); shift ;;
    esac
done

# SCENARIOS[i] and SCEN_ISOS[i] pair up; empty outside corrupt mode.
SCENARIOS=()
SCEN_ISOS=()
ISO_PATH=""
if [[ "$CORRUPT_MODE" == true ]]; then
    SKIP_SETTLE=true
    SCENARIOS=("${POSITIONAL[@]}")
    (( ${#SCENARIOS[@]} )) || SCENARIOS=("${CORRUPT_SCENARIOS[@]}")
    for s in "${SCENARIOS[@]}"; do
        if [[ " ${CORRUPT_SCENARIOS[*]} " != *" $s "* ]]; then
            log_error "Unknown scenario '$s' (choose from: ${CORRUPT_SCENARIOS[*]})."
            exit 1
        fi
        iso="$(find_corrupt_iso "$s")"
        if [[ -z "$iso" ]]; then
            log_error "No corrupt-test ISO for scenario '$s' in $OUTPUT_DIR."
            log_error "Make them with 'just corrupt-test-iso all' first."
            exit 1
        fi
        warn_if_stale_corrupt_iso "$iso"
        SCEN_ISOS+=("$iso")
    done
else
    # Variant flags resolve against the NEWEST build only; an older build is
    # never picked silently. Pass a path explicitly to flash an older ISO.
    ISO_PATH="${POSITIONAL[0]:-}"
    if [[ -z "$ISO_PATH" ]]; then
        ISO_PATH="$(find_latest_iso "$ISO_KIND")"
    fi
    if [[ -z "$ISO_PATH" || ! -f "$ISO_PATH" ]]; then
        log_error "No matching ISO for the newest build in $OUTPUT_DIR."
        if [[ "$OUTPUT_DIR" == */archive/* ]]; then
            log_error "Build it first with 'just build --ref <commit>'."
        else
            log_error "Run 'just build' first, or pass an ISO path explicitly."
        fi
        exit 1
    fi
fi

load_whitelist
if [[ ${#WHITELIST[@]} -eq 0 ]]; then
    log_error "flash-all requires a drive whitelist ($CONFIG_FILE)."
    log_error "For a single drive without a whitelist, use flash-to-usb.sh (just flash)."
    exit 1
fi
find_whitelisted_drives

if [[ ${#FOUND_DRIVES[@]} -eq 0 ]]; then
    log_error "No whitelisted USB drives found."
    exit 1
fi

# Per-drive parallel arrays: normal mode repeats one ISO across every drive,
# corrupt mode zips scenarios onto drives in discovery order.
ENTRIES=()
ISOS=()
SCENS=()
if [[ "$CORRUPT_MODE" == true ]]; then
    COUNT=${#SCENARIOS[@]}
    if (( ${#FOUND_DRIVES[@]} < COUNT )); then
        COUNT=${#FOUND_DRIVES[@]}
        log_error "Only $COUNT drive(s) plugged in for ${#SCENARIOS[@]} scenarios; skipping: ${SCENARIOS[*]:$COUNT}"
    elif (( ${#FOUND_DRIVES[@]} > COUNT )); then
        log_info "${#FOUND_DRIVES[@]} drives plugged in but only $COUNT scenario(s); the extra drives will be left untouched."
    fi
    for ((i = 0; i < COUNT; i++)); do
        ENTRIES+=("${FOUND_DRIVES[$i]}")
        ISOS+=("${SCEN_ISOS[$i]}")
        SCENS+=("${SCENARIOS[$i]}")
    done
else
    for entry in "${FOUND_DRIVES[@]}"; do
        ENTRIES+=("$entry")
        ISOS+=("$ISO_PATH")
        SCENS+=("")
    done
fi

# Per-drive state, indexed alongside ENTRIES. Tracked by serial, not device
# node: a power-cycled drive can come back under a different letter, and
# retrying the old letter could write to whatever landed there instead.
# ST_PORT/ST_PORTNAME are captured now, while every drive is still enumerated:
# a drive that fails or gets ejected loses its /sys/block entry, and with it
# any way to find which hub socket it sits in.
ST_DEV=(); ST_SER=(); ST_PORT=(); ST_PORTNAME=()
for i in "${!ENTRIES[@]}"; do
    IFS='|' read -r dev _ _ ser <<< "${ENTRIES[$i]}"
    ST_DEV+=("$dev"); ST_SER+=("$ser")
    ST_PORT+=("$(usb_port_control "$dev" 2>/dev/null || true)")
    ST_PORTNAME+=("$(usb_port_name "$dev" 2>/dev/null || true)")
done

# Physical socket label for drive index $1 ("top row 3"), from the launch-time
# port capture so it works even after the drive drops off the bus.
slot_name() {
    local port="${ST_PORTNAME[$1]}" label
    [[ -n "$port" ]] || { echo "unknown socket (${ST_DEV[$1]})"; return; }
    label="$(port_label "$port")"
    echo "${label:-socket $port}"
}

echo
if [[ "$CORRUPT_MODE" == true ]]; then
    echo -e "${BOLD}${YELLOW}Will flash ${#ENTRIES[@]} corrupt-test scenario(s), one per drive, in parallel:${NC}"
else
    ISO_VERSION="$(tr -d '[:space:]' < "${ISO_PATH}.version" 2>/dev/null || true)"
    echo -e "${BOLD}${YELLOW}Will flash $(basename "$ISO_PATH") (version ${ISO_VERSION:-unknown}) to ${#ENTRIES[@]} drive(s) in parallel:${NC}"
    # Shipping guard: customer batches should be release builds.
    ISO_SRC_COMMIT="$(tr -d '[:space:]' < "${ISO_PATH}.commit" 2>/dev/null || true)"
    RELEASE_HEAD="$(git -C "$PROJECT_DIR" rev-parse release/1.x 2>/dev/null || true)"
    UNSHIPPABLE=""
    if [[ -z "$ISO_SRC_COMMIT" ]]; then
        UNSHIPPABLE="this ISO has no .commit sidecar, so its source commit is unknown"
    elif [[ -z "$RELEASE_HEAD" ]]; then
        UNSHIPPABLE="release/1.x was not found locally to compare against"
    elif [[ "$RELEASE_HEAD" != "$ISO_SRC_COMMIT"* ]]; then
        if git -C "$PROJECT_DIR" merge-base --is-ancestor "$ISO_SRC_COMMIT" release/1.x 2>/dev/null; then
            ISO_LINE="an older release build"
        elif git -C "$PROJECT_DIR" merge-base --is-ancestor "$ISO_SRC_COMMIT" main 2>/dev/null; then
            ISO_LINE="a main build, not a release build"
        else
            ISO_LINE="from a commit on neither main nor release/1.x"
        fi
        UNSHIPPABLE="this ISO is $ISO_LINE (commit $ISO_SRC_COMMIT), release/1.x is at ${RELEASE_HEAD:0:7}"
    fi
    if [[ -n "$UNSHIPPABLE" ]]; then
        echo -e "  ${YELLOW}${BOLD}Not confirmed as the current release build:${NC}${YELLOW} ${UNSHIPPABLE}.${NC}"
        echo -e "  ${YELLOW}Fine for dev sticks; do not ship these drives to customers.${NC}"
    else
        echo -e "  ${GREEN}Current release build: commit ${ISO_SRC_COMMIT} matches release/1.x.${NC}"
    fi
fi
SLOTS=()
for i in "${!ENTRIES[@]}"; do
    IFS='|' read -r dev size model serial <<< "${ENTRIES[$i]}"
    SLOTS+=("$(slot_name "$i")")
    printf "  %-16s %-10s %-8s %-22s %-16s %s\n" "${SLOTS[$i]}" "$dev" "$size" "$model" "$serial" "${SCENS[$i]:+-> ${SCENS[$i]}}"
done
echo -e "  ${BOLD}Slots:${NC} $(printf '%s\n' "${SLOTS[@]}" | sort -V | paste -sd, | sed 's/,/, /g')"
echo -e "  ${RED}${BOLD}ALL DATA ON THESE DRIVES WILL BE DESTROYED${NC}"
echo

if [[ "$SKIP_CONFIRM" != true ]]; then
    read -p "Type 'yes' to continue: " confirm
    [[ "$confirm" == "yes" ]] || { log_info "Aborted."; exit 0; }
fi

# Verify each distinct ISO against its build checksum once the user commits,
# then hand the verified hash to children so they skip re-hashing 6GB apiece.
# After the prompt so it doesn't stall confirmation; still before any drive is
# written.
declare -A SHA_BY_ISO=()
for iso in "${ISOS[@]}"; do
    [[ -n "${SHA_BY_ISO[$iso]:-}" ]] && continue
    sha="$(verify_iso_checksum "$iso")" || exit 1
    SHA_BY_ISO["$iso"]="$sha"
done
init_manifest
log_info "ISO checksum(s) OK."

# Prime sudo and keep the timestamp fresh for the duration of the run, so
# children don't hit a password prompt mid-dd on long parallel flashes.
sudo -v
( while true; do sudo -n -v 2>/dev/null || exit; sleep 60; done ) &
SUDO_KEEPALIVE_PID=$!

log_info "Pausing udev exec queue..."
sudo udevadm control --stop-exec-queue 2>/dev/null || true
cleanup() {
    kill "$SUDO_KEEPALIVE_PID" 2>/dev/null || true
    sudo udevadm control --start-exec-queue 2>/dev/null || true
}
trap cleanup EXIT INT TERM

LOG_DIR="$(mktemp -d -t purple-flash-all.XXXXXX)"
log_info "Per-drive logs: $LOG_DIR"
echo

# Cross-job coordination lives in files under STATE_DIR: flashed.$i markers
# gate the udev queue restart, slot dirs bound settle/re-verify concurrency,
# and result.$i carries each job's outcome back as "status|dev|tries|log".
STATE_DIR="$LOG_DIR/state"
mkdir -p "$STATE_DIR"
: > "$STATE_DIR/safe-slots"
SETTLE_MAX=$(boot_settle_max_jobs)

# Comma-joined ship-ready slots. Labels can't contain | (save_port_label strips it).
safe_slot_list() { paste -sd'|' "$STATE_DIR/safe-slots" | sed 's/|/, /g'; }

# Record a drive's outcome and announce, by physical slot, that its stick can
# come out of the hub. Good sticks join the running ship-ready list.
finish_drive() {
    local i="$1" status="$2" dev="$3" tries="$4" log="$5" slot safe
    slot="$(slot_name "$i")"
    echo "$status|$dev|$tries|$log|$slot" > "$STATE_DIR/result.$i"
    [[ "$CORRUPT_MODE" == true ]] && return 0
    if [[ "$status" == ok ]]; then
        echo "$slot" >> "$STATE_DIR/safe-slots"
        echo -e "${GREEN}${BOLD}✓ TAKE OUT ${slot}${NC}${GREEN}: done, safe to ship.${NC}"
    else
        echo -e "${RED}${BOLD}✗ TAKE OUT ${slot}${NC}${RED}: FAILED, set it aside, do NOT ship it.${NC}"
    fi
    safe="$(safe_slot_list)"
    echo -e "  ${BOLD}Ship-ready so far ($(wc -l < "$STATE_DIR/safe-slots")/${#ENTRIES[@]}):${NC} ${safe:-none}"
}

# One drive's whole journey, run as its own background job so a slow or
# failing drive never holds up the rest of the batch: flash (with power-cycle
# retries), boot-settle, re-verify, eject.
run_drive() {
    local i="$1"
    local dev="${ST_DEV[$i]}" serial="${ST_SER[$i]}" port="${ST_PORT[$i]}"
    local iso="${ISOS[$i]}" tries=0 ok=false log newdev suffix
    local max_attempts=$MAX_ATTEMPTS
    # Corrupt mode never retries: these sticks are for one throwaway test.
    [[ "$CORRUPT_MODE" == true ]] && max_attempts=1

    while (( tries < max_attempts )); do
        tries=$((tries + 1))
        suffix=""
        (( tries > 1 )) && suffix=".try${tries}"
        log="$LOG_DIR/$(basename "$dev")${suffix}.log"
        echo -e "${BOLD}→ $dev${SCENS[$i]:+ [${SCENS[$i]}]}: flashing (tail -f $log)${NC}"
        if VERIFIED_ISO_SHA256="${SHA_BY_ISO[$iso]}" \
            "$FLASH_SCRIPT" --yes --no-udev-gate --device "$dev" "$iso" >"$log" 2>&1; then
            ok=true
            break
        fi
        (( tries < max_attempts )) || break
        if [[ -z "$port" ]]; then
            log_error "No hub port recorded for $dev ($serial); cannot power-cycle it. Re-seat it by hand and re-run."
            break
        fi
        log_info "$dev failed; power-cycling $serial at $(slot_name "$i") to retry..."
        newdev="$(recover_drive "$port" "$serial" || true)"
        if [[ -z "$newdev" ]]; then
            log_error "$serial did not come back after a power cycle; leaving it failed."
            break
        fi
        [[ "$newdev" != "$dev" ]] && log_info "$serial came back as $newdev (was $dev)."
        dev="$newdev"
    done

    # The parent restarts the udev exec queue once every drive has one of these.
    : > "$STATE_DIR/flashed.$i"

    if [[ "$ok" != true ]]; then
        echo -e "${RED}✗${NC} $dev — FAILED (see $log)"
        finish_drive "$i" fail "$dev" "$tries" "$log"
        return 0
    fi
    echo -e "${GREEN}✓${NC} $dev — flashed and verified$( (( tries > 1 )) && echo " (after retry)")"

    if [[ "$SKIP_SETTLE" != true ]]; then
        # Boot the drive once in QEMU so its controller pays the one-time
        # post-write cost here instead of on the parent's first boot (see
        # guides/usb-flash-settle.md). Slots keep concurrent guests in RAM.
        slot_acquire "$STATE_DIR/settle-slots" "$SETTLE_MAX" 8
        log_info "$dev: boot-settling in QEMU..."
        if boot_settle_with_retry "$dev" "$LOG_DIR/$(basename "$dev").boot-settle.log"; then
            echo -e "${GREEN}✓${NC} $dev: boot-settled"
        else
            echo -e "${YELLOW}!${NC} $dev: boot settle incomplete after retry, first real boot may be slow"
            echo -e "    drive: $(drive_location "$dev")"
            echo -e "    log:   $LOG_DIR/$(basename "$dev").boot-settle.log"
        fi
        slot_release 8

        # Re-read the drive before ejecting, catching flash that decays in the
        # minutes after being written. Must precede eject_drive: a powered-off
        # drive leaves a media-less node whose reads look like corruption.
        if [[ "$REVERIFY" == true ]]; then
            slot_acquire "$STATE_DIR/reverify-slots" 4 8
            log_info "$dev: re-verifying after settle..."
            if ! recheck_after_settle "$dev" "$iso"; then
                slot_release 8
                echo -e "${RED}✗${NC} $dev: verified after writing but NOT after settle, flash is decaying"
                record_manifest fail-post-settle "$dev" "$serial" "" "" "$(basename "$iso")" ""
                finish_drive "$i" fail "$dev" "$tries" "$log"
                return 0
            fi
            slot_release 8
            echo -e "${GREEN}✓${NC} $dev: still intact after settle"
        fi
    fi

    # Ejecting needs udev back (udevadm settle), so wait for the parent to
    # lift the queue after the last drive finishes writing. Corrupt mode skips
    # the eject so the identify phase can watch for unplugs; safe because every
    # write is synced and verified, and these sticks get reflashed anyway.
    if [[ "$CORRUPT_MODE" != true ]]; then
        while [[ ! -e "$STATE_DIR/udev-lifted" ]]; do sleep 1; done
        eject_drive "$dev" || true
    fi
    finish_drive "$i" ok "$dev" "$tries" "$log"
}

PIDS=()
for i in "${!ENTRIES[@]}"; do
    run_drive "$i" &
    PIDS+=("$!")
done

echo
log_info "All ${#ENTRIES[@]} drive pipeline(s) started; each flashes, settles (up to $SETTLE_MAX at a time so QEMU guests fit in RAM), re-verifies, and ejects on its own. Takes a while, walk away."
echo

# Restart the udev exec queue as soon as every drive is done writing (marker
# present, or its job died without leaving one), so early finishers can eject
# while stragglers are still settling.
while true; do
    PENDING=false
    for i in "${!ENTRIES[@]}"; do
        [[ -e "$STATE_DIR/flashed.$i" ]] && continue
        [[ "$(count_running "${PIDS[$i]}")" == 0 ]] && continue
        PENDING=true
        break
    done
    [[ "$PENDING" == false ]] && break
    sleep 2
done
sudo udevadm control --start-exec-queue 2>/dev/null || true
: > "$STATE_DIR/udev-lifted"

for pid in "${PIDS[@]}"; do
    wait "$pid" || true
done

# Fold each job's outcome back into per-drive state. ST_OK[i] is the only
# source of truth for whether a drive is good: every stage below iterates
# indices and consults it rather than matching device nodes, since a
# power-cycled drive can come back on a letter another stick just gave up.
# DEVS is the corrupt-mode identify path's own live node list, which it
# rewrites as drives are replugged.
ST_OK=(); ST_TRIES=(); ST_LOG=()
for i in "${!ENTRIES[@]}"; do
    status=fail; dev="${ST_DEV[$i]}"; tries=0; lg=""
    [[ -f "$STATE_DIR/result.$i" ]] && IFS='|' read -r status dev tries lg _ < "$STATE_DIR/result.$i"
    ST_DEV[$i]="$dev"; ST_TRIES[$i]="$tries"; ST_LOG[$i]="$lg"
    [[ "$status" == ok ]] && ST_OK[$i]=true || ST_OK[$i]=false
done
DEVS=("${ST_DEV[@]}")

FAILED=()
for i in "${!ENTRIES[@]}"; do
    [[ "${ST_OK[$i]}" == true ]] || FAILED+=("${ST_DEV[$i]}")
done

echo
log_info "QA manifest: $(manifest_path)"

# Report which software build just went onto these drives, so I can tie a shipped
# batch to a git hash without digging through the manifest. Uses the currently
# checked-out commit (build-then-flash means HEAD matches the ISO).
SUCCEEDED=$(( ${#DEVS[@]} - ${#FAILED[@]} ))
if [[ $SUCCEEDED -gt 0 && "$CORRUPT_MODE" != true ]]; then
    # Prefer the version baked into the ISO (build-<hash>-<date>, from the .version
    # sidecar 01-remaster-iso.sh writes next to the ISO): that's the commit the
    # software was actually built from. Fall back to the checked-out commit only
    # for older ISOs with no sidecar, which may be AHEAD of what's on the drive.
    FLASH_VERSION=""; FLASH_SHORT=""; FLASH_FULL=""; FLASH_BRANCH=""; FLASH_SRC=""
    if [[ -f "${ISO_PATH}.version" ]]; then
        FLASH_VERSION="$(tr -d '[:space:]' < "${ISO_PATH}.version")"
        FLASH_SRC="iso"
        if [[ "$FLASH_VERSION" == build-*-* ]]; then
            _v="${FLASH_VERSION#build-}"; FLASH_SHORT="${_v%-*}"  # strip build- prefix and -date suffix
        else
            FLASH_SHORT="$FLASH_VERSION"
        fi
        FLASH_FULL="$(git -C "$PROJECT_DIR" rev-parse "$FLASH_SHORT" 2>/dev/null || true)"
    else
        FLASH_SHORT="$(git -C "$PROJECT_DIR" rev-parse --short HEAD 2>/dev/null || true)"
        FLASH_FULL="$(git -C "$PROJECT_DIR" rev-parse HEAD 2>/dev/null || true)"
        FLASH_BRANCH="$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
        FLASH_VERSION="$FLASH_SHORT"
        FLASH_SRC="head"
    fi
    if [[ -n "$FLASH_SHORT" ]]; then
        echo
        echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        if [[ "$FLASH_SRC" == "iso" ]]; then
            echo -e "${BOLD}  Flashed software: ${FLASH_SHORT}${NC}  (from ISO, ${SUCCEEDED} drive(s))"
            echo -e "  build: ${FLASH_VERSION}"
            [[ -n "$FLASH_FULL" ]] && echo -e "  full: ${FLASH_FULL}"
        else
            echo -e "${BOLD}  Flashed software: ${FLASH_SHORT}${NC}  (${FLASH_BRANCH}, ${SUCCEEDED} drive(s))"
            echo -e "  full: ${FLASH_FULL}"
            echo -e "  ${YELLOW}note: this ISO has no .version sidecar, so this is the checked-out commit, which may be ahead of what was built.${NC}"
            git -C "$PROJECT_DIR" diff --quiet HEAD 2>/dev/null || \
                echo -e "  ${YELLOW}note: working tree is dirty too.${NC}"
        fi
        echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

        # Record this batch to the orders app (private flashes table) so the hash
        # shows in the software dropdown when stamping shipments. Best effort:
        # never fails or delays the flash. The endpoint URL and password come from
        # build-scripts/.env (FLASH_LOG_URL, ADMIN_PASSWORD_PROD), which may be a
        # plain file or a symlink to a central machine secrets file. Nothing
        # sensitive is hard-coded in this public repo.
        [[ -f "$SCRIPT_DIR/.env" ]] && source "$SCRIPT_DIR/.env"
        if [[ -n "${FLASH_LOG_URL:-}" && -n "${ADMIN_PASSWORD_PROD:-}" ]]; then
            FLASH_PAYLOAD="{\"git_hash\":\"$FLASH_SHORT\",\"git_full\":\"$FLASH_FULL\",\"branch\":\"$FLASH_BRANCH\",\"iso_name\":\"$(basename "$ISO_PATH")\",\"iso_sha256\":\"${SHA_BY_ISO[$ISO_PATH]}\",\"drive_count\":$SUCCEEDED,\"flashed_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
            # Cloudflare Access service-token headers, if the endpoint is behind
            # Access (both set in build-scripts/.env). Omitted headers just mean
            # the request relies on the app's Basic Auth alone.
            CF_HEADERS=()
            [[ -n "${CF_ACCESS_CLIENT_ID:-}" ]] && CF_HEADERS+=(-H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID")
            [[ -n "${CF_ACCESS_CLIENT_SECRET:-}" ]] && CF_HEADERS+=(-H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET")
            if curl -fsS --max-time 15 -u ":$ADMIN_PASSWORD_PROD" "${CF_HEADERS[@]}" \
                    -H 'Content-Type: application/json' \
                    -X POST "$FLASH_LOG_URL" -d "$FLASH_PAYLOAD" >/dev/null 2>&1; then
                echo -e "${GREEN}Recorded to the orders app; it shows in the software dropdown now.${NC}"
            else
                echo -e "${YELLOW}Could not reach the orders app to record this flash. The hash above is still yours to use.${NC}"
            fi
        else
            echo -e "${YELLOW}FLASH_LOG_URL/ADMIN_PASSWORD_PROD not set in build-scripts/.env, so this flash was not recorded to the orders app. Hash above is still yours to use.${NC}"
        fi
    fi
fi

# Which physical stick got which scenario: the drives skipped the power-off
# eject, so each unplug still drops the device from /sys/block. Watch for that
# and announce the scenario as the user pulls drives one at a time.

drive_present() { [[ -e "/sys/block/$(basename "${DEVS[$1]}")" ]]; }

announce_pulled() {
    local i="$1" scen="${SCENS[$1]}"
    if [[ "${ST_OK[$i]}" != true ]]; then
        echo -e "${RED}✗${NC} That was ${BOLD}${scen}${NC}, but its flash FAILED. Set it aside, don't test it."
    else
        echo -e "${GREEN}✓${NC} That was ${BOLD}${scen}${NC}: $(corrupt_scenario_expectation "$scen"). Label it '$scen'."
    fi
}

# Block until drive index $1 is back on the bus, matched by serial since a
# replug can come up under a new device name, and update DEVS to that name.
wait_for_replug() {
    local idx="$1" serial dev
    IFS='|' read -r _ _ _ serial <<< "${ENTRIES[$idx]}"
    while true; do
        dev="$(lsblk -d -n -o NAME,SERIAL 2>/dev/null | awk -v s="$serial" '$2 == s {print "/dev/" $1; exit}')"
        if [[ -n "$dev" ]]; then
            DEVS[$idx]="$dev"
            return 0
        fi
        sleep 0.5
    done
}

identify_corrupt_drives() {
    sudo sync
    local i part
    # An automounter may have grabbed partitions once the udev queue restarted;
    # unmount so a pulled stick is never dirty.
    for i in "${!DEVS[@]}"; do
        for part in "${DEVS[$i]}"?*; do
            sudo umount "$part" 2>/dev/null || true
        done
    done

    # Unattended runs can't unplug anything; print the map and move on.
    if [[ ! -t 0 ]]; then
        log_info "No terminal; skipping the interactive unplug identification. Scenario map:"
        for i in "${!DEVS[@]}"; do
            echo "  ${DEVS[$i]} -> ${SCENS[$i]}"
        done
        return 0
    fi

    # A drive already gone from the bus (e.g. it dropped off mid-flash) must
    # not be announced as an unplug, or every label after it would be shifted
    # onto the wrong stick.
    local remaining=()
    for i in "${!DEVS[@]}"; do
        if drive_present "$i"; then
            remaining+=("$i")
        else
            echo -e "${YELLOW}!${NC} ${DEVS[$i]} (${BOLD}${SCENS[$i]}${NC}) already dropped off the bus; nothing has been unplugged yet. Its stick is whichever one is left after you identify the others."
        fi
    done

    echo
    echo -e "${BOLD}${YELLOW}Now unplug the drives ONE at a time to identify them.${NC}"
    echo "As each drive disappears, label the stick you just pulled with its scenario."
    echo
    local gone still
    while (( ${#remaining[@]} )); do
        sleep 0.5
        gone=()
        still=()
        for i in "${remaining[@]}"; do
            if drive_present "$i"; then still+=("$i"); else gone+=("$i"); fi
        done
        if (( ${#gone[@]} > 1 )); then
            echo -e "${YELLOW}!${NC} ${#gone[@]} drives disappeared at once, so I can't tell which stick is which. Plug them ALL back in and pull one at a time."
            for i in "${gone[@]}"; do
                wait_for_replug "$i"
            done
            echo -e "${GREEN}All back.${NC} Pull ONE at a time."
            still+=("${gone[@]}")
        elif (( ${#gone[@]} == 1 )); then
            announce_pulled "${gone[0]}"
        fi
        remaining=("${still[@]}")
    done
    echo
    log_info "All drives identified and unplugged."
}

if [[ "$CORRUPT_MODE" == true && ${#DEVS[@]} -gt 0 ]]; then
    identify_corrupt_drives
fi

# Per-drive rundown, so an unattended batch can be judged at a glance instead
# of by reading eleven logs.
if [[ "$CORRUPT_MODE" != true ]]; then
    echo
    echo -e "${BOLD}Batch summary${NC}"
    printf "  %-10s %-18s %-16s %-9s %-8s %s\n" "DEVICE" "SERIAL" "SLOT" "ATTEMPTS" "RATE" "RESULT"
    echo "  --------------------------------------------------------------------------------------------"
    for i in "${!ENTRIES[@]}"; do
        # || true: with pipefail a non-matching grep would abort the summary,
        # which is exactly what happens for a drive that failed before dd ran.
        rate=""
        [[ -f "${ST_LOG[$i]}" ]] && rate="$(tr '\r' '\n' < "${ST_LOG[$i]}" | grep -a "copied" | tail -1 | sed 's/.*copied, [0-9.]* s, //' || true)"
        if [[ "${ST_OK[$i]}" == true ]]; then
            result="${GREEN}verified${NC}"
            (( ST_TRIES[i] > 1 )) && result="${GREEN}verified${NC} ${YELLOW}(after retry)${NC}"
        else
            result="${RED}FAILED${NC}"
        fi
        printf "  %-10s %-18s %-16s %-9s %-8s %b\n" \
            "${ST_DEV[$i]}" "${ST_SER[$i]}" "$(slot_name "$i")" "${ST_TRIES[$i]}" "${rate:-n/a}" "$result"
    done
    echo
fi

if [[ ${#FAILED[@]} -eq 0 ]]; then
    if [[ "$CORRUPT_MODE" != true ]]; then
        RETRIED=0
        for i in "${!ENTRIES[@]}"; do (( ST_TRIES[i] > 1 )) && RETRIED=$((RETRIED + 1)); done
        echo -e "${BOLD}${GREEN}Good to go: ${#DEVS[@]}/${#DEVS[@]} flashed, verified$([[ "$REVERIFY" == true && "$SKIP_SETTLE" != true ]] && echo ", and re-verified after settling"). Unplug them now.${NC}"
        echo -e "${GREEN}Ship-ready slots: $(safe_slot_list)${NC}"
        (( RETRIED )) && echo -e "${YELLOW}$RETRIED drive(s) needed a retry. Watch those serials: a drive that keeps needing one is on its way out.${NC}"
    fi
    exit 0
fi

echo -e "${BOLD}${RED}${#FAILED[@]} of ${#DEVS[@]} drive(s) need attention:${NC}"
for i in "${!ENTRIES[@]}"; do
    [[ "${ST_OK[$i]}" == true ]] && continue
    # Socket from the launch-time capture, not drive_location: a dead drive
    # has no sysfs node left to locate it by.
    echo -e "  ${RED}✗${NC} ${ST_DEV[$i]} (${ST_SER[$i]}) after ${ST_TRIES[$i]} attempt(s): ${BOLD}$(slot_name "$i")${NC}"
    echo -e "      log: ${ST_LOG[$i]:-none}"
    echo -e "      test it: just check-drive ${ST_DEV[$i]}   (add --deny if it fails)"
done
SAFE_LIST="$(safe_slot_list)"
echo -e "${BOLD}The other $(( ${#DEVS[@]} - ${#FAILED[@]} )) drive(s) are verified and fine to ship${SAFE_LIST:+: ${SAFE_LIST}}.${NC}"

# Blink each failed drive's hub socket so it can be found by eye. Failed
# sticks only: a blink is a power cycle, which is fine on a drive whose
# contents are already worthless. 'just blink' does this standalone.
if [[ -t 0 ]]; then
    for i in "${!ENTRIES[@]}"; do
        [[ "${ST_OK[$i]}" == true ]] && continue
        [[ -n "${ST_PORT[$i]}" ]] || continue
        echo
        read -r -p "Blink the socket holding ${ST_SER[$i]}? [Y/n] " ans
        [[ "$ans" == [nN]* ]] && continue
        blink_port_until_enter "${ST_PORT[$i]}" "Blinking $(slot_name "$i")... press Enter once you've spotted it: "
        newdev="$(dev_for_serial "${ST_SER[$i]}" 20 || true)"
        [[ -n "$newdev" && "$newdev" != "${ST_DEV[$i]}" ]] && log_info "It came back as $newdev; use that for check-drive."
    done
fi
exit 1
