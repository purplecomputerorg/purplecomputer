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
## 2026-04-18 08:37 (hunt, claude-sonnet-4-6)

### [CONFUSION: MINOR] No clear "draw here" affordance for a 5-year-old

**Tried:** Looking at the Art room as a first-time child user to figure out how to start drawing

**What happened:** The canvas is blank and dark. The only hints are text at the bottom: "Press Tab to switch tools. Type to paint." There's a small square/turtle in the top-left corner. The color swatches on the right are very small. No big buttons, no finger/stylus icon, no obvious "tap to draw" prompt.

**Expected:** 

### [CONFUSION: MINOR] "Tab" and "ABC" mode labels are cryptic for kids and parents

**Tried:** Understanding what the two modes "Tab" and "ABC" mean

**What happened:** There are two labels "Tab" and "ABC" visible at the top of the canvas. It's not immediately clear what these are — they look like mode indicators but there's no icon or explanation of what each mode does.

**Expected:** Labels like "Turtle" and "Letter Paint" with icons would be more understandable to a child or parent

## 2026-04-18 08:45 (hunt, claude-sonnet-4-6)

### ~~[MEDIUM] Division by zero gives no explanation — just echoes the expression~~ FIXED (commit a06fe4c)

### [CONFUSION: MINOR] Pressing Enter on empty input silently re-runs the last expression — no guidance for kids

**Tried:** Pressing Enter with an empty input field to see what happens

**What happened:** The app re-ran the previous expression ("2 + 3 × 4 = 14") and populated the input with "2 + 3 × 4" again, with no visual indication that it was repeating. There was no "please type something first" prompt.

**Expected:** Either nothing should happen, or a friendly prompt like "Type a number or word to explore!" would guide a child to enter something new.

