# Production Release Checklist

Things to address before shipping Purple Computer to customers.

---

## USB Flashing & Quality Control

### The Problem

Even with SHA256 verification passing, USB drives can fail to boot. In January 2025, a flashed USB verified successfully but failed to boot on a Surface laptop with "no bootable operating system." Re-flashing the same drive worked. Root cause unknown, but possible culprits:

- Flaky flash cells that degrade quickly after write
- UEFI firmware caching/weirdness on first boot attempt
- Partial sync issues not caught by immediate read-back

### Before Shipping Drives

**Drive selection:**
- [ ] Use industrial-grade USB drives (Kingston, SanDisk Industrial) not consumer grade
- [ ] Buy from reputable suppliers, not random Amazon listings (same SKU = different factories)
- [ ] Test a sample from each batch before committing to it

**Flashing process:**
- [ ] Flash using `flash-to-usb.sh` (has SHA256 verification built in)
- [ ] Consider adding delayed re-verification (read back after 30+ seconds)
- [ ] Add EFI bootloader sanity check: mount partition, verify `/EFI/BOOT/BOOTX64.EFI` exists
- [ ] Log every flash: drive serial, timestamp, ISO version, checksum, pass/fail

**Testing:**
- [ ] Boot-test a percentage of drives (every Nth drive, or random sample)
- [ ] Test on multiple hardware types (not just one machine)
- [ ] Any drive that fails verification once should be discarded, not retried

**Physical process:**
- [ ] Label drives only after verification passes
- [ ] Use consistent hardware (same USB hub, same flash station)
- [ ] Track batch numbers for recall purposes

### Slow First Boot After Flashing (drive-side, confirmed 2026-07-08)

Freshly flashed drives take much longer on their first boot than on every boot after. Experiment: a 2011 Mac took 3.5 minutes to first-boot a fresh flash, reproduced twice across reflashes (right-side USB port). After a third flash, the same drive first-booted on a 2014 Mac in 1 minute; then, with no reflash, the 2011 Mac booted it in 15 seconds instead of 3.5 minutes.

Conclusion: the penalty is state on the USB drive (controller-level, likely post-write read recalibration or SLC cache folding), not per-machine UEFI caching. One boot on any machine clears it for all machines.

The sequential dd "settle" read pass in `flash-all.sh` did NOT clear it; an actual boot does. Fix: `boot_settle_drive` in `flash-lib.sh` boots each drive once in QEMU (raw `/dev/sdX` with `cache=none`, so guest reads hit the flash rather than the host page cache), detects boot completion from host-side `/sys/block` read counters, then keeps the drive powered briefly for background relocation. Used by both `flash-all.sh` (parallel) and standalone `flash-to-usb.sh`; skip with `--no-settle`, tune with `BOOT_SETTLE_*` env vars.

### Script Improvements Needed

The current `flash-to-usb.sh` does basic SHA256 verification. For production, add:

1. **EFI partition check** after flashing:
   ```bash
   sudo mount ${TARGET_DEV}1 /mnt
   test -f /mnt/EFI/BOOT/BOOTX64.EFI || fail "EFI bootloader missing"
   sudo umount /mnt
   ```

2. **Delayed second verification**: Wait 30 seconds, drop caches, read back again

3. **CSV logging** for batch tracking:
   ```
   timestamp,drive_serial,iso_file,iso_sha256,usb_sha256,status
   ```

4. **`--production` mode** that enables all strict checks

---

## Hardware Compatibility

- [ ] Test on target hardware (what machines will customers use?)
- [ ] Document supported/tested hardware list
- [ ] Test Secure Boot scenarios (disabled required? or sign the bootloader?)
- [ ] Test both UEFI-only and legacy BIOS if supporting older machines

---

## Software QA

- [ ] Run full test suite
- [ ] Manual testing of all modes
- [ ] Test fresh install experience end-to-end
- [ ] Test on slow/limited hardware (not just dev machines)

---

## Packaging & Documentation

- [ ] User-facing quick start guide (remember: non-technical parents)
- [ ] Troubleshooting guide for common issues
- [ ] Support contact info on physical materials
- [ ] Return/replacement policy documented

---

## Support Infrastructure

- [ ] How will customers report issues?
- [ ] How will we diagnose problems remotely?
- [ ] Logging/telemetry for debugging (opt-in, privacy-respecting)
