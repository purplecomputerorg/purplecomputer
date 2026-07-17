"""
Play Room: Math and Emoji REPL for Kids

IPython-style interface:
- Ask → user types input
- Answer: shows result

Features:
- Basic math: 2 + 2, 3 x 4, 10 - 5
- Word synonyms: times, plus, minus
- Emoji display: typing "cat" shows 🐱
- Emoji math: 3 * cat produces 🐱🐱🐱
- Typo tolerance: long math expressions forgive accidental keystrokes
- Speech: add ! anywhere (e.g., "cat!") or prefix with "say"/"talk"
- Command recall: Enter on empty populates input with last command
- History (up/down arrows)
- Emoji autocomplete (Tab to accept)
- Cursor navigation (left/right arrows)
"""

from textual.widgets import Static, Input
from textual.widget import Widget
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.app import ComposeResult
from textual import events
from textual.message import Message
from textual.strip import Strip
from rich.markup import escape as rich_escape
from rich.segment import Segment
from rich.style import Style
import re
import unicodedata


def _cell_width(ch: str) -> int:
    """Visual cell width of one char in a monospace terminal (1 or 2)."""
    return 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1

from ..constants import ICON_ROBOT, HOLD_OR_TAP_THRESHOLD
from ..content import singularize

from ..content import get_content
from ..code_input import (
    WordHighlighter, CodeInput, InputPrompt,
    AutocompleteHint, RecallHint, ExampleHint,
)
from ..keyboard import (
    KeyRepeatSuppressor, HoldOrTap,
    CharacterAction, NavigationAction, ControlAction,
)
from ..color_mixing import mix_colors_paint, get_color_name_approximation
from ..scrolling import scroll_widget
from .art_room import get_key_color, PaintModeChanged


def _strip_markup(text: str) -> str:
    """Strip Rich markup tags like [#FFF on #000] and [/] from text."""
    return re.sub(r'\[[^\]]*\]', '', text)


# Max results spoken aloud for a repeat command (display shows them all)
SPEAK_REPEAT_CAP = 5


def _pad_narrow_emoji(text: str) -> str:
    """Always add a space after narrow+FE0F emoji to compensate for terminal width.

    Alacritty (and most terminals) only advance the cursor 1 cell for emoji like
    ❤️ (U+2764+FE0F) even though the glyph renders across 2 cells. The first
    space after a narrow emoji gets visually consumed by the glyph overflow, so
    we always insert one. If there's already a space, the double-space ensures
    one is visible. Skips inside Rich markup tags like [on #hex].
    """
    if '\ufe0f' not in text:
        return text
    result = []
    i = 0
    while i < len(text):
        # Skip Rich markup tags
        if text[i] == '[':
            end = text.find(']', i)
            if end != -1:
                result.append(text[i:end + 1])
                i = end + 1
                continue
        result.append(text[i])
        # Always insert a space after FE0F to absorb glyph overflow
        if text[i] == '\ufe0f':
            result.append(' ')
        i += 1
    return ''.join(result)


def _contrast_color(hex_color: str) -> str:
    """Return black or white for readable text on the given background."""
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000000" if luminance > 0.5 else "#FFFFFF"


class KeyboardOnlyScroll(ScrollableContainer):
    """ScrollableContainer that ignores mouse/trackpad scroll events"""

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()
        event.prevent_default()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()
        event.prevent_default()


class HistoryLine(Static):
    """A line in the REPL history (either Ask or Answer)"""

    # Theme colors for ask/answer arrows
    ASK_ARROW_DARK = "#c4a0e8"
    ASK_ARROW_LIGHT = "#7a5a9e"
    ANSWER_ARROW_DARK = "#ffffff"
    ANSWER_ARROW_LIGHT = "#3a2a50"

    # Speech states for the indicator prefix
    SPEECH_NONE = ""       # no speech
    SPEECH_GENERATING = "generating"  # TTS synthesizing
    SPEECH_PLAYING = "playing"        # audio playing
    SPEECH_FILTERED = "filtered"      # blocked by profanity filter

    def __init__(self, text: str, line_type: str = "ask", speaking: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.text = _pad_narrow_emoji(text)
        self.line_type = line_type  # "ask" or "answer"
        self.speaking = speaking
        self.speech_state = self.SPEECH_GENERATING if speaking else self.SPEECH_NONE
        if line_type == "ask":
            self.add_class("ask")

    def _is_dark(self) -> bool:
        try:
            return "dark" in self.app.theme
        except Exception:
            return True

    @staticmethod
    def _tokenize_markup(text: str) -> list[tuple[str, int]]:
        """Split Rich markup into (token, visual_width) pairs.

        Markup blocks with non-whitespace inner content are split at whitespace
        so a long colored span (e.g. 300 dots inside one [purple]...[/]) wraps
        at bead boundaries. All-whitespace blocks (color swatches like
        '[on #ABC]  [/]') stay intact.
        """
        tokens = []
        i = 0
        while i < len(text):
            if text[i] == '[':
                end = text.find('[/]', i)
                if end != -1:
                    block = text[i:end + 3]
                    m = re.match(r'(\[[^\]]*\])(.*)\[/\]$', block, re.DOTALL)
                    if m:
                        open_tag, inner = m.group(1), m.group(2)
                        if inner.strip() == '':
                            width = sum(_cell_width(c) for c in inner)
                            tokens.append((block, width))
                        else:
                            for part in re.split(r'(\s+)', inner):
                                if not part:
                                    continue
                                width = sum(_cell_width(c) for c in part)
                                tokens.append((f"{open_tag}{part}[/]", width))
                        i = end + 3
                        continue
            ch = text[i]
            width = _cell_width(ch)
            tokens.append((ch, width))
            i += 1
        return tokens

    def _wrap_with_arrows(self, text: str, prefix: str, arrow_color: str) -> str:
        """Wrap text under a prefix; continuation lines are indented (no arrow).

        Breaks at token boundaries; leading whitespace on a wrapped line is dropped.
        `arrow_color` is kept for API compatibility but no longer used.
        """
        width = self.size.width
        if width <= 0:
            width = 108  # fallback

        prefix_len = sum(_cell_width(c) for c in re.sub(r'\[[^\]]*\]', '', prefix))
        cont_prefix = ' ' * prefix_len
        cont_len = prefix_len

        tokens = self._tokenize_markup(text)
        lines = []
        current_line = prefix
        current_width = prefix_len
        just_wrapped = False

        for token, tw in tokens:
            if just_wrapped and token.strip() == '':
                continue
            just_wrapped = False
            if current_width + tw > width and current_width > (prefix_len if not lines else cont_len):
                lines.append(current_line)
                current_line = cont_prefix
                current_width = cont_len
                just_wrapped = True
                if token.strip() == '':
                    continue
            current_line += token
            current_width += tw

        if current_line:
            lines.append(current_line)

        return '\n'.join(lines)

    def render(self) -> str:
        dark = self._is_dark()
        if self.line_type == "code_header":
            # Code results header: no "Ask →" prefix, just bold text
            # Extra newline above for visual separation from previous output
            answer_color = self.ANSWER_ARROW_DARK if dark else self.ANSWER_ARROW_LIGHT
            prefix = f"{ICON_ROBOT}  [{answer_color}]→[/] [bold {answer_color}]{self.text}[/] "
            return f"\n{prefix}"
        elif self.line_type == "ask":
            ask_color = self.ASK_ARROW_DARK if dark else self.ASK_ARROW_LIGHT
            prefix = f"[bold {ask_color}]Ask →[/] "
            return self._wrap_with_arrows(rich_escape(self.text), prefix, ask_color)
        else:
            answer_color = self.ANSWER_ARROW_DARK if dark else self.ANSWER_ARROW_LIGHT
            lines = self.text.split('\n')
            if self.speech_state == self.SPEECH_GENERATING:
                speaker = " ··"
            elif self.speech_state == self.SPEECH_PLAYING:
                speaker = " 🔊"
            elif self.speech_state == self.SPEECH_FILTERED:
                speaker = " 🔇"
            else:
                speaker = "   "
            first_prefix = f"{speaker} [{answer_color}]→[/] "
            result = [self._wrap_with_arrows(lines[0], first_prefix, answer_color)]
            for line in lines[1:]:
                if line.strip():
                    cont_prefix = f"    [{answer_color}]→[/] "
                    result.append(self._wrap_with_arrows(line, cont_prefix, answer_color))
                else:
                    result.append("")
            return '\n'.join(result)


class ColorResultLine(Widget):
    """
    A color result display showing component colors and the mixed result.

    Shows: [color1] [color2] → [result swatch]
    With a compact 3x6 result swatch.

    Uses render_line() with Strip/Segment for proper background coloring
    (see CLAUDE.md for the workaround details).
    """

    DEFAULT_CSS = """
    ColorResultLine {
        width: 100%;
        height: 4;
        margin: 0 0;
        padding: 0;
    }
    """

    SWATCH_WIDTH = 6  # Width of the result swatch in characters
    SWATCH_HEIGHT = 3  # Height of the result swatch
    COMPONENT_WIDTH = 2  # Width of each component color box

    # Surface colors for dark and light themes
    SURFACE_DARK = "#2a1845"
    SURFACE_LIGHT = "#e8daf0"
    ARROW_DARK = "#ffffff"
    ARROW_LIGHT = "#3a2a50"

    def __init__(self, hex_color: str, color_name: str, component_colors: list[str] = None, speaking: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._hex_color = hex_color
        self._color_name = color_name
        self._component_colors = component_colors or []
        self._speaking = speaking
        self._speech_state = HistoryLine.SPEECH_GENERATING if speaking else HistoryLine.SPEECH_NONE

    def _get_surface_color(self) -> str:
        """Get surface color based on current theme."""
        try:
            is_dark = "dark" in self.app.theme
            return self.SURFACE_DARK if is_dark else self.SURFACE_LIGHT
        except Exception:
            return self.SURFACE_DARK

    def _is_dark_theme(self) -> bool:
        """Check if current theme is dark."""
        try:
            return "dark" in self.app.theme
        except Exception:
            return True

    def render_line(self, y: int) -> Strip:
        """Render each line of the color result (mixed colors only, 3x6 swatch without name)"""
        width = self.size.width
        if width <= 0:
            width = 40

        # Get theme-aware colors
        surface = self._get_surface_color()
        surface_style = Style(bgcolor=surface)
        is_dark = self._is_dark_theme()
        arrow_color = self.ARROW_DARK if is_dark else self.ARROW_LIGHT
        triangle_style = Style(color=arrow_color, bgcolor=surface)

        # Show component color boxes (multiple components, or single that differs from result)
        show_components = (len(self._component_colors) > 1 or
            (len(self._component_colors) == 1 and
             self._component_colors[0].upper() != self._hex_color.upper()))

        # Line 0: Show component colors and arrow to result
        if y == 0:
            if self._speech_state == HistoryLine.SPEECH_GENERATING:
                segments = [Segment(" ·· ", surface_style), Segment("→ ", triangle_style)]
            elif self._speech_state == HistoryLine.SPEECH_PLAYING:
                segments = [Segment(" 🔊 ", surface_style), Segment("→ ", triangle_style)]
            elif self._speech_state == HistoryLine.SPEECH_FILTERED:
                segments = [Segment(" 🔇 ", surface_style), Segment("→ ", triangle_style)]
            else:
                segments = [Segment("    ", surface_style), Segment("→ ", triangle_style)]

            if show_components:
                for i, comp_hex in enumerate(self._component_colors):
                    # Add small colored box for each component
                    comp_style = Style(bgcolor=comp_hex)
                    segments.append(Segment("  ", comp_style))  # 2-char wide box
                    if i < len(self._component_colors) - 1:
                        segments.append(Segment(" ", surface_style))  # space between

                # Arrow to result
                segments.append(Segment(" → ", Style(color=arrow_color, bgcolor=surface)))

            # Start of result swatch (top row). No name label
            result_style = Style(bgcolor=self._hex_color)
            segments.append(Segment(" " * self.SWATCH_WIDTH, result_style))

            return Strip(segments)

        # Lines 1-2: Continue the result swatch
        elif y < self.SWATCH_HEIGHT:
            segments = [Segment("      ", surface_style)]  # 6 chars to align with "    → "

            # Add spacing for component boxes if present
            if show_components:
                # Each component is 2 chars + 1 space between
                comp_width = len(self._component_colors) * 2 + (len(self._component_colors) - 1)
                segments.append(Segment(" " * comp_width, surface_style))
                segments.append(Segment("   ", surface_style))  # " → " spacing

            # Result swatch continuation
            result_style = Style(bgcolor=self._hex_color)
            segments.append(Segment(" " * self.SWATCH_WIDTH, result_style))

            return Strip(segments)

        # Line 3: Empty line for spacing
        else:
            return Strip([Segment(" " * width, surface_style)])

    def _get_contrast_color(self, hex_color: str) -> str:
        """Get a contrasting text color (black or white) for readability"""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return "#000000" if luminance > 0.5 else "#FFFFFF"


def _play_validator(word: str) -> bool:
    """Check if a word is a valid emoji or color name."""
    return get_content().is_valid_word(word)


def _play_autocomplete(last_word: str, full_text: str = "") -> list[tuple[str, str, str]]:
    """Search emoji/color words for autocomplete suggestions.

    A resolvable word is shown the way it will actually render (exact-first), so
    the hint for "white" is a color swatch, not the fuzzy ✍️ emoji. Otherwise
    fall back to ranked prefix matches.
    """
    content = get_content()
    r = content.resolve(last_word)
    if r.kind == "color":
        return [(last_word, r.value, "")]
    if r.kind == "emoji":
        return [(last_word, "", r.value)]
    return [(w, c, e) for w, c, e in content.search_words(last_word)]


class InlineInput(CodeInput):
    """Play room input: emoji/color autocomplete with math mode."""

    class Submitted(Message, bubble=True):
        """Message sent when user presses Enter."""
        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(
            highlighter=WordHighlighter(_play_validator),
            autocomplete_fn=_play_autocomplete,
            math_mode=True,
            **kwargs,
        )
        self._repeat_suppressor = KeyRepeatSuppressor()

    def action_scroll_up(self) -> None:
        try:
            scroll_widget(self.app.query_one("#history-scroll"), -1)
        except Exception:
            pass

    def action_scroll_down(self) -> None:
        try:
            scroll_widget(self.app.query_one("#history-scroll"), 1)
        except Exception:
            pass


PLAY_HINTS = [
    "Try: cat  \u2022  2 + 2  \u2022  trex!",
    "Try: say hi  (or hello!, both speak aloud)  \u2022  red sun",
    "Try: red + blue!  \u2022  5 dinos",
    "Try: asdfghjkl  \u2022  say yellow",
    "Try: three cats!  \u2022  pink fish",
    "Try: say 4 + 3 cats  \u2022  red + yellow!",
    "Try: I love trex  \u2022  blue frog!",
    "Try: 4 birds + 2 owls  \u2022  say purple  (speaks out loud)",
    "Try: cat times 5  \u2022  light pink unicorn!",
    "Try: I have 5 dinos!  \u2022  say 5 x 5 ducks",
    "Try: pink + purple  \u2022  dark green trex!",
    "Try: say wow!  \u2022  2 red, 3 blue",
    "Try: orange + white  \u2022  rainbow mermaid!  (end with ! to speak it)",
    "Try: 20 19 18 17...  \u2022  bright blue dinosaur!",
    "Try: dinos ... 5  \u2022  2 4 6 8...",
]


class ExpressionEvaluated(Message, bubble=True):
    """Emitted when a play mode expression is evaluated. Used by code panel."""
    def __init__(self, expression: str, result: str):
        super().__init__()
        self.expression = expression
        self.result = result


class PlayMode(Vertical):
    """
    Play room: IPython-style REPL interface for kids.
    """

    DEFAULT_CSS = """
    PlayMode {
        width: 100%;
        height: 100%;
        background: $surface;
    }

    #history-scroll {
        width: 100%;
        height: 1fr;
        border: none;
        scrollbar-gutter: stable;
        padding: 1 1;
        background: $surface;
    }

    HistoryLine {
        width: 100%;
        height: auto;
        padding: 0 0;
        margin: 0;
        background: $surface;
    }

    HistoryLine.ask {
        margin-top: 1;
    }

    #bottom-area {
        dock: bottom;
        width: 100%;
        height: auto;
        padding: 0 1;
        background: $surface;
    }

    #input-row {
        width: 100%;
        height: 1;
        layout: horizontal;
    }

    #autocomplete-hint {
        margin-left: 0;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.evaluator = SimpleEvaluator()
        # Track last command for recall (Enter on empty)
        self._last_input_text: str = ""
        # Space hold: tap inserts space, hold is no-op (consistent with other rooms)
        self._space_hold = HoldOrTap(hold_seconds=HOLD_OR_TAP_THRESHOLD)

    def compose(self) -> ComposeResult:
        yield KeyboardOnlyScroll(id="history-scroll")
        with Vertical(id="bottom-area"):
            with Horizontal(id="input-row"):
                yield InputPrompt(id="input-prompt")
                yield InlineInput(id="play-input")
            yield RecallHint(id="play-recall-hint")
            yield AutocompleteHint(id="autocomplete-hint")
            yield ExampleHint(hints=PLAY_HINTS, id="play-example-hint")

    def on_mount(self) -> None:
        """Focus the input when mode loads"""
        self.query_one("#play-input").focus()

    def evaluate_for_panel(self, expression: str) -> str:
        """Evaluate an expression for the code panel. Returns result string."""
        result = self.evaluator.evaluate(expression)
        if not result:
            return "?"
        # Strip Rich markup for clean display
        return _strip_markup(result)

    def _update_recall_hint(self) -> None:
        """Update the recall hint with last command and show/hide based on input state."""
        try:
            recall = self.query_one("#play-recall-hint", RecallHint)
            recall.set_last_command(self._last_input_text)
            play_input = self.query_one("#play-input", InlineInput)
            recall.show_if_empty(not play_input.value)
        except Exception:
            pass

    def clear_history(self) -> None:
        """Clear the history scroll and reset last result."""
        try:
            scroll = self.query_one("#history-scroll")
            scroll.remove_children()
            self._last_input_text = ""
            self._update_recall_hint()
        except Exception:
            pass

    def _display_result(self, scroll, result: str, speaking: bool = False) -> None:
        """Display a single evaluation result, handling COLOR_RESULT tokens."""
        if "COLOR_RESULT:" not in result:
            scroll.mount(HistoryLine(result, line_type="answer", speaking=speaking))
            return

        # Extract the COLOR_RESULT token
        parts = result.split()
        color_part = None
        before_part, after_part = None, None
        for i, p in enumerate(parts):
            if p.startswith("COLOR_RESULT:"):
                color_part = p
                before_part = " ".join(parts[:i]) if i > 0 else None
                after_part = " ".join(parts[i+1:]) if i < len(parts) - 1 else None
                break

        color_data = self.evaluator._parse_color_result(color_part) if color_part else None
        if not color_data:
            scroll.mount(HistoryLine(result, line_type="answer", speaking=speaking))
            return

        hex_color, color_name, components = color_data
        other_part = " ".join(filter(None, [before_part, after_part]))
        is_modified = (len(components) == 1 and
            components[0].upper() != hex_color.upper())

        if len(components) <= 1 and not is_modified:
            color_box = f"[on {hex_color}]  [/]"
            display = " ".join(filter(None, [before_part, color_box, after_part]))
            scroll.mount(HistoryLine(display, line_type="answer", speaking=speaking))
        elif is_modified and not other_part:
            scroll.mount(ColorResultLine(hex_color, color_name, components, speaking=speaking))
        elif other_part:
            comp_boxes = " ".join(f"[on {c}]  [/]" for c in components)
            result_box = f"[on {hex_color}]  [/]"
            input_line = " ".join(filter(None, [before_part, comp_boxes, after_part]))
            result_line = " ".join(filter(None, [before_part, result_box, after_part]))
            combined = f"{input_line} → {result_line}"
            if self.evaluator._estimate_visual_width(combined) <= 80:
                display = combined
            else:
                display = f"{input_line}\n\n{result_line}"
            scroll.mount(HistoryLine(display, line_type="answer", speaking=speaking))
        else:
            scroll.mount(ColorResultLine(hex_color, color_name, components, speaking=speaking))

    def add_code_results(self, results: list[str]) -> None:
        """Add results from code runner to the history.

        Aggregates all results into a single display block.
        Handles COLOR_RESULT tokens by rendering them as color swatches.
        Strips verbose labels (like "= N emoji") to show compact output.
        """
        if not results:
            return
        try:
            scroll = self.query_one("#history-scroll")

            # Process each result: compact it and handle COLOR_RESULT
            compact_parts = []
            for result in results:
                compact = self._compact_code_result(result)
                if compact:
                    compact_parts.append(compact)

            # Combine all results into one display
            combined = "\n".join(compact_parts)
            if combined.strip():
                scroll.mount(HistoryLine(combined, line_type="answer"))
            scroll.scroll_end(animate=False)
        except Exception:
            pass

    def _compact_code_result(self, result: str) -> str:
        """Compact a code result for aggregate display.

        - Strips "= N emoji" label lines, keeping just the visual
        - Converts COLOR_RESULT tokens into color swatches
        """
        if not result:
            return ""

        # Handle COLOR_RESULT tokens
        if "COLOR_RESULT:" in result:
            return self._render_color_result_inline(result)

        # Strip "= N emoji" label from multiline results (keep the visual)
        lines = result.split('\n')
        if len(lines) >= 2 and lines[0].startswith("= "):
            # The first line is a label like "= 3 🦕", rest is the visual
            return '\n'.join(lines[1:])

        return result

    def _render_color_result_inline(self, result: str) -> str:
        """Convert COLOR_RESULT tokens in a string to color swatches."""
        parts = result.split()
        output_parts = []
        for p in parts:
            if p.startswith("COLOR_RESULT:"):
                color_data = self.evaluator._parse_color_result(p)
                if color_data:
                    hex_color, color_name, components = color_data
                    if components and len(components) >= 2:
                        # Mixed color: show component swatches → result
                        comp_boxes = " ".join(f"[on {c}]  [/]" for c in components)
                        result_box = f"[on {hex_color}]  [/]"
                        output_parts.append(f"{comp_boxes} → {result_box}")
                    else:
                        output_parts.append(f"[on {hex_color}]  [/]")
                else:
                    output_parts.append(p)
            else:
                output_parts.append(p)
        return " ".join(output_parts)

    async def handle_keyboard_action(self, action) -> None:
        """
        Handle keyboard actions from the main app's KeyboardStateMachine.

        This mode uses Textual's Input widget which needs special treatment.
        We handle some actions directly and forward others to the input.
        """
        play_input = self.query_one("#play-input", InlineInput)

        # Flush buffered space tap before any other key
        if not (isinstance(action, ControlAction) and action.action == 'space'):
            if self._space_hold.on_other_key():
                pos = play_input.cursor_position
                play_input.value = play_input.value[:pos] + " " + play_input.value[pos:]
                play_input.cursor_position = pos + 1

        # Handle navigation (up/down for scrolling history, left/right for cursor)
        if isinstance(action, NavigationAction):
            if action.direction == 'up':
                play_input.action_scroll_up()
            elif action.direction == 'down':
                play_input.action_scroll_down()
            elif action.direction == 'left':
                if play_input.cursor_position > 0:
                    play_input.cursor_position -= 1
            elif action.direction == 'right':
                if play_input.cursor_position < len(play_input.value):
                    play_input.cursor_position += 1
            return

        # Handle control actions
        if isinstance(action, ControlAction):
            if action.action == 'tab' and action.is_down:
                play_input.accept_autocomplete()
                return

            if action.action == 'space':
                # Same HoldOrTap pattern as music/art: tap inserts, hold is no-op
                if self._space_hold.fired:
                    if not action.is_down:
                        self._space_hold.on_up()
                    return
                if action.is_down and not action.is_repeat:
                    self._space_hold.on_down(self.set_timer, lambda: None)
                    return
                if action.is_down and action.is_repeat:
                    return  # Suppress repeats while pending
                if not action.is_down:
                    if self._space_hold.on_up():
                        # Tap: insert space
                        pos = play_input.cursor_position
                        play_input.value = play_input.value[:pos] + " " + play_input.value[pos:]
                        play_input.cursor_position = pos + 1
                    return

            if action.action == 'enter' and action.is_down:
                if play_input.value.strip():
                    line = play_input.value.strip()
                    play_input.value = ""

                    play_input.post_message(InlineInput.Submitted(line))
                else:
                    # Enter on empty: recall last command into input
                    if self._last_input_text:
                        play_input.value = self._last_input_text
                        play_input.cursor_position = len(play_input.value)
                play_input.autocomplete_matches = []
                play_input.autocomplete_index = 0
                play_input.exact_match_display = ""
                try:
                    self.query_one("#play-example-hint", ExampleHint).advance()
                except Exception:
                    pass
                return

            if action.action == 'backspace' and action.is_down:
                # Allow key repeats: held backspace erases like an eraser
                pos = play_input.cursor_position
                if pos > 0:
                    play_input.value = play_input.value[:pos - 1] + play_input.value[pos:]
                    play_input.cursor_position = pos - 1
                return

            if action.action == 'escape' and action.is_down and not action.is_repeat:
                if play_input.value:
                    # ESC tap clears the prompt (start over button)
                    play_input.value = ""
                    play_input.cursor_position = 0
                    play_input.autocomplete_matches = []
                    play_input.autocomplete_index = 0
                    play_input.exact_match_display = ""
                return

            return

        # Handle character input
        if isinstance(action, CharacterAction):
            # Skip key repeats for characters (debounce held keys)
            if action.is_repeat:
                return

            char = action.char

            # Math operators: auto-space for readability
            if char in play_input.MATH_OPERATORS:
                pos = play_input.cursor_position
                before = play_input.value[:pos]

                # No spaces if preceded by space, operator, or open paren (allows leading negatives)
                has_operand_before = before and before[-1] not in play_input.MATH_OPERATORS and before[-1] not in ' ('
                if has_operand_before:
                    insert = f" {char} "
                else:
                    insert = char

                play_input.value = before + insert + play_input.value[pos:]
                play_input.cursor_position = pos + len(insert)
                return

            # Insert character at cursor position
            pos = play_input.cursor_position
            play_input.value = play_input.value[:pos] + char + play_input.value[pos:]
            play_input.cursor_position = pos + 1
            # Update color legend to show active row
            self.post_message(PaintModeChanged(True, get_key_color(char)))
            return

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update autocomplete and recall hint display"""
        try:
            play_input = self.query_one("#play-input", InlineInput)
            hint = self.query_one("#autocomplete-hint", AutocompleteHint)
            hint.update(play_input.autocomplete_hint)
            recall = self.query_one("#play-recall-hint", RecallHint)
            recall.show_if_empty(not play_input.value)
        except Exception:
            pass

    async def on_inline_input_submitted(self, event: InlineInput.Submitted) -> None:
        """Handle input submission"""
        input_text = event.value
        scroll = self.query_one("#history-scroll")

        # Check for speech triggers:
        # 1. "!" anywhere in text (strip it)
        # 2. "say" or "talk" prefix (strip it)
        force_speak = False
        eval_text = SimpleEvaluator.split_alnum_runs(input_text)

        # Check for ! anywhere
        if '!' in eval_text:
            force_speak = True
            eval_text = eval_text.replace('!', '')

        # Check for speak prefix (e.g., "say", "talk", "speak") with fuzzy
        words = eval_text.split(None, 1)
        if words:
            prefix = words[0].lower()
            if prefix in SimpleEvaluator.SPEAK_PREFIXES:
                force_speak = True
                eval_text = words[1] if len(words) > 1 else ""
            elif len(prefix) >= 3:
                from ..fuzzy import fuzzy_match_small
                if fuzzy_match_small(prefix, list(SimpleEvaluator.SPEAK_PREFIXES), cutoff=0.7):
                    force_speak = True
                    eval_text = words[1] if len(words) > 1 else ""

        # Clean up whitespace after stripping
        eval_text = eval_text.strip()

        # Add the "Ask →" line to history (without speech markers)
        if eval_text:
            scroll.mount(HistoryLine(eval_text, line_type="ask"))

        # Repeat commands: use PlayCodeRunner (handles fuzzy "repeet" → "repeat")
        from ..code_runner import PlayCodeRunner, parse_lines
        runner = PlayCodeRunner(self.evaluator)
        corrected = runner._fuzzy_correct(eval_text)
        cmds = parse_lines([corrected])
        is_repeat = any(c['type'] == 'repeat' for c in cmds)
        if is_repeat:
            results = runner.run([eval_text])
            for result in results:
                self._display_result(scroll, result, force_speak)
            if runner.corrections:
                try:
                    recall = self.query_one("#play-recall-hint", RecallHint)
                    recall.set_correction(*runner.corrections[0])
                except Exception:
                    pass
            scroll.scroll_end(animate=False)
            self._last_input_text = input_text
            self._update_recall_hint()
            if force_speak and results:
                self._speak_sequence(runner.pairs, scroll)
            return

        # Evaluate and show result
        result = self.evaluator.evaluate(eval_text)
        if result:
            self._display_result(scroll, result, force_speak)

        # Scroll to bottom
        scroll.scroll_end(animate=False)

        # Store raw input for recall (Enter on empty)
        self._last_input_text = input_text
        # Show correction in recall hint: check math corrections first, then content fuzzy
        correction = self.evaluator._last_math_correction
        if not correction:
            c = self.evaluator.content.pop_correction()
            if c and c[0] in eval_text.lower():
                correction = c
        if correction:
            try:
                recall = self.query_one("#play-recall-hint", RecallHint)
                recall.set_correction(correction[0], correction[1])
            except Exception:
                pass
        self._update_recall_hint()

        # Emit for code panel capture
        if eval_text and result:
            self.post_message(ExpressionEvaluated(eval_text, _strip_markup(result)))

        # Handle speech (if ! or say/talk was used)
        if force_speak:
            self._speak(eval_text, result)

    def _speak(self, input_text: str, result: str) -> None:
        """Speak the input and result using Piper TTS.

        Principles:
        - Say minimal text, don't pronounce emoji symbols or color boxes
        - For computation: "input equals result"
        - For simple lookups: just the word
        - Convert operators to words (* → times, + → plus)
        """
        from ..tts import speak

        speakable = self.evaluator._make_speakable(input_text, result)
        if speakable:
            # Find the answer line we just mounted to update its speech indicator
            scroll = self.query_one("#history-scroll")
            answer_widget = scroll.children[-1] if scroll.children else None

            def on_playing():
                if answer_widget:
                    self.app.call_from_thread(
                        self._set_speech_state, answer_widget, HistoryLine.SPEECH_PLAYING
                    )

            def on_done():
                if answer_widget:
                    self.app.call_from_thread(
                        self._set_speech_state, answer_widget, HistoryLine.SPEECH_NONE
                    )

            started = speak(speakable, on_playing=on_playing, on_done=on_done)
            if not started and answer_widget:
                # Speech was blocked (filtered or muted): show muted icon briefly
                self._set_speech_state(answer_widget, HistoryLine.SPEECH_FILTERED)
                self._schedule_clear_speech(answer_widget, 1.5)

    def _speak_sequence(self, pairs: list[tuple[str, str, bool]], scroll) -> None:
        """Speak repeat results in order, lighting each line as it plays.

        Speaks at most SPEAK_REPEAT_CAP items; the rest just display.
        """
        from ..tts import speak_many

        widgets = list(scroll.children)[-len(pairs):]
        items = []
        for (text, result, computed), widget in zip(pairs, widgets):
            speakable = self.evaluator._make_speakable(text, result, computed)
            if speakable and len(items) < SPEAK_REPEAT_CAP:
                items.append((speakable, widget))
            else:
                self._set_speech_state(widget, HistoryLine.SPEECH_NONE)
        if not items:
            return

        def on_playing(i):
            self.app.call_from_thread(
                self._set_speech_state, items[i][1], HistoryLine.SPEECH_PLAYING
            )
            if i:
                self.app.call_from_thread(
                    self._set_speech_state, items[i - 1][1], HistoryLine.SPEECH_NONE
                )

        def on_done():
            for _, widget in items:
                self.app.call_from_thread(
                    self._set_speech_state, widget, HistoryLine.SPEECH_NONE
                )

        started = speak_many(
            [s for s, _ in items], on_playing=on_playing, on_done=on_done
        )
        if not started:
            for _, widget in items:
                self._set_speech_state(widget, HistoryLine.SPEECH_FILTERED)
                self._schedule_clear_speech(widget, 1.5)

    def _set_speech_state(self, widget, state: str) -> None:
        """Update a HistoryLine or ColorResultLine speech indicator."""
        if isinstance(widget, HistoryLine):
            widget.speech_state = state
            widget.refresh()
        elif isinstance(widget, ColorResultLine):
            widget._speech_state = state
            widget.refresh()

    def _schedule_clear_speech(self, widget, delay: float) -> None:
        """Clear a speech indicator after a delay (seconds)."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.call_later(delay, self._set_speech_state, widget, HistoryLine.SPEECH_NONE)
        except RuntimeError:
            pass


class SimpleEvaluator:
    """
    Unified evaluator for math, emojis, and colors.

    Rules (permissive, intuitive for kids):
    - Split by + to get terms
    - Numbers: accumulate, attach to next emoji term
    - Emojis: collect and concatenate
    - Colors: collect and mix (even if non-colors in between)
    - Parens: evaluate inner first, result becomes a term
    """

    # Speech prefixes: trigger TTS for one line, stripped from input
    SPEAK_PREFIXES = {'say', 'talk', 'speak'}

    # Largest count shown inline (dots/emoji/color blocks); above this, switch to abacus.
    INLINE_MAX = 500

    # Operator words recognized when scanning for embedded expressions
    WORD_TO_SYMBOL = {'times': '*', 'plus': '+', 'minus': '-', 'x': '*'}
    # Display operators to normalize before evaluation
    DISPLAY_TO_SYMBOL = {'×': '*', '÷': '/'}
    # Regex for detecting plus expressions (symbol or word)
    PLUS_PATTERN = r'\+|(?<!\w)plus(?!\w)'
    # Regex for valid math expression characters
    MATH_CHARS_PATTERN = r'^[\d\s\+\-\*\/\(\)\.]+$'

    # Split joined alphanumeric runs ("5dinos" -> "5 dinos", "say5" -> "say 5")
    # so prefix detection and TTS see whitespace-delimited tokens. Idempotent.
    _ALNUM_BOUNDARY = re.compile(r'(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)', re.IGNORECASE)

    @classmethod
    def split_alnum_runs(cls, text: str) -> str:
        return cls._ALNUM_BOUNDARY.sub(' ', text)

    # Number words to digits (for kids: zero through twenty, decades, hundred)
    NUMBER_WORDS = {
        'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
        'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
        'ten': '10', 'eleven': '11', 'twelve': '12', 'thirteen': '13',
        'fourteen': '14', 'fifteen': '15', 'sixteen': '16', 'seventeen': '17',
        'eighteen': '18', 'nineteen': '19', 'twenty': '20',
        'thirty': '30', 'forty': '40', 'fifty': '50', 'sixty': '60',
        'seventy': '70', 'eighty': '80', 'ninety': '90', 'hundred': '100',
    }
    _NUMBER_WORDS_PATTERN = re.compile(
        r'\b(' + '|'.join(sorted(NUMBER_WORDS.keys(), key=len, reverse=True)) + r')\b',
        re.IGNORECASE,
    )

    def __init__(self):
        self.content = get_content()
        self._last_math_correction: tuple[str, str] | None = None
        # True when the last evaluate() actually did arithmetic (merged counts,
        # evaluated an expression, mixed colors), not just rendered the input.
        self._last_computed = False

    def evaluate(self, text: str) -> str:
        """Evaluate input and return result string.

        Content-layer fuzzy corrections (e.g., "dinno" → "dino") are tracked
        on self.content._last_correction for the UI to display separately.
        Never raises or produces invalid markup: falls back to colored letter blocks.
        """
        text = text.strip()
        self._last_computed = False
        if not text:
            return ""
        self.content.pop_correction()  # Clear stale corrections
        try:
            result = self._evaluate_inner(text)
            # Safety cap: prevent huge results from crashing the renderer
            if result and len(result) > 5000:
                # Truncate at line boundary to avoid breaking Rich markup
                lines = result[:5000].split('\n')
                result = '\n'.join(lines[:-1]) if len(lines) > 1 else lines[0]
            # Validate Rich markup so broken tags never reach the renderer
            if result and not result.startswith("COLOR_RESULT:"):
                from rich.text import Text
                Text.from_markup(result)
            return result
        except Exception:
            self._last_computed = False
            return self._format_text_as_color_blocks(text)

    # "and"/"&" → "+" only when between digits, colors, or known emoji words
    _AND_PATTERN = re.compile(r'(?<=\S)\s+(?:and|&)\s+(?=\S)', re.IGNORECASE)

    def _normalize_and(self, text: str) -> str:
        """Replace 'and'/'&' with '+' when used as a joiner in expressions.

        Strong signal, either side suffices: a number or a pure color.
        Weak signal: every word in the input is visual (number, color, color
        adjective, or emoji word), so the whole input is a composition and
        "and" is a joiner ("unicorn and dark blue giraffe", "cat and dog").
        Any plain word anywhere means a sentence, keeping "and" visible
        ("cat and me", "I love cat and dog"). Words that are both emoji and
        color ("orange") never count as visual: "+" would color-tint the
        neighbor, so "apple and orange" stays a sentence.
        """
        from ..color_mixing import COLOR_ADJECTIVES

        def is_strong(w):
            if w.isdigit():
                return True
            return bool(self.content.get_color(w)) and not self.content.get_emoji(w)

        def is_visual(w):
            if is_strong(w) or w in COLOR_ADJECTIVES:
                return True
            return bool(self.content.get_emoji(w)) and not self.content.get_color(w)

        all_visual = all(
            is_visual(w) for w in text.lower().split() if w not in ('and', '&')
        )

        def replace_if_expression(m):
            before = text[:m.start()].rstrip().rsplit(None, 1)[-1] if text[:m.start()].rstrip() else ""
            after = text[m.end():].lstrip().split(None, 1)[0] if text[m.end():].lstrip() else ""
            bl, al = before.lower(), after.lower()
            if is_strong(bl) or is_strong(al) or all_visual:
                return ' + '
            return m.group(0)
        return self._AND_PATTERN.sub(replace_if_expression, text)

    def _evaluate_inner(self, text: str) -> str:
        """Core evaluation pipeline."""
        # Normalize "and"/"&" to "+", number words, and commas early
        text = self._normalize_and(text)
        text = self._normalize_number_words(text)
        text = self._normalize_commas(text)

        # Clean math expression typos (repeated operators, stray =, etc.),
        # then normalize operator words and typos between digits once for the
        # whole input, so every path (plus, emoji counts, pure math) agrees:
        # "8 pluss 2 moons" -> "8 + 2 moons"
        self._last_math_correction = None
        text = self._clean_math_expression(text)
        text = self._fuzzy_normalize_operators(text)

        # Patterns: "5 4 3 ..." or "2 cats ... 5" (check before any other eval)
        if '..' in text:
            if pattern := self._eval_pattern(text):
                return pattern

        # Track if original had parens (implies computation)
        had_parens = '(' in text

        # Handle parentheses first
        text = self._eval_parens(text)

        # Try adjective + color (e.g., "bright green", "dark light blue")
        if modified := self._eval_modified_color(text):
            return modified

        # Try text with embedded expression (e.g., "what is 2 + 3", "I have 5 apples")
        if result := self._eval_text_with_expr(text, had_parens):
            return result

        # Check if it's a + expression
        if re.search(self.PLUS_PATTERN, text.lower()):
            if result := self._eval_plus_expr(text):
                result = self._maybe_add_label(result, had_parens)
                return result

        # Try division/subtraction applied to a noun: "6/2 dogs", "5 - 2 cats"
        if op_noun := self._eval_op_noun(text):
            return self._maybe_add_label(op_noun, had_parens)

        # Try multiplication: "3 * cat", "cat times 5", etc.
        if mult := self._eval_mult(text):
            result = self._maybe_add_label(mult, had_parens)
            return result

        # Try pure math
        normalized = self._normalize_math(text)
        if (math_result := self._eval_math(normalized)) is not None:
            if isinstance(math_result, str):
                return math_result
            # If input is just a bare number, skip the label (Ask line already shows it)
            is_bare_number = re.match(r'^\d+$', text.strip())
            # Bare negative numbers (e.g. "-5") aren't useful as math, show as colored text
            is_bare_negative = re.match(r'^-\d+$', text.strip())
            if is_bare_negative:
                return self._format_text_as_color_blocks(text.strip())
            result = self._format_number_with_dots(math_result, show_label=not is_bare_number, expression=normalized)
            if not is_bare_number:
                result = f"= {result}"
            return result

        # Try single word lookup (emoji or color)
        if single := self._lookup(text.lower().strip()):
            return single

        # Try auto-mixing colors with emojis or text (e.g., "red apple", "red blue")
        if auto_mix := self._eval_auto_mix(text):
            return auto_mix

        # Nothing computed: clear any flag set by speculative math attempts above
        self._last_computed = False

        # Try emoji substitution in text (e.g., "I love cat")
        subbed = self._substitute_emojis(text, colorize_unknown=True)
        if subbed != text:
            return self._maybe_add_label(subbed, had_parens)

        # Plain text fallback: show as colored blocks (one per letter)
        return self._format_text_as_color_blocks(text)

    def _maybe_add_label(self, result: str, had_parens: bool) -> str:
        """Add emoji label if result is unlabeled emojis from a paren expression."""
        if had_parens and self._is_emoji_str(result) and '\n' not in result:
            chars = [c for c in result if ord(c) > 127]
            if len(chars) > 1 and all(c == chars[0] for c in chars):
                return f"{len(chars)} {chars[0]}\n{result}"
        return result



    def _eval_text_with_expr(self, text: str, had_parens: bool = False) -> str | None:
        """Handle text containing expressions like 'what is 2+3' or 'I have 5 apples'.

        Returns multi-line result with text prefix preserved on each line.
        Only triggers when there's actual English text before the expression.
        """
        words = text.split()
        if len(words) < 2:
            return None

        # Find where expression starts (first number, operator, color, or emoji word)
        expr_start = None
        for i, word in enumerate(words):
            clean = re.sub(r'[^\w]', '', word.lower())
            if (re.match(r'^\d+$', clean) or
                clean in self.WORD_TO_SYMBOL or
                self._get_color(clean) or
                self._get_emoji(clean)):
                expr_start = i
                break

        if expr_start is None or expr_start == 0:
            return None  # No text prefix found

        # Verify the prefix is actual English text (not emoji, numbers, or operators)
        prefix_words = words[:expr_start]
        if not all(self._is_plain_text(w) for w in prefix_words):
            return None

        # Skip if prefix is all color adjectives (let color adjective handler deal with it)
        from ..color_mixing import COLOR_ADJECTIVES
        if all(w.lower() in COLOR_ADJECTIVES for w in prefix_words):
            return None

        prefix = ' '.join(prefix_words)
        expr_text = ' '.join(words[expr_start:])

        # Evaluate the expression part
        result = self._eval_expr_part(expr_text)
        if result is None:
            return None

        # Add label if parens implied computation
        result = self._maybe_add_label(result, had_parens)

        # Prepend prefix (as colored blocks) to each line of the result
        colored_prefix = self._format_text_as_color_blocks(prefix)
        lines = result.split('\n')
        return '\n'.join(f"{colored_prefix} {line}" for line in lines)

    def _eval_expr_part(self, text: str) -> str | None:
        """Evaluate an expression (without text prefix). Returns multi-line if appropriate."""
        # Handle parentheses
        text = self._eval_parens(text)

        # Try + expression
        if re.search(self.PLUS_PATTERN, text.lower()):
            if result := self._eval_plus_expr(text):
                return result

        # Try multiplication
        if mult := self._eval_mult(text):
            return mult

        # Try pure math (returns with dots visualization)
        normalized = self._normalize_math(text)
        if (math_result := self._eval_math(normalized)) is not None:
            if isinstance(math_result, str):
                return math_result
            return self._format_number_with_dots(math_result, expression=normalized)

        # Try single word lookup
        if single := self._lookup(text.lower().strip()):
            return single

        return None

    def _eval_parens(self, text: str) -> str:
        """Evaluate innermost parentheses first, recursively.

        Results are stripped to plain values (numbers, emojis) so they can
        be safely spliced back into the outer expression without leaking
        Rich markup tags.
        """
        for _ in range(10):
            if not (match := re.search(r'\(([^()]+)\)', text)):
                break
            result = self.evaluate(match.group(1))
            # Strip to first line (removes dot visualization)
            result = result.split('\n')[0]
            # Strip "= " prefix from math results
            if result.startswith("= "):
                result = result[2:]
            # Strip any remaining Rich markup so it doesn't leak into outer text
            result = _strip_markup(result)
            # If result is "N emoji", extract just the emojis for outer expression
            if m := re.match(r'^(\d+)\s+(.+)$', result):
                count, emoji_str = int(m.group(1)), m.group(2).strip()
                if self._is_emoji_str(emoji_str):
                    result = emoji_str * count
            # Collapse "emoji + emoji" back to plain emoji string for reuse
            collapsed = result.replace(' + ', '')
            if collapsed != result and self._is_emoji_str(collapsed):
                result = collapsed
            text = text[:match.start()] + result + text[match.end():]
        return text

    def _eval_plus_expr(self, text: str) -> str | None:
        """Evaluate + expression. Colors act as adjectives for the next item."""
        parts = re.split(r'\s*(?:' + self.PLUS_PATTERN + r')\s*', text.lower())

        items = []   # (type, value) in original order
        pending_nums = []  # individual numbers preserved for emoji grouping

        for part in parts:
            part = part.strip()
            if not part:
                continue

            handled = self._ingest_part(part, items, pending_nums)
            if isinstance(handled, str):
                return handled
            if handled:
                continue

            # Multi-word part the fast paths missed (e.g. "2 bright red dogs"):
            # decompose into semantic units via the shared chunker and ingest each.
            for chunk in self._chunk_words(part.split()):
                r = self._ingest_part(chunk, items, pending_nums)
                if isinstance(r, str):
                    return r
                if not r and chunk.strip():
                    items.append(('text', self._substitute_emojis(chunk)))

        # Attach remaining pending to last emoji or color
        if pending_nums:
            pending = int(sum(pending_nums))
            attached = False
            for i in range(len(items) - 1, -1, -1):
                if items[i][0] == 'emoji':
                    e, c, w = items[i][1]
                    items[i] = ('emoji', (e, c + pending, w))
                    if pending:
                        self._last_computed = True
                    attached = True
                    break
            if not attached:
                for i in range(len(items) - 1, -1, -1):
                    if items[i][0] == 'color':
                        h = items[i][1]
                        for _ in range(pending):
                            items.insert(i + 1, ('color', h))
                        attached = True
                        break

        has_colors = any(t == 'color' for t, _ in items)
        has_emojis = any(t == 'emoji' for t, _ in items)

        if not has_colors and not has_emojis:
            return None

        # Collect emoji info for label formatting
        emoji_items = [(e, c, w) for t, v in items if t == 'emoji' for e, c, w in [v]]
        total_count = sum(c for _, c, _ in emoji_items)
        has_text = any(t == 'text' for t, _ in items)
        # Computation: any term with count > 1
        all_same_emoji = len(set(e for e, _, _ in emoji_items)) == 1 if emoji_items else False
        # Singleton addition: apple + apple + apple (all count=1, same emoji)
        all_singletons = all_same_emoji and all(c == 1 for _, c, _ in emoji_items) and len(emoji_items) > 1
        has_computation = total_count > len(emoji_items) or all_singletons
        show_label = has_computation and not has_colors and not has_text

        # If colors present, use adjective grouping
        if has_colors:
            word_info = []
            for t, v in items:
                if t == 'color':
                    word_info.append(('color', v))
                elif t == 'emoji':
                    e, c, w = v
                    word_info.append(('emoji', e, c))
                elif t == 'text':
                    word_info.append(('text', v))

            groups = self._build_adjective_groups(word_info)
            result = self._render_adjective_groups(groups)

            if result is None:
                return None

            return result

        # Same-emoji expressions: collapse to abacus when total exceeds INLINE_MAX
        # (small counts like "2 + 3 cats" keep grouped inline display)
        if all_same_emoji and not has_text and len(emoji_items) > 1 and total_count > self.INLINE_MAX:
            self._last_computed = True
            e = emoji_items[0][0]
            return self._format_emoji_label(e, total_count)

        # Singleton emoji addition (apple + apple → "= 2 🍎" with dots)
        if all_singletons:
            self._last_computed = True
            e = emoji_items[0][0]
            return self._format_emoji_label(e, total_count)

        # No colors: build result in order, showing + between items
        result_parts = []
        for item_type, value in items:
            if item_type == 'emoji':
                e, c, w = value
                if c > self.INLINE_MAX:
                    result_parts.append(self._format_emoji_label(e, c))
                else:
                    result_parts.append(e * c)
            elif item_type == 'text':
                result_parts.append(self._format_text_as_color_blocks(value))

        result = ' + '.join(result_parts) if result_parts else None
        if show_label and result:
            combined = {}
            for e, c, w in emoji_items:
                combined[e] = combined.get(e, 0) + c
            if len(combined) < len(emoji_items):
                self._last_computed = True
            label_parts = [f"{c} {e}" for e, c in combined.items()]
            label = ' '.join(label_parts)
            result = f"{label}\n{result}"
        return result

    def _ingest_part(self, part: str, items: list, pending_nums: list):
        """Turn one term into items for a + expression.

        Returns True if recognized, a str to short-circuit the whole
        expression (math error/special), or False if unrecognized.
        Colors emit per-color items (adjective model); a pending number
        binds to the next emoji, or multiplies a color when no emoji follows.
        """
        part = part.strip()
        if not part:
            return True

        # Colors act as adjectives: a pending number passes through to the next
        # emoji (e.g. "3 + 2 bright red dogs" -> 5 red dogs). Leftover pending on
        # a color-only expression is multiplied by the trailing-pending logic.
        if hexes := self._parse_color(part):
            items.extend(('color', h) for h in hexes)
            return True

        if emoji_data := self._parse_emoji(part):
            emoji, count, word = emoji_data
            for p in pending_nums:
                items.append(('emoji', (emoji, int(p), word)))
            items.append(('emoji', (emoji, count, word)))
            pending_nums.clear()
            return True

        normalized = self._normalize_math(part)
        if (math_result := self._eval_math(normalized)) is not None:
            if isinstance(math_result, str):
                return math_result
            val = int(math_result) if isinstance(math_result, float) and math_result.is_integer() else math_result
            pending_nums.append(val)
            return True

        if self._is_emoji_str(part):
            chars = [c for c in part if ord(c) > 127]
            pending_sum = int(sum(pending_nums)) if pending_nums else 0
            if chars and all(c == chars[0] for c in chars):
                for p in pending_nums:
                    items.append(('emoji', (chars[0], int(p), None)))
                items.append(('emoji', (chars[0], len(chars), None)))
            else:
                items.append(('emoji', (part, 1 + pending_sum, None)))
            pending_nums.clear()
            return True

        return False

    def _estimate_visual_width(self, markup: str) -> int:
        """Estimate visual width of Rich markup text.

        Strips markup tags, counts emoji as 2 chars wide, ASCII as 1.
        """
        # Remove Rich markup tags like [on #hex], [/], [bold], etc.
        plain = re.sub(r'\[[^\]]*\]', '', markup)
        width = 0
        for ch in plain:
            if ord(ch) > 127:
                width += 2  # emoji and wide chars
            else:
                width += 1
        return width

    def _build_adjective_groups(self, word_info: list) -> list[dict]:
        """Group word_info items by color-as-adjective model.

        Colors attach to the next non-color item. Consecutive colors before
        the same item mix together. A color's tint also carries to following
        groups of the *same* emoji, so "2 + 3 dark red dogs" colors all 5 dogs
        (the count is split by addition but it's one colored noun). A different
        emoji or a new color stops the carry. Trailing colors with no item
        after them form a group with item=None.

        Input: list of ('color', hex) | ('emoji', emoji, count) | ('text', word)
        Output: list of {'colors': [hex...], 'tint': hex_or_None, 'item': info}.
        'colors' drives the input swatches (shown once); 'tint' colors the result.
        """
        groups = []
        current_colors = []
        carry_tint = None
        carry_emoji = None
        for info in word_info:
            if info[0] == 'color':
                current_colors.append(info[1])
                continue
            colors = list(current_colors)
            current_colors = []
            if colors:
                tint = mix_colors_paint(colors) if len(colors) > 1 else colors[0]
            elif info[0] == 'emoji' and info[1] == carry_emoji:
                tint = carry_tint
            else:
                tint = None
            carry_emoji = info[1] if info[0] == 'emoji' and tint else None
            carry_tint = tint if carry_emoji else None
            groups.append({'colors': colors, 'tint': tint, 'item': info})
        if current_colors:
            groups.append({'colors': current_colors, 'tint': None, 'item': None})
        if (len(groups) >= 2
                and groups[-1]['item'] is None
                and not groups[-2]['colors']):
            groups[-2]['colors'] = groups[-1]['colors']
            groups.pop()
        return groups

    def _render_adjective_groups(self, groups: list[dict]) -> str | None:
        """Render adjective groups into markup.

        Handles all-color groups (COLOR_RESULT mixing), colored items,
        plain items, and trailing color swatches.
        """
        # Check if ALL groups are color-only (no items): pure color mixing
        if all(g['item'] is None for g in groups):
            all_colors = []
            for g in groups:
                all_colors.extend(g['colors'])
            if len(all_colors) >= 2:
                self._last_computed = True
                mixed = mix_colors_paint(all_colors)
                name = get_color_name_approximation(mixed)
                return f"COLOR_RESULT:{mixed}:{name.replace(' ', '_')}:{','.join(all_colors)}"
            elif len(all_colors) == 1:
                return None  # Single color, fall through
            return None

        MAX_INLINE_WIDTH = 80
        input_parts = []
        result_parts = []

        for g in groups:
            colors = g['colors']
            item = g['item']

            if item is None:
                # Trailing colors: render as swatches
                for c in colors:
                    input_parts.append(f"[on {c}]  [/]")
                    result_parts.append(f"[on {c}]  [/]")
                continue

            mixed = g['tint']

            # Build input representation for colors
            for c in colors:
                input_parts.append(f"[on {c}]  [/]")

            if item[0] == 'emoji':
                e, count = item[1], item[2]
                emoji_str = e * count
                input_parts.append(emoji_str)
                if mixed:
                    result_parts.append(f"[on {mixed}] {emoji_str} [/]")
                else:
                    result_parts.append(emoji_str)
            elif item[0] == 'text':
                word = item[1]
                input_parts.append(self._format_text_as_color_blocks(word))
                if mixed and all(ch.isalnum() or ch.isspace() for ch in word):
                    result_parts.append(self._format_text_on_color(word, mixed))
                elif mixed:
                    result_parts.append(f"[on {mixed}] {word} [/]")
                else:
                    result_parts.append(self._format_text_as_color_blocks(word))

        input_str = " + ".join(input_parts)
        result = " ".join(result_parts)
        combined = f"{input_str} → {result}"
        if self._estimate_visual_width(combined) <= MAX_INLINE_WIDTH:
            return combined
        return f"{input_str}\n{result}"

    def _eval_auto_mix(self, text: str) -> str | None:
        """Rewrite space-separated mixed content as a + expression.

        Only triggers when at least one word is a color. Groups words into
        logical chunks (adjective+color, number+noun, bare word) and joins
        them with "+", then delegates to _eval_plus_expr.

        Examples:
            "red turtle blue"    -> "red + turtle + blue"
            "dark blue green"    -> "dark blue + green"
            "red 2 blues"        -> "red + 2 blues"
            "red house green car"-> "red + house + green + car"
        """
        words = text.split()
        if len(words) < 2:
            return None

        # Only fire when at least one word is a color, and no non-alpha connectors
        if not any(self._get_color(w.lower()) for w in words):
            return None
        if any(w in ('&', ',', ';') for w in words):
            return None

        groups = self._chunk_words(words)
        if len(groups) < 2:
            return None

        return self._eval_plus_expr(" + ".join(groups))

    # Operator word → symbol mapping (used for exact and fuzzy normalization)
    _OPERATOR_WORDS = {'times': '*', 'plus': '+', 'minus': '-'}
    # Division words only apply between digits ("6 over 2"), never in prose ("game over")
    _DIGIT_OPERATOR_WORDS = {**_OPERATOR_WORDS, 'divide': '/', 'divided': '/', 'over': '/'}
    # Count operators exclude '+'/'plus' (they mean "combine groups", handled by the plus path)
    _COUNT_OPS = ('x', '×', '*', '/', '÷', '-') + tuple(w for w in _DIGIT_OPERATOR_WORDS if w != 'plus')
    _COUNT_TOKEN = re.compile(r'\d+([x×*/÷-]\d+)*', re.IGNORECASE)

    def _is_content_word(self, w: str) -> bool:
        """Exact emoji/color word, singular or plural. Fuzzy content matches
        don't count: a typo like "timess" must stay correctable to an operator."""
        if self.content.exact_emoji(w) or self.content.exact_color(w):
            return True
        s = singularize(w)
        return bool(s and s != w and (self.content.exact_emoji(s) or self.content.exact_color(s)))

    def _fuzzy_op_word(self, word: str) -> str | None:
        """Fuzzy-match a typo to an operator word. Real content words between
        digits ("2 tigers 3", "2 limes 3") are never operators."""
        w = word.lower()
        if self._is_content_word(w):
            return None
        from ..fuzzy import fuzzy_match_small
        return fuzzy_match_small(w, list(self._DIGIT_OPERATOR_WORDS), cutoff=0.7)

    def _is_count_op(self, word: str) -> bool:
        w = word.lower()
        if w in self._COUNT_OPS:
            return True
        matched = self._fuzzy_op_word(w)
        return matched is not None and matched != 'plus'

    def _take_count(self, words: list[str], i: int) -> tuple[str | None, int]:
        """Consume a leading count starting at i: a number or an arithmetic
        expression ("3", "3x2", "3 × 2", "6 / 2", "5 minus 2", "8 divided by 2").
        The expression is evaluated so the count binds to the following noun:
        "6/2 dogs" -> 3 dogs. Returns (count_str_or_None, next_index).
        """
        n = len(words)
        if i >= n or not self._COUNT_TOKEN.fullmatch(words[i]):
            return None, i
        j = i + 1
        while j + 1 < n and self._is_count_op(words[j]):
            k = j + 1
            if words[j].lower().startswith('div') and k < n and words[k].lower() == 'by':
                k += 1
            if k < n and self._COUNT_TOKEN.fullmatch(words[k]):
                j = k + 1
            else:
                break
        val = self._eval_math(self._normalize_math(" ".join(words[i:j])))
        if isinstance(val, (int, float)) and not isinstance(val, bool) \
                and float(val).is_integer() and val >= 0:
            return str(int(val)), j
        return None, i

    def _chunk_words(self, words: list[str]) -> list[str]:
        """Single source of truth for grouping space-separated words into
        semantic units. A unit is [count] [adjective... color]* [noun]: the
        count binds to the noun if present, else multiplies the trailing color.
        Color modifiers are emitted before their noun so the color-as-adjective
        renderer can attach them ("2 bright red dogs" -> ["bright red", "2 dogs"]).
        """
        from ..color_mixing import COLOR_ADJECTIVES

        def is_color_word(w: str) -> bool:
            return bool(self._get_color(w)) and not self._get_emoji(w)

        groups: list[str] = []
        i, n = 0, len(words)
        while i < n:
            # "N x noun" multiplication stays together
            if i + 2 < n and words[i + 1].lower() in ('x', '×', '*', 'times'):
                a, b = words[i], words[i + 2]
                noun = b.lower() if a.isdigit() and not b.isdigit() else (
                    a.lower() if b.isdigit() and not a.isdigit() else None)
                if noun and self._get_emoji(noun):
                    groups.append(f"{a} {words[i + 1]} {b}")
                    i += 3
                    continue

            j = i
            count, j = self._take_count(words, i)

            color_chunks: list[str] = []
            while j < n:
                k = j
                while k < n and words[k].lower() in COLOR_ADJECTIVES:
                    k += 1
                if k < n and is_color_word(words[k].lower()):
                    color_chunks.append(" ".join(words[j:k + 1]))
                    j = k + 1
                else:
                    break

            noun = None
            if j < n and self._get_emoji(words[j].lower()):
                noun = words[j]
                j += 1

            if j == i:  # nothing matched, pass the word through unchanged
                groups.append(words[i])
                i += 1
                continue

            groups.extend(color_chunks)
            if noun:
                groups.append(f"{count} {noun}" if count else noun)
            elif count and color_chunks:
                groups[-1] = f"{count} {color_chunks[-1]}"
            elif count:
                groups.append(count)
            i = j

        return groups

    def _normalize_mult(self, text: str) -> str:
        """Normalize multiplication operators (x, times, ×) to *."""
        result = text.replace('×', '*')
        result = re.sub(r'\btimes\b', '*', result, flags=re.IGNORECASE)
        # Digit-x-digit (e.g. "5x5") has no word boundary, so handle it before \bx\b.
        result = re.sub(r'(?<=\d)\s*x\s*(?=\d)', ' * ', result, flags=re.IGNORECASE)
        result = re.sub(r'(?<=[\d\w])\s*\bx\b\s*(?=[\d\w])', ' * ', result, flags=re.IGNORECASE)
        return result

    def _format_emoji_label(self, emoji: str, count: int, expression: str = "") -> str:
        """Format emoji with label and visualization.

        Uses _format_number_with_dots with emoji as bead for consistent
        grouping and abacus rendering.
        """
        viz = self._format_number_with_dots(count, show_label=False, expression=expression, bead=emoji)
        return f"= {count} {emoji}\n{viz}"

    def _format_color_label(self, hex_color: str, count: int) -> str:
        """Format color multiplication with label and abacus visualization."""
        block = f"[on {hex_color}]  [/]"
        if count <= self.INLINE_MAX:
            return block * count
        viz = self._format_number_with_dots(count, show_label=False, bead=block)
        return f"= {count} {block}\n{viz}"

    # -- Pattern sequences ("5 4 3 ...", "2 cats ... 10") --

    MAX_PATTERN_TERMS = 20

    def _eval_pattern(self, text: str) -> str | None:
        """Evaluate '...' patterns: detect arithmetic sequences and continue them.

        Supports:
        - Pure numbers: "5 4 3 ..." "2 4 6 ... 20"
        - Emoji sequences: "5 cats ..." "cats ... 5" "1 cat 2 cats 3 cats ..."
        """
        m = re.match(r'^(.+?)\s*\.{2,}\s*(.*)$', text)
        if not m:
            return None

        left = m.group(1).strip()
        right = m.group(2).strip()

        # Parse target from right side (optional number)
        target = None
        if right:
            target_m = re.match(r'^(\d+)', right)
            if target_m:
                target = int(target_m.group(1))

        emoji = None
        values = []

        # Pattern: "N word N word ..." (e.g., "1 cat 2 cats 3 cats")
        pairs = re.findall(r'(\d+)\s*([a-zA-Z]+)', left)
        if pairs:
            emojis_found = set()
            for _, word in pairs:
                e = self._get_emoji(word.lower())
                if e:
                    emojis_found.add(e)
            if len(emojis_found) == 1:
                emoji = emojis_found.pop()
                values = [int(n) for n, _ in pairs]

        # Pattern: "N word" (single, e.g., "5 cats")
        if not values:
            single_m = re.match(r'^(\d+)\s*([a-zA-Z]+)$', left)
            if single_m:
                n, word = int(single_m.group(1)), single_m.group(2).lower()
                e = self._get_emoji(word)
                if e:
                    emoji = e
                    values = [n]

        # Pattern: "word" only on left, target on right (e.g., "cats ... 5")
        if not values and not emoji:
            word_m = re.match(r'^([a-zA-Z]+)$', left)
            if word_m:
                e = self._get_emoji(word_m.group(1).lower())
                if e and target is not None:
                    emoji = e
                    values = []

        # Pattern: pure numbers (e.g., "5 4 3", "2 4 6")
        if not values and not emoji:
            nums = re.findall(r'-?\d+', left)
            if len(nums) >= 2:
                values = [int(n) for n in nums]

        if not values and not emoji:
            return None

        # Detect arithmetic step from examples
        if len(values) >= 2:
            diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)]
            if len(set(diffs)) == 1:
                step = diffs[0]
            else:
                return None  # not an arithmetic sequence
        elif len(values) == 1 and emoji:
            # Single value + emoji: countdown by default, count up if target > start
            if target is not None and target > values[0]:
                step = 1
            else:
                step = -1
        elif not values and emoji and target is not None:
            # "cats ... 5": count from 1 up to target
            values = [1]
            step = 1
        else:
            return None

        if step == 0:
            return None

        # Generate the sequence
        sequence = list(values)
        last = values[-1]
        for _ in range(self.MAX_PATTERN_TERMS):
            nxt = last + step
            if target is not None:
                if step > 0 and nxt > target:
                    break
                if step < 0 and nxt < target:
                    break
            else:
                # Emoji patterns stop at 1 (0 emoji is nothing), numbers stop at 0
                min_val = 1 if emoji else 0
                if step < 0 and nxt < min_val:
                    break
                if step > 0 and len(sequence) >= 10:
                    break
            if nxt < 0:
                break
            sequence.append(nxt)
            last = nxt

        # Include target if step lands exactly on it
        if target is not None and sequence and sequence[-1] != target:
            if step > 0 and target > sequence[-1]:
                sequence.append(target)
            elif step < 0 and target < sequence[-1]:
                sequence.append(target)

        if len(sequence) <= 1:
            return None

        if emoji:
            return self._format_emoji_pattern(sequence, emoji)
        else:
            gaps = re.findall(r'\d( +)(?=-?\d)', left)
            sep = gaps[0] if gaps else " "
            return self._format_number_pattern(sequence, sep)

    def _format_emoji_pattern(self, sequence: list[int], emoji: str) -> str:
        """Render emoji sequence as rows (one per count)."""
        lines = []
        for n in sequence:
            if n > 0:
                lines.append(emoji * n)
            elif n == 0:
                lines.append(" ")
        return "\n".join(lines)

    def _format_number_pattern(self, sequence: list[int], sep: str = " ") -> str:
        return sep.join(str(n) for n in sequence)

    def _eval_op_noun(self, text: str) -> str | None:
        """Division/subtraction of a count applied to a single noun or color,
        the analogue of _eval_mult: "6/2 dogs" -> 3 dogs, "5 - 2 reds" -> 3 red
        boxes, "10 - 3 - 2 dogs" -> 5 dogs. Multiplication stays in _eval_mult
        (it renders the abacus grouping), so this only fires when the consumed
        expression actually contains a division or subtraction operator.
        """
        words = text.strip().split()
        count_str, j = self._take_count(words, 0)
        if count_str is None or len(words) - j != 1:
            return None
        consumed = self._normalize_math(" ".join(words[:j]))
        if not any(op in consumed for op in ('/', '-')):
            return None
        count = int(count_str)
        word = words[j].lower()
        if e := self._get_emoji(word):
            return self._format_emoji_label(e, count) if count > 1 else e * count
        if h := self._get_color(word):
            return self._format_color_label(h, count)
        return None

    def _eval_mult(self, text: str) -> str | None:
        """Evaluate multiplication: '3 * cat', '5 x 2 cats', 'cat times 5', '3 cats', 'cats', '🐱🐶 * 2'."""
        t = self._normalize_mult(text.strip())
        t_lower = t.lower()
        has_operator = '*' in t  # After normalization, all mult operators become *

        # "emoji_string * N" (for paren results like "🐱🐶 * 2")
        if m := re.match(r'^(.+?)\s*\*\s*(\d+)$', text.strip()):
            s, count = m.group(1).strip(), int(m.group(2))
            if self._is_emoji_str(s) and count <= 100:
                return s * count

        # "N * emoji_string"
        if m := re.match(r'^(\d+)\s*\*\s*(.+)$', text.strip()):
            count, s = int(m.group(1)), m.group(2).strip()
            if self._is_emoji_str(s) and count <= 100:
                return s * count

        # Try _parse_emoji for word-based patterns
        if emoji_data := self._parse_emoji(t_lower):
            e, c, w = emoji_data
            # Show label+abacus for explicit operators OR large counts
            if c > 1 and (has_operator or c > self.INLINE_MAX):
                expr = ""
                if has_operator:
                    for pat in (r'^(\d+)\s*\*\s*(\d+)(?:\s+|[a-z])', r'^[a-z]+\s*(\d+)\s*\*\s*(\d+)$'):
                        if m := re.match(pat, t_lower):
                            expr = f"{m.group(1)}*{m.group(2)}"
                            break
                return self._format_emoji_label(e, c, expression=expr)
            return e * c

        # "N * word" or "word * N" for colors
        if m := re.match(r'^(\d+)\s*\*\s*(\w+)$', t_lower):
            count, word = int(m.group(1)), m.group(2)
            if h := self._get_color(word):
                return self._format_color_label(h, count)
        if m := re.match(r'^(\w+)\s*\*\s*(\d+)$', t_lower):
            word, count = m.group(1), int(m.group(2))
            if h := self._get_color(word):
                return self._format_color_label(h, count)

        # "N word" for colors (e.g., "3 red")
        if m := re.match(r'^(\d+)\s*(\w+)$', t_lower):
            count, word = int(m.group(1)), m.group(2)
            if h := self._get_color(word):
                return self._format_color_label(h, count)

        # Bare plural for colors (e.g., "yellows" -> 2 yellow boxes)
        if t_lower.endswith('s') and len(t_lower) > 2:
            word = t_lower[:-1]
            if h := self.content.get_color(word):
                return f"[on {h}]  [/]" * 2

        return None

    def _parse_color(self, term: str) -> list[str] | None:
        """Parse color term -> list of hex colors (repeated for multiplication)."""
        term = self._normalize_mult(term.strip()).lower()

        # "color * N" or "N * color"
        if m := re.match(r'^(\w+)\s*\*\s*(\d+)$', term):
            if (h := self._get_color(m.group(1))) and 1 <= int(m.group(2)) <= 20:
                return [h] * int(m.group(2))
        if m := re.match(r'^(\d+)\s*\*\s*(\w+)$', term):
            if (h := self._get_color(m.group(2))) and 1 <= int(m.group(1)) <= 20:
                return [h] * int(m.group(1))

        # "N word" (e.g., "3 yellow" or "3 yellows")
        if m := re.match(r'^(\d+)\s+(\w+)$', term):
            if (h := self._get_color(m.group(2))) and 1 <= int(m.group(1)) <= 20:
                return [h] * int(m.group(1))

        # Bare plural (e.g., "yellows" -> 2 yellow)
        if term.endswith('s') and len(term) > 2:
            word = term[:-1]
            if h := self.content.get_color(word):
                return [h] * 2

        # Just a color name
        if h := self._get_color(term):
            return [h]

        # Adjective + color (e.g., "bright green")
        if mod := self.content.get_modified_color(term):
            return [mod[0]]  # modified hex

        return None

    _EMOJI_PATTERNS = (
        re.compile(r'^(?P<n1>\d+)(?:\s*\*\s*(?P<n2>\d+))?\s*(?P<word>[a-z]\w*)$'),
        re.compile(r'^(?P<word>[a-z]+)\s*(?P<n1>\d+)(?:\s*\*\s*(?P<n2>\d+))?$'),
    )

    def _parse_emoji(self, term: str) -> tuple[str, int, str] | None:
        """Parse emoji term -> (emoji_char, count, word). Accepts label with
        leading or trailing count, optional N*M multiplier, optional space."""
        term = self._normalize_mult(term.strip()).lower()

        for pattern in self._EMOJI_PATTERNS:
            if m := pattern.match(term):
                word, n1, n2 = m['word'], m['n1'], m['n2']
                if e := self._get_emoji(word):
                    if n2:
                        self._last_computed = True
                    return (e, int(n1) * (int(n2) if n2 else 1), word)

        # Word doubles as factor and label, e.g. "3 * cat", "cat * 3"
        if m := re.match(r'^(\d+)\s*\*\s*(\w+)$', term):
            if e := self._get_emoji(m.group(2)):
                return (e, int(m.group(1)), m.group(2))
        if m := re.match(r'^(\w+)\s*\*\s*(\d+)$', term):
            if e := self._get_emoji(m.group(1)):
                return (e, int(m.group(2)), m.group(1))

        # Bare plural (e.g., "cats" -> 2 cat emojis, "tomatoes" -> 2 tomato emojis)
        if singular := singularize(term):
            # Skip uncountable nouns where singular == original (sheep, fish, deer, etc.)
            if singular != term.lower() and (e := self.content.get_emoji(singular)):
                return (e, 2, singular)

        # Single word (may still be a word that looks plural but isn't, e.g., "bus")
        if e := self._get_emoji(term):
            return (e, 1, term)

        return None

    def _get_emoji(self, word: str) -> str | None:
        """Emoji for a word. An exact color blocks a fuzzy emoji match, so
        "white" (exact color) is never read as fuzzy emoji "write" ✍️."""
        if e := self.content.exact_emoji(word):
            return e
        if self.content.exact_color(word):
            return None
        return self.content.fuzzy_emoji(word)

    def _get_color(self, word: str) -> str | None:
        """Color hex for a word. An exact emoji blocks a fuzzy color match, so
        "tree" (exact emoji) is never read as fuzzy color "green"."""
        if h := self.content.exact_color(word):
            return h
        if self.content.exact_emoji(word):
            return None
        return self.content.fuzzy_color(word)

    def _lookup(self, word: str) -> str | None:
        """Look up a bare word as emoji glyph or color box, exact-first.

        Exact match in either dictionary beats a fuzzy match in the other, so
        "white" stays the color and isn't hijacked by fuzzy emoji "write".
        """
        r = self.content.resolve(word)
        if r.kind == "emoji":
            return r.value
        if r.kind == "color":
            return f"[on {r.value}]  [/]"
        return None

    def _eval_modified_color(self, text: str) -> str | None:
        """Evaluate adjective + color, e.g. 'bright green' -> show base and modified swatch."""
        result = self.content.get_modified_color(text)
        if not result:
            return None
        modified_hex, base_hex, adjectives, color_name = result
        full_name = "_".join(adjectives) + "_" + color_name.replace(' ', '_')
        return f"COLOR_RESULT:{modified_hex}:{full_name}:{base_hex}"

    def _is_emoji_str(self, text: str) -> bool:
        """Check if text is emoji characters only."""
        return bool(text) and all(ord(c) > 127 or c.isspace() for c in text)

    def _is_plain_text(self, word: str) -> bool:
        """Check if word is plain English text (not emoji, number, operator, or expression)."""
        return bool(word) and word.isalpha() and all(ord(c) < 128 for c in word)

    def _normalize_number_words(self, text: str) -> str:
        """Convert number words to digits: 'three cats' → '3 cats'."""
        return self._NUMBER_WORDS_PATTERN.sub(
            lambda m: self.NUMBER_WORDS[m.group(1).lower()], text
        )

    def _normalize_commas(self, text: str) -> str:
        """Convert commas to plus when separating items: '2 red, 3 blue' → '2 red + 3 blue'.

        Triggers when there's at least one digit or color near a comma.
        Leaves plain text like 'hello, world' unchanged.
        """
        if ',' not in text:
            return text
        parts = [p.strip() for p in text.split(',')]
        if len(parts) < 2:
            return text
        has_expr = any(
            re.search(r'\d', p) or self.content.get_color(p.split()[0].lower() if p.split() else '')
            for p in parts if p
        )
        if has_expr:
            return ' + '.join(parts)
        return text

    def _normalize_math(self, text: str) -> str:
        """Normalize text for math evaluation: operator words/symbols → ASCII math."""
        result = text.lower()
        # Display operators (×, ÷) → ASCII
        for display, symbol in self.DISPLAY_TO_SYMBOL.items():
            result = result.replace(display, symbol)
        # Operator words → symbols (exact match with negative lookahead)
        for word, symbol in self._OPERATOR_WORDS.items():
            result = re.sub(word + r'(?![a-z])', symbol, result)
        # Fuzzy operator words between digits ("3 timess 2" → "3 * 2")
        result = self._fuzzy_normalize_operators(result)
        # "divided by" and typos (divded, dividd, etc.)
        result = re.sub(r'div\w+\s+by\b', '/', result)
        # x between digits → * (zero-width lookarounds so chained "2x3x4" works)
        result = re.sub(r'(?<=\d)\s*x\s*(?=\d)', '*', result)
        result = self._strip_stray_letters(result)
        # Strip leading zeros from number tokens (Python 3 rejects "01" as a literal)
        return re.sub(r'\b0+(\d)', r'\1', result)

    def _strip_stray_letters(self, text: str) -> str:
        """Drop a lone letter glued to a number ("2 + 3 + a9") when that makes
        the expression pure math: a finger slip, not a word. 'x' is multiplication."""
        if not re.search(r'[+\-*/]', text) or re.match(self.MATH_CHARS_PATTERN, text):
            return text
        stripped = re.sub(r'(?<![a-z])[a-wyz]\s?(?=\d)|(?<=\d)\s?[a-wyz](?![a-z])', '', text)
        if stripped != text and re.match(self.MATH_CHARS_PATTERN, stripped):
            self._last_math_correction = (text.strip(), stripped.strip())
            return stripped
        return text

    def _fuzzy_normalize_operators(self, text: str) -> str:
        """Replace exact or fuzzy operator words that appear between digits."""
        corrected = [False]

        def replace_match(m):
            word = m.group(2)
            if word in self._DIGIT_OPERATOR_WORDS:
                return m.group(1) + self._DIGIT_OPERATOR_WORDS[word] + m.group(3)
            matched = self._fuzzy_op_word(word)
            if matched:
                corrected[0] = True
                return m.group(1) + self._DIGIT_OPERATOR_WORDS[matched] + m.group(3)
            return m.group(0)

        def replace_div_by(m):
            if m.group(2) not in ('divide', 'divided'):
                corrected[0] = True
            return m.group(1) + '/' + m.group(3)

        result = re.sub(r'(\d\s+)([a-z]{3,})(\s+\d)', replace_match, text)
        result = re.sub(r'(\d\s+)(div\w+)\s+by(\s+\d)', replace_div_by, result)
        if corrected[0]:
            self._last_math_correction = (text, result)
        return result

    def _clean_math_expression(self, text: str) -> str:
        """Clean up math expression typos. Each rule is self-guarding by context.

        Handles: repeated operators (++→+), stray = signs, leading/trailing
        operators, xx between digits. Tracks correction for UI display.
        """
        result = text

        # Strip "= <answer>" at end (kid asserting: "5+3=8" → "5+3")
        result = re.sub(r'\s*=\s*\d+\s*$', '', result)

        # Replace stray = with + ONLY if real math operators are also present
        # (so "cat=dog" is untouched, but "5+3=2+1" cleans up)
        if '=' in result and re.search(r'[+\-*/]', result):
            result = result.replace('=', '+')

        # Collapse repeated operators: ++ → +, ** → *, // → /
        result = re.sub(r'([+\-*/])\1+', r'\1', result)

        # Collapse xx between digits: "5 xx 3" → "5 x 3"
        result = re.sub(r'(\d\s*)x+(\s*\d)', r'\1x\2', result, flags=re.IGNORECASE)

        # Strip leading/trailing operators (keep leading - for negatives)
        result = re.sub(r'^[+*/]+\s*', '', result)
        result = re.sub(r'\s*[+\-*/]+$', '', result)

        if result != text:
            self._last_math_correction = (text.strip(), result.strip())

        return result

    def _eval_math(self, text: str) -> float | int | str | None:
        """Safely evaluate math expression. Returns '🤷' for undefined (e.g. x/0)."""
        if not re.match(self.MATH_CHARS_PATTERN, text):
            return None
        try:
            result = eval(text, {"__builtins__": {}}, {})
        except ZeroDivisionError:
            self._last_computed = True
            return "🤷"
        except Exception:
            return None
        # Operator after a digit means real arithmetic; bare numbers don't count
        if re.search(r'[\d)]\s*[+\-*/]', text):
            self._last_computed = True
        if isinstance(result, float):
            # Snap binary float noise (3.2 + 5.4 == 8.600000000000001)
            result = float(f"{result:.12g}")
            if result.is_integer():
                return int(result)
        return result

    def _format_number(self, num: int | float) -> str:
        """Format number (up to 3 decimals). Prefix ≈ when rounding loses precision."""
        if isinstance(num, int) or num == int(num):
            return str(int(num))
        s = str(round(num, 3)).rstrip('0').rstrip('.')
        if float(s) != num:
            return f"≈ {s}"
        return s

    # Colors for abacus rows, from ones up (supports up to 1 billion)
    ABACUS_COLORS = [
        "#c4a0e8",  # ones: purple
        "#7eb8e0",  # tens: blue
        "#6ecfa0",  # hundreds: green
        "#e8d470",  # thousands: gold
        "#e8a07e",  # ten-thousands: orange
        "#e07eb8",  # hundred-thousands: pink
        "#e07e7e",  # millions: red
        "#7ee0c8",  # ten-millions: teal
        "#b8e07e",  # hundred-millions: lime
        "#e0c87e",  # billions: amber
    ]

    PLACE_NAMES = {
        1: "ones",
        10: "tens",
        100: "hundreds",
        1000: "thousands",
        10_000: "ten thousands",
        100_000: "hundred thousands",
        1_000_000: "millions",
        10_000_000: "ten millions",
        100_000_000: "hundred millions",
        1_000_000_000: "billions",
    }

    def _format_number_with_dots(self, num: int | float, show_label: bool = True, expression: str = "", bead: str = "●") -> str:
        """Format number as dots (≤10) or abacus (>10), with grouping for simple math.

        bead: character to use for abacus beads (default ●, can be an emoji).
        """
        formatted = self._format_number(num)
        label = formatted if show_label else None
        is_emoji_bead = bead != "●"
        if isinstance(num, (int, float)) and (isinstance(num, int) or num.is_integer()):
            n = int(num)
            if n >= 1:
                color = self.ABACUS_COLORS[0]
                # ≤ INLINE_MAX: plain dots/beads (with grouping for simple math)
                if n <= self.INLINE_MAX:
                    grouped = self._format_grouped_dots(n, expression, color, bead=bead)
                    if grouped:
                        content = grouped if is_emoji_bead else f"[{color}]{grouped}[/]"
                        if label:
                            return f"{label}\n{content}"
                        return content
                    spaced = " ".join([bead] * n)
                    content = spaced if is_emoji_bead else f"[{color}]{spaced}[/]"
                    if label:
                        return f"{label}\n{content}"
                    return content

                # > INLINE_MAX but within abacus range
                num_digits = len(str(n))
                if num_digits <= len(self.ABACUS_COLORS):
                    # Build all rows from highest place down to ones
                    all_rows = []
                    place = 10 ** (num_digits - 1)
                    remaining = n
                    while place >= 1:
                        digit = remaining // place
                        remaining %= place
                        all_rows.append((place, digit))
                        place //= 10

                    max_label_width = max(len(self.PLACE_NAMES.get(place, f"{place}s")) for place, _ in all_rows)
                    lines = []
                    for i, (place, digit) in enumerate(all_rows):
                        color_idx = len(all_rows) - 1 - i
                        c = self.ABACUS_COLORS[color_idx % len(self.ABACUS_COLORS)]
                        place_label = self.PLACE_NAMES.get(place, f"{place}s").rjust(max_label_width)
                        spaced = " ".join([bead] * digit) if digit > 0 else ""
                        if is_emoji_bead:
                            lines.append(f"[{c}]{place_label}[/]  {spaced}")
                        else:
                            lines.append(f"[{c}]{place_label}  {spaced}[/]")

                    if label:
                        return f"{label}\n" + "\n".join(lines)
                    return "\n".join(lines)

                # Beyond abacus range: colored number blocks
                colored = self._format_text_as_color_blocks(formatted)
                if label:
                    return f"{label}\n{colored}"
                return colored
        if label:
            return label
        return formatted

    def _format_grouped_dots(self, result: int, expression: str, color: str, bead: str = "●") -> str | None:
        """Format dots with grouping for simple addition/multiplication. Returns None if not applicable."""
        if not expression:
            # Default 5+5 grouping for 10 (makes it countable)
            if result == 10:
                return " ".join([bead] * 5) + "   " + " ".join([bead] * 5)
            return None
        # Match simple "a + b" (or "a + b + c + ...")
        terms = re.findall(r'\d+', expression)
        if '+' in expression and not re.search(r'[*/]', expression):
            values = [int(t) for t in terms]
            if sum(values) == result and all(v >= 1 for v in values):
                return "   ".join(" ".join([bead] * v) for v in values)
        # Match simple "a * b"
        m = re.match(r'^\s*(\d+)\s*\*\s*(\d+)\s*$', expression)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a * b == result and a >= 1 and b >= 1:
                groups = "   ".join(" ".join([bead] * a) for _ in range(b))
                return groups
        return None

    def _format_text_as_color_blocks(self, text: str) -> str:
        """Format plain text as colored blocks with letters on top.

        Every printable non-space character gets a colored block.
        This is the safe fallback: no raw markup can leak through.
        """
        blocks = []
        for char in text:
            if char.isspace():
                blocks.append(" ")
            elif ord(char) >= 32:
                bg = get_key_color(char)
                fg = _contrast_color(bg)
                # Escape [ for Rich markup safety
                display = "\\[" if char == '[' else char
                blocks.append(f"[{fg} on {bg}] {display} [/]")
        return "".join(blocks)

    def _format_text_on_color(self, text: str, bg_color: str) -> str:
        """Format text as letter blocks on a solid color background."""
        fg = _contrast_color(bg_color)
        blocks = []
        for char in text:
            if char.isspace():
                blocks.append(" ")
            elif char.isalnum():
                blocks.append(f"[{fg} on {bg_color}] {char} [/]")
            else:
                blocks.append(char)
        return "".join(blocks)

    def _substitute_emojis(self, text: str, colorize_unknown: bool = False) -> str:
        """Replace emoji and color words inline, including 'N word' patterns.

        When colorize_unknown=True, unknown words are rendered as per-letter
        colored blocks instead of plaintext.

        Examples:
            'I love cat' -> 'I 😍 🐱'
            'purple truck' -> '[on #7B2D8E]  [/] 🚚'
            '2 rabbits ate' -> '🐰🐰 ate'
            'the tomatoes' -> 'the 🍅🍅'
        """
        result, i = [], 0
        while i < len(text):
            # Check for "N word" pattern (e.g., "2 rabbits", "3 cats")
            if text[i].isdigit():
                # Collect all digits
                j = i
                while j < len(text) and text[j].isdigit():
                    j += 1
                num_str = text[i:j]
                num = int(num_str)
                # Check if followed by optional space and a word
                k = j
                while k < len(text) and text[k] == ' ':
                    k += 1
                if k < len(text) and text[k].isalpha():
                    # Collect the word
                    word_start = k
                    while k < len(text) and text[k].isalpha():
                        k += 1
                    word = text[word_start:k].lower()
                    # Check if it's an emoji word
                    if (emoji := self._get_emoji(word)) and num <= 100:
                        result.append(emoji * num)
                        i = k
                        continue
                # Not an "N emoji" pattern, just output the number
                if colorize_unknown:
                    result.append(self._format_text_as_color_blocks(num_str))
                else:
                    result.append(num_str)
                i = j
                continue

            if text[i].isalpha():
                j = i
                while j < len(text) and text[j].isalpha():
                    j += 1
                word = text[i:j].lower()
                if rendered := self._lookup(word):
                    result.append(rendered)
                elif colorize_unknown:
                    result.append(self._format_text_as_color_blocks(text[i:j]))
                else:
                    result.append(text[i:j])
                i = j
            else:
                # Try matching emoticons (e.g. :) :D <3) longest first
                # Only try if current char could start an emoticon (not spaces/letters)
                # Use exact match (no strip) to avoid consuming adjacent spaces
                matched = False
                if text[i] in ':;<>':
                    for length in (3, 2):
                        candidate = text[i:i + length]
                        if len(candidate) == length and candidate in self.content.emojis:
                            result.append(self.content.emojis[candidate])
                            i += length
                            matched = True
                            break
                if not matched:
                    ch = text[i]
                    # Escape [ to prevent Rich markup injection
                    result.append("\\[" if ch == '[' else ch)
                    i += 1
        return ''.join(result)

    def _describe_emoji_result(self, text: str, result: str) -> str:
        """Describe emoji result for speech (e.g., '3 apples and 2 bananas')."""
        parts = re.split(r'\s*(?:\+|plus)\s*', text.lower())
        descs = []
        for part in parts:
            part = part.strip()
            if m := re.match(r'^(\d+)\s*(?:[\*x]|times)\s*(\w+)$', part):
                count, name = int(m.group(1)), m.group(2)
                if self.content.get_emoji(name):
                    descs.append(f"{count} {name}s" if count != 1 else f"1 {name}")
            elif m := re.match(r'^(\w+)\s*(?:[\*x]|times)\s*(\d+)$', part):
                name, count = m.group(1), int(m.group(2))
                if self.content.get_emoji(name):
                    descs.append(f"{count} {name}s" if count != 1 else f"1 {name}")
            elif self.content.get_emoji(part):
                descs.append(part)
        if len(descs) == 1:
            return descs[0]
        if len(descs) == 2:
            return f"{descs[0]} and {descs[1]}"
        if descs:
            return ", ".join(descs[:-1]) + f", and {descs[-1]}"
        return result

    def _parse_color_result(self, result: str) -> tuple[str, str, list[str]] | None:
        """Parse COLOR_RESULT string -> (hex, name, components)."""
        if not result.startswith("COLOR_RESULT:"):
            return None
        parts = result.split(":", 3)
        if len(parts) >= 3:
            name = parts[2].replace('_', ' ')  # Convert back from underscore
            return (parts[1], name, parts[3].split(",") if len(parts) > 3 and parts[3] else [])
        return None

    def _make_speakable(self, input_text: str, result: str, computed: bool | None = None) -> str:
        """Convert input/result pair to minimal speakable text.

        Principles:
        - Don't pronounce emoji symbols or color boxes
        - When arithmetic happened: "input equals result"
        - Otherwise: just the input, spoken naturally
        - Speak typo corrections in their corrected form

        `computed` defaults to the flag from the last evaluate() call; the
        repeat path passes per-line flags captured at evaluation time.
        """
        input_text = input_text.strip()
        if not input_text:
            return ""

        if computed is None:
            computed = self._last_computed
        if self._last_math_correction:
            orig, corr = self._last_math_correction
            input_text = re.sub(re.escape(orig), corr, input_text, count=1, flags=re.IGNORECASE)

        # Convert operators to spoken words
        def speakable_ops(text: str) -> str:
            t = text.lower()
            t = re.sub(r'\bx\b', ' times ', t)
            return (t
                .replace("×", " times ")
                .replace("*", " times ")
                .replace("÷", " divided by ")
                .replace("/", " divided by ")
                .replace("+", " plus ")
                .replace("−", " minus ")
                .replace("-", " minus ")
                .replace("(", "").replace(")", "")
            )

        # Extract speakable result (first line, convert emoji counts to words)
        def speakable_result(res: str, input_prefix: str = "") -> str:
            if not res:
                return ""
            # Strip Rich markup and collapse spaces from colored blocks
            first_line = ' '.join(_strip_markup(res.split('\n')[0]).split())

            # Strip "= " prefix from pure math results
            if first_line.startswith("= "):
                first_line = first_line[2:]

            # Strip input prefix from result if present (avoid "what is ... equals what is ...")
            # Compare without spaces since colored blocks add padding around letters
            if input_prefix:
                fl_nospace = first_line.lower().replace(' ', '')
                ip_nospace = input_prefix.lower().replace(' ', '')
                if fl_nospace.startswith(ip_nospace):
                    # Walk first_line to find where prefix letters end
                    matched = 0
                    pos = 0
                    for i, ch in enumerate(first_line):
                        if matched >= len(ip_nospace):
                            pos = i
                            break
                        if ch != ' ' and ch.lower() == ip_nospace[matched]:
                            matched += 1
                    else:
                        pos = len(first_line)
                    first_line = first_line[pos:].strip()

            # Handle COLOR_RESULT
            if "COLOR_RESULT:" in first_line:
                # Extract color name and any surrounding text
                parts = first_line.split()
                out = []
                for p in parts:
                    if p.startswith("COLOR_RESULT:"):
                        color_data = self._parse_color_result(p)
                        if color_data:
                            out.append(color_data[1])  # color name
                    elif not self._is_emoji_str(p):  # Skip emoji parts
                        out.append(p)
                return ' '.join(out)

            # Handle multi-emoji label format (e.g., "6 🍌 2 🦁")
            # Parse patterns like "N emoji N emoji ..."
            emoji_descs = []
            remaining = first_line.strip()
            while remaining:
                m = re.match(r'^(\d+)\s+(\S+)\s*', remaining)
                if not m:
                    break
                count, emoji_part = int(m.group(1)), m.group(2).strip()
                if self._is_emoji_str(emoji_part):
                    emoji_char = emoji_part[0] if emoji_part else ''
                    word = self._emoji_to_word(emoji_char)
                    if word:
                        emoji_descs.append(f"{count} {word}s" if count != 1 else f"1 {word}")
                        remaining = remaining[m.end():].strip()
                        continue
                break

            if emoji_descs:
                if len(emoji_descs) == 1:
                    return emoji_descs[0]
                elif len(emoji_descs) == 2:
                    return f"{emoji_descs[0]} and {emoji_descs[1]}"
                else:
                    return ", ".join(emoji_descs[:-1]) + f", and {emoji_descs[-1]}"

            # Handle pure emoji result (find word equivalents)
            if self._is_emoji_str(first_line.replace(' ', '')):
                return ""  # Will use input description instead

            # Handle number result
            try:
                float(first_line.replace(",", ""))
                return first_line
            except ValueError:
                pass

            return first_line

        # Extract text prefix (e.g., "what is" from "what is 2 + 3")
        def extract_prefix(text: str) -> str:
            words = text.split()
            for i, word in enumerate(words):
                clean = re.sub(r'[^\w]', '', word.lower())
                # Found start of expression (number, operator word, color, or emoji)
                if (re.match(r'^\d+$', clean) or
                    clean in self.WORD_TO_SYMBOL or
                    self._get_color(clean) or
                    self._get_emoji(clean)):
                    return ' '.join(words[:i]) if i > 0 else ""
            return ""

        input_prefix = extract_prefix(input_text)
        result_speak = speakable_result(result, input_prefix)
        input_speak = speakable_ops(input_text)

        # Clean up extra spaces
        input_speak = ' '.join(input_speak.split())

        if not computed:
            # No computation: just say the input naturally
            return input_speak

        # Computation happened: "input equals result"
        if result_speak:
            return f"{input_speak} equals {result_speak}"
        else:
            # Result is pure emoji with no label, describe based on input
            return input_speak

    def _emoji_to_word(self, emoji: str) -> str | None:
        """Reverse lookup: emoji character to word."""
        return self.content.emoji_to_word(emoji)
