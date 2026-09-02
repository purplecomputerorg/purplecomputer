# Release Guide

How to build, release, and update Purple Computer downloads.

## Hosting layout

- `downloads.purplecomputer.org`: the customer download page. Lives in the landing repo (`~/landing/src/pages/downloads.tsx`), served by Vercel, deploys with the landing site. Its root is rewritten to `/downloads` by the landing middleware.
- The files host: the R2 custom domain (`R2_CUSTOM_DOMAIN`, value in the private env file). Serves the actual objects straight from Cloudflare: ISOs, checksums, `latest.json`, and the card PDFs. Everything in this guide uploads here.

The download page reads `latest.json` from the files host at build time (revalidated every 5 minutes), so the version badge updates on its own after a release.

---

## Release Branch (1.x)

Until the next major release, `main` and the shipping branch are separate:

- `main` is where all work lands, via the normal lanes flow.
- `release/1.x`, checked out at `~/purplecomputer-release`, is the branch releases build from. Its only commits are fixes cherry-picked from main. It is never committed to directly and never merges with main in either direction.

Day to day:

```bash
just release-status          # what ships vs what waits (= on release/1.x, + main only)
just release-pick <sha>...   # cherry-pick onto release/1.x, run its tests, show status
purple-build --release       # build the release worktree (includes the with-backup ISO)
just flash-all               # flash customer USBs from that build (prefers with-backup)
just ship                    # confirm, upload, tag
just release-check <sha>     # confirm the public download is that commit
```

A commit that is both fix and feature belongs with the feature. The `-x` flag stamps each pick with its main SHA, which is what `release-status` uses to mark `=`.

When a pick needs hand-edits to fit the release branch (usually because it touches a feature that stays on main), log what changed in [release-pick-adaptations.md](release-pick-adaptations.md).

Build, then flash, then ship: flashing first means a stick can be validated on real hardware before the downloads update. `purple-build --release` is a local wrapper (machine config, not this repo) around `build-in-docker.sh` pointed at the release worktree; it sets `PURPLE_WITH_BACKUP_ISO=1` so shipping builds always carry the backup image copy.

`just ship` prints the commit, the ISO it picked, and the commit count since the last release tag, then asks for confirmation before uploading anything. It refuses if the worktree is not on `release/1.x`, and the release script records the shipped commit in `latest.json`, tags it with the release version, and pushes `release/1.x` and the tag to GitHub on success (the download page links the shipped commit, and GitHub only knows commits that have been pushed). `just release-check <sha>` reads the live download back and fails unless it is that commit, so after telling someone which build they are getting you can prove the download matches. Releases before the commit was recorded fall back to the tag; `v2026.07.27-1107` and earlier have neither, so they report as unknown. It does not build: for a semver release, stamp the version at build time (`PURPLE_VERSION=v1.x purple-build --release`) and `just ship` adopts it; otherwise the version is the build's UTC timestamp, so the download page dates a release by when it was built, not when it was uploaded.

The release script only uploads an ISO built from the checkout it runs in: every build bakes its source commit into the image (`/etc/purple-commit`, surfaced as a `.commit` sidecar next to the ISO), and `release-iso.sh` picks the newest ISO with that commit, ignoring newer builds of other commits (main builds share the output directory). A version stamped at build time via `PURPLE_VERSION` is the release version; `just release` picks it up on its own, so there is no version to repeat or get wrong at release time.

### Why a separate worktree

`~/purplecomputer-release` is a linked worktree of this repo, not a clone: same object database, same branches and tags, just a second directory with `release/1.x` checked out (its `.git` is a pointer file back into the main checkout's).

- Builds read the working tree (docker mounts the project directory), so the branch needs its own directory. The alternative, switching the main checkout back and forth on ship day, is stateful and error-prone.
- A shared object database means `release-pick` cherry-picks local commits directly and tags are visible from both directories, no remote round-trips. The justfile resolves `.venv` through `git-common-dir`, so the worktree also needs no second environment. Release tooling (`just ship`, `release-iso.sh`, `.env`) always runs from this checkout; the worktree only supplies the commit, so tooling fixes on main take effect without a cherry-pick.
- It lives outside `.claude/worktrees/` deliberately: lane worktrees merge into main and get deleted, and this branch must never merge.

It is not a backup: it shares `.git` with the main checkout and dies with it. `just ship` pushes `release/1.x` after every release, so GitHub has a copy as of the last ship.

When the next major release ships from main: delete the branch, the worktree, and this section.



Copy the credentials template and fill it in:

```bash
cp build-scripts/.env.template build-scripts/.env
```

Required values: `R2_BUCKET`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `CF_API_TOKEN`, `CF_ZONE_ID`, `R2_CUSTOM_DOMAIN`.

---

## Full Release (ISO)

### 1. Build the ISO

```bash
./build-scripts/build-in-docker.sh                      # standard build
PURPLE_VERSION=v1.0 ./build-scripts/build-in-docker.sh  # stamp a specific version
```

Output goes to `/opt/purple-installer/output/`. Both a standard and debug ISO are produced.

### 2. Release to Cloudflare R2

```bash
just release            # auto-version from the build time: v2026.04.02-1430
just release v1.0       # semver for major releases
```

This will:
1. Generate SHA-256 checksums for both ISOs
2. Upload standard + debug ISOs to `releases/{version}/`
3. Update Cloudflare redirect rules (`/download.iso` -> versioned path)
4. Write `latest.json` with version, commit, checksums, and sizes, then tag the commit and push `release/1.x` and the tag to GitHub
5. Delete every older release except the one just replaced, which stays as a rollback

The script shows a summary and asks for confirmation before uploading.

### 3. Clean up old releases (by hand)

Every release already prunes R2 down to the current version plus the one before it. To go further, or to keep extra versions:

```bash
just clean-releases                    # interactive: lists old versions, asks before deleting
just clean-releases --dry-run          # preview what would be deleted
just clean-releases --keep v1.0        # also keep v1.0
```

The current version (from `latest.json`) is always kept.

### 4. Flash to USB

```bash
just flash          # standard ISO
just flash-debug    # debug ISO
```

---

## Updating the Download Page

The page is part of the landing site: edit `~/landing/src/pages/downloads.tsx` and deploy the landing repo. Nothing to upload from this repo.

---

## Updating the PDFs

```bash
just upload-pdfs
```

Extracts installation (pages 1-2) and guide (pages 3-4) from `cards/purple.pdf`, uploads them to R2, and purges the Cloudflare cache. The download page embeds them from the files host.

---

## Caching

ISOs use versioned paths (`releases/v1.0/standard.iso`), so each release has a unique URL cached aggressively at the edge (1 day TTL). The `/download.iso` shortcut is a Cloudflare 302 redirect with cache bypassed, so it always resolves to the latest version.

PDFs use fixed filenames, so `upload-pdfs` purges the Cloudflare cache after each upload. If the purge fails (missing CF credentials), a warning is printed but uploads still succeed.

---

## How the Download URL Works

```
User visits <files host>/download.iso
    -> Cloudflare evaluates redirect rule (cache bypassed)
    -> 302 to /releases/v1.0/standard.iso
    -> Cloudflare serves cached ISO (or fetches from R2 origin)
```

When `release-iso.sh` runs, it calls `setup-cloudflare-rules.sh` to update the redirect target. No need to re-upload or rename anything.

---

## Versioning

Every ISO is stamped with a version in `/etc/purple-version`, visible in the Parent Menu.

| Type | Example | Parent Menu shows | When |
|------|---------|-------------------|------|
| Semver | `v1.0` | Version 1.0 | Major releases (`just release v1.0`) |
| Build time | `v2026.03.30-1430` | Build: Mar 30, 2026 | Regular releases (`just ship`), UTC |
| Dev build | `build-abc1234-20260330` | Dev build: abc1234 | No `PURPLE_VERSION` set at build time |

---

## Scripts Reference

All scripts live in `build-scripts/`.

| Script | Just command | Purpose |
|--------|-------------|---------|
| `build-all.sh` (via `build-in-docker.sh`) | `./build-scripts/build-in-docker.sh` | Build standard + debug ISOs |
| `release-iso.sh` | `just release` | Upload ISOs to R2, update redirects |
| `release-check.sh` | `just release-check` | Show the live download's commit, verify it against a hash |
| `upload-pdfs.sh` | `just upload-pdfs` | Upload the card PDFs, purge cache |
| `clean-old-releases.sh` | `just clean-releases` | Delete old release versions from R2 |
| `flash-to-usb.sh` | `just flash` | Write ISO to USB drive |
| `setup-cloudflare-rules.sh` | (called by release) | Configure Cloudflare cache/redirect rules |
| `r2-helpers.sh` | (sourced by upload scripts) | Shared R2 upload and cache purge helpers |
