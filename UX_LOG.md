# UX Change Log

Brief descriptions of user experience changes, newest first.

- Art mode: toggling caps mode no longer strips background colors from typed text (row tints and paint colors now preserved)
- Play mode: fixed continuation lines being indented 1 cell too far when colored text blocks wrap across multiple lines
- Caps Lock key now toggles caps mode on a single press (previously required double-tap like Shift)
- Room picker and install confirmation dialog: up/down arrows now work in addition to left/right for navigation
- Music room: grid key labels, note names, and percussion names now respect caps mode (show uppercase when caps lock is on)
- Power button: hold detection moved out of Textual into asyncio for reliability across hardware. Pressing power button during parent terminal shell now triggers system shutdown via logind instead of crashing.
- Code mode (F4): renamed from "Command" to "Code" so parents immediately see the value (coding for kids) and the room lineup reads Play, Music, Art, Code
- Code mode: "Watch me!" replaces F5 recording. Empty canvas shows "Watch me!" prompt, Enter opens room picker, kid plays in chosen room, F4 returns with captured blocks. Also available via Tab menu. F5 key removed entirely.
- "Adjust Display" menu item hidden on hardware where xrandr brightness/contrast controls don't work (e.g. Surface Laptop 2)
- Rooms renamed: Explore is now Play, Play is now Music, Doodle is now Art
- Music room: Space with no F5 recording replays recent key presses (last 10 seconds or since last pause)
- Music room: F5 recording and playback can now happen simultaneously (overdub, play over yourself)
- F5 badge added to bottom menu bar with keyboard icon
- Recording indicator changed from generic record symbol to "Capturing keys" text with better spacing
- All recording-related text clarified to say "key presses" (toasts, hints) to avoid confusion with voice recording
- Boot splash: solid purple screen with "Starting up..." message during boot, using VT escape codes on tty1 (console output redirected to tty2). Replaces Plymouth, which was unreliable across hardware.
- Music room: Enter now changes instrument in Letters mode too (previously only worked in Music mode).
- Play room: number words (one, two, three) and comma-separated lists now work. "one, two, three dinos" shows a dino abacus. Multiplication with emojis shows grouping ("2 x 3 cats" shows 3 groups of 2 cats).
- Play room: type "..." to continue patterns. Number sequences (5 4 3 ...), emoji pyramids (5 cats ...), ranges (2 4 6 ... 20), and growing sequences (cats ... 5) all work.
- Play room: Enter on empty input recalls last command into the input field (instead of replaying speech). Hint below input shows "Enter to recall: ..." after first command.
- Play room: colors now act as adjectives, modifying the next item. "red apple green banana" shows a red apple and green banana instead of mixing all colors together.
- Music room: note/percussion labels now properly centered in cells. Added "Enter: change instrument" hint at the bottom.
- Recording: F5 now always starts/stops recording (no more F5 playback). New recording overwrites previous. Space in Music room plays back the recording.
- Music room: note/percussion labels now show with ♪ on either side (e.g. "♪ G ♪") near the upper-right of the cell, in a muted color to avoid confusion with the main key letter
- Code mode (F4): renamed from "Build" to "Code" to clarify it's coding; icon changed to console; gutter icons now match room title bar icons (Nerd Font); Tab menu "Mode..." replaced with "Room..." showing 3 rooms (Music, Art, Play) with default sub-modes
- Art: default mode changed from Write to Paint; Paint now appears on left side of Tab header
- Code mode: MODE_SWITCH blocks now show room icon (same as title bar); non-default sub-modes show a hint suffix; cycling targets now cycles rooms instead of all 5 sub-modes
- Code mode: direct coding UX, auto-inserts default mode on empty canvas, Up/Down inline adjusts adjustable blocks (MODE_SWITCH/PAUSE/STROKE/REPEAT), Tab menu trimmed to 7 flat items (removed Record/Adjust/Enter), context-sensitive hint bar shows what Up/Down does
- Code mode: Scratch-inspired block redesign with 6 block types (KEY, QUERY, STROKE, PAUSE, REPEAT, MODE_SWITCH); uniform 5-char grid; explicit PAUSE blocks replace invisible timing gaps; no auto-collapse; mode-aware editing (Play uses compose mode for QUERY blocks, Art paint uses STROKE blocks); v1 save format auto-migrated to v2
- Art: text on painted backgrounds now uses black or white for contrast (was always white/dark); grayscale paint backgrounds no longer disappear when typing over them
- Play: narrow emoji (heart, snow, etc.) always get a padding space to prevent visual overlap in terminal
- Play: plus expressions now show + between items (e.g. apple + banana shows 🍎 + 🍌)
- Play: "red clue" and "red + clue" now produce the same inline format with arrow
- Play: unknown words now render as per-letter colored blocks instead of plaintext
- Play: auto-mix results (e.g. "red apple") now show + between items in the input display
- Play: emoji on colored backgrounds now have spaces between them for readability
- Play: long lines now wrap at colored block boundaries with arrow-indented continuation lines, fixing clipped padding on wrapped colored letters
- Play: bare negative numbers (e.g. "-5") now show as colored text blocks instead of a plain "= -5" math result
- Play: color+emoji results (e.g. "blue cat") now display inline on one line when compact enough, instead of separate lines
- Play: replaced ▶ triangle with → arrow throughout (Ask prompt, answer lines, color swatches) for a cleaner look
- Play: keyboard color map (4-row legend) now shows in the bottom right, same as Art paint mode. Updates active row indicator as you type.
- Play: Tab now accepts autocomplete suggestions (in addition to right arrow). Hint shows "→ Tab".

---

- Play: number digits in colored blocks now use the full grayscale gradient (1=white to 0=black) matching Art room, instead of flat gray
- Play: when math typos are auto-corrected (e.g. "=" treated as "+"), a "→" line shows the corrected expression above the answer
- Play: abacus now starts at 11 instead of 10; 10 shows as dots with 5+5 grouping so it's countable
- Play: color adjectives (bright, dark, light, pale, deep, vivid, dull, muted, neon, soft, rich, warm, cool) modify colors, showing base swatch and result (e.g. "bright green", "dark light blue")
- Play: emoji consolidated into single pack file (packs/core-emoji); added ~80 new emoji (shapes, body parts, household items, space, animal sounds); removed common-word synonyms (good/bad/great/sweet) that made text substitution weird; "love" now maps to ❤️ instead of 😍
- Play: color swatch mixing arrow changed from → to ▶ to match the triangle used everywhere else
- Play: default colors updated to Crayola-style values (red, blue, green) so they match what kids expect
- Play: abacus rows now show ones at bottom and largest place value at top, matching standard abacus layout
- Play: "green potato peanut" now shows potato emoji on green bg + "peanut" letters in green (colors + emojis + text mix together)

- Play: both ask and answer lines use ▶ triangle, aligned. Ask is purple, answer is white. 🔊 icon appears before the triangle when TTS is active
- Play room: autocomplete now accepted with right arrow instead of space. Space always types a space, so you can type partial words without forced completion.
- Play room: typing a complete word (like "apple") shows its emoji/color in the hint area as confirmation, instead of the hint disappearing.
- Play room: numbers ≤9 show plain spaced dots; 10 to ~9 billion show a colored abacus (10 colors); beyond that show colored number blocks
- Play room: simple addition shows grouped dots (● ●   ● ● ●); simple multiplication shows repeated groups (● ●   ● ●   ● ●)
- Play room: colors auto-mix with emojis, other colors, and text without needing + ("red apple" → 🍎 on red, "red blue" → mixed purple, "tavi red" → mixed letter blocks)
- Play room: + operator still works the same way but is now optional for mixing
- Play room: only letters and numbers become colored blocks (symbols like + stay as plain text)
- Play room: unrecognized text now shows colored blocks with letters visible on top (instead of blank colored blocks)
- Play room: number dot visualization uses larger dots (⬤ instead of •); bare number input (e.g. "67") shows only dots without repeating the number
- Code mode: cursor is now a blinking insertion point between blocks (like a text cursor); Enter inserts visual line breaks; backspace deletes the block before the cursor
- Art room: gutter is now a purple checkerboard pattern instead of solid black, visually distinct but not jarring
- Code mode: consecutive identical blocks auto-collapse into one block with "xN" count badge
- Code mode: up/down arrows now adjust block count (when count > 1) or gap timing (when count is 1)
- Code mode: REPEAT blocks at end of a line show repeat count in the gutter
- Recordings auto-collapse consecutive identical actions into counted blocks

## 2026-03

- **Dynamic padding in Alacritty**: Enabled `dynamic_padding` so leftover pixels are distributed evenly around the cell grid, centering it with purple padding on all edges
- **Font sizing simplified**: Replaced runtime Alacritty cell probe with hardcoded JetBrainsMono ratio; reduced fill from 80% to 75% for more headroom on small screens
- **Music room: Enter cycles instruments** (Marimba, Steel Drum, Kalimba, Music Box) in Music mode; header shows current instrument name
- **Music room: note name flashes on keypress** in Music mode, dim text appears below key letter for ~1 second then fades (e.g. "G", "F#", "kick")
- **Toast notifications for mode switches**: Music room Tab (Music/Letters), Music room Enter (instrument name), Art room Tab (Paint/Write), and F5 recording start/stop all show a brief toast
- **Install from Parent Menu**: In live boot mode, Parent Menu now shows "Install on this computer" option with a confirmation dialog; GRUB menu is hidden (boots straight to live mode); parents never need to interact with GRUB
- **Art paint: hold letter then arrow paints continuously**: Holding a character key and then pressing an arrow now paints that character's color while moving, same as holding arrow first then letter
- **Kid-proof power button**: Tap shows sleep screen (cute, not scary, any key wakes); hold 3s shows "Bye!" and shuts down (phone-like); logind set to ignore so TUI controls all power UX
- **Lid close delayed shutdown**: Lid close now turns screen off immediately but waits 2 minutes before shutting down (was 5 seconds); opening lid cancels shutdown; prevents accidental shutdowns when kid briefly closes lid
- **Code mode: Play clears state first**: Pressing Play in Code mode now clears the target mode's canvas/colors before replaying, so playback reproduces the recording from a clean slate
- **Code mode: bright gutter blocks**: Mode icons in the left gutter are now solid bright colored blocks instead of dim text icons
- **Code mode: Up/Down navigates lines**: Arrow keys now jump between lines (like a text editor) instead of adjusting timing
- **Code mode: timing adjust moved to Tab menu**: Gap timing, repeat count, and target cycling are now in the Tab menu under "Adjust"
- **USB update restart prompt**: When a USB update is applied, a simple modal appears saying "New update ready! Press Enter to restart."
- **Removed F9 theme toggle**: Dark mode is now always active; F9 key and theme badge removed from the function bar
- **Code Mode v2: F5 recording**: F5 starts intentional cross-mode recording (replaces always-on capture); press F5 again to stop; press F5 a third time to play back; blinking ⏺ indicator in title bar while recording, ▶ while playing
- **Code Mode v2: Tab menu**: Tab opens a vertical menu modal in Code mode with Record, Insert, and Program sections; "Record in..." starts recording in a specific mode/sub-mode; replaces Enter code mode
- **Code Mode v2: multi-line blocks**: Blocks display across multiple lines with mode icons (♫ 🔤 ✎ 🖌 🔍) in a left gutter; MODE_SWITCH blocks start new lines; long sections wrap with indented continuation
- **Code Mode v2: Enter inserts ↵**: Enter key now inserts a ↵ control block (useful in Play and Art) instead of entering code mode
- **Code Mode v2: repeat max 99**: Repeat block maximum increased from 9 to 99
- **Music room Space**: Space now plays the last F5 recording instead of heuristic-based replay
- **Code Mode (F4)**: Replaced turtle-graphics Code mode with cross-mode visual programming; automatically records Music and Art actions as colored blocks with timing gaps; Space plays the program back live in the real mode; up/down adjusts timing between blocks; 9 save slots (hold number to save, tap to load)

---

## 2026-02

- **Passwordless system**: Removed default password; system auto-logs in with no password prompt, passwordless sudo for all commands
- **Music room numbers speak in Letters mode**: Number keys (0-9) now say their name aloud in Letters sub-mode, just like letter keys do
- **Deterministic TTS**: Speech synthesis now produces identical output for identical input; single letters use phonetic pronunciation (A -> "ay"); short utterances padded for prosody stability; WAV output trimmed and normalized; aggressive caching avoids re-synthesis; common words pre-generated at startup
- **Music room word recognition**: In Letters mode, if typed letters spell a known word (cat, dog, sun, etc.), the word is spoken aloud after replay finishes
- **Music room sub-modes**: Tab switches between Music (instrument sounds) and Letters (speaks letter names aloud via TTS); header indicator shows current sub-mode; sessions record which sub-mode each key was pressed in, so replay preserves the mix
- **Music room replay**: Press space to replay your recent key sequence with original timing; sessions auto-reset after 30 seconds of inactivity; pressing keys during replay starts a new session
- **Sticky shift replaces double-tap shift**: Removed double-tap character shift (caused accidental capitals). Shift key tap activates sticky shift for one character. Double-tap Shift toggles caps lock. Caps Lock key remapped to Shift. Added shift indicator (⇧) in title bar.
- **Live boot default**: USB now boots directly into Purple Computer with no installation needed; internal disk is untouched; "Install Purple Computer" available as GRUB menu option
- **Demo: smart camera tracking**: Camera now uses dominant-region detection (top vs bottom half) instead of centroid averaging, so it correctly bounces between input area and rendered results; faster response (0.5s vs 2s intervals)
- **Demo: closing screen zoom**: "This is Purple Computer" types zoomed in, then zooms out for "Coming soon" line
- **Demo: art music-room text shifted right**: "Now let's go to Music room" text shifted right by 1 cell; no zoom-out transition before Music room
- **Demo: auto-pan via OpenCV**: Camera automatically follows cursor activity during zoomed-in periods using frame differencing, replacing hardcoded pan coordinates
- **Demo: smooth zoom transitions + camera panning**: Zoom transitions now animate smoothly per-frame (smoothstep easing) instead of jumping to a midpoint crop; camera pans follow text as it flows during typing via new ZoomTarget action
- **Demo: dynamic zoom**: Demo scripts can now include ZoomIn/ZoomOut markers; post-processing applies smooth zoom effects for text readability
- **Demo: heart segment text**: Heart drawing now clears the canvas first, then after drawing adds centered text: "This is Purple Computer." and "Coming soon to your old laptop!"
- **Demo: Music room intro text**: After the palm tree drawing completes, text appears at bottom right: "Now let's go to Music room / Play with music and color"
- **Demo: expanded play segment**: Demo now showcases emoji math, color mixing, speech, and a welcome message instead of a short 3-line greeting
- **Demo: art intro text**: Art segment now types "This is Art room. Write and paint!" with color swatches before drawing the palm tree
- **Demo: Music room glissando**: Smiley face builds faster (quicker eyes/nose), then a rapid back-and-forth over the mouth creates a glissando finale
- **Voice clip generation: scans composition segments**: generate_voice_clips.py now extracts phrases from demo.json segments (not just default_script.py); supports --variants N to generate multiple audition copies
- **Color words in free text**: Typing "purple truck" now shows a purple color swatch alongside the truck emoji; previously color words were ignored without a `+` operator
- **Vibrant color mixing**: Red + blue now produces a vibrant purple instead of a muddy dark one; switched from Kubelka-Munk K/S to Beer-Lambert spectral mixing
- **Composable demo segments**: demos can now be composed from named segments via `demo.json`; `--save NAME` on play-ai and install-doodle-demo writes segments and auto-builds the composition; per-segment speed control via `SetSpeed` action
- **Art AI: draw_technique replaces shape examples**: planner now generates per-component `draw_technique` guidance instead of relying on 11 hardcoded shape examples; execution prompt condensed from ~160 lines to ~50 lines of 3 core techniques (horizontal fills, diagonal chains, layered depth)
- **Art AI: human feedback option**: press `f` during judging (triage or per-component) to give free-text feedback that feeds into the next iteration's drawing prompt
- **Art AI: single context view per component**: per-component judging now shows only the full canvas with red highlight (no separate zoomed crop), reducing feh dismissals from two to one
- **Art AI: better curvature for organic shapes**: new `shape_profile` field in composition describes curvature with y-coordinates; execution prompt now has an "arched body" example; both plan and component-library sections pass shape profiles to the drawing AI
- **Art AI: quit stops entire training loop**: pressing `q` during human judging now exits the full training loop, not just the current round
- **Art AI: full-image context in component judging**: per-component judging shows the full canvas with the component region highlighted (red rectangle) for spatial context
- **Art AI: auto-adjust bounds on disconnection**: after rendering a composite, coherence check detects disconnected components and automatically adjusts bounds
- **Art AI: smarter human judging**: auto-skips identical components, allows quitting mid-session with `q`, shows summary of reviewed/skipped/remaining counts
- **Art AI: human judging mode**: `--human` flag replaces AI judge with interactive side-by-side comparison, letting a human pick the better component version
- **Art AI: multi-candidate iteration with focused mutation**: AI now generates multiple candidates per iteration (mutation, informed regen, fresh regen) to escape local maxima; judge provides per-criterion scores and specific improvement targets; contradictory learnings are automatically resolved
- **Art AI: structural connection accuracy**: AI now plans where parts attach to each other, draws connection points correctly (e.g., fronds at top of trunk), and judge penalizes anatomically wrong connections
- **Demo playback: fix right-side artifacts** by clamping cursor coordinates to canvas bounds in demo script generation
- **Art AI: entertaining draw order**: AI now draws the subject first with per-element color mixing (fun to watch), minimizes large monotone background fills (boring to watch), and judge penalizes flat backgrounds
- **Art AI: better shape judging and refinement**: AI judge now evaluates shape quality (organic curves vs boxy rectangles), refinement escalates from targeted tweaks to full restructuring after repeated losses, and color mixing recipes are passed through to the drawing AI

---

## 2026-01

- **Display settings in parent menu**: Parents can now adjust screen brightness and contrast via Parent Menu > Adjust Display; settings persist across sessions
- **Visible gutter border**: Canvas gutter now has a distinct color (black in dark mode, white in light mode) so users can see the non-drawable border area
- **ESC toggles mode picker**: Pressing ESC while mode picker is open now closes it instead of reopening
- **Simplified mode picker**: Mode picker now shows 3 options (Play, Music, Art) instead of 4; Write/Paint are now tools within Art, not separate modes
- **Mode picker hint simplified**: Replaced text instructions with just arrow symbols (◀ ▶) for pre-readers
- **F-keys work in mode picker**: Pressing F1/F2/F3 while mode picker is open dismisses it and switches directly
- **Art tool overlay**: Non-blocking overlay appears briefly when entering Art, showing current tool and "Tab to switch"; dismisses on first action or after 1.2s
- **Art tool indicator**: Header now shows both tools (Write and Paint) with current tool highlighted; Tab hint between them

---

## 2025-01

- **Escape tap mode picker**: Tapping Escape opens a mode picker modal; Esc badge added to mode indicator bar
- **Tab toggles paint/write**: Removed space-space toggle, now only Tab switches between paint and write modes in Art (avoids accidental triggers while drawing)
- **Space-space toggle**: Double-tap space toggles write/paint both ways, requires consecutive spaces
- **Mode switch dismisses prompt**: Switching modes while "keep drawing" prompt is showing dismisses it and switches normally
- **Color mixing fix**: Similar colors no longer produce brighter results when mixed
- **Demo hides mouse**: Demo recordings no longer show the mouse cursor
- **Legend 3 shades**: Color legend shows light/medium/dark gradient per row
- **Cursor thick sides**: Paint cursor uses heavy lines for sides, light corners
- **Legend updates**: Improved color legend visibility in paint mode
- **Paint mode contrast/cursor/legend**: Better cursor visibility and contrast in paint mode
- **Add spaces to operators**: Play room adds spaces around operators when inserting words
- **Caps fixes and directional typing**: Fixed caps behavior and directional typing in paint mode
- **Double tap shift timing**: Only trigger shift on double-tap after a pause or space
- **Paint colors don't blend with bg**: Paint strokes use pure colors, not blended with background
- **Double tap in paint mode**: Double-tap no longer capitalizes in paint mode
- **Arrow held behavior**: When an arrow is held, don't auto-advance in other direction when painting
- **Rename modes**: Renamed modes for clarity (Music, Play, Paint)
- **Add gutter**: Added gutter around canvas so cursor ring can extend to edges
