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
from textual.app import ComposeResult, RenderResult
from textual import events
from textual.message import Message
from textual.strip import Strip
from textual.content import Content
from textual.markup import MarkupError
from rich.segment import Segment
from rich.style import Style
import re


from ..constants import HOLD_OR_TAP_THRESHOLD

from ..content import get_content
from ..code_input import (
    WordHighlighter, CodeInput, InputPrompt,
    AutocompleteHint, RecallHint, ExampleHint,
)
from ..keyboard import (
    KeyRepeatSuppressor, HoldOrTap,
    CharacterAction, NavigationAction, ControlAction,
)
from ..scrolling import scroll_widget
from .art_room import get_key_color, PaintModeChanged


# The evaluator and its markup helpers live in purple_tui/play_eval.py;
# they stay importable from here.
from ..play_eval import (BLOCK_CHARS, SPEAK_REPEAT_CAP, SimpleEvaluator, _cell_width, _contrast_color,  # noqa: F401
                         _escape_markup, _escaped_width, _has_tag, _mix_tint, _repeat_emoji, _strip_markup,
                         pair_speakables, parse_speech_trigger, speakables_for)


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
            if text[i] == '\\' and i + 1 < len(text) and text[i + 1] == '[':
                # Escaped literal "[" the kid typed: keep both chars as one
                # token so the "[" is not mistaken for a tag opener.
                tokens.append(('\\[', _cell_width('[')))
                i += 2
                continue
            if text[i] == '[':
                end = text.find('[/]', i)
                if end != -1:
                    block = text[i:end + 3]
                    m = re.match(r'(\[[^\]]*\])(.*)\[/\]$', block, re.DOTALL)
                    if m:
                        open_tag, inner = m.group(1), m.group(2)
                        # A bare backslash would escape the "[/]" we re-emit
                        # after splitting, so keep such a block whole.
                        if inner.strip() == '' or re.search(r'\\(?!\[)', inner):
                            tokens.append((block, _escaped_width(inner)))
                        else:
                            for part in re.split(r'(\s+)', inner):
                                if not part:
                                    continue
                                tokens.append((f"{open_tag}{part}[/]",
                                               _escaped_width(part)))
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

    def render(self) -> RenderResult:
        markup = self._build_markup()
        try:
            return Content.from_markup(markup)
        except MarkupError:
            # Last line of defence: unbalanced markup must never kill the app.
            # Drop escapes first so no tag survives as visible text.
            return Content(_strip_markup(re.sub(r'\\+(?=\[)', '', markup)))

    def _build_markup(self) -> str:
        dark = self._is_dark()
        if self.line_type == "ask":
            ask_color = self.ASK_ARROW_DARK if dark else self.ASK_ARROW_LIGHT
            prefix = f"[bold {ask_color}]Ask →[/] "
            return self._wrap_with_arrows(_escape_markup(self.text), prefix, ask_color)
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

        force_speak, eval_text = parse_speech_trigger(input_text)

        # Add the "Ask →" line to history (without speech markers)
        if eval_text:
            scroll.mount(HistoryLine(eval_text, line_type="ask"))

        # Repeat commands: use PlayCodeRunner (parse_lines fixes fuzzy "repeet" → "repeat")
        from ..code_runner import PlayCodeRunner, is_repeat_line
        runner = PlayCodeRunner(self.evaluator)
        if is_repeat_line(eval_text):
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
        from ..tts import _dbg
        _dbg(f"submit raw={input_text!r} force_speak={force_speak} result_len={len(result or '')}")
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
        from ..tts import _dbg
        _dbg(f"speakable len={len(speakable)} head={speakable[:60]!r}")
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
            _dbg(f"speak started={started}")
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
        spoken = dict(pair_speakables(self.evaluator, pairs))
        items = []
        for i, widget in enumerate(widgets):
            if i in spoken:
                items.append((spoken[i], widget))
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
