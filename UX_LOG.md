# UX Change Log

Brief descriptions of user experience changes, newest first.

---

## 2026-02

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
