#!/usr/bin/env bash
# Shared helpers for flash-to-usb.sh and flash-all.sh.
# Sourced, not executed.

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

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
# A missing or empty config is fine: flash-to-usb falls back to interactively
# offering small USB drives. Batch tools that need a whitelist check
# ${#WHITELIST[@]} themselves.
load_whitelist() {
    WHITELIST=()
    [[ -f "$CONFIG_FILE" ]] || return 0
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        line=$(echo "$line" | xargs)
        [[ -n "$line" ]] && WHITELIST+=("$line")
    done < "$CONFIG_FILE"
}

# Serials of drives that must never be flashed again, one per line, with an
# optional "# reason" shown when one is skipped. A drive that fails readback
# verification is often dying rather than mis-flashed: without this it stays
# whitelisted by its model rule and eats a full write+verify cycle on every
# subsequent run before failing again.
denylist_path() { echo "$PROJECT_DIR/.flash-denylist.conf"; }

declare -A DENIED_SERIALS
DENYLIST_LOADED=false
load_denylist() {
    [[ "$DENYLIST_LOADED" == true ]] && return 0
    DENYLIST_LOADED=true
    local file line serial reason
    file="$(denylist_path)"
    [[ -f "$file" ]] || return 0
    while IFS= read -r line; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        serial="$(echo "${line%%#*}" | xargs)"
        [[ -z "$serial" ]] && continue
        reason="$(echo "${line#*#}" | xargs)"
        [[ "$reason" == "$serial" ]] && reason=""
        DENIED_SERIALS["$serial"]="${reason:-known bad drive}"
    done < "$file"
}

# True when a serial is denied, with the reason left in DENY_REASON. Callers
# must not wrap this in $(): the cache would then load in a subshell and be
# thrown away, re-reading the file once per drive.
DENY_REASON=""
is_denied() {
    load_denylist
    DENY_REASON="${DENIED_SERIALS[$1]:-}"
    [[ -n "$DENY_REASON" ]]
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
        if is_denied "$SERIAL"; then
            echo "[WARN] Skipping /dev/$NAME (serial $SERIAL): $DENY_REASON" >&2
            continue
        fi
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

# USB drives at or under this size may be offered for flashing without a
# whitelist entry (interactive picker only). "64GB"-marketed sticks report
# roughly 62-64 GB decimal, so 65 GB leaves margin for over-reporting ones
# while excluding every 100GB+ disk that might be someone's real data drive.
MAX_UNLISTED_BYTES=65000000000

# Populate CANDIDATE_DRIVES with "dev|size|model|serial|mounted" entries for
# every plugged-in USB disk at or under MAX_UNLISTED_BYTES.
find_candidate_drives() {
    CANDIDATE_DRIVES=()
    while IFS= read -r line; do
        eval "$line"
        [[ "$TRAN" != "usb" ]] && continue
        [[ "$TYPE" != "disk" ]] && continue
        if is_denied "$SERIAL"; then continue; fi
        [[ -z "$SIZE" || "$SIZE" -eq 0 ]] && continue
        [[ "$SIZE" -gt "$MAX_UNLISTED_BYTES" ]] && continue
        local mounted="" human
        lsblk -n "/dev/$NAME" -o MOUNTPOINT 2>/dev/null | grep -q '[^[:space:]]' && mounted="yes"
        human="$(awk -v b="$SIZE" 'BEGIN{printf "%.1fG", b/1e9}')"
        CANDIDATE_DRIVES+=("/dev/$NAME|$human|$MODEL|$SERIAL|$mounted")
    done < <(lsblk -d -n -b -o NAME,SIZE,TRAN,TYPE,MODEL,SERIAL -P 2>/dev/null)
}

# Verify the ISO matches its build-time .sha256 sidecar, echoing the verified
# hash on success. Returns 1 on mismatch; warns but succeeds when no sidecar
# exists (e.g. a hand-specified ISO). This guards the highest-blast-radius
# mistake: flashing many drives from a truncated or wrong-build ISO, which
# passes every per-drive readback yet is wrong on every stick.
verify_iso_checksum() {
    local iso="$1" sidecar="$1.sha256" expected actual
    # Progress to stderr (stdout is the captured hash): a silent multi-GB
    # sha256sum before the confirm prompt otherwise looks like a hang.
    echo "[INFO] Verifying ISO against build checksum (hashing the full $(du -h "$iso" | cut -f1) ISO, please wait)..." >&2
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

# Each settle guest holds 2GB of RAM (-m 2048) plus QEMU overhead, so an
# unbounded parallel settle OOMs the host. Cap concurrency to what
# MemAvailable can hold, budgeting 2.5GB per guest with 2GB host headroom.
# Override with BOOT_SETTLE_JOBS.
boot_settle_max_jobs() {
    if [[ -n "${BOOT_SETTLE_JOBS:-}" ]]; then
        echo "$BOOT_SETTLE_JOBS"
        return
    fi
    local avail_mb cap
    avail_mb=$(( $(awk '/^MemAvailable:/{print $2}' /proc/meminfo) / 1024 ))
    cap=$(( (avail_mb - 2048) / 2560 ))
    (( cap >= 1 )) || cap=1
    echo "$cap"
}

# Count PIDs still running. Unreaped children sit as zombies until the parent
# waits, so plain kill -0 would never see a slot free up.
count_running() {
    local n=0 pid state
    for pid in "$@"; do
        state=$(ps -o state= -p "$pid" 2>/dev/null | tr -d ' ') || true
        [[ -z "$state" || "$state" == Z* ]] || n=$((n + 1))
    done
    echo "$n"
}

# Boot a freshly flashed drive once in QEMU so its controller pays the
# one-time post-write cost here instead of on a parent's first boot, and so
# casper does its one-time persistence setup (GPT relocation plus mkfs of the
# writable partition) here instead of on the customer's first boot. A
# sequential dd readback does not clear the controller state; a real boot's
# read workload does (see guides/usb-flash-settle.md). cache=none (O_DIRECT)
# so guest reads hit the flash, not the host page cache. Boot completion is detected host-side from /sys/block
# read counters: at least BOOT_SETTLE_MIN_MB read, then BOOT_SETTLE_QUIET_SECS
# with no new reads. The drive then stays powered BOOT_SETTLE_HOLD_SECS so
# the controller can finish background relocation. QEMU's own output goes to
# $log for diagnosis. Returns 1 (without failing the flash) if QEMU exits early
# or the threshold isn't reached within $3 (default BOOT_SETTLE_TIMEOUT_SECS),
# and 2 if settling is impossible at all. Callers wanting a retry use
# boot_settle_with_retry.
boot_settle_drive() {
    local dev="$1" log="$2"
    local timeout="${3:-${BOOT_SETTLE_TIMEOUT_SECS:-600}}"
    local min_mb="${BOOT_SETTLE_MIN_MB:-200}"
    local quiet_target="${BOOT_SETTLE_QUIET_SECS:-30}"
    local hold="${BOOT_SETTLE_HOLD_SECS:-60}"
    local stat
    stat="/sys/block/$(basename "$dev")/stat"

    if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
        echo "[WARN] qemu-system-x86_64 not found; cannot boot-settle $dev" >&2
        return 2
    fi

    local part
    for part in "$dev"?*; do
        sudo umount "$part" 2>/dev/null || true
    done

    local accel=()
    if [[ -e /dev/kvm ]]; then
        accel=(-enable-kvm -cpu host)
    else
        echo "[WARN] /dev/kvm not available; boot settle will be slow" >&2
    fi

    # Guest writes land on the stick deliberately, so casper's persistence
    # setup happens in the factory; recheck_after_settle accounts for the
    # regions it touches (see guides/usb-flash-settle.md).
    sudo qemu-system-x86_64 "${accel[@]}" -m 2048 \
        -drive file="$dev",format=raw,cache=none \
        -boot c -no-reboot -display none \
        >>"$log" 2>&1 &
    local qpid=$!

    local read0 last cur quiet=0 elapsed=0 booted=1 trail=""
    read0=$(awk '{print $3}' "$stat")
    last=$read0
    while (( elapsed < timeout )); do
        sleep 5
        elapsed=$((elapsed + 5))
        [[ -d "/proc/$qpid" ]] || break
        cur=$(awk '{print $3}' "$stat")
        if (( cur != last )); then
            quiet=0
            last=$cur
        else
            quiet=$((quiet + 5))
        fi
        # /sys/block stat counts 512-byte sectors; /2048 converts to MB.
        (( elapsed % 60 == 0 )) && trail+=" ${elapsed}s:$(( (cur - read0) / 2048 ))MB"
        if (( (cur - read0) / 2048 >= min_mb && quiet >= quiet_target )); then
            booted=0
            break
        fi
    done

    local mb=$(( (last - read0) / 2048 ))
    # The read trail separates "slow but progressing" from "stalled early",
    # which is the difference between retrying and suspecting the drive.
    (( booted == 0 )) || echo "[settle] $dev read trail:$trail" >>"$log"
    if (( booted == 0 )); then
        sleep "$hold"
    elif [[ -d "/proc/$qpid" ]]; then
        echo "[WARN] boot settle timed out for $dev after ${elapsed}s with ${mb}MB read (need ${min_mb}MB + ${quiet_target}s quiet)" >&2
    else
        echo "[WARN] QEMU exited early for $dev after ${elapsed}s with ${mb}MB read; see $log" >&2
    fi
    sudo kill "$qpid" 2>/dev/null || true
    wait "$qpid" 2>/dev/null || true
    return "$booted"
}

# An incomplete settle is usually a drive that was still booting when the
# window closed, not a broken one, so retry it with a doubled window before
# asking a human to find the stick. Attempts append to the same $log.
boot_settle_with_retry() {
    local dev="$1" log="$2"
    local attempts="${BOOT_SETTLE_ATTEMPTS:-2}"
    local timeout="${BOOT_SETTLE_TIMEOUT_SECS:-600}"
    local i rc
    for (( i = 1; i <= attempts; i++ )); do
        echo "[settle] $dev attempt $i/$attempts (timeout ${timeout}s)" >>"$log"
        boot_settle_drive "$dev" "$log" "$timeout" && return 0
        rc=$?
        # 2 means settling is impossible here, not that this drive was slow.
        (( rc == 2 )) && return 1
        timeout=$((timeout * 2))
        if (( i < attempts )); then
            echo "[INFO] retrying boot settle for $dev with a ${timeout}s window" >&2
        fi
    done
    return 1
}

# Sysfs directory of the USB device behind a block device, e.g.
# /sys/devices/.../usb4/4-1/4-1.4. Empty when the device isn't USB or is gone.
# Sysfs, not lsblk/udevadm: the flash tools pause udev's exec queue, and an
# ejected drive keeps its sysfs node after its /dev node stops working.
usb_device_dir() {
    local usbdir
    usbdir="$(readlink -f "/sys/block/$(basename "$1")" 2>/dev/null)"
    # .../4-1.4/4-1.4:1.0/host6/... -> .../4-1.4, the first parent that is a
    # USB device rather than an interface or SCSI node.
    while [[ "$usbdir" == /sys/devices/?* && ! -f "$usbdir/idVendor" ]]; do
        usbdir="$(dirname "$usbdir")"
    done
    [[ -f "$usbdir/idVendor" ]] && echo "$usbdir"
}

# Product, serial and USB port path of a drive, so one that still needs
# hands-on attention can be found on the hub without unplugging everything.
# The port is bus-rootport.hubport (e.g. 4-1.4), stable per physical socket.
drive_location() {
    local dev="$1" usbdir
    usbdir="$(usb_device_dir "$dev")"
    if [[ -z "$usbdir" ]]; then
        echo "$dev"
        return
    fi
    echo "$(cat "$usbdir/product" "$usbdir/serial" 2>/dev/null | xargs), USB port $(describe_port "$(basename "$usbdir")")"
}

# USB port name of a drive (e.g. 4-1.4), stable per physical socket.
usb_port_name() {
    local usbdir
    usbdir="$(usb_device_dir "$1")"
    [[ -n "$usbdir" ]] && basename "$usbdir"
}

# Sysfs port-control directory for a hub port NAME, e.g.
# 4-1.4 -> .../4-1:1.0/4-1-port4, or a root-port 2-1 -> .../2-0:1.0/usb2-port1.
# Writing to its "disable" attribute power-cycles just that socket.
port_control_path() {
    local port="$1" parent path
    if [[ "$port" == *.* ]]; then
        parent="${port%.*}"               # 4-1.4 -> 4-1
        path="/sys/bus/usb/devices/$parent:1.0/$parent-port${port##*.}"
    else
        parent="${port%%-*}"              # 2-1 -> 2
        path="/sys/bus/usb/devices/$parent-0:1.0/usb$parent-port${port#*-}"
    fi
    [[ -e "$path/disable" ]] && echo "$path"
}

# Same, resolved from a block device instead of a port name.
usb_port_control() {
    local port
    port="$(usb_port_name "$1")"
    [[ -n "$port" ]] || return 1
    port_control_path "$port"
}

# --- Physical socket labels --------------------------------------------------
# Map of hub socket to a human label ("top row 3"), written by label-ports.sh
# (just label-ports). Lets failure reports point at a stick by where it sits
# instead of a device node, which works even after the drive has dropped off
# the bus. Keyed by the port path below the bus ("1.4" for 4-1.4): the bus
# number changes when the hub's uplink moves to another port on this machine,
# and a USB 2.0 stick enumerates on the hub's 2.0 companion bus, so only the
# path under the hub identifies the physical socket.
port_labels_path() { echo "$PROJECT_DIR/.flash-ports.conf"; }

# 4-1.4 -> 1.4; a bare key passes through.
port_key() { echo "${1#*-}"; }

declare -A PORT_LABELS
PORT_LABELS_LOADED=false
load_port_labels() {
    [[ "$PORT_LABELS_LOADED" == true ]] && return 0
    PORT_LABELS_LOADED=true
    local line port label
    [[ -f "$(port_labels_path)" ]] || return 0
    while IFS='|' read -r port label; do
        port="$(echo "$port" | xargs)"
        [[ -z "$port" || "$port" == \#* ]] && continue
        PORT_LABELS["$(port_key "$port")"]="$(echo "$label" | xargs)"
    done < "$(port_labels_path)"
}

# Label for a port name or key, or empty. Same subshell caveat as is_denied:
# calling this via $() re-reads the file, which is fine for a file this small.
port_label() {
    load_port_labels
    echo "${PORT_LABELS[$(port_key "$1")]:-}"
}

save_port_label() {
    local label="${2//|/ }" key tmp
    load_port_labels
    PORT_LABELS["$(port_key "$1")"]="$label"
    tmp="$(mktemp)"
    for key in "${!PORT_LABELS[@]}"; do echo "${key}|${PORT_LABELS[$key]}"; done | sort -V > "$tmp"
    mv "$tmp" "$(port_labels_path)"
}

# Full port name for a socket key on the fastest bus whose hub exposes that
# socket right now (1.4 -> 4-1.4). Full names pass through; an unresolvable
# key is echoed as is, so callers can always print it and port_control_path
# fails cleanly on it.
resolve_port_name() {
    local key="$1" bus n speed best="$1" best_speed=0
    [[ "$key" == *-* ]] && { echo "$key"; return; }
    for bus in /sys/bus/usb/devices/usb*; do
        n="${bus##*/usb}"
        speed="$(cat "$bus/speed" 2>/dev/null || echo 0)"
        [[ -n "$(port_control_path "$n-$key")" && "$speed" -gt "$best_speed" ]] || continue
        best="$n-$key"; best_speed="$speed"
    done
    echo "$best"
}

# "4-1.4 (top row 3)" when the socket is labeled, else just "4-1.4".
describe_port() {
    local label
    label="$(port_label "$1")"
    echo "$1${label:+ ($label)}"
}

# Repeat a pulse command in the background until the user presses Enter.
# $1 is the prompt, the rest the command to run once per pulse. The user's
# reply is left in REPLY for callers that offer choices.
pulse_until_enter() {
    local prompt="$1" pid
    shift
    ( while true; do "$@"; sleep 0.7; done ) &
    pid=$!
    read -r -p "$prompt"
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
}

port_power_pulse() {
    echo 1 | sudo tee "$1/disable" >/dev/null 2>&1
    sleep 0.7
    echo 0 | sudo tee "$1/disable" >/dev/null 2>&1
}

# Blink a hub socket's LED by toggling port power until the user presses
# Enter, then restore power. $1 is a control path from port_control_path,
# $2 the prompt. Safe only on a stick whose contents no longer matter: each
# blink is a power cycle.
blink_port_until_enter() {
    pulse_until_enter "$2" port_power_pulse "$1"
    echo 0 | sudo tee "$1/disable" >/dev/null 2>&1 || true
}

dev_read_pulse() {
    sudo dd if="$1" of=/dev/null bs=1M count=8 skip=$((RANDOM % 256)) \
        iflag=direct status=none 2>/dev/null || true
}

# Blink a stick's activity LED with bursts of direct reads until the user
# presses Enter. Safe on any stick: no power cycling, so device letters stay
# put and contents are untouched.
blink_dev_reads_until_enter() {
    pulse_until_enter "$2" dev_read_pulse "$1"
}

# --- Cross-process counting semaphore ----------------------------------------
# Bounds how many parallel drive pipelines run an expensive stage at once.
# $1 slot dir, $2 slot count, $3 fd to hold the lock on. Blocks until a slot
# frees. The slot is released by slot_release or automatically when the
# process exits (the fd closes), so a killed job can't leak one.
slot_acquire() {
    local dir="$1" n="$2" fd="$3" k
    mkdir -p "$dir"
    while true; do
        for (( k = 1; k <= n; k++ )); do
            eval "exec $fd>\"$dir/$k\""
            flock -n "$fd" && return 0
        done
        sleep 3
    done
}

slot_release() { eval "exec $1>&-"; }

# Find the block device currently holding a serial, waiting up to $2 seconds
# for it to appear (a power-cycled drive takes a few seconds to re-enumerate,
# and can come back under a different letter).
dev_for_serial() {
    local serial="$1" timeout="${2:-30}" waited=0 name
    while (( waited < timeout )); do
        name="$(lsblk -d -n -o NAME,SERIAL 2>/dev/null | awk -v s="$serial" '$2 == s {print $1; exit}')"
        if [[ -n "$name" && -b "/dev/$name" ]]; then
            echo "/dev/$name"
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    return 1
}

# Power-cycle a hub port and return the device node the drive comes back on,
# which may differ from the one it left. This is what makes an unattended retry
# possible: a drive that failed or was ejected is often gone from the bus
# entirely, and only a port power cycle brings it back without hands on the hub.
#
# Takes a port path from usb_port_control, NOT a device node: an ejected drive
# has no /sys/block entry left to derive the port from, so callers must capture
# the port while the drive is still present.
recover_drive() {
    local port="$1" serial="$2"
    [[ -n "$port" && -e "$port/disable" ]] || return 1
    echo 1 | sudo tee "$port/disable" >/dev/null 2>&1 || return 1
    sleep 3
    echo 0 | sudo tee "$port/disable" >/dev/null 2>&1 || return 1
    dev_for_serial "$serial" 40
}

# SHA256 of $2 bytes of a device starting at byte $3 (default 0), read with
# O_DIRECT after dropping the page cache so the bytes come off the flash
# rather than out of RAM.
device_sha256() {
    sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null || true
    sudo dd if="$1" bs=4M count="$2" skip="${3:-0}" \
        iflag=direct,count_bytes,skip_bytes status=none 2>/dev/null \
        | sha256sum | awk '{print $1}'
}

# The settle boot's casper adds the writable partition, which rewrites the
# primary GPT at the start of the disk. Skip that region when comparing the
# drive against the ISO after settling.
GPT_SKIP_BYTES=1048576

# Confirm a drive still holds the image after boot-settling, catching flash
# that decays right after being written. Compares bytes GPT_SKIP_BYTES..iso_size
# against the same span of the ISO file. MUST run before eject_drive: a
# powered-off drive leaves a media-less node whose reads return garbage, which
# looks exactly like corruption that isn't there.
recheck_after_settle() {
    local dev="$1" iso="$2" bytes expected actual
    bytes=$(( $(stat -c %s "$iso") - GPT_SKIP_BYTES ))
    expected="$(dd if="$iso" bs=4M skip="$GPT_SKIP_BYTES" count="$bytes" \
        iflag=skip_bytes,count_bytes status=none | sha256sum | awk '{print $1}')"
    actual="$(device_sha256 "$dev" "$bytes" "$GPT_SKIP_BYTES")"
    [[ "$actual" == "$expected" ]]
}

# Re-read the partition table, then power off the drive so it re-enumerates
# fresh on next plug-in. Some USB controllers (e.g. Verbatim) won't boot
# unless they re-enumerate; this is what GNOME's "safely eject" and
# balenaEtcher do at the end of a flash.
eject_drive() {
    local dev="$1"
    sudo blockdev --rereadpt "$dev" 2>/dev/null || true
    sudo partprobe "$dev" 2>/dev/null || true
    sudo udevadm settle 2>/dev/null || true
    sudo udisksctl power-off --block-device "$dev" 2>/dev/null \
        || sudo eject "$dev" 2>/dev/null
}

# --- ISO discovery -----------------------------------------------------------
# Each build emits up to three variants sharing one stem:
#   <stem>.iso              standard
#   <stem>.with-backup.iso  standard + second golden image copy (shipped USBs)
#   <stem>.debug.iso        visible GRUB menu, verbose boot
# Variant names are standard|backup|debug everywhere; CLI flags translate at
# the edge. Every helper succeeds with empty output when nothing matches, so
# callers under set -e get their friendly no-ISO errors instead of a die.

# All build ISOs, newest first. The one place corrupt-test ISOs (deliberately
# damaged test artifacts) are excluded from auto-picking.
list_build_isos() {
    ls -t "$OUTPUT_DIR"/purple-*.iso 2>/dev/null | grep -v corrupt-test || true
}

# stdin: ISO paths; keeps only the given variant (default: standard).
filter_variant() {
    case "${1:-}" in
        backup) grep '\.with-backup\.iso$' || true ;;
        debug)  grep '\.debug\.iso$' || true ;;
        *)      grep -vE '\.debug\.iso$|\.with-backup\.iso$' || true ;;
    esac
}

# Path prefix (no variant suffix) of the most recently built ISO,
# e.g. /opt/purple-installer/output/purple-installer-20260719
latest_build_stem() {
    local newest
    newest="$(list_build_isos | head -1)"
    [[ -n "$newest" ]] || return 0
    newest="${newest%.with-backup.iso}"
    newest="${newest%.debug.iso}"
    echo "${newest%.iso}"
}

# find_latest_iso [standard|backup|debug]
# Resolves a variant of the NEWEST build only; prints nothing when that build
# lacks it. Nothing ever silently falls back to an older build; callers decide
# whether to offer older ISOs explicitly. Default: with-backup, else standard.
find_latest_iso() {
    local stem f
    stem="$(latest_build_stem)"
    [[ -n "$stem" ]] || return 0
    if [[ -z "${1:-}" ]]; then
        f="$(variant_path "$stem" backup)"
        [[ -f "$f" ]] || f="$(variant_path "$stem" standard)"
    else
        f="$(variant_path "$stem" "$1")"
    fi
    [[ -f "$f" ]] && echo "$f"
    return 0
}

# Newest ISO of one variant across ALL builds, for offering an explicit,
# user-confirmed fallback when the newest build lacks that variant.
newest_iso_of_variant() {
    list_build_isos | filter_variant "${1:-}" | head -1
}

# --- Corrupt-test scenarios --------------------------------------------------
# Made by make-corrupt-test-iso.sh, flashed by flash-to-usb.sh --corrupt and
# flash-all.sh --corrupt. The scenario lives in the ISO filename.

CORRUPT_SCENARIOS=(primary backup both merge)

corrupt_scenario_expectation() {
    case "$1" in
        primary) echo "expect the install to self-heal from the backup copy" ;;
        backup)  echo "expect the install to succeed normally from the primary" ;;
        both)    echo "expect the damaged-Purple-Key error screen (same range bad in both copies, so even the merge fails)" ;;
        merge)   echo "expect the install to self-heal by merging the good ranges of both copies" ;;
    esac
}

# Newest corrupt-test ISO, optionally restricted to one scenario. Prints
# nothing when none exists.
find_corrupt_iso() {
    local scen="${1:-*}"
    ls -t "$OUTPUT_DIR"/*.corrupt-test-$scen.iso 2>/dev/null | head -1 || true
}

warn_if_stale_corrupt_iso() {
    local stem="${1%%.corrupt-test*}"
    stem="${stem%.with-backup}"
    stem="${stem%.debug}"
    if [[ "$stem" != "$(latest_build_stem)" ]]; then
        echo "[WARN] $(basename "$1") comes from an OLDER build than the newest; re-run 'just corrupt-test-iso' after rebuilding." >&2
    fi
}
