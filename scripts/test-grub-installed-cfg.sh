#!/usr/bin/env bash
# Run the installed system's grub.cfg (the heredoc in 00-build-golden-image.sh)
# under real GRUB in QEMU against a disk image with Purple's layout (p1 ESP,
# p2 root) and check that it resolves root from the device GRUB was loaded
# from, with `search` only as the fallback. No ISO build needed.
#
# Each case boots a grub-mkrescue CD whose config sets $root the way the real
# loader would (ESP under UEFI, root under BIOS, or left on the CD itself so
# the layout assumption fails) before sourcing the installed config. The dummy
# kernel makes `linux` fail with "invalid magic number", which proves the file
# was found on the resolved root.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for cmd in grub-mkrescue qemu-system-x86_64 parted mformat mcopy mke2fs; do
    command -v "$cmd" >/dev/null || { echo "ERROR: $cmd not installed" >&2; exit 1; }
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
BUILD="$REPO/build-scripts/00-build-golden-image.sh"

heredoc() {  # print the body of the heredoc that writes $1
    sed -n "\|cat > \"\$MOUNT_DIR/$1\" <<'EOF'|,\|^EOF\$|p" "$BUILD" | sed '1d;$d'
}

# Root partition contents: dummy kernel plus the config files grub.cfg sources.
ROOTDIR="$WORK/root"
mkdir -p "$ROOTDIR/boot/grub"
head -c 65536 /dev/urandom > "$ROOTDIR/boot/vmlinuz"  # zeros would be a hole, not an extent
heredoc boot/grub/purple-cmdline.cfg > "$ROOTDIR/boot/grub/purple-cmdline.cfg"
cp "$REPO/config/grub/purple-router.cfg" "$REPO/config/grub/purple-variants.cfg" "$ROOTDIR/boot/grub/"

# GPT disk: p1 FAT ESP at 1MiB (16MiB), p2 ext4 root at 17MiB.
DISK="$WORK/disk.img"
truncate -s 64M "$DISK"
parted -s "$DISK" mklabel gpt mkpart ESP fat32 1MiB 17MiB set 1 esp on mkpart primary ext4 17MiB 100%
mformat -i "$WORK/esp.img" -C -T 32768 ::
dd if="$WORK/esp.img" of="$DISK" bs=1M seek=1 conv=notrunc status=none
mke2fs -q -F -t ext4 -d "$ROOTDIR" -E offset=$((17 * 1024 * 1024)) "$DISK" 46M

INSTALLED_CFG="$WORK/installed.cfg"
heredoc boot/grub/grub.cfg > "$INSTALLED_CFG"

FAILED=0
run() {  # case-name  root-to-simulate  expected-root
    local name="$1" root="$2" expect="$3" iso="$WORK/$1.iso" out
    mkdir -p "$WORK/$name/boot/grub"
    cp "$INSTALLED_CFG" "$WORK/$name/boot/grub/installed.cfg"
    {
        echo 'serial; terminal_output serial'
        [ -n "$root" ] && echo "set root=$root"
        echo 'source $prefix/installed.cfg'
        echo 'echo "RESOLVED root=[$root] variant=[$purple_variant] args=[$purple_root_arg $purple_cmdline]"'
    } > "$WORK/$name/boot/grub/grub.cfg"
    grub-mkrescue -o "$iso" "$WORK/$name" >/dev/null 2>&1
    out=$(timeout 60 qemu-system-x86_64 -m 256 -hda "$DISK" -cdrom "$iso" -boot d -display none \
        -serial stdio 2>/dev/null | tr -d '\r' || true)
    local resolved found_kernel
    resolved=$(grep -o 'RESOLVED root=\[[^]]*\]' <<<"$out" | head -1)
    found_kernel=$(grep -c 'invalid magic number' <<<"$out" || true)
    if [ "$resolved" = "RESOLVED root=[$expect]" ] && grep -q 'Starting Purple Computer' <<<"$out" \
        && [ "$found_kernel" -ge 1 ] && grep -q 'args=\[root=LABEL=PURPLE_ROOT ro loglevel=3' <<<"$out"; then
        echo "ok    $name: root=${root:-<cd>} -> $expect, menuentry ran, kernel file found"
    else
        echo "FAIL  $name: root=${root:-<cd>} -> ${resolved:-no RESOLVED line} (expected [$expect])"
        printf '%s\n' "$out" | tail -15 | sed 's/^/      /'
        FAILED=1
    fi
}

run uefi-esp   hd0,gpt1 hd0,gpt2   # UEFI: GRUB loaded from the ESP
run bios-root  hd0,gpt2 hd0,gpt2   # BIOS: core.img already landed on root
run fallback   ""       hd0,gpt2   # loaded from the CD: no gpt2 there, search finds it
exit "$FAILED"
