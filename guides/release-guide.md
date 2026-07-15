# Release Guide

How to build, release, and update Purple Computer downloads.

## Hosting layout

- `downloads.purplecomputer.org`: the customer download page. Lives in the landing repo (`~/landing/src/pages/downloads.tsx`), served by Vercel, deploys with the landing site. Its root is rewritten to `/downloads` by the landing middleware.
- The files host: the R2 custom domain (`R2_CUSTOM_DOMAIN`, value in the private env file). Serves the actual objects straight from Cloudflare: ISOs, checksums, `latest.json`, and the card PDFs. Everything in this guide uploads here.

The download page reads `latest.json` from the files host at build time (revalidated every 5 minutes), so the version badge updates on its own after a release.

---

## Prerequisites

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
just release            # auto-version: v2026.04.02-1430
just release v1.0       # semver for major releases
```

This will:
1. Generate SHA-256 checksums for both ISOs
2. Upload standard + debug ISOs to `releases/{version}/`
3. Update Cloudflare redirect rules (`/download.iso` -> versioned path)
4. Write `latest.json` with version, checksums, and sizes

The script shows a summary and asks for confirmation before uploading.

### 3. Clean up old releases (optional)

```bash
just clean-releases             # interactive: lists old versions, asks before deleting
just clean-releases --dry-run   # preview what would be deleted
```

Deletes all release versions from R2 except the current one (determined from `latest.json`).

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
| Date-time | `v2026.03.30-1430` | Build: Mar 30, 2026 | Regular releases (`just release`) |
| Dev build | `build-abc1234-20260330` | Dev build: abc1234 | No `PURPLE_VERSION` set at build time |

---

## Scripts Reference

All scripts live in `build-scripts/`.

| Script | Just command | Purpose |
|--------|-------------|---------|
| `build-all.sh` (via `build-in-docker.sh`) | `./build-scripts/build-in-docker.sh` | Build standard + debug ISOs |
| `release-iso.sh` | `just release` | Upload ISOs to R2, update redirects |
| `upload-pdfs.sh` | `just upload-pdfs` | Upload the card PDFs, purge cache |
| `clean-old-releases.sh` | `just clean-releases` | Delete old release versions from R2 |
| `flash-to-usb.sh` | `just flash` | Write ISO to USB drive |
| `setup-cloudflare-rules.sh` | (called by release) | Configure Cloudflare cache/redirect rules |
| `r2-helpers.sh` | (sourced by upload scripts) | Shared R2 upload and cache purge helpers |
