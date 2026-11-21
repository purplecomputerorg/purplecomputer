# Blocks: showing where the next block goes

Blocks is one color more often than not (a kid holds one key), drawn small enough to fit the whole floor, and nobody zooms. The cursor has to answer two questions at a glance: **where will the block land**, and **what is it next to**. The cursor is in `purplecomputer/rooms/blocks_room.py`; the camera and painting it draws through are in `blocks_view.py`.

## Rules

1. **Never change a block's color.** Blocks is a color room; a block that looks darker when the cursor moves away teaches the wrong color. Blocks are plain faces with no lines on them: the cursor's marks are its own, never the blocks'.
2. **Only the cursor's own lines draw over everything.** The wire box and its arrow go on top. Anything else the cursor marks (the rings around its column's blocks) sits in the scene, so blocks in front hide it like any block.
3. **Fade only what's in the way, a whole tower at a time.** A front tower fades when any of its blocks is drawn over the glass column or the landing block, by a pixel or more; all of it fades, floor to top, as one flat layer. Everything else stays solid.
4. **One more line costs more than it explains.** A wall of one color reads better as one wall. Seams between blocks, a line from each floating block down to its shadow, and a band across the cursor row's blocks were all drawn once; the build looked cleaner without them, and paints faster: a column's touching blocks of one color are one tall box (`shape` in `blocks_view.py`).

## What the cursor draws

- **Glass column** from the ceiling down to the landing block, plus a faint ceiling patch: which floor spot you're over.
- **Bold wire box** around the landing block: white over a dark edge, width scaled with the cell size, so it reads over any color.
- **Shadow square** under a floating landing spot, the same mark every floating block gets, with no line up to the block.
- **Rings** around each run of blocks in the cursor's column, hidden by blocks in front.
- **Frame around the cursor's row**: a faint upright rectangle on the back of the row, floor to ceiling and wall to wall, so the row reads as one slice of the world rather than a line of unrelated blocks. Drawn behind the row's blocks, so it never crosses over them.
- **Faded towers** in the way, at `FRONT_ALPHA`.

## Looking around

One view can't tell "farther back" from "higher up": both go up the screen. So the kid looks around the build.

- **Shift with the arrows** looks around: Left and Right turn the floor a step at a time to any angle, its near edge going the arrow's way, and Up and Down tilt the view from the side to nearly straight down.
- **Tab** goes back to the front. Held with Up or Down, it moves the cursor's height, as Shift did before it meant looking.

Rules:

- **The arrows go the way they point most.** The floor has four directions, so moving and typing use the side that faces the viewer most. The turn's step (18 degrees) never stops on a diagonal, where two arrows would point the same way, and five steps make a quarter turn, so straight on is always reachable.
- **A view at rest shows the whole floor.** Each angle is sized to fit the floor turned that far, so a turned view is smaller than a straight one. The size eases between the two as the view moves.
- **The tilt stops at 15 and 75 degrees.** Lower, the eye would sink under tall towers and see blocks from below; higher or over the top, the eye would pass the front rows, which the layers around the cursor are split by.
- **Square, 16 by 16.** The old 30 by 12 floor from its side was 30 rows deep with blocks 64% the size.

Tried and dropped: **a round platter under the floor, turning a quarter at a time**, with arrowheads on it for the four ways. Once the view went to any angle, the stops and the platter said less than the view itself.

## Tried and dropped

- **Fade every row in front** whenever anything hid the landing spot: focused the eye but hid half the build for one block in the way.
- **Fade only the overlapping blocks:** one see-through block in a same-colored wall reads as a dark hole.
- **Glass blocks** (faint fill, bright edges per block): stacked glass shows every hidden face and turns into wireframe noise.
- **Fade the landing spot's neighbors too:** too much glass in dense builds.
- **Outline down to the floor** from a floating landing spot: a second tall box crossing everything; the shadow square says the same thing.
- **Spotlight** (screen darkens away from the cursor): keeps the noisy part, right around the cursor, bright.
- **Tint rows other than the cursor's:** a good depth cue, but it changes colors most of the time (rule 1).
- **Light edges on the cursor's row:** lost among the edges every block already has.
- **A dot on each block in the row:** clear, but a tower in the row becomes a column of dots.
- **Cross-hatching on the row:** drawn flat on the screen rather than on the faces, so it reads as the blocks' own texture.
- **Thin solid stripes on the row:** read as scanlines, a rendering glitch rather than a mark.
- **A dashed line on the row:** read as a selection mark. **A soft band across the row's blocks** was kept for a while, then dropped with the seams.
