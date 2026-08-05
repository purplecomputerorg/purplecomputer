---
description: Review release-status with an LLM sanity check, confirm anything that looks off, then hand off the build, flash, and ship steps to the user
---

Review a customer release before the user builds and ships it. Version argument (optional, e.g. `v1.0`): $ARGUMENTS

## 1. Gather state

Run these read-only checks first:

- `just release-status`
- `git -C ~/purplecomputer-release status --short --branch` (must be on `release/1.x` and clean)
- `git status --short` in the main checkout (uncommitted work worth mentioning, not a blocker)
- `git -C ~/purplecomputer-release log --oneline -5` to see what the shipped ISO will actually contain

## 2. Review the contents

Go through the release-status output commit by commit and flag anything that warrants a question before shipping. Look for:

- `+` (waits) commits that look like fixes rather than features: bug fixes, hardware safety fixes, boot fixes. Cherry-pick decisions are the user's to confirm, so propose `just release-pick <sha>` for each candidate with a one-line reason, never pick silently.
- `=` (ships) commits that seem wrong to ship: anything that reads like a feature, temp or debug logging awaiting removal, WIP, or one half of a multi-commit change whose other half still waits.
- Pairs or sequences split across the line: if a `=` commit's follow-up fix is still `+`, that is exactly the kind of thing to raise.
- Anything in the last few release/1.x commits that was never validated (check docs/TODO.md and recent commit messages for pending hardware or VM confirmations if unsure).

## 3. Confirm with the user

Summarize your review: what ships, what waits, and each concern with a one-line reason. Then use AskUserQuestion to confirm:

- Ship as-is
- Run proposed release-picks first (then re-run `just release-status`, re-review, and confirm again)
- Abort

If no version was passed as an argument, also ask whether this is a semver release (version stamped at build time) or an auto date-stamped release.

If nothing looks off at all, say so plainly and still ask for the final confirmation.

## 4. Hand off to the user

Do not run the build or release yourself: the Docker build needs daemon socket access the sandbox blocks, and the user runs these from their own terminal. After confirmation, end by printing the pipeline for them to run:

```
Review done, nothing blocking. Run:
  purple-build --release      # build (PURPLE_VERSION=vX.Y purple-build --release for semver)
  just flash-all              # flash customer USBs, validate one on hardware
  just ship                   # upload the downloads and tag
```

Steps they've already done can be skipped: if the release commit is already built, `purple-build --release` no-ops, and `just ship` releases the existing build. If they later report a failure, help debug from the output they paste; do not attempt the build yourself.
