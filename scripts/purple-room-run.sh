#!/bin/sh
# A family room's process, sealed (guides/family-rooms.md). Purple runs exactly this, through
# sudo, and talks to the room over stdin and stdout. The room gets no network, no devices, no
# homes or USB drives, a read-only system, a tiny /tmp, and a cap on memory and processes.
# When Purple closes stdin, runner.py ends the room; a property this systemd lacks fails the
# start, which Purple shows as "this room needs fixing". /run is an empty tmpfs, not
# InaccessiblePaths: masking it fails the mount namespace (status 226) on the live ISO.
exec /usr/bin/systemd-run --pipe --quiet --collect \
    -p User=purple-room -p NoNewPrivileges=yes -p CapabilityBoundingSet= \
    -p PrivateNetwork=yes \
    -p PrivateDevices=yes -p ProtectSystem=strict -p ProtectHome=yes \
    -p InaccessiblePaths=-/media -p InaccessiblePaths=-/mnt -p TemporaryFileSystem=/run:ro \
    -p InaccessiblePaths=-/dev/shm -p TemporaryFileSystem=/tmp:size=1M \
    -p ProtectKernelTunables=yes -p ProtectKernelModules=yes -p ProtectControlGroups=yes \
    -p RestrictNamespaces=yes -p RestrictRealtime=yes -p LockPersonality=yes \
    -p SystemCallFilter=@system-service -p SystemCallFilter=~@network-io -p SystemCallErrorNumber=EPERM -p SystemCallArchitectures=native \
    -p MemoryMax=256M -p MemorySwapMax=0 -p TasksMax=16 -p RuntimeMaxSec=12h \
    /usr/bin/python3 -I -S /opt/purple/purple_tui/roomkit/runner.py
