# Blocks: showing where the next block goes

Blocks is one color more often than not (a kid holds one key), drawn small enough to fit the whole floor, and nobody zooms. The cursor has to answer two questions at a glance: **which column am I over**, and **where will the block land**. The cursor is in `purplecomputer/rooms/blocks_room.py`; the camera and painting it draws through are in `blocks_view.py`.

## Rules

1. **Never change a block's color.** Blocks is a color room; a block that looks darker when the cursor moves away teaches the wrong color. Blocks are plain faces with no lines on them: the cursor's marks are its own, never the blocks'.
2. **The cursor is its column, not its landing spot.** A landing spot jumps up and down as the cursor crosses towers of different heights; the column only ever moves one cell across the floor. So the part that draws over everything sits on the top level, over the column, and never jumps.
3. **Nothing is see-through, and nothing is cut open.** The line down the column and the landing spot sit in the scene, so nearer blocks hide them like any block. An arrowhead where the line goes behind them says the rest is back there; Tab turns the build to see it.
4. **One more line costs more than it explains.** A wall of one color reads better as one wall, and with no lines on the blocks, the cursor's are the only lines on screen. Seams between blocks, a line from each floating block down to its shadow, and a band across the cursor row's blocks were all drawn once; the build looked cleaner without them, and paints faster: a column's touching blocks of one color are one tall box (`shape` in `blocks_view.py`).
5. **The cursor never looks like a laid block.** A laid block fills its cell; the cursor's block is about half that size.
6. **The edge is the edge.** The walls and the floor stop the cursor; nothing wraps around to the far side. The one wrap is the ceiling's: a letter on a full tower starts the column to its right, at the chosen height, as typing wraps to a new line. A top block the cursor was put on with Shift still takes the letter (it mixes in), and at the right wall there is nowhere to go, so the box knocks against it.

## What the cursor draws

- **Waiting block** one level over the top of the grid (`HOVER`), so it never shares a cell with a block and nothing stands in front of it: a small block in the brush color floating in a glass bubble (`BUBBLE`), so it never reads as a block already laid. The small block blinks; the bubble stays.
- **The four arrow keys lie flat** around the waiting block, thin slabs of faint glass in the build's perspective, each out from it the way that arrow moves the cursor, with its arrow upright on it as printed on the real key (`_arrow_keys`, `KEY_SPAN`). Lying flat, the key going away reads as away, never as up. A key going away sits level with the box's top and one coming toward level with its bottom, the sides in between, so the box hides none of them.
- **At the edge, the key that way becomes a stop bar:** a short bright bar lying flat where the key would be, with no arrow (`WALL_SPAN`), the way a line on the road says stop. Pushing an arrow into it knocks the bubble toward it and back (`_knock`, `BUMP`), so a press that goes nowhere still answers. The ceiling answers the same way: Shift with Up on the top level knocks the bubble up, and Shift with Down at the floor knocks it down.
- **Line** from the waiting block down the column's free cells: a faint hairline (`LINE_ALPHA`) with a small arrowhead where it lands (`HEAD`), so the bubble and the spot lead and the line only joins them. A bold line with a tall arrowhead was nearly as loud as the waiting block; dashed, it read as clutter.
- **Landing spot**, a thinner wire box with the waiting block's soft shadow in it (`SPOT_SHADOW`), the way something held over a spot darkens it, and the **shadow square** every floating block gets when it floats.
- **A wire box is the edges of the faces the eye sees**, so it reads as a cube. One line around the cell's outline read as a flat, odd polygon.
- **The marks are painted three times the size and scaled down** (`_smooth`): pygame's wide lines have hard, stepped edges, and on the only lines on screen that shows.
- **Arrowhead over the rows in front** at the lowest point of the line they leave in view, when they hide its end.
- **A new block falls** from the waiting block to its spot in `DROP_S`, speeding up, so the eye goes down the column to where it lands. A block under another falls from just under that one. A falling block stays out of the cached layers until it lands: each frame it is drawn over them, then what stands in front of it is drawn over it, a short list found once a fall (`_draw_falls`). So a frame of a fall costs the same in a build of any size, and it repaints only where the falling blocks were and are, plus the cursor if they touch it (`_fall_patch`, through `app.repaint`). Where something stands in front, the block is drawn again over it, faint (`GHOST_ALPHA`), so its fall still shows behind a wall. Its shadow lies on its spot from the start and darkens as it comes down (`FALL_SHADOW`), so the hover, the fall and the landing read as one drop. A letter typed while the block under it is still falling joins that fall (`_drop`), so fast typing drops one short stack in one animation rather than a string of them.

While the view turns the cursor is drawn too, in its place among the blocks.

## Looking around

One view can't tell "farther back" from "higher up": both go up the screen. So the kid turns the build to see it from another side.

- **A tap of Tab** turns the build to its next side, straight on: a quarter of the way around, clockwise seen from above, and back to the resting tilt, so a tap always lands on a standard view however far it was looked around, as its header picture shows.
- **The view is the viewer's, not the build's.** History doesn't keep it: Time Travel steps through builds in whatever view is up, and Tab still turns while it does. Clearing the room faces the front again.
- **History from the old 30 by 12 floor** says no size; a step that doesn't keeps its middle on today's middle (`OLD_FLOOR`), the same shift for every step, so scrubbing an old build doesn't slide it around. Only blocks within 7 columns of the old floor's left or right end fall past today's walls.
- **Tab held with the arrows** looks around: Left and Right turn the floor a step at a time to any angle, its near edge going the arrow's way, and Up and Down tilt the view from the side to nearly straight down. The footer shows this while Tab is down.

Rules:

- **The arrows go the way they point most.** The floor has four directions, so moving uses the side that faces the viewer most. Looking around, the turn's step (18 degrees) never stops on a diagonal, where two arrows would point the same way, and five steps make a quarter turn, so straight on is always reachable.
- **A view at rest shows the whole floor.** Each angle is sized to fit the floor turned that far, so a turned view is smaller than a straight one. The size eases between the two as the view moves.
- **A tilt stop answers back.** Tab with Up or Down at a stop springs the view a few degrees back off it, the way that still goes, and the footer's arrows drop the one with nowhere left to go. Silence there read as a broken key.
- **The tilt stops at 15 and 75 degrees.** Lower, the eye would sink under tall towers and see blocks from below; higher or over the top, the eye would pass the front rows, which the layers around the cursor are split by.
- **Square, 16 by 16.** The old 30 by 12 floor from its side was 30 rows deep with blocks 64% the size.

Tried and dropped: **a round platter under the floor, turning a quarter at a time**, with arrowheads on it for the four ways. Once the view went to any angle, the stops and the platter said less than the view itself.

## The keys

The aim is keys nobody has to think about. Height comes from typing, so the arrows are free for the floor.

- **Letters always build up.** A block drops into the column and lands on top of what is there; the cursor stays. That is the contrast with Art, where typing runs along. Backspace takes the top block off, so typing and Backspace are up and down while building.
- **The four arrows move the cursor across the floor**, Up away from the viewer and Down toward them: the floor runs up the screen as it goes back, so that is how it looks.
- **A letter held while an arrow moves the cursor lays a line**, any of the four ways: a row, or a wall's first course.
- **Shift with Up or Down** moves the cursor's height without building, onto blocks too (typing there mixes into them). That height stays put as the cursor moves, for bridges and floating blocks. The footer shows it while Shift is down.
- **Enter** drops a block in the current color on top, and never mixes into a block, so holding it grows a tower until the column is full.

This is what 3D builders do: the plain controls move over the ground, and blocks stack.

Tried and dropped:

- **Up and Down as the height, Left and Right along the floor, and Shift with Up or Down, or a quarter turn, to go away and toward.** Building up felt first-class, but typing already builds up, so the two best keys moved the cursor through empty air while the floor's other direction, needed for every block, sat behind a modifier.
- **Typing goes the way the cursor last walked**, with Enter or Shift Up to turn it upward: a hidden mode, set as a side effect of moving.
- **Typing repeats the step that brought the cursor here from the block laid last**, so one spot stacked and a step between two blocks started a row, with the spot after the next edged to show the guess. Nothing to set, but too much to work out, and it guessed wrong for two towers side by side.
- **Enter that first only turned typing upward, then walked the cursor up.** Two meanings on one key, and building up took a second key that nobody remembered.
- **A tap of Tab turning the build 18 degrees.** Fine for looking, but five taps to see the next side.

## The guide beside the floor

The square floor leaves the room's sides empty, and the header alone didn't teach the 3D keys: a grown-up trying it understood that Tab turns, but not that Tab is held while the arrows are pressed, and never noticed Shift. So the header keeps only the color wheel, the brush and Tab, and the sides show two columns of pictures (`blocks_guide.py`): **Build** on the left (two sticker-colored letters with a block dropping from the bubble to its spot, a faint copy above it for the motion, the arrow keys in their keyboard shape with the cursor moving a tile, Shift with Up and Down with a raised cursor box) and **Look around** on the right (Tab with the turn picture, Tab held plus the arrows with the sphere).

- **Each row is one unit:** its picture, its keys right under it, and its words under those, with more space between rows than anything inside one, so it's clear what goes with what. Pictures take whatever height the column leaves.
- **Quiet on purpose.** No panel or border, half strength, a small muted title and one line of words under each row for the grown-up; the pictures carry it for a kid. It is painted into the ground layer, so any block standing over it covers it.
- **It answers back.** Holding a row's key brings that row up to full strength: Tab lights the look row the moment it is down, before an arrow, which is when "keep holding, press arrows" matters.
- **The code line** takes the letters, arrows and Shift, so Build goes; Look stays, and Tab held with the arrows looks around there too. A tap of Tab is decided on release: the code line takes it (a suggested word) if it wants it, else the build turns.
- **They hold still.** The columns are placed once per screen size, outside the widest the floor ever gets (turned to a diagonal, at every tilt), so turning or tilting never moves them and the floor never reaches them. A side too narrow for that (`MIN_W`) shows no column.

## Tried and dropped

- **Every key in the header:** chips for hold Shift with Up and Down, hold Tab with the four arrows, and the arrows' own move chip. Rows of small arrows blurred into one another, and a grown-up still missed that Tab is held while the arrows are pressed.
- **A cursor on the landing spot** (a bold edge and small block where the next block goes): it jumps far up and down the screen from one key to the next over uneven towers. **Gliding it there** in 150 ms still read as jumpy.
- **A round window cut in the rows in front** wherever they hid the landing spot: a hole in a wall confused more than it showed.
- **Upright keycaps around the waiting block**, out from it the way each arrow moves it on screen: drawn flat on the screen, the Up key above the box read as up, and the Down key sat on the line.
- **A low curb in place of the key at an edge:** seen turned, the side curbs looked like flaps on the box rather than a wall.
- **A glass wall standing against the box at an edge, and a glass pane at the ceiling:** once the cursor was a bubble, the wall framed it in a square and the pane cut under it, and it was hard to tell the cursor from the glass.
- **Four flat wings out of the waiting block, a keycap at the end of each**, to tie each arrow to a side. More lines at the ceiling than the keycaps alone, and from the resting view the away and toward wings were slivers.
- **A cursor of many marks:** a glass column from the ceiling, a patch on the ceiling, rings around the column's blocks, a frame and a floor stripe on the cursor's row, a padded wire box and a see-through landing block. Each answered a question, and together they hid the answer.
- **Fading the front towers in the way:** a see-through tower shows every edge behind it.
- **A full-size solid block as the cursor:** it looks laid already, and blinking it doesn't help, since half the time it still looks laid.
- **The landing spot's edge showing through a wall:** it reads as sitting on the wall's face.
- **Fade every row in front** whenever anything hid the landing spot: focused the eye but hid half the build for one block in the way.
- **Fade only the overlapping blocks:** one see-through block in a same-colored wall reads as a dark hole.
- **Glass blocks** (faint fill, bright edges per block): stacked glass shows every hidden face and turns into wireframe noise.
- **Outline down to the floor** from a floating landing spot: a second tall box crossing everything; the shadow square says the same thing.
- **Spotlight** (screen darkens away from the cursor): keeps the noisy part, right around the cursor, bright.
- **Tint rows other than the cursor's:** a good depth cue, but it changes colors most of the time (rule 1).
- **Light edges on the cursor's row:** lost among the edges every block already has.
- **A dot on each block in the row:** clear, but a tower in the row becomes a column of dots.
- **Cross-hatching on the row:** drawn flat on the screen rather than on the faces, so it reads as the blocks' own texture.
- **Thin solid stripes on the row:** read as scanlines, a rendering glitch rather than a mark.
- **A dashed line on the row:** read as a selection mark. **A soft band across the row's blocks** was kept for a while, then dropped with the seams.

## Keeping it fast on old laptops

- **A block landing reworks only its column and the four beside it**, whose faces it hides or shows (`_shaped`, `column_shape`), and repaints only around that column.
- **The cursor moving to another row** repaints only what crosses from behind it to in front of it, or back (`Painter.crossed`), not the whole build.
- **A run of blocks closed in on every side is never painted**, at rest or turning: in a crowded build that is about half of them.
- **Falling blocks repaint only around themselves** (above).
- **The boot log's frame summary** names the room each frame came from, so a slow laptop's log shows where its time goes.
