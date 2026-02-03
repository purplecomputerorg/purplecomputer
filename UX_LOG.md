# UX Change Log

Brief descriptions of user experience changes, newest first.

---

## 2026-02

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
