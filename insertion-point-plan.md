# Plan: Insertion-Point Cursor + LINE_BREAK for Code Mode

## Context

Code mode's cursor currently points AT a block (index into block list). This causes problems:
- No blocks = no cursor = no visual indicator of where you are
- Need phantom blocks (LINE_BREAK) just to have cursor positions on empty lines
- Inconsistent with Doodle mode, where the cursor is a position that exists independently of content

The fix: make the cursor an **insertion point** (like a text cursor), add **blinking** (matching Doodle's 0.4s interval), and add **LINE_BREAK** as an invisible structural block for line breaks.

This builds on already-implemented work: auto-collapse (`count` field, `matches()`, recording collapse), line-scoped REPEAT (gutter badge), and LINE_BREAK block type.

## Design

### Cursor Model

**Old:** `_cursor: int` = index of selected block (0 to len-1). Undefined when empty.

**New:** `_cursor: int` = insertion point (0 to len(blocks)). Position N means "between block N-1 and block N."

- Position 0: before all blocks (start of program)
- Position N: after block N-1, before block N
- Position len(blocks): after all blocks (end of program)
- Empty program: cursor is 0, renders as blinking cursor on empty line

### Visual Rendering

**Blinking cursor indicator** (matching Doodle mode):
- 0.4s blink interval using Textual's `set_interval()`
- `_cursor_visible` boolean toggled each interval
- Cursor rendered as a thin (1-char wide) blinking vertical bar between blocks
- Uses BLOCK_HEIGHT tall rendering (spans all 4 sub-rows of a line)
- Color: `#6633AA` (same purple as Doodle text cursor, `CURSOR_BG_NORMAL`)

**Block highlight**: The block just before the cursor (block at cursor-1) gets a subtle highlight to show what backspace would delete. Use the existing gold top/bottom border pattern but dimmer, or just bold text.

**Rendering in `_render_block_strip()`**: Iterate through blocks on the line, and after each block, check if the cursor position falls there. If so, render a 1-char-wide blinking cursor column. Also check if cursor is at position 0 (before first block on the line).

### LINE_BREAK Block

- `ProgramBlockType.LINE_BREAK` (already added to program.py)
- **Invisible**: 0 width in `total_width`, skipped in block strip rendering
- **Structural**: causes `_layout_lines()` to start a new line
- **Carries forward** the previous line's mode icon in the gutter
- **Playback**: completely ignored (no action produced)
- **Enter key** inserts a LINE_BREAK at cursor position
- **Backspace** on a LINE_BREAK deletes it (merging lines)

### Navigation

- **Left**: cursor moves left by 1 position (skipping LINE_BREAK blocks seamlessly)
- **Right**: cursor moves right by 1 position
- **Up**: jump to same horizontal position on previous line
- **Down**: jump to same horizontal position on next line
- **Home/start**: cursor to position 0 on current line
- **End**: cursor to end of current line

### Insert & Delete

- **Insert** (typing a key): insert new block at cursor position, advance cursor by 1
- **Auto-collapse**: if the block at cursor-1 matches the new block, increment its count instead
- **Backspace**: if cursor > 0, delete block at cursor-1, cursor decrements by 1
- **Delete block at cursor-1** means: if it's a LINE_BREAK, lines merge; if it's a regular block, it disappears

### Tab Menu Changes

- "Insert Enter key ↵": inserts a CONTROL enter block (for playback)
- "Adjust count": adjust count on block at cursor-1
- "Longer/shorter pause": adjust gap on block at cursor-1
- All adjust actions operate on the block before the cursor (cursor-1)

## Files to Modify

### `purple_tui/program.py` (minimal changes)
- LINE_BREAK type already added, just clean up icon/color (use `LINE_BREAK_COLOR`)
- `total_width` returns 0 for LINE_BREAK (already done)
- Ensure LINE_BREAK serialization round-trips

### `purple_tui/modes/build_mode.py` (major refactor)
- **CodeCanvas**: add `_cursor_visible` + blink timer (matching Doodle's pattern)
- **CodeCanvas**: refactor `_render_block_strip()` to render cursor between blocks
- **CodeCanvas**: update `_render_empty_line()` to show blinking cursor
- **`_layout_lines()`**: handle LINE_BREAK as line separator (already partially done)
- **`_cursor_to_line_pos()`**: adapt for insertion-point cursor model
- **BuildMode**: change all cursor logic from block-index to insertion-point
  - `_handle_navigation()`: left/right moves insertion point
  - `_handle_character()`: insert at cursor position
  - `_handle_control()`: Enter inserts LINE_BREAK, backspace deletes block before cursor
  - `_jump_line()`: adapt for new cursor model
  - `_insert_block()`: insert at cursor position (not after cursor)
  - `_delete_block()`: delete block before cursor
  - `_try_auto_collapse()`: check block at cursor-1

### `purple_tui/code_menu.py`
- Replace "Cycle value" with "More/fewer repeats" (already done)
- Add "Insert Enter key ↵" (already done)
- Menu adjust actions reference cursor-1 block

### `tests/test_program.py`
- Add LINE_BREAK tests (layout, serialization, playback ignores it)
- Update `_cursor_to_line_pos` tests for insertion-point model
- Existing block count + auto-collapse tests stay as-is

## Implementation Order

1. Add blink timer to CodeCanvas (following Doodle's pattern exactly)
2. Refactor cursor model in BuildMode: change `_cursor` semantics from block-index to insertion-point
3. Update `_insert_block()` and `_delete_block()` for insertion-point
4. Update `_handle_navigation()`, `_handle_character()`, `_handle_control()`
5. Update `_cursor_to_line_pos()` for insertion-point semantics
6. Refactor `_render_block_strip()` to render cursor between blocks
7. Update `_render_empty_line()` to show blinking cursor
8. Clean up LINE_BREAK in `_layout_lines()` (line separator, carries mode icon)
9. Update Tab menu result handlers for cursor-1 operations
10. Update tests

## Key Patterns to Reuse

- **Blink timer**: Copy exactly from Doodle mode (`doodle_mode.py:336-346`)
  - `set_interval(0.4, self._toggle_blink)`
  - `_cursor_visible` boolean
  - `_start_blink()` / `_stop_blink()` lifecycle
- **Cursor color**: `#6633AA` (`CURSOR_BG_NORMAL` from Doodle)
- **render_line() + Strip + Segment pattern**: already used in CodeCanvas
- **LINE_BREAK in layout**: similar to MODE_SWITCH line-break logic

## Verification

```bash
source .venv/bin/activate
pytest tests/test_program.py -v
pytest tests/ -v  # full suite
```

Visual verification on device:
- Empty Code mode shows blinking cursor
- Type keys: blocks appear, cursor blinks after last block
- Left/right: cursor moves between blocks, blink resets
- Enter: creates new line, cursor on next line
- Backspace on LINE_BREAK: merges lines
- Up/down: jumps between lines
- Auto-collapse: typing same key increments count on previous block
