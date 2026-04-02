# Debug Shell Escape

When the app freezes or shows a blank screen on the debug ISO, use SysRq to escape to a shell.

## Steps

1. **Alt + PrtSc + R** (releases the keyboard from the app's evdev grab)
2. **Ctrl + Alt + F2** (switches to tty2, which has an auto-login shell)
3. Debug as needed
4. **Ctrl + Alt + F1** to return to the app

## Verify SysRq is enabled

```bash
cat /proc/sys/kernel/sysrq
```

Should print `1`. If it prints `0`, enable it manually:

```bash
sudo sh -c 'echo 1 > /proc/sys/kernel/sysrq'
```

## Surface Laptops

Make sure Fn Lock is **on** (light on) so the F-keys send F1, F2, etc. directly. PrtSc may be on F7 or F8 depending on the model: check the key markings.

## How it works

SysRq is handled by the kernel before any userspace process, so it works even when the app is completely frozen.

SysRq is enabled in two places (both debug-only):
- **Live boot:** sysctl drop-in `99-purple-zzz-debug.conf`, written when `purple.debug=1` is on the kernel command line
- **Installed system:** `purple-splash` service runs `sysctl -w kernel.sysrq=1` when `/opt/purple/debug` exists

Prod builds have SysRq disabled (`kernel.sysrq = 0`) so kids can't accidentally trigger it.
