"""Code for the Blocks room, in Art's words: a color, a way, a count.
`red up 5` stacks a tower, `blue right 6` lays a row, `right hello` builds
the letters, each in its own color, and `repeat 4 right 1 up 1` makes
stairs. Like typing, every block lands at the cursor, which then moves on
that way, so lines run on from where the last one ended."""

import asyncio

from ...code_runner import ArtCodeRunner

# Code words to the room's ways; up and down are height, back and front depth.
WAYS = {"right": "right", "left": "left", "back": "up", "front": "down", "up": "rise", "down": "sink"}
WORDS = {way: word for word, way in WAYS.items()}
KEEP_GOING = ("forward", "go")    # on the way it already goes
MAX_COUNT = 100
BLOCK_S = 0.03


class BlocksCodeRunner(ArtCodeRunner):
    """Art's parsing (repeat, colors, nearest-word numbers, fixes for typos)
    with the Blocks room's moves."""

    _COMMANDS = []

    def _tokenize_motion(self, words: list[str]) -> list[tuple]:
        tokens, i = [], 0
        while i < len(words):
            w = words[i].lower()
            if w in WAYS or w in KEEP_GOING:
                tokens.append(("anchor", (w, WAYS.get(w))))
            elif w.isdigit():
                tokens.append(("number", min(int(w), MAX_COUNT)))
            elif (color := self._resolve_leading_color(words[i:]))[0]:
                tokens.append(("color", color[0]))
                i += color[1]
                continue
            else:
                tokens.append(("text", words[i]))
            i += 1
        return tokens

    async def _execute_motion_plans(self, plans: list[dict]) -> None:
        room = self.canvas
        for plan in plans:
            if plan["color"]:
                self._apply_color(plan["color"])
            if plan["dir"]:
                room.set_way(plan["dir"])
            count = plan["dist"] or (0 if plan["leftover"] else 1)
            for _ in range(count):
                room.build()
                await asyncio.sleep(BLOCK_S)
            if plan["leftover"]:
                await self._emit_text(plan["leftover"], paint=True)

    async def _emit_text(self, text: str, paint: bool) -> None:
        """Each letter a block in its own color; a space moves on without one."""
        room = self.canvas
        for ch in text:
            if ch == " " or not room.build_letter(ch):
                room.skip()
            await asyncio.sleep(BLOCK_S)

    def _apply_color(self, hex_color: str) -> None:
        self.canvas.set_brush_color(hex_color)
