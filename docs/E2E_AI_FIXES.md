# What the e2e-ai sweep found (2026-11-12 11:38)

`just e2e-ai-sweep` spent $9.58 on 11 scenarios (personas: `scripts/e2e_ai_scenarios.py`). Every run's screenshots, logs and report.json are in `/tmp/purple-e2e-ai/sweep-20261112-112540`.

| Scenario | Spent | Real findings |
|---|---|---|
| 1-room-maker | $1.31 | 1 |
| 1-breaker | $1.44 | 4 |
| 1-toddler-masher | $0.17 | 0 |
| 1-thorough-tour | $1.92 | 1 |
| 1-grandparent | $0.50 | 1 |
| 1-phone-parent | $0.31 | 0 |
| 1-coder-kid | $1.08 | 0 |
| 1-music-family | $0.54 | 2 |
| 1-returning-parent | $0.49 | 2 |
| 1-two-languages | $0.49 | 2 |
| 2-thorough-tour | $0.85 | 1 |

## How to use this

- **Verify each repro before changing code.** These findings come from AI testers, and an AI tester can be wrong. Several kid testers couldn't hear, so nothing here confirms or rules out sound behavior.
- **Read CLAUDE.md first.** Only the canvas UI (`purple_tui/canvas/`) and Studio (`studio/`) get fixes. The Textual UI is frozen.
- **Add a test for each real bug.**
  - Purple-side bugs go in `tests/canvas/`.
  - Studio-side bugs go in Studio's tests. No Studio test files appear in the file list, so find the runner under `studio/` first.
  - Pack round trips (Studio makes it, Purple reads it) go in `tests/canvas/test_studio_to_purple.py`.
- **"Where to look" is always a guess** based on file names. Confirm it before editing.

## Fix these

### 1. [high] [studio] Typed "Words for Purple to say" is thrown away on Done unless "▶ Say it" was pressed

**What happens:** A parent opens a word, keeps Purple's voice, and types a sentence in the "Words for Purple to say" box. If they click Done without pressing "▶ Say it", the sentence is not saved.
- The editor shows "✓ In your Purple Pack." the whole time, so nothing warns the parent.
- Reopening the word shows an empty box with the placeholder `Purple says "biscuit"`.
- The Meaning typed in the same session is kept. Only the spoken sentence is lost.
- The sentence is kept, and the Download count goes up, only after pressing "▶ Say it".
- Studio's own example card promises this works: "Purple says the words you typed: 'Biscuit is our silly dog'".

**Expected:** The sentence is saved on Done (or on blur), the same way Meaning is. If it can't be, the editor should not say "In your Purple Pack" while it's unsaved.

**Repro:**
1. In Studio, go to Words and add `zebra`.
2. Under Sound, keep Purple's voice and type `stripes stripes` in "Words for Purple to say".
3. Note that the editor shows "✓ In your Purple Pack."
4. Click Done without pressing "▶ Say it". (1-thorough-tour also tried Tab, then Close. Same result.)
5. Click zebra to open it again. The say box is empty, and the sentence is not in the downloaded pack.

**Seen in:** 1-breaker (every time, with plain text and with accents/symbols, on two words), 1-thorough-tour (word "biscuit").

**Screenshots:**
- /tmp/purple-e2e-ai/sweep-20261112-112540/shots/1-breaker-studio-011.png (typed text next to the "✓ In your Purple Pack." banner)
- /tmp/purple-e2e-ai/sweep-20261112-112540/shots/1-thorough-tour-studio-013.png (reopened word: Meaning kept, say box empty)

**Where to look (guess):**
- `studio/src/ui/words.ts`: the word editor and its Done handler. Compare how the Meaning field commits with how the say field commits.
- The say text may only be stored when "Say it" renders audio. Check `studio/src/state.ts`, `studio/src/saved.ts`, `studio/sdk/src/says.ts` and `studio/src/live/piper.ts`.
- That theory fits issue 5: a Purple's-voice word ended up as `content/voice/nino.wav` and was counted as "your voice".

**Confidence:** High. Two scenarios, consistent behavior, and screenshots of both the misleading state and the empty reopened box. A Studio test that types, clicks Done and reopens would settle it.

### 2. [medium] [between] Studio saves "niño" as "nino", and Purple doesn't find it when the kid types "niño"

**What happens:**
- **In Studio:** the parent types `niño`, and Studio silently turns it into `nino`.
  - The prompt reads `What should "nino" show?`.
  - The emoji search is prefilled with `nino` and finds nothing.
  - The pack keys the word as `nino` (`content/voice/nino.wav`).
- **On Purple:** typing `nino` shows the photo and the meaning "un niño pequeño". Typing `niño` with the ñ shows only letter tiles (n i ñ o) and no photo.
- Purple accepts ñ as input, so the correctly spelled word can't reach the parent's word.

**Expected:** Typing `niño` on Purple finds the pack word `nino`. Studio says it stores words "the way kids type it on Purple", so Purple's lookup should fold accents the same way Studio does.

**Repro:**
1. In Studio, open Words.
2. Type `niño` in New word and press Enter.
3. See `What should "nino" show?` and an emoji search for `nino` with nothing found.
4. Add a photo, download the pack, and add it on Purple.
5. On Purple, press Esc, choose Play, type `niño` (with ñ) and press Enter. Only letter tiles show.
6. Type `nino` and press Enter. The pack photo shows.

**Seen in:** 1-two-languages. Also 1-breaker, where the parent saw niño become "nino" in Studio; their kid only typed "nino".

**Screenshots:**
- /tmp/purple-e2e-ai/sweep-20261112-112540/shots/1-two-languages-studio-008.png
- /tmp/purple-e2e-ai/sweep-20261112-112540/shots/1-two-languages-purple-kid-009.png

**Where to look (guess):**
- Purple's word lookup: `purple_tui/play_eval.py`, `purple_tui/canvas/rooms/play_room.py`, and pack word loading in `purple_tui/content.py` / `purple_tui/pack_manager.py`. Apply Studio's accent folding to the typed word before matching pack words.
- Studio's folding lives somewhere in `studio/src/ui/words.ts`. Copy its exact rule so both sides agree.
- The empty emoji search is a separate small fix in `studio/src/ui/emojipicker.ts` / `studio/src/emoji.ts`.
- Test in `tests/canvas/test_studio_to_purple.py`. `tests/canvas/test_languages.py` may already cover folding.

**Confidence:** High on the symptom (both screenshots). Not tested: `who is niño` and spelling the word in Music's Letters mode. Checking those would show how many lookup paths need the fold.

### 3. [medium] [purple] Chinese characters in a meaning render as empty boxes □□ in Play

**What happens:**
- nino's meaning includes `中文`. In Play, `who is nino` shows everything else correctly as plain text: `<b>`, quotes, `); \`, é and 🎉.
- `中文` shows as two empty boxes.
- Studio accepts the text without any warning.

**Expected:** Purple draws the characters, or Studio warns that Purple can't show them.

**Repro:**
1. In Studio, give a word a meaning containing `中文`.
2. Download the pack and add it on Purple.
3. On Purple, press Esc and choose Play.
4. Type `who is nino` and press Enter. The meaning line shows □□ where `中文` should be.

**Seen in:** 1-breaker.

**Screenshots:** /tmp/purple-e2e-ai/sweep-20261112-112540/shots/1-breaker-purple-kid-005.png

**Where to look (guess):**
- Text rendering and font loading: `purple_tui/canvas/gfx.py`, `purple_tui/canvas/ui.py`, `purple_tui/font_sizer.py`. Look for a missing fallback font.
- If shipping a CJK font is too big, add a Studio-side warning in `studio/src/ui/words.ts`. That tradeoff may need a person's decision.

**Confidence:** High on the symptom. Rendering one CJK string in a canvas test would confirm the cause.

### 4. [low] [purple] "Added purple-sunny-otter" message never goes away

**What happens:** After the pack is added, a message reading "Added purple-sunny-otter" appears at the bottom of the screen. It stayed up for the whole session:
- through all of Dog Quiz,
- back on the room list,
- and in Picture Keyboard at kid step 22.

It sits on top of the bottom border of the play area.

**Expected:** The message fades after a few seconds.

**Repro:**
1. Add the purple-sunny-otter pack on Purple and turn on its rooms.
2. Open Dog Quiz and play it to the end.
3. Press Esc, then open Picture Keyboard.
4. The message is still on screen, overlapping the bottom of the play area.

**Seen in:** 1-room-maker. In 1-grandparent and 1-two-languages the parent also saw "Added …" but didn't say whether it lingered.

**Screenshots:** /tmp/purple-e2e-ai/sweep-20261112-112540/shots/1-room-maker-purple-kid-022.png

**Where to look (guess):**
- `purple_tui/pack_arrivals.py` (sets the message).
- `purple_tui/canvas/app.py` / `purple_tui/canvas/ui.py` (draws it and should expire it).
- Before fixing, check whether the timeout uses a clock that `purple_tui/canvas/harness.py` doesn't advance. If so, this could be a harness artifact rather than a real bug.
- Test in `tests/canvas/test_pack_arrivals.py`.

**Confidence:** Medium. Clear screenshot, one scenario. Confirming it on a real or non-harness clock would raise it.

### 5. [low] [studio] Download page lists a Purple's-voice word under "words in your voice"

**What happens:**
- The parent recorded their own voice only for "abuela". For "niño" they kept Purple's voice.
- The Download summary shows "2 words in your voice" with 🎤 "abuela" and 🎤 "nino".
- The pack contains `content/voice/nino.wav`, apparently Purple's voice rendered to a file.
- The Download badge reads 4 for 2 words.

**Expected:** Only recordings the parent made are listed as "in your voice". This should match Studio's own 🔊 PURPLE'S VOICE / 🎤 YOUR VOICE labels.

**Repro:**
1. In Words, add abuela and record your voice.
2. Add niño and keep Purple's voice. (The parent had Purple say "niño". Whether they pressed "Say it" isn't recorded; see issue 1.)
3. Open the Download page.
4. See "2 words in your voice" listing abuela and nino with mic icons.

**Seen in:** 1-two-languages.

**Screenshots:** /tmp/purple-e2e-ai/sweep-20261112-112540/shots/1-two-languages-studio-014.png

**Where to look (guess):**
- `studio/src/ui/download.ts`: the summary may count any `voice/*.wav` as a recording instead of checking the word's sound source.
- `studio/src/state.ts`: the badge count.

**Confidence:** Medium-high. The screenshot shows the label clearly. Repeating the steps with and without pressing "Say it" would show what triggers it.

### 6. [low] [studio] Download summary reportedly lists Kazoo, which was never added

**What happens:**
- The parent opened the Kazoo editor but didn't click Add or move a slider. The editor said "Not in your Purple Pack".
- The parent reports the Download page then listed "1 instrument: Kazoo".
- The pack has no instrument file, and Kazoo never appeared on Purple.
- The Download badge read 3, which matches 2 letters plus 1 color, not an instrument.

**Expected:** The Download summary lists exactly what is in the pack.

**Repro:**
1. Open Instruments.
2. Click Kazoo. Don't click Add or move a slider.
3. Add letters and a screen color.
4. Go to Download and read the summary.
5. Compare it with the files in the downloaded .purplepack.

**Seen in:** 1-music-family.

**Screenshots:**
- /tmp/purple-e2e-ai/sweep-20261112-112540/shots/1-music-family-studio-006.png (Kazoo editor with preset slider values and a "Back to a plain Accordion" link)
- /tmp/purple-e2e-ai/sweep-20261112-112540/shots/1-music-family-studio-007.png (badge 3)

**Where to look (guess):**
- The editor offers "Back to a plain Accordion", so opening Kazoo may create an edited-instrument state. The summary in `studio/src/ui/download.ts` may read that state, while the pack builder and badge (`studio/src/pack.ts`, `studio/src/state.ts`) don't.
- `studio/src/ui/instrument.ts` is the editor.

**Confidence:** Low. No screenshot of the Download page; this rests on the tester's quote. A screenshot of the summary after these steps would confirm or kill it.

### 7. [low] [studio] Picking "Your voice" shows a green "In your Purple Pack" box before anything is recorded

**What happens:** After picking "Your voice" on a word, Studio shows a green "In your Purple Pack" confirmation even though nothing has been recorded.

**Expected:** No success state until a recording exists. A prompt to record would fit better.

**Repro:**
1. In Studio, add a word.
2. Pick "Your voice".
3. Don't record anything, and look at the status box.

**Seen in:** 1-returning-parent.

**Screenshots:** none.

**Where to look (guess):**
- `studio/src/ui/words.ts` and `studio/src/ui/record.ts`.
- The banner seems to reflect "the word is in the pack", not "this field is saved". Issue 1 shows the same banner while say text is unsaved, so fixing what the banner means may fix both.

**Confidence:** Medium. No screenshot. A screenshot right after picking "Your voice" would raise it.

### 8. [low] [studio] Renaming a picture doesn't update its card under "Yours" or the page heading

**What happens:**
- The parent renamed "Backyard" to "Biscuit's Yard" and tabbed out.
- The rename did save:
  - the URL changed to `#pictures/biscuits-yard`,
  - the pack's files are named biscuits-yard,
  - Purple's Art Open list shows the new name.
- But the card under "Yours" (and its "Choose Backyard" label) still says "Backyard". The tester says the heading does too.
- 1-thorough-tour's parent saw the same thing until they left the page and came back.

**Expected:** The card, its label and the heading show the new name right away.

**Repro:**
1. Open Pictures and upload backyard.png.
2. Change Name to "Biscuit's Yard" and Tab out of the field.
3. Look at the page heading and at the card under "Yours".

**Seen in:** 2-thorough-tour, 1-thorough-tour.

**Screenshots:** /tmp/purple-e2e-ai/sweep-20261112-112540/shots/2-thorough-tour-studio-005.png

**Where to look (guess):** `studio/src/ui/pictures.ts`. The rename handler likely updates state and the URL but doesn't re-render the "Yours" list or the heading.

**Confidence:** High. Two scenarios and a screenshot.

### 9. [low] [studio] Meaning typed before Done is lost on page reload

**What happens:**
- The parent added "taco", typed a Meaning, and reloaded without clicking Done.
- "taco" survived the reload, but its Meaning was empty.
- The downloaded pack has no meaning for taco, and there was no warning before the reload.

**Expected:** The draft survives a reload like the word does, or the page warns before unloading.

**Repro:**
1. In Studio, go to Words and add `taco`.
2. Type any text in Meaning.
3. Reload the page without clicking Done.
4. Open taco. Meaning is empty.

**Seen in:** 1-breaker.

**Screenshots:** none.

**Where to look (guess):** `studio/src/ui/words.ts` (when field edits are committed) and `studio/src/saved.ts` (what is persisted).

**Confidence:** Medium. One scenario, no screenshot. This is easy to confirm in a browser test.

### 10. [low] [studio] Rename errors appear under the "new word" box, not in the word being edited

**What happens:**
- Renaming zebra to `nino` is correctly refused. So is a 200+ character name.
- But the error ("'nino' is already in the list.") shows under the "Type a new word / Add new word" box.
- It looks like an add failed, not the rename.

**Expected:** The error appears in zebra's editor, next to its Word field.

**Repro:**
1. In Studio, go to Words with nino and zebra.
2. Open zebra and change the Word field to `nino`.
3. See the error appear under the new-word box.

**Seen in:** 1-breaker.

**Screenshots:** /tmp/purple-e2e-ai/sweep-20261112-112540/shots/1-breaker-studio-012.png

**Where to look (guess):** `studio/src/ui/words.ts`. Rename validation probably reuses the add-word error slot.

**Confidence:** High. The screenshot shows the error in the wrong place.

### 11. [low] [studio] "Needs a Purple Computer downloaded on October 29, 2026 or later" shows even for a plain word and photo

**What happens:** Every download showed "uses something new, so it needs a Purple Computer downloaded on October 29, 2026 or later". That includes:
- one word plus one photo (1-returning-parent),
- one picture plus one emoji word (1-toddler-masher).

Every scenario where the date was reported had a picture or photo in the pack. Packs with meanings got October 22, and letter sounds got November 11.

**Expected:** The warning appears only when the pack really uses something newer than what most Purples have.

**Repro:**
1. Open Studio and add the word "cookie" with a photo (backyard.png).
2. Download the Purple Pack.
3. Read the message under the button.

**Seen in:**
- 1-returning-parent (every download)
- 1-toddler-masher
- 1-grandparent
- 1-thorough-tour (three dates)

**Screenshots:** /tmp/purple-e2e-ai/sweep-20261112-112540/shots/1-grandparent-studio-008.png (the wording; that pack also had a letter recording).

**Where to look (guess):** The minimum-version check in `studio/sdk/src/pack.ts` / `studio/src/pack.ts`, and the message in `studio/src/ui/download.ts`. Find which pack feature maps to October 29.

**Confidence:** Low. Photos may genuinely need the October 29 Purple. If they do, this is a wording problem (see Decide), not a bug. Reading the version mapping settles it.

## Decide these

- **Wording after download** (1-grandparent, 1-thorough-tour, 1-returning-parent). Parents found the grey text long and jargon-heavy:
  - "downloaded" means both the pack and Purple itself,
  - "sounds that play after their letter" and "only while Letters says names" aren't explained,
  - several dates appear,
  - it doesn't say where the file was saved,
  - step 1 still reads "Download your Purple Pack" after it's done.

  Options:
  - (a) A short "Saved to your Downloads. Next: copy it to a USB drive" message, with version details behind a "Will my Purple run this?" link.
  - (b) Show one date only (the latest needed).
  - (c) Mark step 1 done after downloading.
- **Accents in Studio's word names** (1-two-languages). Issue 2 fixes matching. Separately, decide whether Studio should show and store "niño" as typed and fold only when matching, or keep folding up front.
- **Instruments from your own recording** (1-music-family). The Instruments editor only has synth presets with sliders, while Letters supports recording. Options: add record/upload for instruments, or add a hint that instruments are synth-only.
- **Photo size in Play** (1-phone-parent and 2-thorough-tour kids). Both called the word's photo a "small generic picture icon" or "tiny landscape icon", while the built-in `cat` showed a big picture. Screenshot 1-two-languages-purple-kid-009.png shows pack photos at emoji size. Options: show pack photos bigger, or keep them emoji-sized.
- **Preview focus states** (1-room-maker, 1-thorough-tour, 1-two-languages). Parents saw the preview "turn grey" or "blue/dim" after typing and couldn't tell whether it was broken. Options: clearer "click to type" / "paused" labels, or no dimming.
- **Picture Keyboard joined the pack without "Add to my Purple Pack"** (1-room-maker). Editing a key added the room automatically. Decide whether editing should add the room, and whether to say so when it does.
- **Download summary layout** (1-returning-parent). A word with a recording is listed twice, under "words in your voice" and "words" (visible in 1-two-languages-studio-014.png). Every download uses the same file name, so a "(1)" copy is possible (not verified). Decide whether to merge the rows and whether to vary the name.
- **Finding where to record a name** (1-grandparent). The parent had trouble working out that Words is where a voice saying a name goes, and the record button there is an unlabelled microphone icon.
- **Purple-side info gaps:**
  - Purple Packs in the parent menu lists packs by name only, with no contents (1-grandparent).
  - A Spanish-speaking parent found no language setting in the grown-up menu (1-two-languages).

## Already known

- None of this sweep's findings match an open (not struck-through) entry in docs/AI_UX_BUGS.md.
- The struck "No confirmation after downloading" entry (marked NOT A BUG) is related but different. This sweep confirms the message appears; the complaint is its wording (see Decide).

## Coverage

**Exercised well:**
- Studio Words: adding, accent folding, refusing emoji, blank, long and duplicate names, rename validation, meanings, HTML and symbols as plain text, Purple's voice vs your voice.
- Play-room lookups on Purple: the plain word, `who is …`, sentences with pack words, `NINO * 3`.
- Adding a pack from USB and seeing it in the parent menu's Purple Packs.
- The picture quiz room played to the end, and Picture Keyboard keys with a photo and emoji.
- The world starter renamed "Star Hunt": Studio's code error message (THINGZ) and collecting one star on Purple.
- Screen color (Forest) carried to Purple, and pictures appearing in Art's Open list.

**Never reached or never verified:**
- **Any sound on Purple.** Every kid tester was deaf. Not checked:
  - recorded word voices,
  - Purple's-voice say text,
  - letter recordings (G/M),
  - the Star Hunt gong,
  - Picture Keyboard's spoken "Biscuit".
  
  The next sweep needs an audio-capable check, such as the harness logging which clip played.
- **Starter rooms other than the quiz and the world:** the story with choices, the memory game, and the other examples in `studio/src/examples/` (beats, garden, snake).
- **An instrument or game room landing on Purple.** No pack carried an instrument.
- **Reopening a downloaded pack in Studio after edits.** 1-returning-parent never confirmed that the recording, meaning, words-on-picture or fill-screen came back.
- **Picture "fill the screen" and words-on-picture on Purple.** 1-returning-parent's kid couldn't find the backyard picture anywhere. The judge didn't keep that finding, so it's worth a direct look.
- **Studio:** deleting items, Clear everything, the browser back button, downloading twice, and the Picture Keyboard room's notes and preview.
- **Purple:**
  - the code panel (Esc+Space / "write code"; the coder kid couldn't get in from Star Hunt),
  - Save/Open, Time Travel,
  - Kid Profiles and Help,
  - removing a pack,
  - Enter-hold looping in Music,
  - fast mashing.
- **Accented and non-Latin words** in Music's Letters spelling and in Blocks.
