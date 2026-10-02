#!/bin/sh
# Purple Computer: put the static reboot/poweroff binary on its own exec,suid
# tmpfs. Ubuntu's /run is nosuid,noexec, and once a live USB is pulled this
# binary is the only thing left that runs (sh, Python, sudo SIGBUS on the
# dead overlay), so it must be in RAM before the stick can go.
set -e
DIR=/run/purple-reboot-mount
[ -x "$DIR/purple-reboot" ] && exit 0
mkdir -p "$DIR"
mount -t tmpfs -o size=1M,exec,suid tmpfs "$DIR"
cp /opt/purple/bin/purple-reboot "$DIR/purple-reboot"
chmod 4755 "$DIR/purple-reboot"
