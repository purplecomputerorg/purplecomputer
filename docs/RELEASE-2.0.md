# Purple 2.0 release (November 2026)

Main's canvas build became the one customers get, and main became the shipping branch. Customers just see "Purple": the downloads page names no version and has no preview wording. Builds are still versioned `v2.0.N` (Parent Menu, page badge). Tracked in PUR-16.

## Downloads (landing repo)

- **`downloads.purplecomputer.org`** serves main's build: `purple2/latest.json` on the files host and the four box cards it lists. The preview wording, the testing-terms checkboxes and the feedback form are gone (`/api/purple2-feedback` deleted). Its small print links the v1 page.
- **`downloads.purplecomputer.org/v1`** is the previous page: `latest.json`, the `/download*.iso` redirects, the installation and guide cards. Not indexed.
- **purplecomputer.org/cards** shows the four cards; **`/cards/v1`** shows the two v1 cards, for boxes that came with those. The `/help` tile matches.
- **One gate for both pages:** `DOWNLOADS_ACCESS_KEY` and the `downloads_auth` cookie. An order, a preorder, or a grant made on either old page unlocks. `PURPLE2_ACCESS_KEY` is no longer read. `/admin/downloads` lost its page picker; activity rows say Current or v1.
- **`purple2.purplecomputer.org/`** redirects (307) to `downloads.purplecomputer.org/` with the query string kept, so the early access email's `?email=` still fills in the gate.
- **Internal names kept:** channel `purple2` is the current build and `purple1` is v1, in download logs and on R2 (`purple2/` prefix). Renaming them would churn logged data for nothing customers see.

## Shipping (this repo)

- `just rtbf` tests, builds (with-backup) and flashes main; it refuses unless the checkout is on `main` and clean, since only then is the image stamped `v2.0.N`.
- `just ship` publishes a main build to the download (it was `just ship-2`). It refuses dev builds (`build-<hash>-<date>`), which families would see as a bare commit hash in the Parent Menu. ISOs now download as `purple-computer-v2.0.N.iso`.
- v1: `release/1.x` is frozen. `just ship-v1` publishes it (it was `just ship`); the `release-*` recipes are unchanged. `just release` is gone: it published whatever checkout it ran in to the v1 paths.
- Updated to match: `guides/release-guide.md`, CLAUDE.md, MANUAL, `/ship`, `ship-status` rows.

## People who used a downloads page before the switch

- **Unlocked the old downloads page:** still unlocked (same cookie), and now offered the new build. Installing over v1 keeps settings, Time Travel history, packs and the computer's name (`save_old_purple` in `install.sh`).
- **2.0 preview testers:** already on this build line, nothing to reinstall. The purple2 cookie was host-only, so they enter their email once on the downloads host (filled in when they come from the email link). Testers granted access without an order still get in.
- **A page left open:** download links on either host keep working; v1's files are untouched and `just ship` keeps the version it replaces.
- **Old direct `/download.iso` links** still give v1.

## When v1 can go

Once no family needs v1: delete `release/1.x` and `~/purplecomputer-release`, the landing `/v1` and `/cards/v1` pages and `V1_CARDS`, `release-iso.sh`, `release-check.sh`, `release-status.sh`, the `release-*` and `ship-v1` recipes, and the v1 section of the release guide.
