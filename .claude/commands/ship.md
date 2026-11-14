---
description: Review what shipping main would give families with an LLM sanity check, confirm anything that looks off, then hand off the build, flash, and ship steps to the user
---

Review a customer release from main before the user builds and ships it. Optional commit to ship instead of HEAD: $ARGUMENTS

## 1. Gather state

Run these read-only checks first:

- `just ship-status -v` (what the download and the newest build are missing from main, commit by commit)
- `git status --short --branch` in the main checkout (must be on `main` and clean: `just rtbf` refuses otherwise, and only a clean main build gets the `v2.0.N` version `just ship` accepts)
- `git log --oneline origin/main..main` (unpushed commits: the download page links the shipped commit on GitHub, so it has to be pushed via /push)
- `just test` (lint and tests on main; a failure here is a blocker to raise, not a nit)

## 2. Review the contents

Go through the commits the "Download" row is missing and flag anything that warrants a question before shipping. Look for:

- Temp or debug logging awaiting removal, WIP, or one half of a multi-commit change whose other half hasn't landed.
- Boot, install, power or keyboard changes never validated on hardware or in a VM (check recent commit messages and Linear for pending confirmations if unsure).
- A "Studio Purple" row behind Studio: packs or rooms Studio makes that this build can't open. Suggest `just compat-check`.

## 3. Confirm with the user

Summarize your review: what ships, and each concern with a one-line reason. Then use AskUserQuestion to confirm:

- Ship as-is
- Fix first (then re-run the checks, re-review, and confirm again)
- Abort

If nothing looks off at all, say so plainly and still ask for the final confirmation.

## 4. Hand off to the user

Do not run the build or ship yourself: the Docker build needs daemon socket access the sandbox blocks, and the user runs these from their own terminal. After confirmation, end by printing the pipeline for them to run:

```
Review done, nothing blocking. Run:
  just rtbf      # test, build (with-backup), flash the whitelisted drives plugged in; validate one on hardware
  just ship      # publish that build to downloads.purplecomputer.org and tag it
```

Steps they've already done can be skipped: if the commit is already built, the build step no-ops. If commits landed on main after the build that was flashed and validated, `just ship <sha>` ships that earlier build. v1 (`release/1.x`) is frozen and no longer shipped. If they later report a failure, help debug from the output they paste; do not attempt the build yourself.
