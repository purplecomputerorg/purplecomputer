# Complete Guide: Forcing Subiquity to Use ONLY Offline apt Repository

## Problem Summary
Subiquity's apt integration aggressively generates online mirror entries (archive.ubuntu.com) even when you configure an offline repository. This breaks fully offline installations.

## Root Cause
When you define `sources:` in the apt block, Subiquity treats this as a **request to generate apt configuration**, which includes adding default Ubuntu mirrors alongside your custom sources.

## The Solution: Early-Commands Override

### Key Principles
1. **DO NOT** use `sources:` in the apt block
2. Configure `/etc/apt/sources.list` in `early-commands` BEFORE Subiquity initializes apt
3. Use `preserve_sources_list: true` to prevent Subiquity from overwriting your configuration
4. Use `fallback: offline-install` to disable mirror selection UI

### Working Configuration

```yaml
autoinstall:
  version: 1

  # STEP 1: Override apt sources BEFORE Subiquity initializes
  early-commands:
    - echo 3 > /proc/sys/kernel/printk
    - echo "Welcome to Purple Computer - Installation starting..."

    # CRITICAL: Override apt sources BEFORE Subiquity initializes apt
    # This prevents Subiquity from generating online mirror entries
    - rm -f /etc/apt/sources.list
    - rm -rf /etc/apt/sources.list.d/*
    - echo "deb [trusted=yes] file:///cdrom noble main restricted universe multiverse" > /etc/apt/sources.list
    - echo "Forced offline apt configuration - cdrom only"

  # STEP 2: Minimal apt block (NO sources: key!)
  apt:
    geoip: false                    # Disable geolocation-based mirror selection
    fallback: offline-install       # Skip mirror selection UI if apt fails
    preserve_sources_list: true     # Don't overwrite our early-commands config
    # DO NOT add "sources:" here!

  packages:
    - xorg
    - python3
    # ... your packages ...
```

## Why This Works

1. **early-commands runs first**: Before Subiquity initializes apt, we delete all default sources and write our cdrom-only configuration

2. **preserve_sources_list: true**: Tells Subiquity "don't touch /etc/apt/sources.list"

3. **No sources: key**: By omitting `sources:`, we tell Subiquity "don't generate any apt configuration"

4. **fallback: offline-install**: Prevents Subiquity from showing mirror selection UI if network is unavailable

## ISO Repository Structure

Your ISO must have a proper Debian repository structure at the root:

```
/cdrom/
├── dists/
│   └── noble/
│       ├── Release
│       ├── InRelease (optional)
│       └── main/
│           └── binary-amd64/
│               ├── Packages
│               └── Packages.gz
└── pool/
    └── (all .deb files)
```

## Verification During Install

During installation, check that Subiquity used ONLY your cdrom repo:

1. Switch to another TTY (Ctrl+Alt+F2)
2. Check the generated config:
   ```bash
   cat /target/etc/apt/sources.list.d/subiquity-curtin-apt.conf
   ```

You should see ONLY:
```
deb [trusted=yes] file:///cdrom noble main restricted universe multiverse
```

If you see `archive.ubuntu.com` entries, the configuration failed.

## Common Mistakes

### ❌ WRONG: Using sources: in apt block
```yaml
apt:
  preserve_sources_list: true
  sources:
    cdrom:
      source: "deb file:///cdrom noble main"
```
**Problem**: Even with `preserve_sources_list`, the `sources:` key triggers Subiquity to generate online mirrors.

### ❌ WRONG: Configuring sources in late-commands
```yaml
late-commands:
  - echo "deb file:///cdrom noble main" > /target/etc/apt/sources.list
```
**Problem**: Too late! Subiquity already ran `apt update` during package installation with online mirrors.

### ✅ CORRECT: Configure in early-commands
```yaml
early-commands:
  - rm -f /etc/apt/sources.list
  - echo "deb [trusted=yes] file:///cdrom noble main restricted universe multiverse" > /etc/apt/sources.list

apt:
  preserve_sources_list: true
  # NO sources: key!
```

## Advanced: Multiple Components

If your repository has multiple components (main, restricted, universe, multiverse):

```bash
echo "deb [trusted=yes] file:///cdrom noble main restricted universe multiverse" > /etc/apt/sources.list
```

Make sure your `dists/noble/` has subdirectories for each component:
```
dists/noble/
├── main/binary-amd64/
├── restricted/binary-amd64/
├── universe/binary-amd64/
└── multiverse/binary-amd64/
```

## Debugging Tips

### 1. Check if apt is using cdrom only
During installation (switch to TTY2):
```bash
grep -r "archive.ubuntu.com" /etc/apt/
```
Should return nothing.

### 2. Verify repository is readable
```bash
apt-cache policy
```
Should show only `file:///cdrom` sources.

### 3. Test package availability
```bash
apt update
apt-cache search python3
```

### 4. Check Subiquity logs
```bash
journalctl -u subiquity
```

## Expected Result

After following this guide, your installation will:
- ✅ Use ONLY file:///cdrom as the apt source
- ✅ Never contact archive.ubuntu.com during installation
- ✅ Install all packages from your bundled repository
- ✅ Complete successfully offline with full dependency resolution
- ✅ Generate `/target/etc/apt/sources.list.d/subiquity-curtin-apt.conf` containing ONLY your cdrom entry

## Post-Installation

After installation, you may want to restore online repos for updates. Do this in late-commands or first-boot:

```yaml
late-commands:
  - |
    cat > /target/etc/apt/sources.list <<'EOF'
    deb http://archive.ubuntu.com/ubuntu noble main restricted universe multiverse
    deb http://archive.ubuntu.com/ubuntu noble-updates main restricted universe multiverse
    deb http://archive.ubuntu.com/ubuntu noble-security main restricted universe multiverse
    EOF
```

This ensures the installed system can receive updates post-installation while keeping the installation itself fully offline.

## Summary

**The magic formula:**
1. Configure `/etc/apt/sources.list` in `early-commands` with cdrom repo
2. Use minimal apt block with `preserve_sources_list: true` and `fallback: offline-install`
3. **DO NOT** define `sources:` in the apt block
4. Verify during installation that only cdrom sources are present

This approach forces Subiquity to detect a pre-configured, valid apt setup and prevents it from generating any online sources.
