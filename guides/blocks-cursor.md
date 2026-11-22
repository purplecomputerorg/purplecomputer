# Blocks: showing where the next block goes

Blocks is one color more often than not (a kid holds one key), drawn small enough to fit the whole floor, and nobody zooms. The cursor has to answer two questions at a glance: **where will the block land**, and **what is it next to**. The cursor is in `purplecomputer/rooms/blocks_room.py`; the camera and painting it draws through are in `blocks_view.py`.

## Rules

1. **Never change a block's color.** Blocks is a color room; a block that looks darker when the cursor moves away teaches the wrong color. Blocks are plain faces with no lines on them: the cursor's marks are its own, never the blocks'.
2. **Only the cursor's edge and arrow draw over everything.** Its small block and shadow sit in the scene, so blocks in front hide them like any block.
3. **Nothing is see-through.** Where the rows in front hide the cursor's spot, they get a round window onto it: a crisp hole, everything in it solid. Everything else stays whole.
4. **One more line costs more than it explains.** A wall of one color reads better as one wall, and with no lines on the blocks, the cursor's edge is the only line on screen, which is what makes it easy to find. Seams between blocks, a line from each floating block down to its shadow, and a band across the cursor row's blocks were all drawn once; the build looked cleaner without them, and paints faster: a column's touching blocks of one color are one tall box (`shape` in `blocks_view.py`).
5. **The cursor never looks like a laid block.** A laid block fills its cell; the cursor's block is about half that size.

## What the cursor draws

- **Bold edge** around the spot the next block goes: white over a dark edge, width scaled with the cell size, so it reads over any color.
- **Small block** in the brush color in the middle of the spot. It blinks; the edge stays.
- **Arrow** out of the spot the way typing goes.
- **Shadow square** under a floating spot, the same mark every floating block gets, with no line up to the block.
- **Round window** in the rows in front when they hide more than `WINDOW_COVER` of the spot. The block just laid right in front of the cursor doesn't count and stays solid in the window, so typing away from the viewer still shows each block land; the cursor then shows as its edge over that block.
- **A glide** when the spot lands more than `GLIDE_OVER` cells away on screen, as when typing along a row of uneven towers: the edge, block and arrow slide there in `GLIDE_S`, slowing down, so the eye follows. A step next door is instant, and nothing moves unless a key was pressed.

## Looking around

One view can't tell "farther back" from "higher up": both go up the screen. So the kid looks around the build.

- **A tap of Tab** turns the build one step, so a little kid can walk all the way around it with one key.
- **Tab held with the arrows** looks around: Left and Right turn the floor a step at a time to any angle, its near edge going the arrow's way, and Up and Down tilt the view from the side to nearly straight down. The footer shows this while Tab is down.
- **Shift with Up or Down** moves the cursor's height, and is not a way to look.

## Building up

- **Enter builds up.** It drops a block in the current color in the first free spot over the block typing just laid, and goes on up, so a letter then Enter, Enter is a tower in that letter's color, and holding Enter grows it until the column is full. If the cursor has moved since the last block, Enter builds over the cursor.
- **Nothing locks in.** An arrow takes typing sideways again, and Enter brings it back up.
- **Shift with Up or Down** moves the cursor's height without building, for bridges and floating blocks, and typing then goes that way.
- Tried and dropped: **Enter that first only turned typing upward, then walked the cursor up.** Two meanings on one key, and building up took a second key that nobody remembered.

Rules:

- **The arrows go the way they point most.** The floor has four directions, so moving and typing use the side that faces the viewer most. The turn's step (18 degrees) never stops on a diagonal, where two arrows would point the same way, and five steps make a quarter turn, so straight on is always reachable.
- **A view at rest shows the whole floor.** Each angle is sized to fit the floor turned that far, so a turned view is smaller than a straight one. The size eases between the two as the view moves.
- **The tilt stops at 15 and 75 degrees.** Lower, the eye would sink under tall towers and see blocks from below; higher or over the top, the eye would pass the front rows, which the layers around the cursor are split by.
- **Square, 16 by 16.** The old 30 by 12 floor from its side was 30 rows deep with blocks 64% the size.

Tried and dropped: **a round platter under the floor, turning a quarter at a time**, with arrowheads on it for the four ways. Once the view went to any angle, the stops and the platter said less than the view itself.

## Tried and dropped

- **A cursor of many marks:** a glass column from the ceiling, a patch on the ceiling, rings around the column's blocks, a frame and a floor stripe on the cursor's row, a padded wire box and a see-through landing block. Each answered a question, and together they hid the answer.
- **Fading the front towers in the way:** a see-through tower shows every edge behind it. The window shows less and says more.
- **A full-size solid block as the cursor:** it looks laid already, and blinking it doesn't help, since half the time it still looks laid.
- **Only the edge showing through a wall, with no window:** fewest marks, but the block just typed can't be seen, and the edge reads as sitting on the wall's face.
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
