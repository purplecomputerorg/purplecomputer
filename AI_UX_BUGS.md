# AI UX Test Bugs

Bugs discovered by automated AI UX testing (`just ux`). Mark fixed bugs with ~~strikethrough~~ or delete them.

## 2026-03-31 11:20 (coder, claude-opus-4-6)

### ~~[MEDIUM] Tab autocomplete for color replaces entire input instead of appending~~ FIXED

When typing "co" and pressing Tab, it autocompletes to "color" correctly. Then it shows color options (red, green, blue, etc.). Pressing Tab again to select "red" replaces the entire input with just "red " instead of "color red ". The user expects the completed input to be "color red" but gets just "red".

**Repro:**
1. Open Art room
2. Open code panel (toggle_code_panel)
3. Type 'co'
4. Press Tab to autocomplete to 'color'
5. Press Tab again to select 'red' from the color suggestions
6. Observe that the input now shows 'red ' instead of 'color red '

### [LOW] Music room shows "Hold Space: close code" when code panel is not open

In the Music room, the bottom right shows "Hold Space: close code" even though the code panel is not currently open. It should say "Hold Space: write code!" or similar to indicate the panel can be opened, not closed. This is confusing because the code panel is not visible.

**Repro:**
1. Open Art room and open code panel
2. Close code panel
3. Switch to Music room
4. Observe bottom right corner shows 'Hold Space: close code' even though code panel is not open
