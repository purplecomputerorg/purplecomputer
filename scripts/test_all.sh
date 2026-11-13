#!/usr/bin/env bash
# Every check that costs no money, in one run. Keeps going past failures, prints a table,
# exits 1 if anything failed. A step whose tools are missing is listed as SKIP with the reason.
#
# Usage: just test-all [--no-sudo]    --no-sudo skips the partitioning test (for unattended runs)
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC2034  # read by flash-lib.sh
PROJECT_DIR="$ROOT"
source "$ROOT/build-scripts/config.sh"
source "$ROOT/build-scripts/flash-lib.sh"

SUDO=1
for arg in "$@"; do
    case "$arg" in
        --no-sudo) SUDO=0 ;;
        *) echo "test-all: unknown option $arg" >&2; exit 2 ;;
    esac
done

LOGS="${TMPDIR:-/tmp}/purple-test-all/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$LOGS"
RESULTS=() FAILED=0

record() { RESULTS+=("$(printf '%-5s %-16s %s' "$1" "$2" "$3")"); }
skip() { record SKIP "$1" "$2"; echo "$1 ... skipped ($2)"; }

# Each word is a command to require; a|b means either will do. Prints the first one missing.
missing() {
    local spec c
    for spec in "$@"; do
        for c in ${spec//|/ }; do command -v "$c" >/dev/null && continue 2; done
        echo "${spec//|/ or }"
        return
    done
}

# Skips inside a passing step are easy to miss, so the table shows their count.
skip_count() { grep -oE '[0-9]+ skipped' "$1" | tail -1 | sed 's/^/, /'; }

# run NAME "needed commands" COMMAND...
run() {
    local name=$1 needs=$2 miss log start
    shift 2
    miss=$(missing $needs)
    [[ -z $miss ]] || { skip "$name" "no $miss"; return; }
    log="$LOGS/$name.log" start=$SECONDS
    printf '%s ... ' "$name"
    if (cd "$ROOT" && "$@") >"$log" 2>&1; then
        echo ok
        record PASS "$name" "$((SECONDS - start))s$(skip_count "$log")"
    else
        echo FAILED
        tail -n 25 "$log" | sed -E 's/\x1b\[[0-9;?]*[a-zA-Z]//g; s/^/    /'
        record FAIL "$name" "$((SECONDS - start))s, $log"
        FAILED=1
    fi
}

head_iso() {
    use_build_of_ref HEAD && list_build_isos | filter_variant standard | head -1
}

# Sudo first, while the password prompt is fresh.
if [[ $SUDO == 1 ]] && sudo -v; then
    run partitioning "" just test-partitioning
else
    skip partitioning "no sudo"
fi
run pytest "" just test
run studio-test "node npm" just studio-test
run reboot-binary "gcc" just test-reboot
run grub-router "grub-mkrescue qemu-system-x86_64" scripts/test-grub-router.sh
run grub-installed "grub-mkrescue qemu-system-x86_64 parted mformat mcopy mke2fs" scripts/test-grub-installed-cfg.sh
run e2e-studio "node npm chromium|chromium-browser|google-chrome" just e2e-studio
run studio-layout "node npm firefox-esr|firefox" just studio-layout
if git -C "$ROOT" rev-parse --verify -q release/2.x >/dev/null; then
    run room-compat "" just room-compat
else
    skip room-compat "no release/2.x branch"
fi
if [[ ! -w /dev/kvm ]]; then
    skip e2e-vm "no /dev/kvm"
elif [[ -z "$(head_iso)" ]]; then
    skip e2e-vm "no build of HEAD (just build)"
else
    run e2e-vm "qemu-system-x86_64 socat" just e2e-vm --ref HEAD
fi

echo
printf '%s\n' "${RESULTS[@]}"
echo "logs: $LOGS"
exit $FAILED
