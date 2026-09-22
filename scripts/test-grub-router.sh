#!/usr/bin/env bash
# Boot config/grub/purple-router.cfg in QEMU against faked CPUs and SMBIOS
# models and check which kernel variant it picks. No ISO build needed.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for cmd in grub-mkrescue qemu-system-x86_64; do
    command -v "$cmd" >/dev/null || { echo "ERROR: $cmd not installed" >&2; exit 1; }
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/boot/grub"
cp "$REPO/config/grub/purple-variants.cfg" "$WORK/boot/grub/"
{
    echo 'serial; terminal_output serial'
    cat "$REPO/config/grub/purple-router.cfg"
    echo 'echo "ROUTER variant=[$purple_variant] args=[$purple_args]"; halt'
} > "$WORK/boot/grub/grub.cfg"
grub-mkrescue -o "$WORK/router.iso" "$WORK" >/dev/null 2>&1

# QEMU wants commas in SMBIOS strings doubled.
FAILED=0
run() {
    local expect="$1" args="$2"; shift 2
    local got
    got=$(timeout 30 qemu-system-x86_64 -m 256 -cdrom "$WORK/router.iso" -display none \
        -serial stdio "$@" 2>/dev/null | tr -d '\r' | grep -o 'variant=\[[^]]*\] args=\[[^]]*\]' | head -1 || true)
    if [ "$got" = "variant=[$expect] args=[$args]" ]; then
        echo "ok    $* -> $got"
    else
        echo "FAIL  $* -> ${got:-no output} (expected [$expect] [$args])"; FAILED=1
    fi
}

eval "$(sed -n 's/^set \(purple_[a-z0-9_]*=\)/\1/p' "$REPO/config/grub/purple-variants.cfg")"
run ""      ""  -smbios type=1,product=MacBookPro14,,1
run ""      ""  -smbios type=1,product=MacBookPro11,,3
run ""      ""  -smbios type=1,product=20AMS3RH00
run ""      ""  -smbios type=1,product=MacBookAir10,,1
run -t2     "$purple_t2_args" -smbios type=1,product=MacBookAir9,,1
run -t2     "$purple_t2_args" -smbios type=1,product=MacBookPro16,,1
run -t2     "$purple_t2_args" -smbios type=1,product=Macmini8,,1
run -t2     "$purple_t2_args" -smbios type=1,product=iMac20,,2
run ""      "$purple_c2mac_args" -smbios type=1,product=MacBookAir3,,2
run ""      "$purple_c2mac_args" -smbios type=1,product=MacBook5,,2
run ""      ""  -smbios type=1,product=MacBook5,,1
run ""      ""  -smbios type=1,product=MacBookAir4,,2
run -i386   "$purple_i386_args" -cpu pentium3
exit "$FAILED"
