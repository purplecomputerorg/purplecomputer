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
    return [s.strip() for s in re.split(r'(?<!\.)\.(?!\.)|[,;|]', text) if s.strip()]


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


def parse_lines(lines: list[str], split_commands: bool = True) -> list[dict]:
    """Parse lines into a list of commands.

    Handles inline `repeat N cmd1, cmd2` syntax.
    Clause separators (, . ; |) split a line into multiple commands.
    Returns a flat list of command dicts with 'type' and params.

    When `split_commands` is True (default, used by Music/Play), each clause is
    further split at command-keyword boundaries. Art passes False so its
    nearest-anchor classifier sees whole clauses and can bind colors between
    motions to the right anchor.
    """
    result = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Inline repeat: "repeat N cmd1, cmd2" or "repeat cmd1, cmd2" (default 2)
        # Optional colon after count: "repeat 3: cat, dog"
        m = re.match(r'^repeat\s+(\d+):?\s+(.+)$', line, re.IGNORECASE)
        if m:
            count, body_text = int(m.group(1)), m.group(2)
        else:
            m = re.match(r'^repeat\s+(.+)$', line, re.IGNORECASE)
            if m:
                count, body_text = 2, m.group(1)
        if m:
            count = max(1, min(count, 100))
            sub_lines = _split_clauses(body_text)
            body_cmds = parse_lines(sub_lines, split_commands=split_commands)
            result.append({'type': 'repeat', 'count': count, 'body': body_cmds})
            continue

        clauses = _split_clauses(line)
        parts = []
        for clause in clauses:
            parts.extend(_split_commands(clause) if split_commands else [clause])
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
    Handles `repeat` as a command keyword (with fuzzy correction).
    Results are collected and returned.
    """

    _KEYWORD_VOCAB = ['repeat']

    def __init__(self, evaluator):
        self.evaluator = evaluator
        self.corrections: list[tuple[str, str]] = []

    def run(self, lines: list[str]) -> list[str]:
        """Run code and return list of result strings."""
        # Fuzzy-correct repeat keyword before parsing
        corrected_lines = []
        for line in lines:
            corrected_lines.append(self._fuzzy_correct(line))

        cmds = parse_lines(corrected_lines)
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

    def _fuzzy_correct(self, line: str) -> str:
        """Fuzzy-correct command keywords, matching music/art runner pattern."""
        words = line.strip().split(None, 1)
        if not words or len(words[0]) < 3:
            return line
        first = words[0].lower()
        if first in ('repeat',):
            return line
        from .fuzzy import fuzzy_match_small
        corrected = fuzzy_match_small(first, self._KEYWORD_VOCAB, cutoff=0.7)
        if corrected and corrected != first:
            new_line = corrected + (' ' + words[1] if len(words) > 1 else '')
            self.corrections.append((line.strip(), new_line))
            return new_line
        return line


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

    async def _run_command_table(self, text: str) -> bool:
        """Run the first matching command handler. Returns True if a command
        keyword matched, claiming the line, whether or not the handler could
        act on its argument. Note playing is only a fallback for non-command
        lines, so a recognized keyword is never sounded out letter by letter."""
        for pattern, handler_name in self._COMMANDS:
            m = pattern.match(text)
            if m:
                await getattr(self, handler_name)(m)
                return True
        return False

    async def _dispatch(self, text: str) -> None:
        self._original_text = text  # Track for correction display
        self._correction_final = ""  # Reset per-dispatch
        self._suppress_handler_corrections = False

        # Stage 1: a recognized command keyword claims the line.
        if await self._run_command_table(text):
            return

        # Stage 2: fuzzy-correct a misspelled keyword (e.g. "chooze marimba"),
        # then retry the table. A keyword may correct to a speed word
        # (fast/slow), which has no table entry; record the fix and let stage 3
        # parse the speed prefix.
        words = text.strip().split(None, 1)
        if words and len(words[0]) >= 3:
            from .fuzzy import fuzzy_match_small
            corrected_kw = fuzzy_match_small(words[0].lower(), self._KEYWORD_VOCAB, cutoff=0.7)
            if corrected_kw and corrected_kw != words[0].lower():
                corrected = corrected_kw + (' ' + words[1] if len(words) > 1 else '')
                self._suppress_handler_corrections = True
                if await self._run_command_table(corrected):
                    self.corrections.append((text, self._build_final_correction(corrected)))
                    return
                self.corrections.append((text, corrected))

        # Stage 3: not a command, play the line as notes.
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

    def _resolve_leading_instrument(self, words: list[str]) -> tuple[str | None, int]:
        """Resolve an instrument from the first word. Instrument names and
        aliases are single words, so anything after the first word is notes to
        play, mirroring how the Art room peels a leading color off a line."""
        if not words:
            return None, 0
        resolved = self._resolve_instrument(words[0])
        return (resolved, 1) if resolved else (None, 0)

    async def _do_instrument(self, m) -> bool | None:
        keyword = m.group(0).split()[0]
        words = m.group(1).split()
        resolved, used = self._resolve_leading_instrument(words)
        if not (resolved and self.set_instrument):
            return None
        if resolved.lower() != words[0].lower():
            self._correction_final = f'{keyword} {resolved.lower()}'
            if not self._suppress_handler_corrections:
                self.corrections.append((self._original_text, self._correction_final))
        self.set_instrument(resolved.lower())
        await asyncio.sleep(0.1)
        remainder = " ".join(words[used:])
        if remainder:
            # Re-dispatch resets the per-line correction fields, so save and
            # restore them for the caller (stage 2 reads _correction_final).
            saved = (self._original_text, self._correction_final,
                     self._suppress_handler_corrections)
            await self._dispatch(remainder)
            (self._original_text, self._correction_final,
             self._suppress_handler_corrections) = saved
        return True

    async def _do_play(self, m) -> bool | None:
        arg = m.group(1).strip()
        resolved = self._resolve_instrument(arg)
        if resolved and self.set_instrument:
            if resolved.lower() != arg.lower():
                self._correction_final = f'play {resolved.lower()}'
                if not self._suppress_handler_corrections:
                    self.corrections.append((self._original_text, self._correction_final))
            self.set_instrument(resolved.lower())
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


from .fuzzy import fuzzy_match_small


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

# Self-directed motion verbs: the verb itself determines how the heading turns
# (None = leave heading as-is). turn/face are handled separately because they
# take a direction argument. back/backward additionally move opposite the
# heading; every other verb moves along it.
_VERB_TURN = {
    'forward': None, 'go': None, 'move': None, 'walk': None, 'step': None,
    'back': None, 'backward': None,
    'left': 'left', 'right': 'right', 'up': 'up', 'down': 'down',
    'spin': 'spin', 'rotate': 'spin',
}
# Translate verbs move one step when given no distance and no text; rotation
# (spin/rotate) and turn/face only move when a distance is supplied.
_DEFAULT_MOVE_VERBS = frozenset(_VERB_TURN) - {'spin', 'rotate'}


class ArtCodeRunner:
    """Run code in the Art room context.

    Uses a command table for dispatch: each entry is a (regex, handler) pair
    checked in priority order. Unrecognized text goes through a resolution
    pipeline (bare color, modified color, fuzzy match) before giving up.
    Corrections are tracked for UI feedback.
    """

    # Explicit-command table: (compiled_regex, handler_method_name). Motion is
    # handled by the bag-of-tokens classifier (`_classify_motion`) one stage
    # later, so any text not matched here goes through that pipeline.
    _COMMANDS = [
        (re.compile(r'^paint\s+(on|off)\s*$', re.I), '_do_paint_toggle'),
        (re.compile(r'^paint\s+(.+?)\s*$', re.I), '_do_paint_inline'),
        (re.compile(r'^write\s+(on|off)\s*$', re.I), '_do_write_toggle'),
        (re.compile(r'^write\s+(.+?)\s*$', re.I), '_do_write_inline'),
        (re.compile(r'^color\s+(.+?)\s*$', re.I), '_do_color'),
        (re.compile(r'^lift\s*$', re.I), '_do_lift'),
        (re.compile(r'^(?:pen\s*up|penup)\s*$', re.I), '_do_pen_up'),
        (re.compile(r'^(?:pen\s*down|pendown)\s*$', re.I), '_do_pen_down'),
    ]

    def __init__(self, canvas):
        self.canvas = canvas
        self.corrections: list[tuple[str, str]] = []

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(self, lines: list[str], paint: bool = True) -> None:
        """Run art code. Corrections are stored in self.corrections."""
        expanded = []
        for line in lines:
            expanded.extend(self._peel_color_before_repeat(line))
        cmds = parse_lines(expanded, split_commands=False)
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

    def _peel_color_before_repeat(self, line: str) -> list[str]:
        """Split a leading color off when it precedes `repeat` so the loop body
        paints in that color: "purple repeat 4 forward 8 spin". `repeat` is only
        a loop at the start of a line, so the color must become its own line."""
        words = line.split()
        _, used = self._resolve_leading_color(words)
        if used and used < len(words) and words[used].lower() == 'repeat':
            return [" ".join(words[:used]), " ".join(words[used:])]
        return [line]

    async def _dispatch(self, text: str, _resolving: bool = False) -> None:
        """Try explicit commands, then motion classifier, then resolution."""
        # Stage 1: explicit-command table (paint/write/color/lift/pen).
        for pattern, handler_name in self._COMMANDS:
            m = pattern.match(text)
            if m:
                handler = getattr(self, handler_name)
                if await handler(m):
                    return

        # Stage 2: motion classifier. Fires when the line has any direction or
        # motion verb. Tokens (color, number, leftover text) are assigned to
        # the nearest anchor — so "green 10 down", "10 green down", and
        # "red down 5 blue right 5" all just work.
        plans = self._classify_motion(text)
        if plans:
            await self._execute_motion_plans(plans)
            return

        # Stage 3: write mode types characters (that's its purpose).
        if self._write_on:
            await self._emit_text(text, paint=False)
            return

        # Stage 4: resolution pipeline (only on first pass). Handles bare
        # colors and `green 5`-style no-anchor lines via leading-color peel,
        # plus fuzzy verb correction (`forwrd 10` → `forward 10`).
        if not _resolving:
            if self._resolve(text):
                return

        # Stage 5: paint mode paints each character (like interactive mode).
        if self._paint_on:
            await self._emit_text(text, paint=True)

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
        await self._emit_text(arg, paint=True)
        return True

    async def _do_write_toggle(self, m) -> bool | None:
        self._write_on = m.group(1).lower() == 'on'
        if self._write_on:
            self._paint_on = False
        self.canvas._set_paint_mode(not self._write_on)
        return True

    async def _do_write_inline(self, m) -> bool | None:
        """write <text>: type each character as text at cursor."""
        await self._emit_text(m.group(1), paint=False)
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

    def _match_turn_dir(self, verb: str, word: str) -> str | None:
        """Resolve a turn/face direction argument (exact or fuzzy). Digits and
        unmatched words return None so the word falls through to other roles."""
        word = word.lower()
        if word.isdigit():
            return None
        vocab = _TURN_VOCAB if verb == 'turn' else _DIRECTION_VOCAB
        if word in vocab:
            return word
        corrected = fuzzy_match_small(word, vocab)
        if corrected:
            self.corrections.append((f'{verb} {word}', f'{verb} {corrected}'))
        return corrected

    # ------------------------------------------------------------------
    # Motion classifier: bag-of-tokens with nearest-anchor assignment
    # ------------------------------------------------------------------
    #
    # The line is tokenized into typed tokens (anchor / color / number / text).
    # Every motion verb or direction word becomes an "anchor"; each non-anchor
    # token is assigned to the nearest anchor by token index (ties favor the
    # earlier anchor). Consecutive text tokens form one phrase bound to the
    # previous anchor (or the first anchor if the phrase precedes all of them).
    # The result is one motion plan per anchor, executed in order.

    def _classify_motion(self, text: str) -> list[dict] | None:
        """Return a list of motion plans for `text`, or None if no anchor."""
        words = text.split()
        if not words:
            return None
        tokens = self._tokenize_motion(words)
        anchor_idxs = [j for j, t in enumerate(tokens) if t[0] == 'anchor']
        if not anchor_idxs:
            return None

        plans = []
        for a in anchor_idxs:
            verb, direction = tokens[a][1]
            plans.append({'verb': verb, 'dir': direction, 'dist': None,
                          'color': None, '_leftover': []})

        def nearest(j: int) -> int:
            best, best_d = 0, None
            for pi, a in enumerate(anchor_idxs):
                d = abs(j - a)
                if best_d is None or d < best_d:
                    best, best_d = pi, d
            return best

        # First pass: numbers and colors → nearest anchor.
        for j, tok in enumerate(tokens):
            if tok[0] == 'number':
                plan = plans[nearest(j)]
                if plan['dist'] is None:
                    plan['dist'] = tok[1]
            elif tok[0] == 'color':
                plans[nearest(j)]['color'] = tok[1]

        # Second pass: consecutive text tokens become one phrase bound to the
        # previous anchor (or the first if none precedes).
        i = 0
        while i < len(tokens):
            if tokens[i][0] != 'text':
                i += 1
                continue
            start = i
            while i < len(tokens) and tokens[i][0] == 'text':
                i += 1
            prev = next((a for a in reversed(anchor_idxs) if a < start), anchor_idxs[0])
            phrase = ' '.join(tokens[k][1] for k in range(start, i))
            plans[anchor_idxs.index(prev)]['_leftover'].append((start, phrase))

        for plan in plans:
            parts = sorted(plan.pop('_leftover'), key=lambda x: x[0])
            plan['leftover'] = ' '.join(p for _, p in parts)
        return plans

    def _tokenize_motion(self, words: list[str]) -> list[tuple]:
        """Tokenize words into anchor / number / color / text tokens.

        Anchor value is (verb, direction|None). `turn`/`face` greedily absorb
        the next word as a direction when it resolves to one (else direction
        stays None and falls through to spin/face-noop behavior in execute).
        """
        tokens: list[tuple] = []
        i = 0
        while i < len(words):
            w = words[i].lower()
            if w in ('turn', 'face'):
                direction = None
                if i + 1 < len(words):
                    direction = self._match_turn_dir(w, words[i + 1])
                if direction:
                    tokens.append(('anchor', (w, direction)))
                    i += 2
                else:
                    tokens.append(('anchor', (w, None)))
                    i += 1
                continue
            if w in _VERB_TURN:
                direction = w if w in _DIRECTION_VOCAB else _VERB_TURN[w]
                tokens.append(('anchor', (w, direction)))
                i += 1
                continue
            if w.isdigit():
                tokens.append(('number', min(int(w), 200)))
                i += 1
                continue
            hex_c, used = self._resolve_leading_color(words[i:])
            if hex_c:
                tokens.append(('color', hex_c))
                i += used
                continue
            tokens.append(('text', words[i]))
            i += 1
        return tokens

    async def _execute_motion_plans(self, plans: list[dict]) -> None:
        """Execute motion plans in order. Color is applied before the move so
        the stroke paints in that color; brush color carries forward."""
        for plan in plans:
            verb = plan['verb']
            direction = plan['dir']
            distance = plan['dist']
            leftover = plan['leftover']

            # Bare `turn` with no direction spins 90; bare `face` is a no-op
            # heading-wise (matches pre-refactor `_heading_plan`).
            if verb == 'turn' and direction is None:
                direction = 'spin'

            move_opposite = verb in ('back', 'backward')

            if distance is None and not leftover and verb in _DEFAULT_MOVE_VERBS:
                distance = 1

            if plan['color']:
                self._apply_color(plan['color'])
            if direction:
                self.canvas.turn(direction)
            if distance:
                heading = self.canvas._heading
                move_dir = _OPPOSITE[heading] if move_opposite else heading
                self.canvas._use_heading_cursor = True
                action = "paint" if self._paint_on else "move"
                self.canvas.execute_logo_command(action, move_dir, distance)
            if leftover:
                await self._emit_text(leftover, paint=self._paint_on)
            await asyncio.sleep(0.05)

    async def _emit_text(self, text: str, paint: bool) -> None:
        """Emit each character in the current heading direction. When painting,
        spaces still advance without painting; when not, every char is typed."""
        heading = self.canvas._heading
        for ch in text:
            if paint and ch != ' ':
                self.canvas.paint_char(ch, direction=heading)
            else:
                self.canvas.type_char(ch, direction=heading)
            await asyncio.sleep(0.02)

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
            remainder = " ".join(words[words_used:])
            if remainder:
                # Bare number after color → forward N (e.g. "blue 5" → 5 blue squares).
                # Splitting a color off its remainder is normalization, not a fix, so
                # it records no correction; a real fix surfaces from the re-dispatch.
                if re.match(r'^\d+$', remainder):
                    asyncio.ensure_future(self._dispatch(f"forward {remainder}"))
                else:
                    asyncio.ensure_future(self._dispatch(remainder))
            return True

        # 2. Fuzzy command keyword (e.g. "forwrd 10" -> "forward 10"), but never
        #    on a real word: "tree" overlaps "repeat" enough to fool difflib, so
        #    a known emoji word must be painted, not coerced into a command.
        first = words[0].lower()
        corrected_kw = None if get_content().exact_emoji(first) else \
            fuzzy_match_small(first, _COMMAND_VOCAB)
        if corrected_kw and corrected_kw != first:
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
            hex_color = content.exact_color(color_word)
            if hex_color:
                if adj_count > 0:
                    mod = content.get_modified_color(" ".join(words[:adj_count + 1]))
                    if mod:
                        return mod[0], adj_count + 1
                return hex_color, adj_count + 1

        # Tight fuzzy color (DL distance), but never on a real word: an exact
        # emoji word ("tree", "school") must be painted as letters, not coerced
        # into a color it merely shares letters with. Loose matching for bare
        # words is intentionally absent here; it lives in the `color X` command.
        if adj_count < len(words):
            color_word = words[adj_count].lower()
            if not content.exact_emoji(color_word):
                if hex_color := content.fuzzy_color(color_word):
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
        self.canvas._post_paint_mode_changed()
        self.canvas.refresh()
