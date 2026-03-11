"""
Code runners for each room.

Parse and execute code from the Code Space text editor.
Shared syntax: `repeat N` ... `end` blocks.
"""

import asyncio
import re


def parse_lines(lines: list[str]) -> list[dict]:
    """Parse lines into a list of commands.

    Handles `repeat N` ... `end` blocks (can be nested).
    Returns a flat list of command dicts with 'type' and params.
    """
    result = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1

        if not line:
            continue

        # repeat N
        m = re.match(r'^repeat\s+(\d+)\s*$', line, re.IGNORECASE)
        if m:
            count = int(m.group(1))
            count = max(1, min(count, 100))  # Safety cap
            # Collect body until "end"
            body_lines = []
            depth = 1
            while i < len(lines) and depth > 0:
                bline = lines[i].strip()
                i += 1
                if re.match(r'^repeat\s+\d+', bline, re.IGNORECASE):
                    depth += 1
                    body_lines.append(bline)
                elif re.match(r'^end\s*$', bline, re.IGNORECASE):
                    depth -= 1
                    if depth > 0:
                        body_lines.append(bline)
                else:
                    body_lines.append(bline)
            # Recursively parse body
            body_cmds = parse_lines(body_lines)
            result.append({'type': 'repeat', 'count': count, 'body': body_cmds})
            continue

        if re.match(r'^end\s*$', line, re.IGNORECASE):
            continue  # Stray end, ignore

        result.append({'type': 'line', 'text': line})

    return result


def flatten_commands(cmds: list[dict]) -> list[dict]:
    """Expand repeat blocks into flat command lists."""
    result = []
    for cmd in cmds:
        if cmd['type'] == 'repeat':
            body = flatten_commands(cmd['body'])
            for _ in range(cmd['count']):
                result.extend(body)
        else:
            result.append(cmd)
    return result


class PlayCodeRunner:
    """Run code in the Play room context.

    Each non-command line is evaluated via SimpleEvaluator.
    Results are collected and returned.
    """

    def __init__(self, evaluator):
        self.evaluator = evaluator

    def run(self, lines: list[str]) -> list[str]:
        """Run code and return list of result strings."""
        cmds = parse_lines(lines)
        flat = flatten_commands(cmds)
        results = []
        for cmd in flat:
            if cmd['type'] == 'line':
                text = cmd['text']
                result = self.evaluator.evaluate(text)
                if result:
                    results.append(result)
        return results


class MusicCodeRunner:
    """Run code in the Music room context.

    Letters on a line play as notes sequentially.
    `choose [instrument]` or `instrument [name]` changes instrument.
    """

    def __init__(self, play_key_fn, set_instrument_fn=None,
                 color_fn=None, flash_fn=None):
        """
        play_key_fn: callable(key: str, mode: str) to play a note
        set_instrument_fn: callable(instrument_id: str) to change instrument
        color_fn: callable(key: str) to set key color
        flash_fn: callable(key: str) to flash a note
        """
        self.play_key = play_key_fn
        self.set_instrument = set_instrument_fn
        self.color_fn = color_fn
        self.flash_fn = flash_fn

    async def run(self, lines: list[str], mode: str = "music") -> None:
        """Run music code asynchronously with timing."""
        from .music_constants import ALL_KEYS

        cmds = parse_lines(lines)
        flat = flatten_commands(cmds)

        for cmd in flat:
            if cmd['type'] != 'line':
                continue
            text = cmd['text']

            # instrument/choose command
            m = re.match(r'^(?:choose|instrument)\s+(.+)$', text, re.IGNORECASE)
            if m and self.set_instrument:
                self.set_instrument(m.group(1).strip())
                await asyncio.sleep(0.1)
                continue

            # Play each character as a note
            for ch in text:
                lookup = ch.upper() if ch.isalpha() else ch
                if lookup in ALL_KEYS:
                    if self.color_fn:
                        self.color_fn(lookup)
                    self.play_key(lookup, mode)
                    if self.flash_fn:
                        self.flash_fn(lookup)
                    await asyncio.sleep(0.2)


class ArtCodeRunner:
    """Run code in the Art room context.

    Movement: left N, right N, up N, down N
    Drawing: paint on/off, write on/off
    Text in write mode: characters typed at cursor position
    """

    def __init__(self, canvas):
        """canvas: ArtCanvas widget to dispatch commands to."""
        self.canvas = canvas

    async def run(self, lines: list[str]) -> None:
        """Run art code asynchronously."""
        cmds = parse_lines(lines)
        flat = flatten_commands(cmds)

        paint_on = False
        write_on = False

        for cmd in flat:
            if cmd['type'] != 'line':
                continue
            text = cmd['text']

            # paint on/off
            m = re.match(r'^paint\s+(on|off)\s*$', text, re.IGNORECASE)
            if m:
                paint_on = m.group(1).lower() == 'on'
                continue

            # write on/off
            m = re.match(r'^write\s+(on|off)\s*$', text, re.IGNORECASE)
            if m:
                write_on = m.group(1).lower() == 'on'
                continue

            # Movement: direction N
            m = re.match(r'^(left|right|up|down)\s*(\d*)\s*$', text, re.IGNORECASE)
            if m:
                direction = m.group(1).lower()
                distance = int(m.group(2)) if m.group(2) else 1
                distance = min(distance, 200)  # Safety cap

                action = "paint" if paint_on else "move"
                self.canvas.execute_logo_command(action, direction, distance)
                await asyncio.sleep(0.05)
                continue

            # In write mode, type characters at cursor
            if write_on:
                for ch in text:
                    self.canvas.type_char(ch)
                    await asyncio.sleep(0.02)
                continue
