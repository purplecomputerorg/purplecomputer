#!/bin/bash
# Stage 2: Purple in the third boot slot (KERN-C / ROOT-C). ChromeOS's slots A and B and the
# firmware are never written. Run as root from the stick: sudo bash, then
#   bash install-slot.sh              read-only: checks the machine and prints the plan
#   bash install-slot.sh --write      does the next phase (see below)
#   bash install-slot.sh --chromeos   boots stock ChromeOS from now on (slot C priority 0)
# Two phases, because the partition table is only re-read at boot:
#   1. Shrinks the stateful partition entry to make room and reboots. ChromeOS finds its data
#      partition too small, wipes it and sets itself up again (a few minutes). Everything in
#      ChromeOS's user data and /usr/local is lost.
#   2. Run again: copies the running kernel and rootfs into slot C, takes rootfs verification off
#      the copy with Google's make_dev_ssd.sh, adds Purple and an upstart job to the copy, and
#      gives slot C one try at the next boot. A slot that does not reach Purple's UI is not tried
#      again, so the machine falls back to ChromeOS by itself.
# Design: guides/chromebook-dev-mode-plan.md
set -u -o pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
LOGS=("$SRC/install-slot.log" /usr/local/purple/install-slot.log)
MNT=/tmp/purple-rootc
DEST="$MNT/opt/purple"
. "$SRC/common.sh"

MAKE_DEV_SSD=/usr/share/vboot/bin/make_dev_ssd.sh
ALIGN=4096                          # sectors: 2 MiB
ROOTC_EXTRA=$((1024 * 2048))        # sectors: 1 GiB on top of the rootfs copy, for Purple
STATE_MIN=$((4 * 1024 * 2048))      # sectors: never shrink stateful below 4 GiB
JOBS_OFF="ui update-engine"         # Chrome never starts; nothing may update from slot C
MODE="${1:---check}"

die() { log "STOP: $*"; exit 1; }
part() { case "$DISK" in *[0-9]) echo "${DISK}p$1" ;; *) echo "$DISK$1" ;; esac; }
begin() { cgpt show -i "$1" -b "$DISK"; }
size() { cgpt show -i "$1" -s "$DISK"; }
label() { cgpt show -i "$1" -l "$DISK"; }
align_down() { echo $(($1 / ALIGN * ALIGN)); }

DISK="$(rootdev -s -d)"
ROOT_NUM="$(rootdev -s | grep -o '[0-9]*$')"
KERN_NUM=$((ROOT_NUM - 1))

check_machine() {
    log "=== checks $(date) ==="
    show cgpt show "$DISK"
    show sh -c 'grep -H -A2 "^start on" /etc/init/ui.conf /etc/init/cras.conf /etc/init/powerd.conf \
        /etc/init/system-services.conf /etc/init/boot-complete.conf /etc/init/update-engine.conf \
        /etc/init/frecon.conf /etc/init/boot-splash.conf'
    show crossystem mainfw_type dev_boot_signed_only
    [ "$(crossystem mainfw_type)" = developer ] || die "not in Developer Mode"
    [ "$(crossystem dev_boot_signed_only)" = 0 ] || die "firmware only boots Google-signed kernels"
    case "$ROOT_NUM" in 3 | 5) ;; *) die "running from partition $ROOT_NUM, expected ChromeOS slot A or B" ;; esac
    for tool in cgpt dd e2fsck resize2fs "$MAKE_DEV_SSD"; do
        command -v "$tool" >/dev/null || die "missing $tool"
    done
    [ "$(label 1)" = STATE ] && [ "$(label 6)" = KERN-C ] && [ "$(label 7)" = ROOT-C ] \
        || die "unexpected partition labels"
    for job in $JOBS_OFF; do
        [ "$(grep -c '^start on' "/etc/init/$job.conf")" = 1 ] || die "$job.conf: no single start on line"
        grep -A1 '^start on' "/etc/init/$job.conf" | tail -1 | grep -qE '^\s+(and|or|\()' \
            && die "$job.conf: start on spans lines"
    done
    for file in purple-app.tar.gz python-x86_64.tar.gz NotoColorEmoji.ttf purple-run.sh libf128shim.so flite; do
        [ -s "$SRC/$file" ] || die "bundle is missing $file"
    done
}

# Slot C goes at the end of the disk, in space taken from the end of stateful.
plan_layout() {
    STATE_BEGIN="$(begin 1)"
    local state_end=$((STATE_BEGIN + $(size 1))) last_other
    last_other="$(cgpt show -q "$DISK" | awk '$3 != 1 && $1 > max { max = $1 } END { print max }')"
    KERN_SIZE="$(size "$KERN_NUM")"
    ROOTC_SIZE=$(($(size "$ROOT_NUM") + ROOTC_EXTRA))
    SLOT_READY=0
    if [ "$(size 7)" -ge "$ROOTC_SIZE" ] && [ "$(size 6)" -ge "$KERN_SIZE" ]; then
        SLOT_READY=1
        log "plan: slot C has room already (KERN-C $(size 6), ROOT-C $(size 7) sectors). Next: phase 2."
        return
    fi
    [ "$last_other" -lt "$STATE_BEGIN" ] || die "stateful is not the last partition on the disk"
    KERNC_BEGIN="$(align_down $((state_end - KERN_SIZE)))"
    ROOTC_BEGIN="$(align_down $((KERNC_BEGIN - ROOTC_SIZE)))"
    STATE_SIZE=$((ROOTC_BEGIN - STATE_BEGIN))
    [ "$STATE_SIZE" -ge "$STATE_MIN" ] || die "stateful would shrink below 4 GiB"
    log "plan: phase 1 (sectors of 512 bytes)"
    log "  STATE   begin $STATE_BEGIN size $(size 1) -> $STATE_SIZE  ($((STATE_SIZE / 2048)) MiB)"
    log "  ROOT-C  begin $ROOTC_BEGIN size $ROOTC_SIZE  ($((ROOTC_SIZE / 2048)) MiB)"
    log "  KERN-C  begin $KERNC_BEGIN size $KERN_SIZE  ($((KERN_SIZE / 2048)) MiB)"
}

countdown() {
    log "$1 Ctrl+C within 10 seconds to stop."
    sleep 10
}

phase1() {
    countdown "PHASE 1: shrinking stateful. ChromeOS will wipe its user data at the next boot."
    step cgpt add -i 1 -s "$STATE_SIZE" "$DISK"
    step cgpt add -i 7 -b "$ROOTC_BEGIN" -s "$ROOTC_SIZE" "$DISK"
    step cgpt add -i 6 -b "$KERNC_BEGIN" -s "$KERN_SIZE" -P 0 -T 0 -S 0 "$DISK"
    show cgpt show "$DISK"
    sync
    log "Phase 1 done. Rebooting. Press Ctrl+D at the white screen, let ChromeOS repair itself,"
    log "then come back to this shell and run: bash install-slot.sh --write"
    sleep 5
    reboot
}

add_purple_job() {
    local init="$MNT/etc/init" job
    { echo 'description "Purple Computer"'
      grep -E '^(start|stop) on' "$init/ui.conf"
      echo "respawn"
      echo "exec /bin/bash /opt/purple/purple-run.sh --job"
    } > "$init/purple.conf"
    for job in $JOBS_OFF; do
        step sed -i 's/^start on /# purple: &/' "$init/$job.conf"
    done
    show cat "$init/purple.conf"
}

phase2() {
    local top
    countdown "PHASE 2: writing slot C ($(part 6), $(part 7))."
    step dd if="$(part "$KERN_NUM")" of="$(part 6)" bs=4M
    step dd if="$(part "$ROOT_NUM")" of="$(part 7)" bs=4M
    step "$MAKE_DEV_SSD" --remove_rootfs_verification --partitions 6 -i "$DISK"
    show e2fsck -fy "$(part 7)"
    step resize2fs "$(part 7)"
    step mkdir -p "$MNT"
    step mount "$(part 7)" "$MNT"
    install_app
    add_purple_job
    show df -h "$MNT"
    step umount "$MNT"
    top="$(for i in 2 4; do cgpt show -i "$i" -P "$DISK"; done | sort -n | tail -1)"
    step cgpt add -i 6 -P $((top < 15 ? top + 1 : 15)) -T 1 -S 0 "$DISK"
    show cgpt show "$DISK"
    sync
    log "Phase 2 done. Reboot (type: reboot), press Ctrl+D at the white screen, and Purple should start."
    log "If it does not, power off and on again: the machine returns to ChromeOS by itself."
    log "To leave Purple: hold Ctrl+\\ for 3 seconds. Back to stock ChromeOS for good: --chromeos"
}

case "$MODE" in
--chromeos)
    step cgpt add -i 6 -P 0 -T 0 -S 0 "$DISK"
    log "Slot C switched off. Reboot to get stock ChromeOS."
    ;;
--check | --write)
    check_machine
    plan_layout
    if [ "$MODE" = --check ]; then
        log "Read-only check passed. Nothing was changed. Send $SRC/install-slot.log back before --write."
    elif [ "$SLOT_READY" = 1 ]; then
        phase2
    else
        phase1
    fi
    ;;
*) die "unknown option $MODE" ;;
esac
