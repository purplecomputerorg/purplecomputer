# Debug Shell Escape

When the app freezes or shows a blank screen on the debug ISO, use SysRq to escape to a shell.

## Steps

1. **Alt + PrtSc + R** (releases the keyboard from the app's evdev grab)
2. **Ctrl + Alt + F2** (switches to tty2, which has an auto-login shell)
3. Debug as needed
4. **Ctrl + Alt + F1** to return to the app

## Surface Laptops

Make sure Fn Lock is **on** (light on) so the F-keys send F1, F2, etc. directly. PrtSc may be on F7 or F8 depending on the model: check the key markings.

## Notes

- SysRq is only enabled on the debug ISO. Prod builds have it disabled so kids can't accidentally trigger it.
- This works even when the app is completely frozen, because SysRq is handled by the kernel before any userspace process.
- The sysctl setting is in `/etc/sysctl.d/99-purple-zzz-debug.conf` (written at boot when `purple.debug=1` is on the kernel command line).
