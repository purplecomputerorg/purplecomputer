# UX Change Log

Brief descriptions of user experience changes, newest first.

---

- Explore: "green potato peanut" now shows potato emoji on green bg + "peanut" letters in green (colors + emojis + text mix together)

- Explore mode: answers show a 🔊 speaker icon when TTS is active (triggered by "say", "talk", or "!")
- Explore mode: autocomplete now accepted with right arrow instead of space. Space always types a space, so you can type partial words without forced completion.
- Explore mode: typing a complete word (like "apple") shows its emoji/color in the hint area as confirmation, instead of the hint disappearing.
- Explore mode: numbers display as a colored abacus with place-value rows (ones on top, bigger places below), spaced dots, and a different color per row
- Explore mode: colors auto-mix with emojis, other colors, and text without needing + ("red apple" → 🍎 on red, "red blue" → mixed purple, "tavi red" → mixed letter blocks)
- Explore mode: + operator still works the same way but is now optional for mixing
- Explore mode: only letters and numbers become colored blocks (symbols like + stay as plain text)
- Explore mode: unrecognized text now shows colored blocks with letters visible on top (instead of blank colored blocks)
- Explore mode: number dot visualization uses larger dots (⬤ instead of •); bare number input (e.g. "67") shows only dots without repeating the number
- Code mode: cursor is now a blinking insertion point between blocks (like a text cursor); Enter inserts visual line breaks; backspace deletes the block before the cursor
- Doodle mode: gutter is now a purple checkerboard pattern instead of solid black, visually distinct but not jarring
- Code mode: consecutive identical blocks auto-collapse into one block with "xN" count badge
- Code mode: up/down arrows now adjust block count (when count > 1) or gap timing (when count is 1)
- Code mode: REPEAT blocks at end of a line show repeat count in the gutter
- Recordings auto-collapse consecutive identical actions into counted blocks

## 2026-03

- **Doodle paint: hold letter then arrow paints continuously**: Holding a character key and then pressing an arrow now paints that character's color while moving, same as holding arrow first then letter
- **Kid-proof power button**: Tap shows sleep screen (cute, not scary, any key wakes); hold 3s shows "Bye!" and shuts down (phone-like); logind set to ignore so TUI controls all power UX
- **Lid close delayed shutdown**: Lid close now turns screen off immediately but waits 2 minutes before shutting down (was 5 seconds); opening lid cancels shutdown; prevents accidental shutdowns when kid briefly closes lid
- **Code mode: Play clears state first**: Pressing Play in Code mode now clears the target mode's canvas/colors before replaying, so playback reproduces the recording from a clean slate
- **Code mode: bright gutter blocks**: Mode icons in the left gutter are now solid bright colored blocks instead of dim text icons
- **Code mode: Up/Down navigates lines**: Arrow keys now jump between lines (like a text editor) instead of adjusting timing
- **Code mode: timing adjust moved to Tab menu**: Gap timing, repeat count, and target cycling are now in the Tab menu under "Adjust"
- **USB update restart prompt**: When a USB update is applied, a simple modal appears saying "New update ready! Press Enter to restart."
- **Removed F9 theme toggle**: Dark mode is now always active; F9 key and theme badge removed from the function bar
- **Code Mode v2: F5 recording**: F5 starts intentional cross-mode recording (replaces always-on capture); press F5 again to stop; press F5 a third time to play back; blinking ⏺ indicator in title bar while recording, ▶ while playing
- **Code Mode v2: Tab menu**: Tab opens a vertical menu modal in Code mode with Record, Insert, and Program sections; "Record in..." starts recording in a specific mode/sub-mode; replaces Enter command mode
- **Code Mode v2: multi-line blocks**: Blocks display across multiple lines with mode icons (♫ 🔤 ✎ 🖌 🔍) in a left gutter; MODE_SWITCH blocks start new lines; long sections wrap with indented continuation
- **Code Mode v2: Enter inserts ↵**: Enter key now inserts a ↵ control block (useful in Explore and Doodle) instead of entering command mode
- **Code Mode v2: repeat max 99**: Repeat block maximum increased from 9 to 99
- **Play mode Space**: Space now plays the last F5 recording instead of heuristic-based replay
- **Code Mode (F4)**: Replaced turtle-graphics Build mode with cross-mode visual programming; automatically records Play and Doodle actions as colored blocks with timing gaps; Space plays the program back live in the real mode; up/down adjusts timing between blocks; 9 save slots (hold number to save, tap to load)

---

## 2026-02

- **Passwordless system**: Removed default password; system auto-logs in with no password prompt, passwordless sudo for all commands
- **Play mode numbers speak in Letters mode**: Number keys (0-9) now say their name aloud in Letters sub-mode, just like letter keys do
- **Deterministic TTS**: Speech synthesis now produces identical output for identical input; single letters use phonetic pronunciation (A -> "ay"); short utterances padded for prosody stability; WAV output trimmed and normalized; aggressive caching avoids re-synthesis; common words pre-generated at startup
- **Play mode word recognition**: In Letters mode, if typed letters spell a known word (cat, dog, sun, etc.), the word is spoken aloud after replay finishes
- **Play mode sub-modes**: Tab switches between Music (instrument sounds) and Letters (speaks letter names aloud via TTS); header indicator shows current sub-mode; sessions record which sub-mode each key was pressed in, so replay preserves the mix
- **Play mode replay**: Press space to replay your recent key sequence with original timing; sessions auto-reset after 30 seconds of inactivity; pressing keys during replay starts a new session
- **Sticky shift replaces double-tap shift**: Removed double-tap character shift (caused accidental capitals). Shift key tap activates sticky shift for one character. Double-tap Shift toggles caps lock. Caps Lock key remapped to Shift. Added shift indicator (⇧) in title bar.
- **Live boot default**: USB now boots directly into Purple Computer with no installation needed; internal disk is untouched; "Install Purple Computer" available as GRUB menu option
- **Demo: smart camera tracking**: Camera now uses dominant-region detection (top vs bottom half) instead of centroid averaging, so it correctly bounces between input area and rendered results; faster response (0.5s vs 2s intervals)
- **Demo: closing screen zoom**: "This is Purple Computer" types zoomed in, then zooms out for "Coming soon" line
- **Demo: doodle play-mode text shifted right**: "Now let's go to Play mode" text shifted right by 1 cell; no zoom-out transition before play mode
- **Demo: auto-pan via OpenCV**: Camera automatically follows cursor activity during zoomed-in periods using frame differencing, replacing hardcoded pan coordinates
- **Demo: smooth zoom transitions + camera panning**: Zoom transitions now animate smoothly per-frame (smoothstep easing) instead of jumping to a midpoint crop; camera pans follow text as it flows during typing via new ZoomTarget action
- **Demo: dynamic zoom**: Demo scripts can now include ZoomIn/ZoomOut markers; post-processing applies smooth zoom effects for text readability
- **Demo: heart segment text**: Heart drawing now clears the canvas first, then after drawing adds centered text: "This is Purple Computer." and "Coming soon to your old laptop!"
- **Demo: play mode intro text**: After the palm tree drawing completes, text appears at bottom right: "Now let's go to Play mode / Play with music and color"
- **Demo: expanded explore segment**: Demo now showcases emoji math, color mixing, speech, and a welcome message instead of a short 3-line greeting
- **Demo: doodle intro text**: Doodle segment now types "This is Doodle mode. Write and paint!" with color swatches before drawing the palm tree
- **Demo: play mode glissando**: Smiley face builds faster (quicker eyes/nose), then a rapid back-and-forth over the mouth creates a glissando finale
- **Voice clip generation: scans composition segments**: generate_voice_clips.py now extracts phrases from demo.json segments (not just default_script.py); supports --variants N to generate multiple audition copies
- **Color words in free text**: Typing "purple truck" now shows a purple color swatch alongside the truck emoji; previously color words were ignored without a `+` operator
- **Vibrant color mixing**: Red + blue now produces a vibrant purple instead of a muddy dark one; switched from Kubelka-Munk K/S to Beer-Lambert spectral mixing
- **Composable demo segments**: demos can now be composed from named segments via `demo.json`; `--save NAME` on play-ai and install-doodle-demo writes segments and auto-builds the composition; per-segment speed control via `SetSpeed` action
- **Doodle AI: draw_technique replaces shape examples**: planner now generates per-component `draw_technique` guidance instead of relying on 11 hardcoded shape examples; execution prompt condensed from ~160 lines to ~50 lines of 3 core techniques (horizontal fills, diagonal chains, layered depth)
- **Doodle AI: human feedback option**: press `f` during judging (triage or per-component) to give free-text feedback that feeds into the next iteration's drawing prompt
- **Doodle AI: single context view per component**: per-component judging now shows only the full canvas with red highlight (no separate zoomed crop), reducing feh dismissals from two to one
- **Doodle AI: better curvature for organic shapes**: new `shape_profile` field in composition describes curvature with y-coordinates; execution prompt now has an "arched body" example; both plan and component-library sections pass shape profiles to the drawing AI
- **Doodle AI: quit stops entire training loop**: pressing `q` during human judging now exits the full training loop, not just the current round
- **Doodle AI: full-image context in component judging**: per-component judging shows the full canvas with the component region highlighted (red rectangle) for spatial context
- **Doodle AI: auto-adjust bounds on disconnection**: after rendering a composite, coherence check detects disconnected components and automatically adjusts bounds
- **Doodle AI: smarter human judging**: auto-skips identical components, allows quitting mid-session with `q`, shows summary of reviewed/skipped/remaining counts
- **Doodle AI: human judging mode**: `--human` flag replaces AI judge with interactive side-by-side comparison, letting a human pick the better component version
- **Doodle AI: multi-candidate iteration with focused mutation**: AI now generates multiple candidates per iteration (mutation, informed regen, fresh regen) to escape local maxima; judge provides per-criterion scores and specific improvement targets; contradictory learnings are automatically resolved
- **Doodle AI: structural connection accuracy**: AI now plans where parts attach to each other, draws connection points correctly (e.g., fronds at top of trunk), and judge penalizes anatomically wrong connections
- **Demo playback: fix right-side artifacts** by clamping cursor coordinates to canvas bounds in demo script generation
- **Doodle AI: entertaining draw order**: AI now draws the subject first with per-element color mixing (fun to watch), minimizes large monotone background fills (boring to watch), and judge penalizes flat backgrounds
- **Doodle AI: better shape judging and refinement**: AI judge now evaluates shape quality (organic curves vs boxy rectangles), refinement escalates from targeted tweaks to full restructuring after repeated losses, and color mixing recipes are passed through to the drawing AI

---

## 2026-01

- **Display settings in parent menu**: Parents can now adjust screen brightness and contrast via Parent Menu > Adjust Display; settings persist across sessions
- **Visible gutter border**: Canvas gutter now has a distinct color (black in dark mode, white in light mode) so users can see the non-drawable border area
- **ESC toggles mode picker**: Pressing ESC while mode picker is open now closes it instead of reopening
- **Simplified mode picker**: Mode picker now shows 3 options (Explore, Play, Doodle) instead of 4; Write/Paint are now tools within Doodle, not separate modes
- **Mode picker hint simplified**: Replaced text instructions with just arrow symbols (◀ ▶) for pre-readers
- **F-keys work in mode picker**: Pressing F1/F2/F3 while mode picker is open dismisses it and switches directly
- **Doodle tool overlay**: Non-blocking overlay appears briefly when entering Doodle, showing current tool and "Tab to switch"; dismisses on first action or after 1.2s
- **Doodle tool indicator**: Header now shows both tools (Write and Paint) with current tool highlighted; Tab hint between them

---

## 2025-01

- **Escape tap mode picker**: Tapping Escape opens a mode picker modal; Esc badge added to mode indicator bar
- **Tab toggles paint/write**: Removed space-space toggle, now only Tab switches between paint and write modes in Doodle (avoids accidental triggers while drawing)
- **Space-space toggle**: Double-tap space toggles write/paint both ways, requires consecutive spaces
- **Mode switch dismisses prompt**: Switching modes while "keep drawing" prompt is showing dismisses it and switches normally
- **Color mixing fix**: Similar colors no longer produce brighter results when mixed
- **Demo hides mouse**: Demo recordings no longer show the mouse cursor
- **Legend 3 shades**: Color legend shows light/medium/dark gradient per row
- **Cursor thick sides**: Paint cursor uses heavy lines for sides, light corners
- **Legend updates**: Improved color legend visibility in paint mode
- **Paint mode contrast/cursor/legend**: Better cursor visibility and contrast in paint mode
- **Add spaces to operators**: Explore mode adds spaces around operators when inserting words
- **Caps fixes and directional typing**: Fixed caps behavior and directional typing in paint mode
- **Double tap shift timing**: Only trigger shift on double-tap after a pause or space
- **Paint colors don't blend with bg**: Paint strokes use pure colors, not blended with background
- **Double tap in paint mode**: Double-tap no longer capitalizes in paint mode
- **Arrow held behavior**: When an arrow is held, don't auto-advance in other direction when painting
- **Rename modes**: Renamed modes for clarity (Play, Explore, Paint)
- **Add gutter**: Added gutter around canvas so cursor ring can extend to edges
