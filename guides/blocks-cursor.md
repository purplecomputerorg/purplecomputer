# Blocks: showing where the next block goes

Blocks is one color more often than not (a kid holds one key), drawn small enough to fit the whole floor, and nobody zooms. The cursor has to answer two questions at a glance: **where will the block land**, and **what is it next to**. Everything here is in `purple_tui/canvas/rooms/blocks_room.py`.

## Rules

1. **Never change a block's color.** Blocks is a color room; a block that looks darker when the cursor moves away teaches the wrong color. Mark things with edges, never with tints.
2. **Only the cursor's own lines draw over everything.** The wire box and its arrow go on top. Anything else the cursor marks (the rings around its column's blocks) sits in the scene, so blocks in front hide it like any block.
3. **Fade only what's in the way, a whole tower at a time.** A front tower fades when any of its blocks is drawn over the glass column or the landing block, by a pixel or more; all of it fades, floor to top, as one flat layer. Everything else stays solid.
4. **One more line costs more than it explains.** Every block already has edges; a cursor mark has to be clearly bolder than them or it's noise.

## What the cursor draws

- **Glass column** from the ceiling down to the landing block, plus a faint ceiling patch: which floor spot you're over.
- **Bold wire box** around the landing block: white over a dark edge, width scaled with the cell size, so it reads over any color.
- **Shadow square** under a floating landing spot, the same mark every floating block gets.
- **Rings** around each run of blocks in the cursor's column, hidden by blocks in front.
- **Frame around the cursor's row**: a faint upright rectangle on the back of the row, floor to ceiling and wall to wall, so the row reads as one slice of the world rather than a line of unrelated blocks. Drawn behind the row's blocks, so it never crosses over them.
- **Stripes on the cursor's row**: blocks in that row get two light lines across the top and front faces, running along the row like the frame's edges, their color showing between them, so you can tell a block beside the landing spot from one a row in front or behind. Built into the scene, which already rebuilds only when the cursor changes rows.
- **Faded towers** in the way, at `FRONT_ALPHA`.

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
