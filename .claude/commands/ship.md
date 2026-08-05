---
description: Review release-status with an LLM sanity check, confirm anything that looks off, then run just ship
---

Ship a customer release, with a review pass before anything builds. Version argument (optional, e.g. `v1.0`): $ARGUMENTS

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

If no version was passed as an argument, also ask whether this is a semver release (needs `just ship vX.Y`) or an auto date-stamped build (plain `just ship`).

If nothing looks off at all, say so plainly and still ask for the final ship confirmation.

## 4. Ship

Only after explicit confirmation. `just ship` prompts y/N on stdin, and your in-chat confirmation replaces that prompt, so pipe the answer:

```bash
printf 'y\n' | just ship [version]
```

Run it in the background (the Docker build plus upload takes well over 10 minutes), monitor it, and report the outcome: released version, tag, and download URL on success, or the failing step's output on failure. Do not retry a failed build without showing the user the error first.
