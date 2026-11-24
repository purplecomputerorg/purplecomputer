# Updating Purple from a Purple Key

A family with Purple installed updates it by booting a newer Purple Key and installing again. This guide covers what a live boot does when the laptop already has Purple: what it tells the parent, and what each choice keeps.

Tests: `tests/test_old_install.py` (screens and choices), `tests/test_install_keep.py` (what `install.sh` finds and copies).

## What the probe finds

At startup a live boot runs `install.sh --probe` in the background (`purplecomputer/old_install.py`). It reads partition 2 of the internal disk without writing to it and copies the old Purple's data into `/run/purple-keep`:

- `config/`: `~/.config/purple` (settings, PIN, Time Travel, saves, each kid's folder)
- `.purple/`: installed packs, and a name renamed before Nov 2026 (no TTS cache)
- `computer_name.txt` and `purple-version`: the install-time name and the build

| Probe prints | State | Means |
|---|---|---|
| nothing | `None` | No Purple (no `PURPLE_ROOT` label), or no internal disk |
| `[PURPLE-FOUND] name` | `found` | Purple with the kid's work: any `saves/*.json` or `timeline/*.jsonl`, any kid's |
| `[PURPLE-EMPTY] name` | `empty` | Purple with only settings. Every v1 install, since v1 had no saves or Time Travel |
| `[PURPLE-FOUND-UNREADABLE]` | `unreadable` | A `PURPLE_ROOT` partition that couldn't be mounted or copied in full |

## What the parent sees

`found` and `empty` are updates, so every screen says Update. `None` and `unreadable` say Install.

| State | Welcome screen note | Pop-up after the welcome screen | Parent Menu row | Menu confirm (after the name screen) |
|---|---|---|---|---|
| `None` | "To install Purple and keep it, hold Esc…" | none | Install on this Computer | Install: "Everything on this computer will be erased." |
| `found` | "This Key can update the Purple on this laptop, keeping your kid's work." | Update and keep everything / Update and start fresh / **Just play for now** ("What's made now won't be kept when you update") | Update Purple on this Computer | Update and keep everything / No, go back / Update and start fresh |
| `empty` | "This Key can update the Purple on this laptop." | Update / **Just play for now** | Update Purple on this Computer | Update / No, go back |
| `unreadable` | same as `None` | none | Install on this Computer | Install anyway / No, go back, with "Installing will erase it." |

Bold is the default. If the Key has a parent PIN, the pop-up asks for it before installing. Every Update screen opens with "This Key has a new version of Purple." It says "different" only when the versions show the Key isn't newer (`old_install.key_is_newer`): the same build, or an earlier build date. A v1 laptop, an unknown format or a missing version file counts as new.

"Update and start fresh" asks again: "This erases everything your kid saved on this laptop."

## What each choice installs

| Choice | Settings and PIN | Rooms and Time Travel | Saves (Open) | Packs | Name |
|---|---|---|---|---|---|
| Install (`None`, `unreadable`) | Key's | Key's | Key's | none | typed at install |
| Update and keep everything (`found`) | laptop's | laptop's | laptop's + Key's | laptop's | typed at install |
| Update and start fresh (`found`) | Key's | Key's | Key's | none | typed at install |
| Update (`empty`) | laptop's, copied onto the Key first (`settings.adopt`) | Key's | Key's | none | typed at install |

The name screen starts with the laptop's name for `found` and `empty`. A blank name drops it.

Why "keep" drops the Key's Time Travel: Time Travel is one history per room, and two histories can't both be the room's present. The laptop's wins because it's the work the family chose to keep, and the "Just play for now" note tells the parent up front that play on the Key won't come along. Saves are separate files, so the Key's are added.

Why `empty` brings the Key's work whole: the laptop has nothing for it to clash with. Only its settings and PIN (the keys v2 knows) are copied onto the Key's before the usual install. A v1 file that still says `silent_mode` comes over as a volume limit of 0, so a silent laptop stays silent.

## Timing

The probe mounts the laptop's disk, so it can take a few seconds. A key pressed on the welcome screen before it finishes skips the pop-up: the parent plays, and Parent Menu, Install waits for the probe and then shows the right confirm screen. The welcome note switches to the update line as soon as the probe finishes.

## Known gap

With "keep", only the first kid's saves come from the Key (`saves/`, not `kids/*/saves/`). A Key with more than one kid profile loses the other kids' saves. Merging the laptop's and the Key's kid lists would fix it.
