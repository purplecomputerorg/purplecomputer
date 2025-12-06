# Purple Computer FAI Installation System

Complete FAI-based automated installer for offline Ubuntu/Debian installation.

## Overview

This FAI configuration provides:
- Fully automated, offline installation from CD/USB
- Minimal base system + minimal X11 + terminal environment
- Custom LVM disk layout optimized for 2010-2015 laptops
- Post-install user creation, dotfiles, and auto-login setup
- Embedded local apt repository for 100% offline operation

## Directory Structure

```
/srv/fai/
├── config/              # FAI configuration (this directory)
│   ├── class/          # Class definition scripts
│   ├── disk_config/    # Partition/LVM layouts
│   ├── package_config/ # Package lists per class
│   ├── scripts/        # Post-install scripts
│   ├── hooks/          # FAI hooks for various stages
│   ├── files/          # Configuration files to copy
│   └── basefiles/      # Base system files
├── nfsroot/            # FAI installation environment
└── mirror/             # Local apt repository

/opt/purple-installer/   # Build scripts and utilities
└── local-repo/         # Local repository staging area
```

## Quick Start

1. Build the FAI configuration and local repository
2. Create bootable ISO with embedded repository
3. Boot from ISO/USB and installation runs automatically
4. System reboots into configured minimal X environment

See `BUILDING.md` for detailed build instructions.
See `STRUCTURE.md` for complete file layout reference.
