#!/bin/bash
# Purple Computer: on the 2016-2017 Macs whose speakers the stock drivers never
# switch on, load the patched build instead; everywhere else, and on any
# failure, load the stock module. guides/mac-audio.md
#   purple-mac-audio load MODULE   modprobe install rule (config/modprobe/purple-mac-audio.conf)
#   purple-mac-audio softvol CARD  udev import (config/udev/91-purple-mac-audio.rules)
VARIANTS=${PURPLE_VARIANTS:-/boot/grub/purple-variants.cfg}
MODULES=${PURPLE_MAC_MODULES:-/opt/purple/modules/$(uname -r)}
PRODUCT=${PURPLE_PRODUCT_FILE:-/sys/class/dmi/id/product_name}
SYSMOD=${PURPLE_SYS_MODULE:-/sys/module}
ASOUND=${PURPLE_ASOUND:-/proc/asound}

eval "$(sed -n 's/^set \(purple_[a-z0-9_]*_models=\)/\1/p' "$VARIANTS" 2>/dev/null)"

models_for() {
    case $1 in
        snd_hda_codec_cirrus) echo "${purple_cs4208mac_models:-}" ;;
        snd_hda_codec_cs8409) echo "${purple_cs8409mac_models:-}" ;;
    esac
}

wanted() {
    local re
    re=$(models_for "$1")
    [ -n "$re" ] && [ -f "$MODULES/$1.ko" ] && [[ $(cat "$PRODUCT" 2>/dev/null) =~ $re ]]
}

load_patched() {
    local dep
    for dep in $(modinfo -F depends "$MODULES/$1.ko" | tr , ' '); do
        modprobe "$dep" || return 1
    done
    insmod "$MODULES/$1.ko"
}

kmsg() { echo "purple-mac-audio: $*" > /dev/kmsg 2>/dev/null; }

case ${1:-} in
    load)
        if wanted "$2"; then
            load_patched "$2" && { kmsg "loaded patched $2"; exit 0; }
            kmsg "patched $2 failed to load, using stock"
        fi
        exec modprobe --ignore-install "$2" ;;
    softvol)
        # The 12" driver's only volume control is the headphone amp; Pulse must scale the speakers itself.
        grep -qs O "$SYSMOD/snd_hda_codec_cirrus/taint" && grep -qs CS4208 "$ASOUND/card$2"/codec#* \
            && echo PURPLE_SOFTVOL=1 ;;
esac
exit 0
