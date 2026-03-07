"""
Explore Room: Math and Emoji REPL for Kids

IPython-style interface:
- Ask → user types input
- Answer: shows result

Features:
- Basic math: 2 + 2, 3 x 4, 10 - 5
- Word synonyms: times, plus, minus
- Emoji display: typing "cat" shows 🐱
- Emoji math: 3 * cat produces 🐱🐱🐱
- Typo tolerance: long math expressions forgive accidental keystrokes
- Speech: add ! anywhere (e.g., "cat!") or Enter on empty to repeat
- History (up/down arrows)
- Emoji autocomplete (Space to accept)
"""

from textual.widgets import Static, Input
from textual.widget import Widget
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.app import ComposeResult
from textual import events
from textual.message import Message
from textual.strip import Strip
from rich.segment import Segment
from rich.style import Style
from rich.highlighter import Highlighter
from rich.text import Text
import re

from ..content import singularize

from ..content import get_content
from ..keyboard import (
    SHIFT_MAP, KeyRepeatSuppressor,
    CharacterAction, NavigationAction, ControlAction,
)
from ..color_mixing import mix_colors_paint, get_color_name_approximation
from ..scrolling import scroll_widget
from .doodle_room import get_key_color, PaintModeChanged


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

    def __init__(self, text: str, line_type: str = "ask", speaking: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.text = _pad_narrow_emoji(text)
        self.line_type = line_type  # "ask" or "answer"
        self.speaking = speaking
        self.add_class("caps-sensitive")
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

        Each token is either a complete markup block like '[#000 on #FFF] x [/]'
        or a single plain character.
        """
        tokens = []
        i = 0
        while i < len(text):
            # Check for Rich markup block: [tag]content[/]
            if text[i] == '[':
                # Find the closing [/] for this block
                end = text.find('[/]', i)
                if end != -1:
                    token = text[i:end + 3]
                    # Visual width = length of content between tags
                    inner = re.sub(r'\[[^\]]*\]', '', token)
                    width = sum(2 if ord(c) > 127 else 1 for c in inner)
                    tokens.append((token, width))
                    i = end + 3
                    continue
            # Plain character
            ch = text[i]
            width = 2 if ord(ch) > 127 else 1
            tokens.append((ch, width))
            i += 1
        return tokens

    def _wrap_with_arrows(self, text: str, prefix: str, arrow_color: str) -> str:
        """Wrap text with arrow-indented continuation lines.

        Breaks at token boundaries so colored blocks don't get split.
        """
        width = self.size.width
        if width <= 0:
            width = 108  # fallback

        prefix_len = sum(2 if ord(c) > 127 else 1 for c in re.sub(r'\[[^\]]*\]', '', prefix))
        cont_prefix = f"     [{arrow_color}]→[/] "
        cont_len = sum(2 if ord(c) > 127 else 1 for c in re.sub(r'\[[^\]]*\]', '', cont_prefix))

        tokens = self._tokenize_markup(text)
        lines = []
        current_line = prefix
        current_width = prefix_len

        for token, tw in tokens:
            if current_width + tw > width and current_width > (prefix_len if not lines else cont_len):
                lines.append(current_line)
                current_line = cont_prefix
                current_width = cont_len
            current_line += token
            current_width += tw

        if current_line:
            lines.append(current_line)

        return '\n'.join(lines)

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        dark = self._is_dark()
        if self.line_type == "ask":
            ask_color = self.ASK_ARROW_DARK if dark else self.ASK_ARROW_LIGHT
            prefix = f"[bold {ask_color}]Ask →[/] "
            return self._wrap_with_arrows(caps(self.text), prefix, ask_color)
        else:
            answer_color = self.ANSWER_ARROW_DARK if dark else self.ANSWER_ARROW_LIGHT
            lines = self.text.split('\n')
            speaker = " 🔊" if self.speaking else "   "
            first_prefix = f"{speaker} [{answer_color}]→[/] "
            result = [self._wrap_with_arrows(caps(lines[0]), first_prefix, answer_color)]
            for line in lines[1:]:
                if line.strip():
                    cont_prefix = f"    [{answer_color}]→[/] "
                    result.append(self._wrap_with_arrows(caps(line), cont_prefix, answer_color))
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
            if self._speaking:
                segments = [Segment(" 🔊 ", surface_style), Segment("→ ", triangle_style)]
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


class ValidWordHighlighter(Highlighter):
    """Underlines valid emoji and color words as user types."""

    def highlight(self, text: Text) -> None:
        content = get_content()
        plain = str(text).lower()
        for match in re.finditer(r'[a-z]+', plain):
            if content.is_valid_word(match.group()):
                text.stylize("underline", match.start(), match.end())


class InlineInput(Input):
    """
    Inline input widget that appears after Ask: prompt.
    """

    class Submitted(Message, bubble=True):
        """Message sent when user presses Enter"""
        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    # Display math operators as clearer Unicode versions (not emoji, so they inherit text color)
    # Only substitute * and / since + and - are already clear
    MATH_DISPLAY = {
        '*': '×',   # Multiplication sign U+00D7
        '/': '÷',   # Division sign U+00F7
    }

    # Math operators that get auto-spaced for readability (e.g., "5+3" becomes "5 + 3")
    MATH_OPERATORS = {'+', '-', '*', '/'}

    def __init__(self, **kwargs):
        super().__init__(placeholder="", highlighter=ValidWordHighlighter(), **kwargs)
        self.autocomplete_matches: list[tuple[str, str]] = []  # [(word, emoji/hex), ...]
        self.autocomplete_type: str = "emoji"  # "emoji" or "color"
        self.autocomplete_index: int = 0
        self.exact_match_display: str = ""  # emoji/color hint for exact word matches
        self._repeat_suppressor = KeyRepeatSuppressor()

    def action_scroll_up(self) -> None:
        """Scroll the history up"""
        try:
            scroll_widget(self.app.query_one("#history-scroll"), -1)
        except Exception:
            pass

    def action_scroll_down(self) -> None:
        """Scroll the history down"""
        try:
            scroll_widget(self.app.query_one("#history-scroll"), 1)
        except Exception:
            pass

    async def _on_key(self, event: events.Key) -> None:
        """Suppress terminal key events. All input comes via evdev/handle_keyboard_action()."""
        # Purple Computer uses evdev for keyboard input, bypassing the terminal.
        # This handler suppresses any terminal key events to avoid duplicate processing.
        # See handle_keyboard_action() in ExploreMode for the actual input handling.
        event.stop()
        event.prevent_default()

    def _check_autocomplete(self) -> None:
        """Check if current input should show autocomplete for colors and/or emojis.

        Colors and emojis can both appear in expressions like "cat + red" or "red + blue",
        so we search both and combine results, prioritizing exact matches.
        """
        content = get_content()
        text = self.value.lower().strip()

        # Common 2-letter words that shouldn't trigger autocomplete
        COMMON_2CHAR = {'am', 'an', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if',
                        'in', 'is', 'it', 'me', 'my', 'no', 'of', 'on', 'or', 'so',
                        'to', 'up', 'us', 'we', 'hi', 'oh', 'ok'}

        # Find the last word being typed (sequence of letters at the end)
        match = re.search(r'([a-z]+)$', text)
        last_word = match.group(1) if match else ""
        if len(last_word) < 2 or last_word in COMMON_2CHAR:
            self.autocomplete_matches = []
            self.autocomplete_type = "emoji"
            self.autocomplete_index = 0
            self.exact_match_display = ""
            return

        # If exact match exists, show its emoji/color as confirmation (no arrow hint)
        if content.is_valid_word(last_word):
            self.autocomplete_matches = []
            self.autocomplete_type = "emoji"
            self.autocomplete_index = 0
            emoji = content.get_emoji(last_word)
            color = content.get_color(last_word)
            parts = []
            if emoji:
                parts.append(emoji)
            if color:
                parts.append(f"[{color}]██[/]")
            self.exact_match_display = " ".join(parts)
            return
        self.exact_match_display = ""

        # Search both colors and emojis
        color_matches = {w: h for w, h in content.search_colors(last_word) if w != last_word}
        emoji_matches = {w: e for w, e in content.search_emojis(last_word) if w != last_word}

        # Combine results, grouping overlapping words together
        # Format: (word, color_hex or None, emoji or None)
        all_words = sorted(set(color_matches.keys()) | set(emoji_matches.keys()))
        combined = []
        for word in all_words:
            color_hex = color_matches.get(word)
            emoji = emoji_matches.get(word)
            combined.append((word, color_hex, emoji))

        # Limit to 5 total suggestions
        combined = combined[:5]

        if not combined:
            self.autocomplete_matches = []
            self.autocomplete_type = "emoji"
            self.autocomplete_index = 0
            self.exact_match_display = ""
            return

        # Store matches as (word, color_hex, emoji) tuples
        has_colors = any(c for _, c, _ in combined)
        has_emojis = any(e for _, _, e in combined)

        self.autocomplete_matches = combined
        self.autocomplete_type = "mixed" if (has_colors and has_emojis) else ("color" if has_colors else "emoji")
        self.autocomplete_index = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update autocomplete suggestions as user types"""
        self._check_autocomplete()

    @property
    def autocomplete_hint(self) -> str:
        """Get the autocomplete hint to display. Shows up to 5 options.

        Handles colors (shown as colored blocks) and emojis.
        Overlapping words (both color and emoji) show as: word [color] emoji
        When an exact match is typed, shows just the emoji/color as confirmation.
        """
        # Exact match: show emoji/color confirmation (no arrow hint)
        if self.exact_match_display:
            return self.exact_match_display

        if not self.autocomplete_matches:
            return ""

        caps = getattr(self.app, 'caps_text', lambda x: x)

        # Show up to 5 matches
        shown = self.autocomplete_matches[:5]
        parts = []

        for word, color_hex, emoji in shown:
            # Build display: word emoji? [color]?
            display = f"[dim]{caps(word)}[/]"
            if emoji:
                display += f" {emoji}"
            if color_hex:
                display += f" [{color_hex}]██[/]"
            parts.append(display)

        hint = "   ".join(parts)
        return f"{hint}   [dim]→ Tab[/]"


class InputPrompt(Static):
    """Shows 'Ask →' prompt with input area"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_class("caps-sensitive")

    def render(self) -> str:
        text = self.app.caps_text("Ask") if hasattr(self.app, 'caps_text') else "Ask"
        return f"[bold #c4a0e8]{text} →[/]"


class AutocompleteHint(Static):
    """Shows autocomplete suggestion and help hints"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_class("caps-sensitive")


class ExampleHint(Static):
    """Shows example hint with caps support"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_class("caps-sensitive")

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        text = caps("Try: cat  •  2 + 2  •  red + blue  •  cat times 3")
        return f"[dim]{text}[/]"


class ExploreMode(Vertical):
    """
    Explore Mode: IPython-style REPL interface for kids.
    """

    DEFAULT_CSS = """
    ExploreMode {
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

    #input-prompt {
        width: auto;
        height: 1;
        color: $primary;
    }

    #explore-input {
        width: 1fr;
        height: 1;
        border: none;
        background: $surface;
        padding: 0;
        margin: 0 0 0 1;
    }

    #explore-input:focus {
        border: none;
    }

    #autocomplete-hint {
        height: 1;
        color: $text-muted;
        margin-bottom: 1;
        margin-top: 1;
        margin-left: 5;
    }

    #explore-example-hint {
        height: 1;
        text-align: center;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.evaluator = SimpleEvaluator()
        # Track last input/result for "speak again" (Enter on empty)
        self._last_eval_text: str = ""
        self._last_result: str = ""

    def compose(self) -> ComposeResult:
        yield KeyboardOnlyScroll(id="history-scroll")
        with Vertical(id="bottom-area"):
            with Horizontal(id="input-row"):
                yield InputPrompt(id="input-prompt")
                yield InlineInput(id="explore-input")
            yield AutocompleteHint(id="autocomplete-hint")
            yield ExampleHint(id="explore-example-hint")

    def on_mount(self) -> None:
        """Focus the input when mode loads"""
        self.query_one("#explore-input").focus()

    def clear_history(self) -> None:
        """Clear the history scroll and reset last result."""
        try:
            scroll = self.query_one("#history-scroll")
            scroll.remove_children()
            self._last_eval_text = ""
            self._last_result = ""
        except Exception:
            pass

    async def handle_keyboard_action(self, action) -> None:
        """
        Handle keyboard actions from the main app's KeyboardStateMachine.

        This mode uses Textual's Input widget which needs special treatment.
        We handle some actions directly and forward others to the input.
        """
        explore_input = self.query_one("#explore-input", InlineInput)

        # Handle navigation (up/down for scrolling history, left/right ignored)
        if isinstance(action, NavigationAction):
            if action.direction == 'up':
                explore_input.action_scroll_up()
            elif action.direction == 'down':
                explore_input.action_scroll_down()
            elif action.direction == 'right' and explore_input.autocomplete_matches:
                # Right arrow: accept autocomplete suggestion
                selected_word = explore_input.autocomplete_matches[explore_input.autocomplete_index][0]
                words = explore_input.value.split()
                if words:
                    words[-1] = selected_word
                    explore_input.value = " ".join(words) + " "
                    explore_input.cursor_position = len(explore_input.value)
                explore_input.autocomplete_matches = []
                explore_input.autocomplete_index = 0
                explore_input.exact_match_display = ""
                explore_input._check_autocomplete()
            # Left arrow is ignored (no cursor movement for kids)
            return

        # Handle control actions
        if isinstance(action, ControlAction):
            if action.action == 'tab' and action.is_down and explore_input.autocomplete_matches:
                # Tab: accept autocomplete suggestion (same as right arrow)
                selected_word = explore_input.autocomplete_matches[explore_input.autocomplete_index][0]
                words = explore_input.value.split()
                if words:
                    words[-1] = selected_word
                    explore_input.value = " ".join(words) + " "
                    explore_input.cursor_position = len(explore_input.value)
                explore_input.autocomplete_matches = []
                explore_input.autocomplete_index = 0
                explore_input.exact_match_display = ""
                explore_input._check_autocomplete()
                return

            if action.action == 'space' and action.is_down:
                # Space always types a space (autocomplete is accepted with right arrow)
                explore_input.value += " "
                explore_input.cursor_position = len(explore_input.value)
                explore_input._check_autocomplete()
                return

            if action.action == 'enter' and action.is_down:
                if explore_input.value.strip():
                    explore_input.post_message(InlineInput.Submitted(explore_input.value))
                    explore_input.value = ""
                else:
                    # Enter on empty: speak last result ("say it again")
                    if self._last_eval_text or self._last_result:
                        self._speak(self._last_eval_text, self._last_result)
                explore_input.autocomplete_matches = []
                explore_input.autocomplete_index = 0
                explore_input.exact_match_display = ""
                return

            if action.action == 'backspace' and action.is_down:
                # Allow key repeats: held backspace erases like an eraser
                if explore_input.value:
                    # Always delete from end (simpler for kids, no cursor confusion)
                    explore_input.value = explore_input.value[:-1]
                    explore_input.cursor_position = len(explore_input.value)
                    explore_input._check_autocomplete()
                return

            if action.action == 'escape' and action.is_down and not action.is_repeat:
                # ESC tap clears the prompt (start over button)
                if explore_input.value:
                    explore_input.value = ""
                    explore_input.cursor_position = 0
                    explore_input.autocomplete_matches = []
                    explore_input.autocomplete_index = 0
                    explore_input.exact_match_display = ""
                    explore_input._check_autocomplete()
                return

            return

        # Handle character input
        if isinstance(action, CharacterAction):
            # Skip key repeats for characters (debounce held keys)
            if action.is_repeat:
                return

            char = action.char

            # Math operators: auto-space for readability and substitute display chars
            if char in explore_input.MATH_OPERATORS:
                display_char = explore_input.MATH_DISPLAY.get(char, char)
                value = explore_input.value

                # Add spaces around operator only if there's an operand before (binary operation)
                # No spaces if preceded by space, operator, or open paren (allows negative numbers)
                has_operand_before = value and value[-1] not in ' +-×÷*/('
                if has_operand_before:
                    insert = f" {display_char} "
                else:
                    insert = display_char

                explore_input.value = value + insert
                explore_input.cursor_position = len(explore_input.value)
                explore_input._check_autocomplete()
                return

            # Normal character (always append at end)
            explore_input.value += char
            explore_input.cursor_position = len(explore_input.value)
            explore_input._check_autocomplete()
            # Update color legend to show active row
            self.post_message(PaintModeChanged(True, get_key_color(char)))
            return

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update autocomplete hint display"""
        try:
            explore_input = self.query_one("#explore-input", InlineInput)
            hint = self.query_one("#autocomplete-hint", AutocompleteHint)
            hint.update(explore_input.autocomplete_hint)
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
        eval_text = input_text

        # Check for ! anywhere
        if '!' in eval_text:
            force_speak = True
            eval_text = eval_text.replace('!', '')

        # Check for speak prefix (e.g., "say", "talk")
        words = eval_text.split(None, 1)
        if words and words[0].lower() in SimpleEvaluator.SPEAK_PREFIXES:
            force_speak = True
            eval_text = words[1] if len(words) > 1 else ""

        # Clean up whitespace after stripping
        eval_text = eval_text.strip()

        # Add the "Ask →" line to history (without speech markers)
        if eval_text:
            scroll.mount(HistoryLine(eval_text, line_type="ask"))

        # Evaluate and show result
        result = self.evaluator.evaluate(eval_text)
        if result:
            # Check if this is a color result (special format)
            # Mixed results look like "text COLOR_RESULT:hex:name:comps emoji_stuff"
            color_part, before_part, after_part = None, None, None
            if "COLOR_RESULT:" in result:
                # Find and extract the COLOR_RESULT token
                parts = result.split()
                for i, p in enumerate(parts):
                    if p.startswith("COLOR_RESULT:"):
                        color_part = p
                        before_part = " ".join(parts[:i]) if i > 0 else None
                        after_part = " ".join(parts[i+1:]) if i < len(parts) - 1 else None
                        break

            if color_part:
                color_data = self.evaluator._parse_color_result(color_part)
                if color_data:
                    hex_color, color_name, components = color_data
                    other_part = " ".join(filter(None, [before_part, after_part]))
                    # Modified color (1 component that differs): show base → result swatch
                    is_modified = (len(components) == 1 and
                        components[0].upper() != hex_color.upper())
                    # Bare single color: inline box; modified or multi-color: swatch
                    if len(components) <= 1 and not is_modified:
                        color_box = f"[on {hex_color}]  [/]"
                        parts = [before_part, color_box, after_part]
                        display = " ".join(filter(None, parts))
                        scroll.mount(HistoryLine(display, line_type="answer", speaking=force_speak))
                    elif is_modified and not other_part:
                        scroll.mount(ColorResultLine(hex_color, color_name, components, speaking=force_speak))
                    else:
                        # Multi-color with emoji: show inputs → result
                        if other_part:
                            comp_boxes = " ".join(f"[on {c}]  [/]" for c in components)
                            result_box = f"[on {hex_color}]  [/]"
                            input_parts = [before_part, comp_boxes, after_part]
                            input_line = " ".join(filter(None, input_parts))
                            result_parts = [before_part, result_box, after_part]
                            result_line = " ".join(filter(None, result_parts))
                            # Prefer inline when compact enough
                            combined = f"{input_line} → {result_line}"
                            if self.evaluator._estimate_visual_width(combined) <= 80:
                                display = combined
                            else:
                                display = f"{input_line}\n\n{result_line}"
                            scroll.mount(HistoryLine(display, line_type="answer", speaking=force_speak))
                        else:
                            scroll.mount(ColorResultLine(hex_color, color_name, components, speaking=force_speak))
            else:
                scroll.mount(HistoryLine(result, line_type="answer", speaking=force_speak))

        # Scroll to bottom
        scroll.scroll_end(animate=False)

        # Store for "speak again" (Enter on empty)
        self._last_eval_text = eval_text
        self._last_result = result or ""

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
            speak(speakable)


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
    SPEAK_PREFIXES = {'say', 'talk'}

    # Math operators: symbols and their word equivalents
    MATH_SYMBOLS = {'+', '-', '*', '/', '×', '÷', '−'}
    WORD_TO_SYMBOL = {'times': '*', 'plus': '+', 'minus': '-', 'x': '*'}
    # Display operators to normalize before evaluation
    DISPLAY_TO_SYMBOL = {'×': '*', '÷': '/'}
    # Regex for detecting plus expressions (symbol or word)
    PLUS_PATTERN = r'\+|(?<!\w)plus(?!\w)'
    # Regex for valid math expression characters
    MATH_CHARS_PATTERN = r'^[\d\s\+\-\*\/\(\)\.]+$'
    # Valid math punctuation (operators, parens, decimal) for "mostly math" detection
    MATH_PUNCTUATION = set('+-*/(). ')
    # Thresholds for "mostly math" detection (filters typos like accidental '=')
    MIN_MATH_OPERATORS = 3
    MATH_RATIO_THRESHOLD = 0.6  # 60% of punctuation must be math symbols

    def __init__(self):
        self.content = get_content()

    def evaluate(self, text: str) -> str:
        """Evaluate input and return result string."""
        text = text.strip()
        if not text:
            return ""

        # Clean typos in mostly-math expressions (e.g., accidental '=' key)
        original_text = text
        text = self._clean_mostly_math(text)
        was_corrected = (text != original_text)

        # Track if original had parens (implies computation)
        had_parens = '(' in text

        # Handle parentheses first
        text = self._eval_parens(text)

        # Try adjective + color (e.g., "bright green", "dark light blue")
        if modified := self._eval_modified_color(text):
            return modified

        # Try text with embedded expression (e.g., "what is 2 + 3", "I have 5 apples")
        if result := self._eval_text_with_expr(text, had_parens):
            return self._prepend_corrected(result, text, was_corrected)

        # Check if it's a + expression
        if re.search(self.PLUS_PATTERN, text.lower()):
            if result := self._eval_plus_expr(text):
                result = self._maybe_add_label(result, had_parens)
                return self._prepend_corrected(result, text, was_corrected)

        # Try multiplication: "3 * cat", "cat times 5", etc.
        if mult := self._eval_mult(text):
            result = self._maybe_add_label(mult, had_parens)
            return self._prepend_corrected(result, text, was_corrected)

        # Try pure math
        normalized = self._normalize_math(text)
        if (math_result := self._eval_math(normalized)) is not None:
            # If input is just a bare number, skip the label (Ask line already shows it)
            is_bare_number = re.match(r'^\d+$', text.strip())
            # Bare negative numbers (e.g. "-5") aren't useful as math, show as colored text
            is_bare_negative = re.match(r'^-\d+$', text.strip())
            if is_bare_negative:
                return self._format_text_as_color_blocks(text.strip())
            result = self._format_number_with_dots(math_result, show_label=not is_bare_number, expression=normalized)
            if not is_bare_number:
                result = f"= {result}"
            return self._prepend_corrected(result, text, was_corrected)

        # Try single word lookup (emoji or color)
        if single := self._lookup(text.lower().strip()):
            return single

        # Try auto-mixing colors with emojis or text (e.g., "red apple", "red blue")
        if auto_mix := self._eval_auto_mix(text):
            return auto_mix

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

    def _prepend_corrected(self, result: str, corrected_text: str, was_corrected: bool) -> str:
        """If the input was auto-corrected, prepend a line showing what was actually calculated."""
        if was_corrected:
            return f"→ {corrected_text}\n{result}"
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

        # Prepend prefix to each line of the result
        lines = result.split('\n')
        return '\n'.join(f"{prefix} {line}" for line in lines)

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
            return self._format_number_with_dots(math_result, expression=normalized)

        # Try single word lookup
        if single := self._lookup(text.lower().strip()):
            return single

        return None

    def _eval_parens(self, text: str) -> str:
        """Evaluate innermost parentheses first, recursively."""
        for _ in range(10):
            if not (match := re.search(r'\(([^()]+)\)', text)):
                break
            result = self.evaluate(match.group(1))
            # Strip label/dot visualization for use in outer expressions
            result = result.split('\n')[0]
            # Strip "= " prefix from math results
            if result.startswith("= "):
                result = result[2:]
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
        """Evaluate + expression. Preserves order. Numbers attach to next term (color or emoji). Colors mix."""
        parts = re.split(r'\s*(?:' + self.PLUS_PATTERN + r')\s*', text.lower())

        colors = []  # Collect for mixing
        items = []   # (type, value) in original order: value is (emoji, count, word) for emoji
        pending = 0

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Color term (collect for mixing, placeholder at first position)
            # Pending numbers add extra copies of this color
            if hexes := self._parse_color(part):
                if pending > 0:
                    # Add pending copies of first color in this term
                    hexes = [hexes[0]] * pending + hexes
                    pending = 0
                colors.extend(hexes)
                if not any(t == 'color' for t, _ in items):
                    items.append(('color', None))
                continue

            # Emoji term (pending becomes a separate group for visual grouping)
            if emoji_data := self._parse_emoji(part):
                emoji, count, word = emoji_data
                if pending:
                    items.append(('emoji', (emoji, pending, word)))
                items.append(('emoji', (emoji, count, word)))
                pending = 0
                continue

            # Bare number or math expression (e.g., "3 * 4")
            normalized = self._normalize_math(part)
            if (math_result := self._eval_math(normalized)) is not None:
                pending += int(math_result) if float(math_result).is_integer() else math_result
                continue

            # Emoji string (from parens)
            if self._is_emoji_str(part):
                chars = [c for c in part if ord(c) > 127]
                if chars and all(c == chars[0] for c in chars):
                    items.append(('emoji', (chars[0], len(chars) + pending, None)))
                else:
                    items.append(('emoji', (part, 1 + pending, None)))
                pending = 0
                continue

            # Unknown: try emoji substitution, pass through
            # Extract leading "N word" emoji patterns (e.g., "2 rabbits ate 3" -> 2 rabbit emojis + "ate" + pending=3)
            remaining = part
            # Extract leading "N emoji-word" pattern
            if m := re.match(r'^(\d+)\s+(\w+)\s+(.+)$', remaining):
                num, word, rest = int(m.group(1)), m.group(2).lower(), m.group(3)
                if emoji := self._get_emoji(word):
                    items.append(('emoji', (emoji, num, word.rstrip('s') if word.endswith('s') else word)))
                    remaining = rest
            # Extract trailing number to add to pending (e.g., "ate 3" -> "ate" + pending=3)
            if m := re.match(r'^(.+?)\s+(\d+)$', remaining):
                text_part, num = m.group(1), int(m.group(2))
                if text_part.strip():
                    items.append(('text', self._substitute_emojis(text_part)))
                pending += num
            elif remaining.strip():
                items.append(('text', self._substitute_emojis(remaining)))

        # Attach remaining pending to last emoji or color
        if pending:
            for i in range(len(items) - 1, -1, -1):
                if items[i][0] == 'emoji':
                    e, c, w = items[i][1]
                    items[i] = ('emoji', (e, c + pending, w))
                    pending = 0
                    break
            # If still pending and have colors, attach to colors
            if pending and colors:
                colors.extend([colors[-1]] * int(pending))
                pending = 0

        # Collect emoji info for label formatting
        emoji_items = [(e, c, w) for t, v in items if t == 'emoji' for e, c, w in [v]]
        # Show label if any computation happened (counts > 1 or multiple types with total > types)
        # e.g., "3 cats" (single type, count > 1) or "2 * 3 banana + lions" (multiple, total > 2)
        total_count = sum(c for _, c, _ in emoji_items)
        has_computation = (
            total_count > len(emoji_items)  # More emojis than unique types means multiplication happened
        )
        show_label = (has_computation
                      and not colors and not any(t == 'text' for t, _ in items))

        # Compute mixed color for combining with emojis or text
        mixed_color = None
        if colors:
            mixed_color = mix_colors_paint(colors) if len(colors) > 1 else colors[0]

        only_colors_and_emojis = all(t in ('color', 'emoji') for t, _ in items)
        has_mixable_text = any(
            t == 'text' and all(ch.isalnum() or ch.isspace() for ch in v)
            for t, v in items
        )

        # Emojis on colored background (e.g., "red + apple", "blue + yellow + 3 cats")
        if mixed_color and emoji_items and only_colors_and_emojis:
            emoji_strs = []
            input_parts = []
            for t, v in items:
                if t == 'emoji':
                    e, c, w = v
                    emoji_strs.append(e * c)
                    input_parts.append(e * c)
                elif t == 'color':
                    input_parts.append(
                        " + ".join(f"[on {c}]  [/]" for c in colors)
                    )
            result = f"[on {mixed_color}] {' '.join(emoji_strs)} [/]"
            if pending:
                result += " " + self._format_number_with_dots(pending)
            input_line = " + ".join(input_parts)
            combined = f"{input_line} → {result}"
            if self._estimate_visual_width(combined) <= 80:
                return combined
            return f"{input_line}\n{result}"

        # Text blocks mixed with color (e.g., "tavi + red", "hello + blue + yellow")
        if mixed_color and has_mixable_text:
            result_parts = []
            input_parts = []
            for t, v in items:
                if t == 'color':
                    input_parts.append(
                        " + ".join(f"[on {c}]  [/]" for c in colors)
                    )
                elif t == 'emoji':
                    e, c, w = v
                    emoji_str = e * c
                    result_parts.append(f"[on {mixed_color}] {emoji_str} [/]")
                    input_parts.append(emoji_str)
                elif t == 'text':
                    if all(ch.isalnum() or ch.isspace() for ch in v):
                        result_parts.append(
                            self._format_text_on_color(v, mixed_color)
                        )
                        input_parts.append(self._format_text_as_color_blocks(v))
                    else:
                        result_parts.append(v)
                        input_parts.append(v)
            if pending:
                result_parts.append(self._format_number_with_dots(pending))
            result = " ".join(result_parts) if result_parts else None
            if result and input_parts:
                input_str = " + ".join(input_parts)
                combined = f"{input_str} → {result}"
                if self._estimate_visual_width(combined) <= 80:
                    return combined
                return f"{input_str}\n{result}"
            return result

        # Build result in order, showing + between items
        result_parts = []
        for item_type, value in items:
            if item_type == 'color' and colors:
                mixed = mix_colors_paint(colors) if len(colors) > 1 else colors[0]
                name = get_color_name_approximation(mixed)
                result_parts.append(f"COLOR_RESULT:{mixed}:{name.replace(' ', '_')}:{','.join(colors)}")
            elif item_type == 'emoji':
                e, c, w = value
                result_parts.append(e * c)
            elif item_type == 'text':
                result_parts.append(value)

        if pending:
            result_parts.append(self._format_number_with_dots(pending))

        # Only return if we have colors or emojis (not just text/numbers which pure math can handle)
        if colors or any(t == 'emoji' for t, _ in items):
            result = ' + '.join(result_parts) if result_parts else None
            # Add label line for emoji computation
            if show_label and result:
                # Combine same emoji types: "1 dog + 3 dogs" → "4 🐶"
                combined = {}
                for e, c, w in emoji_items:
                    combined[e] = combined.get(e, 0) + c
                label_parts = [f"{c} {e}" for e, c in combined.items()]
                label = ' '.join(label_parts)
                result = f"{label}\n{result}"
            return result
        return None

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

    def _eval_auto_mix(self, text: str) -> str | None:
        """Auto-mix colors with emojis, other colors, or text without requiring +.

        Triggers when all words are colors, emojis, or plain text, with at least
        one color and something to mix with. Falls through for unknown word types.
        """
        words = text.split()
        if len(words) < 2:
            return None

        # Merge adjective+color groups before categorizing
        # e.g. ["bright", "green", "blue"] -> [("bright green", modified_hex), ("blue", blue_hex)]
        from ..color_mixing import COLOR_ADJECTIVES
        merged_words = []
        i = 0
        while i < len(words):
            lower = words[i].lower()
            if lower in COLOR_ADJECTIVES:
                # Collect consecutive adjectives
                adj_start = i
                while i < len(words) and words[i].lower() in COLOR_ADJECTIVES:
                    i += 1
                if i < len(words):
                    # Try adjectives + remaining word as modified color
                    adj_phrase = " ".join(w.lower() for w in words[adj_start:i+1])
                    if mod := self.content.get_modified_color(adj_phrase):
                        merged_words.append(("__modified_color__", mod[0]))
                        i += 1
                        continue
                # Not a valid adjective+color, put words back as-is
                for j in range(adj_start, min(i, len(words))):
                    merged_words.append(words[j])
            else:
                merged_words.append(words[i])
                i += 1

        # Categorize each word
        word_info = []  # list of ('color', hex) | ('emoji', e, count) | ('text', word)
        colors = []
        has_emoji = False
        has_text = False

        for word in merged_words:
            # Handle pre-merged modified colors
            if isinstance(word, tuple) and word[0] == "__modified_color__":
                word_info.append(('color', word[1]))
                colors.append(word[1])
                continue
            lower = word.lower()
            if h := self._get_color(lower):
                word_info.append(('color', h))
                colors.append(h)
            elif emoji_data := self._parse_emoji(lower):
                e, c, w = emoji_data
                word_info.append(('emoji', e, c))
                has_emoji = True
            elif self._is_plain_text(lower):
                word_info.append(('text', word))
                has_text = True
            else:
                return None  # Unknown word type, fall through

        if not colors:
            return None
        if not has_emoji and len(colors) < 2 and not has_text:
            return None
        mixed = mix_colors_paint(colors) if len(colors) > 1 else colors[0]

        # Max visual width for inline display (accounts for "    → " prefix = 6 chars)
        MAX_INLINE_WIDTH = 80

        # Colors + emojis (and optionally text): paint emojis on color bg, text as colored letters
        if has_emoji:
            input_parts = []
            emoji_strs = []
            text_words = []
            for info in word_info:
                if info[0] == 'color':
                    input_parts.append(f"[on {info[1]}]  [/]")
                elif info[0] == 'emoji':
                    s = info[1] * info[2]
                    emoji_strs.append(s)
                    input_parts.append(s)
                elif info[0] == 'text':
                    input_parts.append(self._format_text_as_color_blocks(info[1]))
                    text_words.append(info[1])
            result_parts = []
            if emoji_strs:
                result_parts.append(f"[on {mixed}] {' '.join(emoji_strs)} [/]")
            if text_words:
                result_parts.append(self._format_text_on_color(" ".join(text_words), mixed))
            input_str = " + ".join(input_parts)
            result = " ".join(result_parts)
            # Prefer inline when compact enough
            combined = f"{input_str} → {result}"
            if self._estimate_visual_width(combined) <= MAX_INLINE_WIDTH:
                return combined
            return f"{input_str}\n{result}"

        # Colors only (2+): mix and show components + result
        if len(colors) >= 2 and not has_text:
            name = get_color_name_approximation(mixed)
            return f"COLOR_RESULT:{mixed}:{name.replace(' ', '_')}:{','.join(colors)}"

        # Colors + plain text: mix text blocks with color
        if has_text:
            input_parts = []
            text_words = []
            for info in word_info:
                if info[0] == 'color':
                    input_parts.append(f"[on {info[1]}]  [/]")
                elif info[0] == 'text':
                    input_parts.append(self._format_text_as_color_blocks(info[1]))
                    text_words.append(info[1])
            input_str = " + ".join(input_parts)
            text_str = " ".join(text_words)
            result = self._format_text_on_color(text_str, mixed)
            # Prefer inline when compact enough
            combined = f"{input_str} → {result}"
            if self._estimate_visual_width(combined) <= MAX_INLINE_WIDTH:
                return combined
            return f"{input_str}\n{result}"

        return None

    def _normalize_mult(self, text: str) -> str:
        """Normalize multiplication operators (x, times, ×) to *."""
        result = text.replace('×', '*')
        result = re.sub(r'\btimes\b', '*', result, flags=re.IGNORECASE)
        result = re.sub(r'(?<=[\d\w])\s*\bx\b\s*(?=[\d\w])', ' * ', result, flags=re.IGNORECASE)
        return result

    def _format_emoji_label(self, emoji: str, count: int) -> str:
        """Format emoji with label: 'N 🐱' then full visualization."""
        return f"{count} {emoji}\n{emoji * count}"

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
            if c <= 100:
                # Show label if there's explicit operator (*, x, times)
                if has_operator and c > 1:
                    return self._format_emoji_label(e, c)
                return e * c

        # "N * word" for colors (no label for colors)
        if m := re.match(r'^(\d+)\s*\*\s*(\w+)$', t_lower):
            count, word = int(m.group(1)), m.group(2)
            if (h := self._get_color(word)) and count <= 100:
                return f"[on {h}]  [/]" * count

        # "word * N" for colors
        if m := re.match(r'^(\w+)\s*\*\s*(\d+)$', t_lower):
            word, count = m.group(1), int(m.group(2))
            if (h := self._get_color(word)) and count <= 100:
                return f"[on {h}]  [/]" * count

        # "N word" for colors (e.g., "3 red")
        if m := re.match(r'^(\d+)\s*(\w+)$', t_lower):
            count, word = int(m.group(1)), m.group(2)
            if (h := self._get_color(word)) and count <= 100:
                return f"[on {h}]  [/]" * count

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

    def _parse_emoji(self, term: str) -> tuple[str, int, str] | None:
        """Parse emoji term -> (emoji_char, count, word)."""
        term = self._normalize_mult(term.strip()).lower()

        # "N * M word" (e.g., "3 * 4 cats")
        if m := re.match(r'^(\d+)\s*\*\s*(\d+)\s+(\w+)$', term):
            n1, n2, word = int(m.group(1)), int(m.group(2)), m.group(3)
            count = n1 * n2
            if (e := self._get_emoji(word)) and count <= 100:
                return (e, count, word)

        # "N * word" or "word * N"
        if m := re.match(r'^(\d+)\s*\*\s*(\w+)$', term):
            word = m.group(2)
            if (e := self._get_emoji(word)) and int(m.group(1)) <= 100:
                return (e, int(m.group(1)), word)
        if m := re.match(r'^(\w+)\s*\*\s*(\d+)$', term):
            word = m.group(1)
            if (e := self._get_emoji(word)) and int(m.group(2)) <= 100:
                return (e, int(m.group(2)), word)

        # "N word" or "Nword"
        if m := re.match(r'^(\d+)\s*(\w+)$', term):
            word = m.group(2)
            if (e := self._get_emoji(word)) and int(m.group(1)) <= 100:
                return (e, int(m.group(1)), word)

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
        """Get emoji (content.get_emoji handles plurals via inflect)."""
        return self.content.get_emoji(word)

    def _get_color(self, word: str) -> str | None:
        """Get color hex (content.get_color handles plurals via inflect)."""
        return self.content.get_color(word)

    def _lookup(self, word: str) -> str | None:
        """Look up word as emoji or color box."""
        if e := self._get_emoji(word):
            return e
        if h := self._get_color(word):
            return f"[on {h}]  [/]"
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

    def _normalize_math(self, text: str) -> str:
        """Normalize text for math evaluation."""
        result = text.lower()
        # Convert display operators (fullwidth, ×, ÷) to ASCII symbols first
        for display, symbol in self.DISPLAY_TO_SYMBOL.items():
            result = result.replace(display, symbol)
        # Convert word operators to symbols (no word boundaries to allow "3times4")
        for word, symbol in self.WORD_TO_SYMBOL.items():
            if word != 'x':  # 'x' is handled specially below
                result = result.replace(word, symbol)
        # Handle "divided by" separately (two words)
        result = re.sub(r'divided\s*by', '/', result)
        # Handle x between digits (avoid replacing 'x' in words like "fox")
        return re.sub(r'(\d)\s*x\s*(\d)', r'\1*\2', result)

    def _clean_mostly_math(self, text: str) -> str:
        """Clean text that looks mostly like math (filters typos like accidental '=').

        If the text has at least MIN_MATH_OPERATORS math operators and at least
        MATH_RATIO_THRESHOLD of ASCII punctuation symbols are valid math punctuation,
        filter out the invalid ones. Digits, letters, emojis, spaces are always kept.

        Example: "2+3+4-5+5+3-2=3+4+6" -> "2+3+4-5+5+3-23+4+6" (= removed)
        """
        # Count math operators
        math_ops = set('+-*/')
        math_op_count = sum(1 for c in text if c in math_ops)

        # Get all ASCII punctuation (excludes digits, letters, spaces, emojis)
        ascii_punct = [c for c in text if ord(c) < 128 and not c.isalnum() and not c.isspace()]
        # Count how many are valid math punctuation
        math_punct_count = sum(1 for c in ascii_punct if c in self.MATH_PUNCTUATION)

        # Check if it looks mostly like math
        if (math_op_count >= self.MIN_MATH_OPERATORS and
            len(ascii_punct) > 0 and
            math_punct_count / len(ascii_punct) >= self.MATH_RATIO_THRESHOLD):
            # Replace invalid ASCII punctuation with '+' (likely typo, e.g. '=' next to '+')
            def keep_or_plus(c):
                if c.isalnum() or c.isspace() or ord(c) > 127 or c in self.MATH_PUNCTUATION:
                    return c
                return '+'
            return ''.join(keep_or_plus(c) for c in text)

        return text

    def _eval_math(self, text: str) -> float | int | None:
        """Safely evaluate math expression."""
        if not re.match(self.MATH_CHARS_PATTERN, text):
            return None
        try:
            result = eval(text, {"__builtins__": {}}, {})
            return int(result) if isinstance(result, float) and result.is_integer() else result
        except Exception:
            return None

    def _format_number(self, num: int | float) -> str:
        """Format number (up to 3 decimals)."""
        if isinstance(num, int) or num == int(num):
            return str(int(num))
        return str(round(num, 3)).rstrip('0').rstrip('.')

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

    def _format_number_with_dots(self, num: int | float, show_label: bool = True, expression: str = "") -> str:
        """Format number as dots (≤10) or abacus (>10), with grouping for simple math."""
        formatted = self._format_number(num)
        label = formatted if show_label else None
        if isinstance(num, (int, float)) and (isinstance(num, int) or num.is_integer()):
            n = int(num)
            if n >= 1:
                color = self.ABACUS_COLORS[0]
                # ≤ 10: plain dots (with grouping for simple math)
                if n <= 10:
                    grouped = self._format_grouped_dots(n, expression, color)
                    if grouped:
                        if label:
                            return f"{label}\n[{color}]{grouped}[/]"
                        return f"[{color}]{grouped}[/]"
                    spaced_dots = " ".join("●" * n)
                    if label:
                        return f"{label}\n[{color}]{spaced_dots}[/]"
                    return f"[{color}]{spaced_dots}[/]"

                # > 9 but within abacus range
                num_digits = len(str(n))
                if num_digits <= len(self.ABACUS_COLORS):
                    rows = []
                    place = 1
                    remaining = n
                    while remaining > 0:
                        digit = remaining % 10
                        remaining //= 10
                        if digit > 0:
                            rows.append((place, digit))
                        place *= 10

                    rows.reverse()
                    max_label_width = max(len(f"{place}s") for place, _ in rows)
                    lines = []
                    for i, (place, digit) in enumerate(rows):
                        color_idx = len(rows) - 1 - i
                        c = self.ABACUS_COLORS[color_idx % len(self.ABACUS_COLORS)]
                        place_label = f"{place}s".rjust(max_label_width)
                        spaced_dots = " ".join("●" * digit)
                        lines.append(f"[{c}]{place_label}  {spaced_dots}[/]")

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

    def _format_grouped_dots(self, result: int, expression: str, color: str) -> str | None:
        """Format dots with grouping for simple addition/multiplication. Returns None if not applicable."""
        if not expression:
            # Default 5+5 grouping for 10 (makes it countable)
            if result == 10:
                return " ".join("●" * 5) + "   " + " ".join("●" * 5)
            return None
        # Match simple "a + b"
        m = re.match(r'^\s*(\d+)\s*\+\s*(\d+)\s*$', expression)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a + b == result and a >= 1 and b >= 1:
                return " ".join("●" * a) + "   " + " ".join("●" * b)
        # Match simple "a * b"
        m = re.match(r'^\s*(\d+)\s*\*\s*(\d+)\s*$', expression)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a * b == result and a >= 1 and b >= 1:
                groups = "   ".join(" ".join("●" * a) for _ in range(b))
                return groups
        return None

    def _format_text_as_color_blocks(self, text: str) -> str:
        """Format plain text as colored blocks with letters on top."""
        blocks = []
        for char in text:
            if char.isspace():
                blocks.append(" ")
            elif char.isalnum():
                bg = get_key_color(char)
                fg = _contrast_color(bg)
                blocks.append(f"[{fg} on {bg}] {char} [/]")
            else:
                blocks.append(char)
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
                result.append(num_str)
                i = j
                continue

            if text[i].isalpha():
                j = i
                while j < len(text) and text[j].isalpha():
                    j += 1
                word = text[i:j].lower()
                if emoji := self._get_emoji(word):
                    result.append(emoji)
                elif color_hex := self._get_color(word):
                    result.append(f"[on {color_hex}]  [/]")
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
                    result.append(text[i])
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

    def _make_speakable(self, input_text: str, result: str) -> str:
        """Convert input/result pair to minimal speakable text.

        Principles:
        - Don't pronounce emoji symbols or color boxes
        - For computation: "input equals result"
        - For simple lookups (no operators): just the word
        - Handle text prefixes naturally
        """
        input_text = input_text.strip()
        if not input_text:
            return ""

        # Check if input has operators (implies computation)
        def has_operator(text: str) -> bool:
            t = text.lower()
            if any(op in text for op in self.MATH_SYMBOLS):
                return True
            if any(f' {w} ' in f' {t} ' or t.startswith(f'{w} ') or t.endswith(f' {w}')
                   for w in self.WORD_TO_SYMBOL):
                return True
            if 'divided' in t:
                return True
            return False

        # Convert operators to spoken words
        def speakable_ops(text: str) -> str:
            t = text.lower()
            t = re.sub(r'(\d)\s*x\s*(\d)', r'\1 times \2', t)
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
            first_line = res.split('\n')[0]

            # Strip "= " prefix from pure math results
            if first_line.startswith("= "):
                first_line = first_line[2:]

            # Strip input prefix from result if present (avoid "what is ... equals what is ...")
            if input_prefix and first_line.lower().startswith(input_prefix.lower()):
                first_line = first_line[len(input_prefix):].strip()

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

        # Simple echo (input "5" → output "5", input "cat" → output emoji)
        computed = has_operator(input_text)
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
