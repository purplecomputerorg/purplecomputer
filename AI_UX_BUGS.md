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

### [MEDIUM] Division by zero gives no explanation — just echoes the expression

When a child types "1 / 0" (or "1 ÷ 0"), the app shows "→ 1  ÷  0 " with no answer, no error message, and no kid-friendly explanation. The hint bar then says "Enter to try again: 1 ÷ 0", which implies there is a valid answer to try for, but division by zero is mathematically undefined. A child (or parent) gets no feedback about why it didn't work.

### [LOW] Place value display shows rendering artefacts (▆▆) in empty rows for 10000

After computing 9999 + 1 = 10000, the place value breakdown shows stray block characters (▆▆) in the 'thousands' row even though its value should be 0 (empty). Other rows like hundreds, tens, ones appear correctly blank. This is a visual rendering artefact.

**Repro:**
1. Switch to Play room
2. Type '9999 + 1'
3. Press Enter
4. Observe the place value display — the 'thousands' row shows '▆▆' artefacts (rendering noise) instead of being empty

### [MEDIUM] Exclamation mark (!) is silently stripped from input



### [LOW] Exclamation mark (!) is silently stripped from input — shown as @#$% instead of !@#$%

When a user types "!@#$%", the exclamation mark is silently dropped. The input bar shows "@#$%" and the result shows "→ @  #  $  % ". The "!" character is consumed without any feedback. This could confuse a child who typed an exclamation mark as part of their input.

**Repro:**
1. Switch to Play room
2. Type '!@#$%'
3. Press Enter
4. Observe: input bar shows '@#$%' (! missing), result shows '→ @  #  $  % ' (! missing)

### [MEDIUM] HTML entity &amp; shown unescaped in hint bar — should display as '&'



### [LOW] HTML entity '&amp;' shown literally in 'Try:' hint bar instead of '&'

The hint/suggestion bar at the bottom of the Play room shows: 'Try: repeat 3: 2 green &amp; 3 periwinkle'. The '&amp;' is a raw HTML entity that was not unescaped before display. It should render as '&'. This is a text rendering/escaping bug.

**Repro:**
1. Switch to Play room
2. Type various expressions
3. Observe the hint bar 'Try' suggestion row
4. The text reads: 'repeat 3: 2 green &amp; 3 periwinkle' where &amp; is shown as a literal HTML entity instead of '&'

### [CONFUSION: MINOR] Pressing Enter on empty input silently re-runs the last expression

**Tried:** Pressing Enter with an empty input field to see what happens

**What happened:** The app re-ran the previous expression ("2 + 3 × 4 = 14") and populated the input with "2 + 3 × 4" again, with no visual indication that it was repeating. There was no "please type something first" prompt.

**Expected:** 

### [CONFUSION: MINOR] Pressing Enter on empty input silently re-runs the last expression — no guidance for kids

**Tried:** Pressing Enter with an empty input field to see what happens

**What happened:** The app re-ran the previous expression ("2 + 3 × 4 = 14") and populated the input with "2 + 3 × 4" again, with no visual indication that it was repeating. There was no "please type something first" prompt.

**Expected:** Either nothing should happen, or a friendly prompt like "Type a number or word to explore!" would guide a child to enter something new.

### [CONFUSION: MINOR] Special characters echoed back with no explanation — no "I don't understand" message

**Tried:** Typing special characters (!@#$%) to see how the app handles non-math, non-word input

**What happened:** The app just echoed "@  #  $  %" back verbatim with no answer, no error, and no explanation. The hint bar said "Enter to try again: !@#$%", implying there's something to retry — but there's no meaningful output to retry for.

**Expected:** A friendly message like "Hmm, I don't know that one! Try a number like 5 + 3 or a word like 'cat'." A 5-year-old who accidentally types symbols would get no guidance.

## 2026-04-18 09:19 (hunt, claude-haiku-4-5-20251001)

### [CONFUSION: MINOR] NaN input parsed as individual characters instead of special value

**Tried:** Typed 'NaN' and pressed Enter

**What happened:** 

**Expected:** 

### [CONFUSION: MINOR] NaN input parsed as individual characters instead of special value

**Tried:** Typed 'NaN' and pressed Enter to see if it recognizes the JavaScript NaN value

**What happened:** The system output "N  a  N" - parsing each letter separately

**Expected:** Either recognizing NaN as a special mathematical value, or showing an error/message explaining it's not a valid command

### [CONFUSION: MINOR] Scientific notation (1e999) parsed as individual characters instead of expression

**Tried:** Typed '1e999' and pressed Enter to see if it evaluates to Infinity

**What happened:** The system output "1  e  9  9  9" - parsing each character separately instead of evaluating scientific notation

**Expected:** Either evaluating the expression as a number (should show Infinity), or showing an error message explaining the notation isn't supported

