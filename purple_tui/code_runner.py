"""
Code runners for each room.

Parse and execute code from REPL input.
Shared syntax: inline `repeat N cmd1, cmd2` across all rooms.
"""

import asyncio
import logging
import re

from .content import get_content
from .rooms.art_room import get_key_color

log = logging.getLogger(__name__)


def _split_clauses(text: str) -> list[str]:
    """Split text on clause separators: , . ; |

    Returns a list of trimmed, non-empty clauses.
    """
    return [s.strip() for s in re.split(r'[,.\;|]', text) if s.strip()]


# Command keywords that start a new command when found mid-line.
# Includes direction words and new commands (spin/face/back/backward/rotate).
_COMMAND_STARTS = re.compile(
    r'\b(?=(?:turn|spin|rotate|face|forward|go|move|walk|step|back|backward|paint|write|color|lift|pen|choose|select|use|play|instrument|letters|fast|slow|repeat|left|right|up|down)\b)',
    re.IGNORECASE,
)

# Patterns for merging multi-word commands after keyword splitting.
# "turn"/"face" + direction and "pen" + up/down must stay together.
_MULTIWORD_MERGE = [
    # (bare_keyword_re, following_arg_re)
    (re.compile(r'^turn$', re.IGNORECASE),
     re.compile(r'^(?:left|right|up|down|back|backward|around|\d)', re.IGNORECASE)),
    (re.compile(r'^face$', re.IGNORECASE),
     re.compile(r'^(?:left|right|up|down)\b', re.IGNORECASE)),
    (re.compile(r'^pen$', re.IGNORECASE),
     re.compile(r'^(?:up|down)\b', re.IGNORECASE)),
]


def _merge_multiword(parts: list[str]) -> list[str]:
    """Rejoin bare 'turn'/'face'/'pen' with the following argument chunk."""
    merged = []
    i = 0
    while i < len(parts):
        if i + 1 < len(parts):
            for bare_re, arg_re in _MULTIWORD_MERGE:
                if bare_re.match(parts[i]) and arg_re.match(parts[i + 1]):
                    merged.append(parts[i] + ' ' + parts[i + 1])
                    i += 2
                    break
            else:
                merged.append(parts[i])
                i += 1
            continue
        merged.append(parts[i])
        i += 1
    return merged


def _split_commands(text: str) -> list[str]:
    """Split a single line into multiple commands at keyword boundaries.

    Handles cases like "turn right down 3" or "forward 10 turn left forward 5".
    Falls back to returning [text] if no split points are found.
    """
    # Find all split positions from command-start keywords
    positions = set()
    for m in _COMMAND_STARTS.finditer(text):
        positions.add(m.start())

    if len(positions) <= 1:
        return [text]

    # Split at the found positions
    sorted_pos = sorted(positions)
    parts = []
    for i, pos in enumerate(sorted_pos):
        end = sorted_pos[i + 1] if i + 1 < len(sorted_pos) else len(text)
        chunk = text[pos:end].strip()
        if chunk:
            parts.append(chunk)

    # If there's leading text before the first command, prepend it
    if sorted_pos[0] > 0:
        leading = text[:sorted_pos[0]].strip()
        if leading:
            parts.insert(0, leading)

    parts = _merge_multiword(parts) if parts else [text]
    return parts if parts else [text]


def parse_lines(lines: list[str]) -> list[dict]:
    """Parse lines into a list of commands.

    Handles inline `repeat N cmd1, cmd2` syntax.
    Clause separators (, . ; |) split a line into multiple commands.
    Returns a flat list of command dicts with 'type' and params.
    """
    result = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Inline repeat: repeat N cmd1, cmd2, ...
        m = re.match(r'^repeat\s+(\d+)\s+(.+)$', line, re.IGNORECASE)
        if m:
            count = max(1, min(int(m.group(1)), 100))
            sub_lines = _split_clauses(m.group(2))
            body_cmds = parse_lines(sub_lines)
            result.append({'type': 'repeat', 'count': count, 'body': body_cmds})
            continue

        # Split on clause separators, then on command-keyword boundaries
        clauses = _split_clauses(line)
        parts = []
        for clause in clauses:
            parts.extend(_split_commands(clause))
        if not parts:
            parts = [line]
        for part in parts:
            result.append({'type': 'line', 'text': part})

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
                try:
                    result = self.evaluator.evaluate(text)
                    if result:
                        results.append(result)
                except Exception:
                    log.debug("Play command failed: %s", text, exc_info=True)
                    continue
        return results


class MusicCodeRunner:
    """Run code in the Music room context.

    Uses a command table for dispatch (same pattern as ArtCodeRunner).
    Unrecognized text plays as notes character-by-character.
    """

    # Speed presets: delay between notes in seconds
    SPEED_NORMAL = 0.2
    SPEED_FAST = 0.04
    SPEED_SLOW = 0.6

    # Command table: (compiled_regex, handler_method_name)
    _COMMANDS = [
        (re.compile(r'^letters\s+(\S+)\s*$', re.I), '_do_letters'),
        (re.compile(r'^(?:choose|instrument|select|use)\s+(.+)$', re.I), '_do_instrument'),
        (re.compile(r'^play\s+(.+)$', re.I), '_do_play'),
    ]

    # Command keywords for fuzzy matching
    _KEYWORD_VOCAB = ['letters', 'choose', 'instrument', 'select', 'use', 'play', 'fast', 'slow']

    def __init__(self, play_key_fn, set_instrument_fn=None,
                 color_fn=None, flash_fn=None, set_letters_fn=None):
        self.play_key = play_key_fn
        self.set_instrument = set_instrument_fn
        self.color_fn = color_fn
        self.flash_fn = flash_fn
        self.set_letters = set_letters_fn
        self.corrections: list[tuple[str, str]] = []
        self._original_text: str = ""
        self._correction_final: str = ""

    def _build_final_correction(self, corrected_text: str) -> str:
        """Return the final corrected form (handler may have further refined it)."""
        return self._correction_final or corrected_text

    @staticmethod
    def _resolve_instrument(name: str) -> str | None:
        """Resolve instrument name (exact, alias, prefix, or fuzzy). Returns resolved name or None."""
        if not name:
            return None
        from .music_constants import INSTRUMENTS, INSTRUMENT_ALIASES
        name_lower = INSTRUMENT_ALIASES.get(name.lower(), name.lower())
        # Exact match
        for inst_id, inst_name in INSTRUMENTS:
            if inst_name.lower() == name_lower or inst_id.lower() == name_lower:
                return inst_name
        # Prefix match
        for inst_id, inst_name in INSTRUMENTS:
            if inst_name.lower().startswith(name_lower) or inst_id.lower().startswith(name_lower):
                return inst_name
        # Fuzzy match
        from .fuzzy import fuzzy_match_small
        all_names = [n for _, n in INSTRUMENTS] + list(INSTRUMENT_ALIASES.keys())
        if match := fuzzy_match_small(name_lower, [n.lower() for n in all_names], cutoff=0.6):
            resolved = INSTRUMENT_ALIASES.get(match, match)
            for inst_id, inst_name in INSTRUMENTS:
                if inst_name.lower() == resolved or inst_id.lower() == resolved:
                    return inst_name
        return None

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(self, lines: list[str], mode: str = "music") -> None:
        """Run music code. Corrections stored in self.corrections."""
        from .music_constants import ALL_KEYS

        cmds = parse_lines(lines)
        flat = flatten_commands(cmds)
        self._mode = mode
        self._all_keys = ALL_KEYS

        for cmd in flat:
            if cmd['type'] != 'line':
                continue
            try:
                await self._dispatch(cmd['text'])
            except asyncio.CancelledError:
                raise
            except Exception:
                log.debug("Music command failed: %s", cmd['text'], exc_info=True)

    async def _dispatch(self, text: str) -> None:
        self._original_text = text  # Track for correction display
        self._correction_final = ""  # Reset per-dispatch
        self._suppress_handler_corrections = False

        # Stage 1: command table
        for pattern, handler_name in self._COMMANDS:
            m = pattern.match(text)
            if m:
                handler = getattr(self, handler_name)
                if await handler(m):
                    return

        # Stage 2: fuzzy keyword correction (e.g., "chooze marimba")
        words = text.strip().split(None, 1)
        if words and len(words[0]) >= 3:
            from .fuzzy import fuzzy_match_small
            corrected_kw = fuzzy_match_small(words[0].lower(), self._KEYWORD_VOCAB, cutoff=0.7)
            if corrected_kw and corrected_kw != words[0].lower():
                corrected = corrected_kw + (' ' + words[1] if len(words) > 1 else '')
                self._suppress_handler_corrections = True
                # Re-try with corrected text (command table only, no recursion)
                for pattern, handler_name in self._COMMANDS:
                    m = pattern.match(corrected)
                    if m:
                        handler = getattr(self, handler_name)
                        if await handler(m):
                            # Single correction: original → final (handler may have refined)
                            self.corrections.append((text, self._build_final_correction(corrected)))
                            return
                # Keyword corrected but no handler matched: record keyword fix
                self.corrections.append((text, corrected))

        # Stage 3: speed prefix + play notes
        await self._play_notes(text)

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    async def _do_letters(self, m) -> bool | None:
        arg = m.group(1).lower()
        if arg in ('on', 'off'):
            letters_on = arg == 'on'
            self._mode = "letters" if letters_on else "music"
            if self.set_letters:
                self.set_letters(letters_on)
            return True
        # Fuzzy match on/off
        from .fuzzy import fuzzy_match_small
        corrected = fuzzy_match_small(arg, ['on', 'off'], cutoff=0.7)
        if corrected:
            self.corrections.append((f'letters {arg}', f'letters {corrected}'))
            letters_on = corrected == 'on'
            self._mode = "letters" if letters_on else "music"
            if self.set_letters:
                self.set_letters(letters_on)
            return True
        return None

    async def _do_instrument(self, m) -> bool | None:
        name = m.group(1).strip()
        resolved = self._resolve_instrument(name)
        if resolved and self.set_instrument:
            keyword = m.group(0).split()[0]
            if resolved.lower() != name.lower():
                self._correction_final = f'{keyword} {resolved.lower()}'
                if not self._suppress_handler_corrections:
                    self.corrections.append((self._original_text, self._correction_final))
            self.set_instrument(name)
            await asyncio.sleep(0.1)
            return True
        return None

    async def _do_play(self, m) -> bool | None:
        arg = m.group(1).strip()
        resolved = self._resolve_instrument(arg)
        if resolved and self.set_instrument:
            if resolved.lower() != arg.lower():
                self._correction_final = f'play {resolved.lower()}'
                if not self._suppress_handler_corrections:
                    self.corrections.append((self._original_text, self._correction_final))
            self.set_instrument(arg)
            await asyncio.sleep(0.1)
            return True
        # Not an instrument: play as notes
        await self._play_notes(arg)
        return True

    async def _play_notes(self, text: str) -> None:
        """Parse speed prefix and play characters as notes."""
        delay = self.SPEED_NORMAL
        m = re.match(r'^(fast|slow)\s+(.+)$', text, re.IGNORECASE)
        if m:
            delay = self.SPEED_FAST if m.group(1).lower() == 'fast' else self.SPEED_SLOW
            text = m.group(2)
        else:
            # Fuzzy speed prefix
            words = text.split(None, 1)
            if words and len(words) > 1 and len(words[0]) >= 3:
                from .fuzzy import fuzzy_match_small
                speed = fuzzy_match_small(words[0].lower(), ['fast', 'slow'], cutoff=0.7)
                if speed:
                    self.corrections.append((text, f'{speed} {words[1]}'))
                    delay = self.SPEED_FAST if speed == 'fast' else self.SPEED_SLOW
                    text = words[1]

        for ch in text:
            lookup = ch.upper() if ch.isalpha() else ch
            if lookup in self._all_keys:
                if self.color_fn:
                    self.color_fn(lookup)
                self.play_key(lookup, self._mode)
                if self.flash_fn:
                    self.flash_fn(lookup)
                await asyncio.sleep(delay)


from .fuzzy import fuzzy_match, fuzzy_match_small


# Vocabulary lists for fuzzy matching
_COMMAND_VOCAB = [
    'turn', 'forward', 'go', 'move', 'walk', 'step', 'paint', 'write',
    'color', 'lift', 'pen', 'left', 'right', 'up', 'down', 'spin', 'face',
    'rotate', 'repeat', 'back', 'backward',
]
_TURN_VOCAB = ['left', 'right', 'up', 'down', 'back', 'backward', 'around']
_DIRECTION_VOCAB = ['left', 'right', 'up', 'down']
_TOGGLE_VOCAB = ['on', 'off']
_OPPOSITE = {'right': 'left', 'left': 'right', 'up': 'down', 'down': 'up'}


class ArtCodeRunner:
    """Run code in the Art room context.

    Uses a command table for dispatch: each entry is a (regex, handler) pair
    checked in priority order. Unrecognized text goes through a resolution
    pipeline (bare color, modified color, fuzzy match) before giving up.
    Corrections are tracked for UI feedback.
    """

    # Command table: (compiled_regex, handler_method_name)
    # Checked in order; first match wins.
    _COMMANDS = [
        (re.compile(r'^paint\s+(on|off)\s*$', re.I), '_do_paint_toggle'),
        (re.compile(r'^paint\s+(.+?)\s*$', re.I), '_do_paint_inline'),
        (re.compile(r'^write\s+(on|off)\s*$', re.I), '_do_write_toggle'),
        (re.compile(r'^write\s+(.+?)\s*$', re.I), '_do_write_inline'),
        (re.compile(r'^color\s+(.+?)\s*$', re.I), '_do_color'),
        (re.compile(r'^lift\s*$', re.I), '_do_lift'),
        (re.compile(r'^(?:pen\s*up|penup)\s*$', re.I), '_do_pen_up'),
        (re.compile(r'^(?:pen\s*down|pendown)\s*$', re.I), '_do_pen_down'),
        (re.compile(r'^(?:spin|rotate)\s*$', re.I), '_do_spin'),
        (re.compile(r'^face\s+(\S+)\s*$', re.I), '_do_face'),
        (re.compile(r'^turn\s+(\S+)\s*$', re.I), '_do_turn'),
        (re.compile(r'^turn\s*$', re.I), '_do_spin'),
        (re.compile(r'^(?:forward|go|move|walk|step)\s*(\d*)\s*$', re.I), '_do_forward'),
        (re.compile(r'^(?:back|backward)\s*(\d*)\s*$', re.I), '_do_back'),
        (re.compile(r'^(left|right|up|down)\s+(\d+)\s*$', re.I), '_do_direction'),
        (re.compile(r'^(left|right|up|down)\s*$', re.I), '_do_direction'),
    ]

    def __init__(self, canvas):
        self.canvas = canvas
        self.corrections: list[tuple[str, str]] = []

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(self, lines: list[str], paint: bool = True) -> None:
        """Run art code. Corrections are stored in self.corrections."""
        cmds = parse_lines(lines)
        flat = flatten_commands(cmds)
        self._paint_on = paint
        self._write_on = not paint

        for cmd in flat:
            if cmd['type'] != 'line':
                continue
            try:
                await self._dispatch(cmd['text'])
            except asyncio.CancelledError:
                raise
            except Exception:
                log.debug("Art command failed: %s", cmd['text'], exc_info=True)

    async def _dispatch(self, text: str, _resolving: bool = False) -> None:
        """Try command table, then resolution pipeline."""
        # Stage 1: command table (exact + per-handler fuzzy)
        for pattern, handler_name in self._COMMANDS:
            m = pattern.match(text)
            if m:
                handler = getattr(self, handler_name)
                if await handler(m):
                    return

        # Stage 2: write mode types characters (that's its purpose)
        if self._write_on:
            heading = self.canvas._heading
            for ch in text:
                self.canvas.type_char(ch, direction=heading)
                await asyncio.sleep(0.02)
            return

        # Stage 3: resolution pipeline (only on first pass)
        if not _resolving:
            resolved = self._resolve(text)
            if resolved:
                return

        # Stage 4: paint mode paints each character (like interactive mode)
        if self._paint_on:
            heading = self.canvas._heading
            for ch in text:
                self.canvas.paint_char(ch, direction=heading)
                await asyncio.sleep(0.02)

    # ------------------------------------------------------------------
    # Command handlers (return True if handled, None to pass)
    # ------------------------------------------------------------------

    async def _do_paint_toggle(self, m) -> bool | None:
        self._paint_on = m.group(1).lower() == 'on'
        if self._paint_on:
            self._write_on = False
        self.canvas._set_paint_mode(self._paint_on)
        return True

    async def _do_paint_inline(self, m) -> bool | None:
        """paint <text>: color name → one block in that color, else per-char blocks."""
        arg = m.group(1).strip()
        content = get_content()
        hex_color = content.get_color(arg.lower())
        if hex_color:
            self._apply_color(hex_color)
            self.canvas.paint_char('█', direction=self.canvas._heading)
            await asyncio.sleep(0.05)
            return True
        heading = self.canvas._heading
        for ch in arg:
            if ch == ' ':
                self.canvas.type_char(ch, direction=heading)
            else:
                self.canvas.paint_char(ch, direction=heading)
            await asyncio.sleep(0.02)
        return True

    async def _do_write_toggle(self, m) -> bool | None:
        self._write_on = m.group(1).lower() == 'on'
        if self._write_on:
            self._paint_on = False
        self.canvas._set_paint_mode(not self._write_on)
        return True

    async def _do_write_inline(self, m) -> bool | None:
        """write <text>: type each character as text at cursor."""
        heading = self.canvas._heading
        for ch in m.group(1):
            self.canvas.type_char(ch, direction=heading)
            await asyncio.sleep(0.02)
        return True

    async def _do_color(self, m) -> bool | None:
        """color <name/adj+name/key>: switch brush color."""
        color_arg = m.group(1).strip().lower()
        content = get_content()
        hex_color = content.get_color(color_arg)
        if not hex_color:
            mod = content.get_modified_color(color_arg)
            if mod:
                hex_color = mod[0]
        if not hex_color:
            candidate = get_key_color(color_arg)
            if candidate != "#AAAAAA":
                hex_color = candidate
        if not hex_color:
            corrected = fuzzy_match_small(color_arg, list(content.colors.keys()))
            if corrected:
                hex_color = content.get_color(corrected)
                self.corrections.append((f'color {color_arg}', f'color {corrected}'))
        if hex_color:
            self._apply_color(hex_color)
            return True
        return None

    async def _do_lift(self, m) -> bool | None:
        self._paint_on = not self._paint_on
        return True

    async def _do_pen_up(self, m) -> bool | None:
        self._paint_on = False
        return True

    async def _do_pen_down(self, m) -> bool | None:
        self._paint_on = True
        return True

    async def _do_spin(self, m) -> bool | None:
        self.canvas.turn('spin')
        await asyncio.sleep(0.05)
        return True

    async def _do_face(self, m) -> bool | None:
        """face <direction>: set heading absolutely."""
        arg = m.group(1).lower()
        if arg in _DIRECTION_VOCAB:
            self.canvas.turn(arg)
            await asyncio.sleep(0.05)
            return True
        corrected = fuzzy_match_small(arg, _DIRECTION_VOCAB)
        if corrected:
            self.corrections.append((f'face {arg}', f'face {corrected}'))
            self.canvas.turn(corrected)
            await asyncio.sleep(0.05)
            return True
        return None

    async def _do_turn(self, m) -> bool | None:
        """turn <direction/angle>: absolute for directions, spin for 90, etc."""
        arg = m.group(1).lower()
        valid = ('left', 'right', 'up', 'down', 'back', 'backward', 'around')
        if arg in valid or arg.isdigit():
            self.canvas.turn(arg)
            await asyncio.sleep(0.05)
            return True
        corrected = fuzzy_match_small(arg, _TURN_VOCAB)
        if corrected:
            self.corrections.append((f'turn {arg}', f'turn {corrected}'))
            self.canvas.turn(corrected)
            await asyncio.sleep(0.05)
            return True
        return None

    async def _do_forward(self, m) -> bool | None:
        distance = int(m.group(1)) if m.group(1) else 1
        distance = min(distance, 200)
        action = "paint" if self._paint_on else "move"
        self.canvas._use_heading_cursor = True
        self.canvas.execute_logo_command(action, self.canvas._heading, distance)
        await asyncio.sleep(0.05)
        return True

    async def _do_back(self, m) -> bool | None:
        """back/backward [N]: move opposite to current heading."""
        distance = int(m.group(1)) if m.group(1) else 1
        distance = min(distance, 200)
        opposite = _OPPOSITE[self.canvas._heading]
        action = "paint" if self._paint_on else "move"
        self.canvas._use_heading_cursor = True
        self.canvas.execute_logo_command(action, opposite, distance)
        await asyncio.sleep(0.05)
        return True

    async def _do_direction(self, m) -> bool | None:
        """left/right/up/down [N]: face direction + move N."""
        direction = m.group(1).lower()
        distance = int(m.group(2)) if m.lastindex >= 2 and m.group(2) else 1
        distance = min(distance, 200)
        if self.canvas._heading != direction:
            self.canvas._heading = direction
            self.canvas._mark_cursor_dirty()
            self.canvas.refresh()
        self.canvas._use_heading_cursor = True
        action = "paint" if self._paint_on else "move"
        self.canvas.execute_logo_command(action, direction, distance)
        await asyncio.sleep(0.05)
        return True

    # ------------------------------------------------------------------
    # Resolution pipeline (for unmatched text)
    # ------------------------------------------------------------------

    def _resolve(self, text: str) -> bool:
        """Try to interpret unrecognized text. Returns True if handled."""
        words = text.strip().split()
        if not words:
            return False

        # 1. Try to match a color from the start, dispatch any remainder.
        #    Handles: "blue", "dark blue", "blue go 5", "dark blue go 5"
        color_hex, words_used = self._resolve_leading_color(words)
        if color_hex:
            self._apply_color(color_hex)
            color_text = " ".join(words[:words_used])
            remainder = " ".join(words[words_used:])
            if remainder:
                self.corrections.append((text, f"{color_text}, {remainder}"))
                asyncio.ensure_future(self._dispatch(remainder))
            else:
                self.corrections.append((text, color_text))
            return True

        # 2. Fuzzy command keyword (e.g. "forwrd 10" -> "forward 10")
        corrected_kw = fuzzy_match_small(words[0].lower(), _COMMAND_VOCAB)
        if corrected_kw and corrected_kw != words[0].lower():
            corrected_text = corrected_kw + (" " + " ".join(words[1:]) if len(words) > 1 else "")
            self.corrections.append((text, corrected_text))
            asyncio.ensure_future(self._dispatch(corrected_text, _resolving=True))
            return True

        return False

    def _resolve_leading_color(self, words: list[str]) -> tuple[str | None, int]:
        """Try to match a color from the start of words.

        Returns (hex_color, number_of_words_consumed) or (None, 0).
        Tries: exact color, modified color (adjectives + color), fuzzy color.
        """
        from .color_mixing import COLOR_ADJECTIVES

        content = get_content()

        # Count leading adjectives (dark, bright, light, ...)
        adj_count = 0
        for w in words:
            if w.lower() in COLOR_ADJECTIVES:
                adj_count += 1
            else:
                break

        # Try exact color on the word after adjectives
        if adj_count < len(words):
            color_word = words[adj_count].lower()
            hex_color = content.get_color(color_word)
            if hex_color:
                if adj_count > 0:
                    mod = content.get_modified_color(" ".join(words[:adj_count + 1]))
                    if mod:
                        return mod[0], adj_count + 1
                return hex_color, adj_count + 1

        # Try fuzzy color on the first non-adjective word
        if adj_count < len(words):
            color_word = words[adj_count].lower()
            corrected = fuzzy_match_small(color_word, list(content.colors.keys()))
            if corrected:
                hex_color = content.get_color(corrected)
                if hex_color:
                    return hex_color, adj_count + 1

        return None, 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _apply_color(self, hex_color: str) -> None:
        """Switch brush to given color and enter paint mode."""
        self.canvas._last_key_color = hex_color
        self.canvas._paint_mode = True
        self._paint_on = True
        self._write_on = False
        self.canvas._mark_cursor_dirty()
        from .rooms.art_room import PaintModeChanged
        self.canvas.post_message(PaintModeChanged(True, hex_color))
        self.canvas.refresh()
