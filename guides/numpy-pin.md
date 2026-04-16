# NumPy < 2 Pin

## Problem

NumPy 2.x requires X86_V2 baseline instructions (SSE4.2, POPCNT). Older machines
like the MacBook Pro A1278 (Core 2 Duo) don't have these. Importing numpy on
these CPUs crashes immediately:

```
RuntimeError: NumPy was built with baseline optimizations:
(X86_V2) but your machine doesn't support:
(X86_V2).
```

NumPy is a transitive dependency: pygame uses it for surfarray, onnxruntime (via
piper-tts) uses it for inference. Neither requires numpy 2.x.

## Decision

Pin `numpy>=1.24,<2` in requirements.txt. NumPy 1.26.x (the last 1.x line)
works on all x86_64 CPUs back to the original amd64 baseline.

## Why the downsides don't matter here

- **Security patches:** Purple Computer is offline. No network attack surface.
- **EOL risk:** The pin only affects ISO build time. If numpy 1.x stops getting
  releases, we can revisit. A deployed device never upgrades packages.
- **Compatibility:** As of 2026-04, onnxruntime requires `numpy>=1.21.6` and
  pygame doesn't declare a numpy dependency at all. No conflicts.
- **Performance:** No meaningful difference for audio mixing and TTS inference.

## When to revisit

If a future version of pygame or onnxruntime requires numpy 2.x, we'd need to
either drop Core 2 Duo support or find numpy 2.x wheels built with X86_V1
baseline (the numpy team has discussed this but hasn't shipped it yet).
