# Release Guide

How to build, release, and update Purple Computer downloads.

## Hosting layout

- `downloads.purplecomputer.org`: the customer download pages, in the landing repo (`~/landing/src/components/DownloadsPage.tsx`), served by Vercel, deploying with the landing site. The root is the current build (from `purple2/latest.json`); `/v1` is the frozen v1 (from `latest.json`), for families still on it. Both share one email gate. The old 2.0 preview host, `purple2.purplecomputer.org`, redirects to the root.
- The files host: the R2 custom domain (`R2_CUSTOM_DOMAIN`, value in the private env file). Serves the actual objects straight from Cloudflare: ISOs, checksums, the manifests, and the card PDFs. Everything in this guide uploads here.

Each page reads its manifest from the files host (cached 5 minutes), so the version badge updates on its own after a release.

---

## Shipping (main)

`main` is the shipping branch: customer USBs and the download both come from it.

```bash
just rtbf                    # test, build (with-backup), flash every whitelisted drive plugged in
just ship [commit]           # publish that build to the download, tag it v2.0.N
just ship-status             # what families have vs main, and what to run
```

`just rtbf` needs the main checkout on `main` and clean, since only a clean commit on main gets a `v2.0.N` version (see Versioning). `just ship` refuses any other build: families see the version in the Parent Menu. `PURPLE_WITH_BACKUP_ISO=1 just build` builds without testing or flashing. Build, then flash, then ship: flashing first means a stick can be validated on real hardware before the download updates.

`just ship [commit]` uploads standard + debug, plus the four `cards/v2/out` card PDFs as committed at the commit you name (default HEAD, even when it falls back to an older build), to `purple2/<version>/` on the files host (the prefix is from when this was the 2.0 preview), writes `purple2/latest.json`, and prunes `purple2/` to that version plus the one it replaced. It never touches `releases/`, `latest.json` or the redirects, which stay v1's. It tags the commit with its `v2.0.N` version and pushes the tag. When those exact ISOs are already live it only refreshes the cards under their version, so `just ship` after a card-only commit updates the cards without a rebuild. The page links the versioned paths straight from `purple2/latest.json`, so there are no redirects to maintain.

`just ship-status` gives one line each for the newest ISO build, the download, Studio, and purplecomputer.org: whether it's behind main and what to run (`-v` lists the missing commits). It also flags Studio running Purple the download doesn't have yet, since its demo and packs then show Purple families can't get. `just ship` and `just studio-deploy` print it when they finish.

---

## v1 (release/1.x)

Frozen and no longer shipped (the cutover: [docs/RELEASE-2.0.md](../docs/RELEASE-2.0.md)). Nothing commits to `release/1.x`. Families still on v1 get its last release from `downloads.purplecomputer.org/v1` (`releases/<version>/` and `latest.json` on the files host, plus the `/download.iso` redirects), and its cards from purplecomputer.org/cards/v1. Those objects stay up on their own; no command in this repo writes to them except `just upload-pdfs`.

To rebuild the v1 ISO if the hosted copy is ever lost:

```bash
just build --ref release/1.x     # builds that commit with its own build scripts, under /opt/purple-installer/archive/<hash>/
just flash --ref release/1.x     # flash that build
```

Once no family needs v1: delete the branch, the `/v1` pages in landing, and this section.

---

## Credentials

Copy the credentials template and fill it in:

```bash
cp build-scripts/.env.template build-scripts/.env
```

Required values: `R2_BUCKET`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `CF_API_TOKEN`, `CF_ZONE_ID`, `R2_CUSTOM_DOMAIN`.

---

## Updating the Download Page

The pages are part of the landing site: edit `~/landing/src/components/DownloadsPage.tsx` and deploy the landing repo. Nothing to upload from this repo.

---

## Updating the v1 PDFs

```bash
just upload-pdfs
```

Extracts v1's installation (pages 1-2) and guide (pages 3-4) cards from `cards/purple.pdf`, uploads them to R2, and purges the Cloudflare cache. The v1 pages embed them from the files host. The current cards ship with `just ship`.

---

## Caching

ISOs use versioned paths (`purple2/v2.0.1301/standard.iso`, `releases/v1.0/standard.iso`), so each release has a unique URL cached aggressively at the edge (1 day TTL). v1's `/download.iso` shortcut is a Cloudflare 302 redirect with cache bypassed, so it always resolves to the latest v1.

v1's PDFs use fixed filenames, so `upload-pdfs` purges the Cloudflare cache after each upload. If the purge fails (missing CF credentials), a warning is printed but uploads still succeed.

---

## How the v1 Download URL Works

```
User visits <files host>/download.iso
    -> Cloudflare evaluates redirect rule (cache bypassed)
    -> 302 to /releases/v1.0/standard.iso
    -> Cloudflare serves cached ISO (or fetches from R2 origin)
```

The redirect target was last set by `setup-cloudflare-rules.sh <version>` when v1 shipped; it only needs running again if the rules are lost.

---

## Versioning

Every ISO is stamped with a version in `/etc/purple-version`, visible in the Parent Menu.

| Type | Example | Parent Menu shows | When |
|------|---------|-------------------|------|
| Image count | `v2.0.1151` | Version 2.0.1151 | A clean commit on main (`just rtbf` or `just build`, then `just ship`) |
| Semver, build time | `v1.0`, `v2026.03.30-1430` | Version 1.0, Build: Mar 30, 2026 | Past v1 releases |
| Dev build | `build-abc1234-20260330` | Version abc1234 | Anything else with no `PURPLE_VERSION` set: uncommitted changes, a lane branch |

The image count is the number of commits on main (first parent) that touch a path the image build copies in, or the scripts that build it (`image_paths` in `build-scripts/image-lib.sh`). Docs, guides, tests and Studio commits leave it alone, so two builds with the same number carry the same image. It counts on from the newest `v2.0.N` tag, so a later change to the path list can't renumber published builds. `major.minor` comes from `__version__` in `purple_tui/__init__.py`; bump that by hand for a milestone and the count carries on.

---

## Scripts Reference

All scripts live in `build-scripts/`.

| Script | Just command | Purpose |
|--------|-------------|---------|
| `build-all.sh` (via `build-in-docker.sh`) | `./build-scripts/build-in-docker.sh` | Build standard + debug ISOs |
| `purple-rtbf.sh` | `just rtbf` | Test, build (with-backup) and flash a clean main |
| `upload-purple2.sh` | `just ship` | Publish a main build to the download |
| `upload-pdfs.sh` | `just upload-pdfs` | Upload the v1 card PDFs, purge cache |
| `flash-to-usb.sh` | `just flash` | Write ISO to USB drive |
| `setup-cloudflare-rules.sh` | (run by hand) | Configure Cloudflare cache/redirect rules |
| `r2-helpers.sh` | (sourced by upload scripts) | Shared R2 upload and cache purge helpers |
