# What the e2e-ai sweep found (2026-11-12 13:55)

`just e2e-ai-sweep` spent $9.32 on 17 scenarios (personas: `scripts/e2e_ai_scenarios.py`). Every run's screenshots, logs and report.json are in `/tmp/purple-e2e-ai/sweep-20261112-134022`.

| Scenario | Spent | Real findings |
|---|---|---|
| 1-breaker | $0.87 | 1 |
| 1-music-family | $0.41 | 1 |
| 1-returning-parent | $0.30 | 1 |
| 1-room-maker | $0.90 | 1 |
| 1-grandparent | $0.50 | 1 |
| 1-phone-parent | $0.66 | 0 |
| 1-thorough-tour | $1.03 | 2 |
| 1-toddler-masher | $0.22 | 1 |
| 1-coder-kid | $0.53 | 1 |
| 2-toddler-masher | $0.37 | 0 |
| 2-returning-parent | $0.28 | 1 |
| 3-returning-parent | $0.22 | 0 |
| 2-music-family | $0.54 | 1 |
| 2-grandparent | $0.45 | 1 |
| 3-music-family | $0.46 | 0 |
| 2-thorough-tour | $0.75 | 0 |
| 3-grandparent | $0.30 | 0 |

## How to use this

- **Verify each repro before changing code.** These come from AI testers and an AI judge, and either can be wrong. Several "Where to look" entries are guesses from file names only.
- **Read CLAUDE.md first.** Only the canvas UI (`purplecomputer/`) and Studio (`studio/`) get fixes. The Textual UI is frozen.
- **Add a test for each real bug:**
  - Purple-side bugs go in `tests/`.
  - Studio-side bugs go in Studio's tests.
  - Anything about what ends up in a downloaded pack goes in `tests/test_studio_to_purple.py`.
- **Studio's preview is a separate thing from real Purple.** Studio's preview runs Purple's Python in the browser (`studio/src/live/`), but several findings were only seen in the preview and not on real Purple. Check which side a bug is actually on before fixing.

## Fix these

### 1. [high] [studio] Studio's Purple preview is stuck under a flat bright-blue cover and ignores the chosen colors

**What happens**
- The preview screen on Studio's right side turns a saturated blue. The room underneath is only faintly visible, so it looks like an overlay rather than a theme.
- It was seen in Play, Art, Letters and Music.
- It appeared before any color was picked and stayed after Forest was chosen. The Colors card shows dark green, but the preview never does.
- Parents clicked "Click to type here" and typed their word (mama, mia!, biscuit?) for 20+ seconds. The cover never cleared and the word never appeared.
- In 3-grandparent the cover cleared once, then came back after typing.
- In 1-thorough-tour the Memory room preview was gray-green, then turned blue once Memory was added to the pack.
- It is intermittent:
  - 2-music-family's Music preview was correctly green (screenshot `2-music-family-studio-005.png`).
  - 3-music-family saw green in Art and Music.
  - The 1-room-maker, 1-breaker and 2-returning-parent previews were not blue.
- The same packs are correct on real Purple. The check "screen is the pack's #10241a" passed, and the kids saw green and their words. So only Studio's preview is broken.
- A related symptom, which may share a cause: in `1-music-family-studio-006.png` the Music room is selected, but the caption under the room buttons still reads Art's "Type on the keyboard to paint." Elsewhere, Music's caption is "Purple's Music room. Letter keys play notes…". The room switch may not fully refresh the preview area.

**Expected**
- Any update or restart cover clears once the preview is ready.
- The preview shows the pack's chosen screen color.
- Clicking the preview gives it focus, and typed words show.
- The caption matches the selected room.

**Repro** (combined from the scenarios; reproduction is not guaranteed because the bug is intermittent)
1. Open Studio at 1280x900. Go to Words and add a word (e.g. "mama") with an uploaded photo.
2. Look at the Play preview. It is bright blue with "Click to type here".
3. Click the preview, type the word and press Enter, repeating for about 20 seconds. The cover stays and the word never shows.
4. Go to Colors and choose Forest, then switch the preview to Art and then Music. It stays blue, and the caption still reads "Type on the keyboard to paint."
5. Optionally, add the Memory room in New Rooms and watch its preview go from gray-green to blue.

**Seen in**
- With screenshots: 1-thorough-tour, 1-music-family, 1-toddler-masher.
- From tester summaries only: 2-grandparent (its screenshot 012 also shows it), 3-grandparent, 2-thorough-tour, 2-toddler-masher.
- Seven scenarios in total.

**Screenshots**
- /tmp/purple-e2e-ai/sweep-20261112-134022/shots/1-thorough-tour-studio-008.png
- /tmp/purple-e2e-ai/sweep-20261112-134022/shots/1-thorough-tour-studio-016.png
- /tmp/purple-e2e-ai/sweep-20261112-134022/shots/1-music-family-studio-006.png
- /tmp/purple-e2e-ai/sweep-20261112-134022/shots/1-toddler-masher-studio-010.png
- /tmp/purple-e2e-ai/sweep-20261112-134022/shots/2-grandparent-studio-012.png

**Where to look** (guesses)
- `studio/src/ui/live.ts`, `studio/src/ui/laptop.ts`, `studio/src/ui/stage.ts`: these likely own the preview, its "updating" cover and the click-to-focus label. A cover whose hide step is skipped when a restart is superseded by another edit would match "cleared once, came back after typing".
- `studio/src/styles.css`: the cover's blue color.
- `studio/src/live/boot.ts`, `studio/src/live/frame.ts`: preview restart and first frame.
- `studio/src/ui/colors.ts`, `studio/sdk/src/purple/theme.ts`: how the chosen theme reaches the preview.
- `tests/test_studio_live.py`: may already cover the live preview.

**Confidence**
- High that it happens: seven scenarios and five screenshots.
- Low on the cause.
- Raise it by reproducing at 1280x900, then, while the screen is blue:
  - inspect the DOM for an element layered over the preview canvas;
  - read the browser console for preview restart errors.

### 2. [medium] [studio] After reopening a pack and replacing a word's photo with an emoji, the old photo stays in the pack as a "room picture or sound"

**What happens**
- A parent reopens a downloaded pack and changes a word's picture from their uploaded photo (backyard.png) to an emoji.
- Studio keeps the photo and reclassifies it:
  - The Download summary lists "1 room picture or sound: backyard".
  - New Rooms shows a badge of 1, though no room was made.
  - The Download count includes it (3 = 2 words + 1).
- The re-downloaded pack still contains `content/images/backyard.png`, according to the tester's inspection of the file.
- Purple never shows the photo: Play correctly answers with the emoji. It is still the parent's private photo shipping in a pack they believe no longer contains it.
- The only way to remove it is "Throw away" under New Rooms, and nothing says that item is the old word photo.
- Related history: this looks like the struck-through entry in docs/AI_UX_BUGS.md, "Word's photo is also counted as a room picture… FIXED". That fix probably covers fresh words but not images loaded from a reopened pack.

**Expected**
- When a word's photo is replaced and nothing else uses it, the photo leaves the pack and the room counts.
- If it is kept on purpose, it is labeled as the old word photo, not as a room item.

**Repro**
1. In Studio, add the word "backyard" (or "dog") with an uploaded photo (backyard.png). Download the pack.
2. Reload Studio, clear everything, and open the downloaded .purplepack.
3. Change that word's picture to an emoji (🌳). Optionally add another word.
4. Open Download. It shows "1 room picture or sound: backyard", and New Rooms has a badge of 1.
5. Download again and list the pack's files. `content/images/backyard.png` is still there.

**Seen in**
- 1-returning-parent and 2-returning-parent.
- Possibly 2-thorough-tour, whose parent mentioned "the photo being listed twice" without detail.
- 3-returning-parent reopened a pack without swapping the photo and reported nothing, so the swap is probably the trigger.

**Screenshots**
- /tmp/purple-e2e-ai/sweep-20261112-134022/shots/1-returning-parent-studio-010.png
- /tmp/purple-e2e-ai/sweep-20261112-134022/shots/2-returning-parent-studio-006.png

**Where to look** (guesses)
- `studio/src/ui/packfile.ts`: opening a pack likely imports `content/images/*` as shared or room files, so the word only references them.
- `studio/src/pack.ts`: building the pack, deciding which images ship.
- `studio/src/state.ts`: the word-to-image ownership model.
- `studio/src/ui/download.ts`: the summary and counts.
- `studio/src/ui/roomfiles.ts`: the New Rooms "room pictures and sounds" list and badge.
- `studio/src/ui/words.ts`: the picture swap.
- Add a round-trip test in `tests/test_studio_to_purple.py`: reopen, swap, download, and assert no orphan image.

**Confidence**
- High for the summary and badge: they are visible in the screenshot.
- Medium for the pack still containing the file. That rests on the tester's file listing in two scenarios.
- Raise it by unpacking the second download and checking `content/images/`.

### 3. [medium] [studio] Picture Quiz preview draws an empty choice after a page reload

**What happens**
- The Picture Quiz Q1 has an uploaded photo as the RIGHT answer ("Biscuit") and the starter pig and sheep as OTHER choices.
- After a page reload, the preview shows "1" with no picture above it, the photo above "2", and the sheep above "3".
- The form still lists the pig with its emoji thumbnail, so the data is present but not drawn.
- The tester said all three pictures showed before the reload. That is not backed by a screenshot.
- No pack was downloaded, so whether a real Purple shows the blank is unknown.
- Note: the form's pig thumbnail is 🐖, not 🐷. If that glyph has no picture in Purple's emoji set, the blank would show regardless of the reload.

**Expected** All choices draw their picture.

**Repro**
1. In Studio, open New Rooms and choose "A picture quiz".
2. Set Q1's text to "Which one is our dog Biscuit?". Set the RIGHT picture to an uploaded photo and its word to "Biscuit". Leave the pig and sheep as OTHER.
3. Reload the page and wait for the preview.
4. Choice 1 has no picture. Because choices are shuffled, check which choice is blank across reloads.

**Seen in** 1-room-maker

**Screenshots**
- /tmp/purple-e2e-ai/sweep-20261112-134022/shots/1-room-maker-studio-016.png

**Where to look** (guesses)
- `purplecomputer/emoji_pictures.py` and `studio/src/emoji.ts`: whether 🐖 resolves to a drawable picture. `tests/test_emoji_pictures.py` is the natural place for a test.
- `studio/src/ui/templateform.ts` or `studio/src/ui/builderkit.ts`: the form that writes the quiz Python.
- `studio/src/saved.ts`: restoring room state after reload.
- `studio/src/rooms/guest.py`: room runtime in the preview.

**Confidence**
- Medium-low: one scenario and one screenshot.
- Raise it in three ways:
  - Check whether 🐖 renders in Play on its own.
  - Reproduce with and without a reload.
  - Download the pack and run the quiz on real Purple.

### 4. [medium] [purple] Long word meaning runs past the right edge of Play instead of wrapping inside the screen

**What happens**
- A long meaning was set: `<b>bold</b> "quote" 'apos' ); \ DROP TABLE; ñandú café 🎉 <script>alert(1)</script>`.
- Typing "who nino" shows the first line cut at "…DROP TABLE; ñan". The second line starts at `<script>`.
- So the text does wrap, but at a width wider than what is visible, and "dú café 🎉" is never seen.
- The "Type →" input box also runs past the right edge.
- HTML-like text is shown as plain text, so escaping is fine.
- Caveat: this was seen only in Studio's preview, with its zoom on (the button reads "Whole screen"). The clipping could be the zoom cropping the screen rather than Play's wrap width. Real Purple was not tested with this meaning.

**Expected** The meaning wraps within the visible width, and the input box fits on screen.

**Repro**
1. In Studio, go to Words, add "nino" with an emoji, and set Meaning to the string above.
2. In the preview's Play room, type `who nino` and press Enter.
3. The first meaning line is cut off at the right edge, and the input box overflows.
4. Repeat with the preview zoom off, and on real Purple at 1366x768.

**Seen in** 1-breaker

**Screenshots**
- /tmp/purple-e2e-ai/sweep-20261112-134022/shots/1-breaker-studio-016.png

**Where to look** (guesses)
- `purplecomputer/rooms/play_room.py`: meaning layout and wrap width.
- `studio/src/ui/laptop.ts` and `studio/src/ui/live.ts`: what "Zoom in" / "Whole screen" crops.
- Tests to extend: `tests/test_meanings.py` and `tests/test_layout_fit.py`. `tests/test_play_markup_safety.py` already covers escaping.

**Confidence**
- Low-medium.
- Raise it by reproducing on real Purple, or in the preview with zoom off. If it doesn't reproduce there, the bug is in Studio's zoom, not in Play.

### 5. [low] [studio] Card selection circle is drawn empty while the item is in the pack

**What happens**
- On Instruments, under YOURS, the "My Kazoo" card shows "✓ In my Pack", but the unlabeled round control at its top right is empty.
- On Pictures, under YOURS, "Backyard" also shows an empty circle. That tester said the control reported itself as checked, so its visual and accessible states may disagree.
- A parent reads the empty circle as "not chosen" and might click it to "fix" that.

**Expected**
- The circle's look matches its state and the pack state.
- The circle has a label or tooltip saying what it does.

**Repro**
1. In Studio, open Instruments, make an instrument from Kazoo ("My Kazoo") and add it to the pack.
2. Look at its card under YOURS. It shows "✓ In my Pack" next to an empty circle.

**Seen in**
- 2-music-family (Instruments).
- 2-returning-parent (Pictures). That case is in the reopened-pack state from issue 2, so first confirm what the Pictures circle means.

**Screenshots**
- /tmp/purple-e2e-ai/sweep-20261112-134022/shots/2-music-family-studio-005.png
- /tmp/purple-e2e-ai/sweep-20261112-134022/shots/2-returning-parent-studio-006.png

**Where to look** (guesses)
- `studio/src/shelf.ts` and `studio/src/cards.ts`: shared "Yours" card rendering.
- `studio/src/ui/instrument.ts` and `studio/src/ui/pictures.ts`: the two pages.
- `studio/src/styles.css`: checked-state styling.

**Confidence**
- Medium. The screenshots show the empty circle next to "In my Pack", but nobody established what the circle does.
- Read the code for its purpose first, then check its `aria-checked` against what is drawn.

### 6. [low] [purple] Rooms screen says "Family rooms on: 1 of 5" with five rooms checked

**What happens**
- After adding a pack with a Memory room, the Rooms screen shows Art, Music, Play, Blocks and Memory checked.
- The text reads "Family rooms on: 1 of 5".
- "Family rooms" is never defined. It probably means pack rooms, with a limit of 5.
- "of 5" coincides with the five built-in tiles, so it reads like a wrong count.

**Expected** Wording that says what is counted and what the limit is, e.g. that it counts rooms from Purple Packs and up to 5 can be on.

**Repro**
1. Add a pack containing the Memory room on Purple.
2. On the Rooms screen, check Memory.
3. Read the counter line.

**Seen in** 1-thorough-tour

**Screenshots**
- /tmp/purple-e2e-ai/sweep-20261112-134022/shots/1-thorough-tour-purple-handoff-003.png

**Where to look** (guess)
- `purplecomputer/rooms/rooms_screen.py`: the counter text and the limit.
- `purplecomputer/roomkit/limits.py`: possibly where 5 is defined.
- `purplecomputer/i18n.py`: if strings are translated.
- Test in `tests/test_rooms_off.py` or `tests/test_room_picker.py`.

**Confidence**
- High that the text is shown; the screenshot is clear.
- Medium on what "5" means. Confirm it in the code before rewording.

## Decide these

- **How big should a parent's photo be in Play?**
  - **What tripped testers up:** a word's photo is drawn at emoji size, about 37x28 px on a 1366-wide screen. Parent, grandparent and kid testers couldn't tell it was a real photo. The fixture backyard.png is itself a simple sky/grass/sun drawing, which made this worse, but a real family photo would also be unrecognizable at that size.
  - **Evidence:**
    - Kept findings in 1-grandparent and 2-grandparent: screenshots `1-grandparent-purple-handoff-017.png`, `1-grandparent-purple-kid-006.png`, `2-grandparent-purple-kid-008.png`, `2-grandparent-studio-012.png`.
    - Also raised in 3-grandparent, 3-returning-parent, 1-toddler-masher and 1-phone-parent.
    - Studio's copy says the photo shows "instead of Purple's emoji", so emoji size may be by design.
  - **Options:**
    1. Keep emoji size.
    2. Draw a photo-only answer large, and keep it emoji-size inside sentences.
    3. Always draw photos larger.
  - **Where:** `purplecomputer/rooms/play_room.py`, `tests/test_word_pictures.py`.
- **Starter rooms' CAPITAL settings have no numbers to change.**
  - **What tripped testers up:** in Memory, Snake, Garden and Explore, the "easy settings in CAPITALS" are lists, emoji, colors and sound names. Simple knobs like card count, speed or lives are buried in code; Memory's card count is in `cards = CARDS[:13] * 2`. Long lines are also clipped in the small code box.
  - **Evidence:** 1-coder-kid, screenshot `/tmp/purple-e2e-ai/sweep-20261112-134022/shots/1-coder-kid-studio-015.png`.
  - **Options:**
    - Add numeric CAPITAL settings (e.g. PAIRS, SPEED) to some or all starters (`studio/src/examples/*.py`).
    - Keep them as they are.
    - Separately, choose whether the code box wraps, gets wider, or keeps scrolling sideways.
- **Where do Pictures show up for the kid?**
  - **What tripped testers up:** kids looked for the parent's Picture in Play.
  - **Evidence:**
    - 2-toddler-masher's kid typed "backyard" in Play and got only letter tiles.
    - 1-thorough-tour's kid never saw the caption "Our backyard".
    - Studio says Pictures become paintings in Art, but no tester checked Art on Purple.
  - **Options:** leave it to the parent, or add a hint on Purple or in Studio's Download steps saying "your picture is in Art".
- **What a grandparent sees after adding a pack.**
  - **What tripped testers up:** the 3-grandparent tester on Purple said the pack screen doesn't say which room the new word is in or what to type, and the Purple Packs list doesn't show what's inside.
  - **Evidence:** from the summary only, no kept finding.
  - **Options:** show a short contents line ("1 word: mia, in Play"), or leave it as is.

## Already known

- None of this sweep's kept findings match an open (not struck through) entry in docs/AI_UX_BUGS.md.
- Testers' "already reported" remarks refer to other scenarios in this same sweep.
- Issue 2 resembles the struck-through "Word's photo is also counted as a room picture… FIXED". Treat it as a gap in that fix, not as a known open bug.

## Coverage

**Exercised well**
- Words with emoji, photo, meaning, and recorded or Purple voice: round trip Studio → pack → Play on Purple. Typing the word, "who is X", and "say X" / "X!" all worked.
- Forest colors on real Purple (the check passed).
- Custom instruments appearing in Music, with G/H lighting up in both letter modes.
- Reopening a downloaded pack and editing it (three returning-parent runs).
- Adding a pack from USB, the Rooms screen, and the Parent Menu listing the pack.
- The Picture Keyboard and Memory rooms opening on Purple.
- Key mashing, held keys and room switching (no crashes).

**Never reached or not verifiable**
- **Any audio.** No tester could hear, so these are all unconfirmed: recorded letters, grandma.wav on words and letters, Kazoo playback, and Purple's voice.
- **Studio preview checks.** Most were skipped because of issue 1. Re-run preview-dependent scenarios once it's fixed.
- **Art on Purple.** Pictures as paintings and painting over a parent photo were never checked.
- **Blocks and Write.** Barely touched.
- **Rooms that never reached Purple.** Picture Quiz, edited room code (1-coder-kid never downloaded), and Memory with photo cards were never downloaded or played to the end. 1-breaker, 1-room-maker, 1-coder-kid and 2-thorough-tour had no Purple side at all.
- **Long meanings on real Purple.** Needed to settle issue 4.
- **Phone-sized Studio.** Only 1-phone-parent, and it filed nothing.
- **Ocean and other non-Forest colors on Purple.**

**Unfiled leads from tester summaries** (worth targeting, no evidence yet)
- On a phone, the emoji picker covers the key rows and runs off the bottom of the screen (1-phone-parent).
- Emoji search: "nana" returns bananas, and "biscuit" returns nothing (1-phone-parent).
- Play showed a "Type → biscuit" line with the photo before the kid typed anything (1-phone-parent kid).
- The Picture Keyboard shows the picture with no word under it (1-phone-parent kid).
- Play's history line shows "mia" when "mia!" was typed (1-grandparent kid). This may be intended.
