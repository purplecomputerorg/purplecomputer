"""
Ask Mode - Math and Emoji REPL for Kids

IPython-style interface:
- Ask: user types input
- Answer: shows result

Features:
- Basic math: 2 + 2, 3 x 4, 10 - 5
- Word synonyms: times, plus, minus
- Emoji display: typing "cat" shows 🐱
- Emoji math: 3 * cat produces 🐱🐱🐱
- Speech output (Tab to toggle)
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
import re

from ..content import get_content
from ..constants import (
    TOGGLE_DEBOUNCE, DOUBLE_TAP_TIME,
    ICON_VOLUME_ON, ICON_VOLUME_OFF,
)
from ..keyboard import SHIFT_MAP
from ..color_mixing import mix_colors_paint, get_color_name_approximation


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

    def __init__(self, text: str, line_type: str = "ask", **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.line_type = line_type  # "ask" or "answer"
        if line_type == "ask":
            self.add_class("ask")

    def render(self) -> str:
        if self.line_type == "ask":
            return f"[bold #c4a0e8]Ask:[/] {self.text}"
        else:
            return f"[#a888d0]  →[/] {self.text}"


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

    def __init__(self, hex_color: str, color_name: str, component_colors: list[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._hex_color = hex_color
        self._color_name = color_name
        self._component_colors = component_colors or []

    def render_line(self, y: int) -> Strip:
        """Render each line of the color result"""
        width = self.size.width
        if width <= 0:
            width = 40

        prefix = "  →  "
        prefix_style = Style(color="#a888d0")

        # Line 0: Show component colors and arrow to result
        if y == 0:
            segments = [Segment(prefix, prefix_style)]

            # Show component color boxes
            if len(self._component_colors) > 1:
                for i, comp_hex in enumerate(self._component_colors):
                    # Add small colored box for each component
                    comp_style = Style(bgcolor=comp_hex)
                    segments.append(Segment("  ", comp_style))  # 2-char wide box
                    if i < len(self._component_colors) - 1:
                        segments.append(Segment(" ", Style()))  # space between

                # Arrow to result
                segments.append(Segment(" → ", Style(color="#a888d0")))

            # Start of result swatch (top row)
            result_style = Style(bgcolor=self._hex_color)
            segments.append(Segment(" " * self.SWATCH_WIDTH, result_style))

            # Color name after swatch
            text_color = self._get_contrast_color(self._hex_color)
            name_style = Style(color=text_color, bgcolor=self._hex_color, bold=True)
            segments.append(Segment(f" {self._color_name.upper()} ", name_style))

            return Strip(segments)

        # Lines 1-2: Continue the result swatch
        elif y < self.SWATCH_HEIGHT:
            segments = [Segment(prefix, Style())]  # Invisible prefix for alignment

            # Add spacing for component boxes if present
            if len(self._component_colors) > 1:
                # Each component is 2 chars + 1 space between
                comp_width = len(self._component_colors) * 2 + (len(self._component_colors) - 1)
                segments.append(Segment(" " * comp_width, Style()))
                segments.append(Segment("   ", Style()))  # " → " spacing

            # Result swatch continuation
            result_style = Style(bgcolor=self._hex_color)
            segments.append(Segment(" " * self.SWATCH_WIDTH, result_style))

            return Strip(segments)

        # Line 3: Empty line for spacing
        else:
            return Strip([Segment(" " * width, Style())])

    def _get_contrast_color(self, hex_color: str) -> str:
        """Get a contrasting text color (black or white) for readability"""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return "#000000" if luminance > 0.5 else "#FFFFFF"


class InlineInput(Input):
    """
    Inline input widget that appears after Ask: prompt.
    """

    class Submitted(Message, bubble=True):
        """Message sent when user presses Enter"""
        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    BINDINGS = [
        ("up", "scroll_up", "Scroll up"),
        ("down", "scroll_down", "Scroll down"),
        ("tab", "toggle_speech", "Toggle speech"),
    ]

    def __init__(self, **kwargs):
        super().__init__(placeholder="", **kwargs)
        self.autocomplete_matches: list[tuple[str, str]] = []  # [(word, emoji/hex), ...]
        self.autocomplete_type: str = "emoji"  # "emoji" or "color"
        self.autocomplete_index: int = 0
        self.last_char = None
        self.last_char_time = 0

    def action_scroll_up(self) -> None:
        """Scroll history up"""
        try:
            scroll = self.app.query_one("#history-scroll")
            scroll.scroll_up()
        except Exception:
            pass

    def action_scroll_down(self) -> None:
        """Scroll history down"""
        try:
            scroll = self.app.query_one("#history-scroll")
            scroll.scroll_down()
        except Exception:
            pass

    def action_toggle_speech(self) -> None:
        """Toggle speech on/off"""
        try:
            # Find the AskMode parent and toggle its speech indicator
            ask_mode = self.ancestors_with_self
            for ancestor in ask_mode:
                if isinstance(ancestor, AskMode):
                    indicator = ancestor.query_one("#speech-indicator", SpeechIndicator)
                    indicator.toggle()
                    break
        except Exception:
            pass

    def _check_autocomplete(self) -> None:
        """Check if current input should show autocomplete for colors or emojis"""
        content = get_content()
        text = self.value.lower().strip()

        # Get last word being typed (handle + operator for color mixing)
        # Split by spaces and + to get the last "word" being typed
        parts = re.split(r'[\s+]+', text)
        words = [p for p in parts if p]
        if not words:
            self.autocomplete_matches = []
            self.autocomplete_type = "emoji"
            self.autocomplete_index = 0
            return

        last_word = words[-1]
        if len(last_word) < 2:
            self.autocomplete_matches = []
            self.autocomplete_type = "emoji"
            self.autocomplete_index = 0
            return

        # Check if this looks like a color expression (has + or other color words)
        is_color_context = '+' in text or any(content.get_color(w) for w in words[:-1])

        # Search colors first (they take priority in color context)
        color_matches = content.search_colors(last_word)
        color_matches = [(w, h) for w, h in color_matches if w != last_word][:5]

        # If we have color matches, use those
        if color_matches:
            # If exact color match, don't show autocomplete
            if content.get_color(last_word):
                self.autocomplete_matches = []
                self.autocomplete_type = "color"
                self.autocomplete_index = 0
                return
            self.autocomplete_matches = color_matches
            self.autocomplete_type = "color"
            self.autocomplete_index = 0
            return

        # If in color context but no color matches, don't suggest emojis
        if is_color_context:
            self.autocomplete_matches = []
            self.autocomplete_type = "color"
            self.autocomplete_index = 0
            return

        # If the last word exactly matches an emoji, don't show autocomplete
        # This prevents "sun" + space from autocompleting to "sunflower"
        if content.get_emoji(last_word):
            self.autocomplete_matches = []
            self.autocomplete_type = "emoji"
            self.autocomplete_index = 0
            return

        # Search for emoji matches - get up to 5
        matches = content.search_emojis(last_word)
        # Filter out exact match and limit to 5
        self.autocomplete_matches = [(w, e) for w, e in matches if w != last_word][:5]
        self.autocomplete_type = "emoji"
        self.autocomplete_index = 0

    async def _on_key(self, event: events.Key) -> None:
        """Handle special keys before parent Input processes them"""
        import time

        char = event.character
        key = event.key

        # Space - accept autocomplete if there's a suggestion
        if event.key == "space" and self.autocomplete_matches:
            event.stop()
            event.prevent_default()
            # Replace last word with selected autocomplete
            selected_word = self.autocomplete_matches[self.autocomplete_index][0]
            words = self.value.split()
            if words:
                words[-1] = selected_word
                self.value = " ".join(words) + " "
                # Move cursor to end
                self.cursor_position = len(self.value)
            self.autocomplete_matches = []
            self.autocomplete_index = 0
            self.last_char = None
            return

        # Enter - submit
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            if self.value.strip():
                self.post_message(self.Submitted(self.value))
                self.value = ""
            self.autocomplete_matches = []
            self.autocomplete_index = 0
            self.last_char = None
            return

        # Double-tap for shifted characters
        if char and char in SHIFT_MAP:
            now = time.time()
            if self.last_char == char and (now - self.last_char_time) < DOUBLE_TAP_TIME:
                # Double-tap detected - replace last char with shifted version
                event.stop()
                event.prevent_default()
                # Remove last character and insert shifted
                if self.value:
                    self.value = self.value[:-1] + SHIFT_MAP[char]
                    self.cursor_position = len(self.value)
                self.last_char = None
                return
            else:
                # First tap - remember it
                self.last_char = char
                self.last_char_time = now
        else:
            self.last_char = None

        # Let parent handle other keys
        await super()._on_key(event)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update autocomplete suggestions as user types"""
        self._check_autocomplete()

    @property
    def autocomplete_hint(self) -> str:
        """Get the autocomplete hint to display - shows up to 5 options"""
        if not self.autocomplete_matches:
            return ""

        # Show up to 5 matches
        shown = self.autocomplete_matches[:5]
        parts = []

        if self.autocomplete_type == "color":
            # Show colored blocks for colors
            for name, hex_code in shown:
                # Use a colored square block with the color as background
                parts.append(f"{name} [{hex_code}]██[/]")
        else:
            # Show emojis as before
            for word, emoji in shown:
                parts.append(f"{word} {emoji}")

        hint = "   ".join(parts)
        return f"[dim]{hint}   ← space[/]"


class InputPrompt(Static):
    """Shows 'Ask:' prompt with input area"""

    def render(self) -> str:
        text = self.app.caps_text("Ask:") if hasattr(self.app, 'caps_text') else "Ask:"
        return f"[bold #c4a0e8]{text}[/]"


class AutocompleteHint(Static):
    """Shows autocomplete suggestion and help hints"""
    pass


class ExampleHint(Static):
    """Shows example hint with caps support"""

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        text = caps("Try: cat  •  2 + 2  •  red + blue  •  cat times 3")
        return f"[dim]{text}[/]"


class SpeechIndicator(Static):
    """Shows whether speech is on/off - Tab to toggle"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.speech_on = False
        self._state_before_toggle = False  # Track state before rapid toggles

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        if self.speech_on:
            return f"[bold green]{ICON_VOLUME_ON}  {caps('Tab: talking ON')}[/]"
        else:
            return f"[dim]{ICON_VOLUME_OFF}  {caps('Tab: talking off')}[/]"

    def _speak_if_changed(self) -> None:
        """Speak current state only if it differs from state before toggle sequence"""
        import threading

        def do_speak():
            from ..tts import speak, stop, init
            stop()  # Cancel any previous
            if self.speech_on != self._state_before_toggle:
                if self.speech_on:
                    init()
                speak("talking on" if self.speech_on else "talking off")
            # Reset for next toggle sequence
            self._state_before_toggle = self.speech_on

        # Run in background thread to avoid blocking UI
        threading.Thread(target=do_speak, daemon=True).start()

    def toggle(self) -> bool:
        # On first toggle in a sequence, remember the starting state
        # (if timer fires, it resets _state_before_toggle to current)
        if self.speech_on == self._state_before_toggle:
            self._state_before_toggle = self.speech_on

        self.speech_on = not self.speech_on

        # Update UI immediately - call refresh before anything else
        self.refresh()

        # Debounce: only speak after delay if state actually changed
        self.set_timer(TOGGLE_DEBOUNCE, self._speak_if_changed)

        return self.speech_on


class AskMode(Vertical):
    """
    Ask Mode - IPython-style REPL interface for kids.
    """

    DEFAULT_CSS = """
    AskMode {
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

    #ask-input {
        width: 1fr;
        height: 1;
        border: none;
        background: $surface;
        padding: 0;
        margin: 0 0 0 1;
    }

    #ask-input:focus {
        border: none;
    }

    #autocomplete-hint {
        height: 1;
        color: $text-muted;
        margin-bottom: 1;
        margin-top: 1;
        margin-left: 5;
    }

    #example-hint {
        height: 1;
        text-align: center;
        color: $text-muted;
    }

    #speech-indicator {
        dock: top;
        height: 1;
        text-align: right;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.evaluator = SimpleEvaluator()

    def compose(self) -> ComposeResult:
        yield SpeechIndicator(id="speech-indicator")
        yield KeyboardOnlyScroll(id="history-scroll")
        with Vertical(id="bottom-area"):
            with Horizontal(id="input-row"):
                yield InputPrompt(id="input-prompt")
                yield InlineInput(id="ask-input")
            yield AutocompleteHint(id="autocomplete-hint")
            yield ExampleHint(id="example-hint")

    def on_mount(self) -> None:
        """Focus the input when mode loads"""
        self.query_one("#ask-input").focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update autocomplete hint display"""
        try:
            ask_input = self.query_one("#ask-input", InlineInput)
            hint = self.query_one("#autocomplete-hint", AutocompleteHint)
            hint.update(ask_input.autocomplete_hint)
        except Exception:
            pass

    async def on_inline_input_submitted(self, event: InlineInput.Submitted) -> None:
        """Handle input submission"""
        input_text = event.value
        scroll = self.query_one("#history-scroll")

        # Add the "Ask:" line to history
        scroll.mount(HistoryLine(input_text, line_type="ask"))

        # Evaluate and show result
        result = self.evaluator.evaluate(input_text)
        if result:
            # Check if this is a color result (special format)
            color_data = self.evaluator._parse_color_result(result)
            if color_data:
                hex_color, color_name, components = color_data
                scroll.mount(ColorResultLine(hex_color, color_name, components))
            else:
                scroll.mount(HistoryLine(result, line_type="answer"))

        # Scroll to bottom
        scroll.scroll_end(animate=False)

        # Handle speech if enabled
        try:
            indicator = self.query_one("#speech-indicator", SpeechIndicator)
            if indicator.speech_on:
                self._speak(input_text, result)
        except Exception:
            pass

    def _speak(self, input_text: str, result: str) -> None:
        """Speak the input and result using Piper TTS"""
        from ..tts import speak

        # Check if input has math operators (not just number+word like "2banana")
        def has_math_operator(text: str) -> bool:
            # Has +, -, *, /, x (between numbers), times, plus, minus, divided
            import re
            text_lower = text.lower()
            if any(op in text for op in ['+', '-', '*', '/', '×', '÷']):
                return True
            if re.search(r'\d\s*x\s*\d', text_lower):  # x between numbers
                return True
            if any(word in text_lower for word in [' times ', ' plus ', ' minus ', ' divided']):
                return True
            # "times" or "x" with emoji word (like "cat times 3" or "3 x cat")
            if re.search(r'(times|(?<!\w)x(?!\w))', text_lower):
                return True
            return False

        # Make math expressions speakable
        def make_speakable(text: str) -> str:
            import re
            text = text.lower()
            text = re.sub(r'(\d)\s*x\s*(\d)', r'\1 times \2', text)
            return (text
                .replace("×", " times ")
                .replace("*", " times ")
                .replace("÷", " divided by ")
                .replace("/", " divided by ")
                .replace("+", " plus ")
                .replace("−", " minus ")
                .replace("-", " minus ")
                .replace("=", " equals ")
            )

        input_lower = input_text.lower().strip()
        has_operator = has_math_operator(input_text)

        # Check if result is a color mixing result
        if result and result.startswith("COLOR_RESULT:"):
            color_data = self.evaluator._parse_color_result(result)
            if color_data:
                _, color_name, _ = color_data
                # Make the input more speakable
                speakable_input = make_speakable(input_lower)
                text_to_speak = f"{speakable_input} equals {color_name}"
                speak(text_to_speak)
                return

        # Check if result is emoji (contains high unicode chars)
        if result and any(ord(c) > 127 for c in result):
            if has_operator:
                # Math with emoji: "2 * cat" -> "2 times cat equals 2 cats"
                description = self.evaluator._describe_emoji_result(input_text, result)
                text_to_speak = f"{make_speakable(input_text)} equals {description}"
            else:
                # No math operator: just read the input naturally
                # "2banana" -> "2 banana", "cat" -> "cat", "ari is cool" -> "ari is cool"
                text_to_speak = make_speakable(input_lower)
        # Check if result looks like math output (number, possibly with dots)
        elif result:
            result_num = result.split('\n')[0]
            try:
                float(result_num.replace(",", ""))
                # For simple number echo (input "5" -> output "5"), just say the number
                if input_lower == result_num:
                    text_to_speak = result_num
                elif has_operator:
                    text_to_speak = f"{make_speakable(input_text)} equals {result_num}"
                else:
                    text_to_speak = input_lower
            except (ValueError, AttributeError):
                # Not math, just speak the input
                text_to_speak = input_lower
        else:
            text_to_speak = input_lower

        speak(text_to_speak)


class SimpleEvaluator:
    """
    Simple math and emoji evaluator for kids.

    Supports:
    - Basic arithmetic: +, -, *, /
    - Word synonyms: "times", "plus", "minus", "divided by"
    - x between numbers treated as multiplication
    - Emoji variables and emoji math
    """

    def __init__(self):
        self.content = get_content()

    def evaluate(self, text: str) -> str:
        """Evaluate the input and return a result string"""
        text = text.strip()
        if not text:
            return ""

        # Handle parentheses first by evaluating innermost groups
        text = self._eval_parentheses(text)

        # Try color mixing first (e.g., "red + blue", "red + red + blue")
        color_result = self._eval_color_mixing(text)
        if color_result:
            return color_result

        # Try emoji math first (e.g., "3 * cat", "2 apples", "3banana")
        # This handles plurals and number+word combinations
        emoji_result = self._eval_emoji_math(text)
        if emoji_result:
            return emoji_result

        # Normalize input for math
        normalized = self._normalize(text)

        # Try to evaluate as math expression
        try:
            result = self._eval_math(normalized)
            if result is not None:
                return self._format_number_with_dots(result)
        except Exception:
            pass

        # Try emoji lookup for single word
        emoji = self.content.get_emoji(text.lower())
        if emoji:
            return emoji

        # Try emoji substitution in non-math text (e.g., "apple & orange")
        emoji_sub = self._substitute_emojis(text)
        if emoji_sub and emoji_sub != text:
            return emoji_sub

        # Just return the input as-is (string echo)
        return text

    def _eval_parentheses(self, text: str) -> str:
        """Recursively evaluate innermost parentheses first"""
        max_iterations = 10  # Prevent infinite loops
        for _ in range(max_iterations):
            # Find innermost parentheses (no nested parens inside)
            match = re.search(r'\(([^()]+)\)', text)
            if not match:
                break

            inner = match.group(1)
            inner_result = self._eval_inner(inner)
            # Replace the parenthesized expression with its result
            text = text[:match.start()] + inner_result + text[match.end():]

        return text

    def _eval_inner(self, text: str) -> str:
        """Evaluate an expression without parentheses"""
        text = text.strip()

        # Try pure math first
        normalized = self._normalize(text)
        try:
            result = self._eval_math(normalized)
            if result is not None:
                return self._format_number(result)
        except Exception:
            pass

        # Try emoji math
        emoji_result = self._eval_emoji_math(text)
        if emoji_result:
            return emoji_result

        # Try single emoji lookup
        emoji = self.content.get_emoji(text.lower())
        if emoji:
            return emoji

        # Return as-is
        return text

    def _normalize(self, text: str) -> str:
        """Normalize text for evaluation"""
        # Replace word operators with symbols (works with or without spaces: 2times3, 2 times 3)
        replacements = [
            (r'times', '*'),
            (r'plus', '+'),
            (r'minus', '-'),
            (r'divided\s*by', '/'),
        ]

        result = text.lower()
        for pattern, replacement in replacements:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        # x between numbers -> *
        result = re.sub(r'(\d)\s*x\s*(\d)', r'\1 * \2', result)

        return result

    def _eval_math(self, text: str) -> float | int | None:
        """Safely evaluate a math expression"""
        # Only allow digits, operators, spaces, parentheses, and decimal points
        if not re.match(r'^[\d\s\+\-\*\/\(\)\.]+$', text):
            return None

        try:
            result = eval(text, {"__builtins__": {}}, {})
            # Return int if it's a whole number
            if isinstance(result, float) and result.is_integer():
                return int(result)
            return result
        except Exception:
            return None

    def _format_number(self, num: int | float) -> str:
        """Format a number - up to 3 decimals, rounded"""
        if isinstance(num, int) or num == int(num):
            return str(int(num))
        rounded = round(num, 3)
        return str(rounded).rstrip('0').rstrip('.')

    def _format_number_with_dots(self, num: int | float) -> str:
        """Format a number with dot visualization for small integers"""
        formatted = self._format_number(num)

        # Only show dots for positive whole numbers less than 1000
        if isinstance(num, int) or (isinstance(num, float) and num.is_integer()):
            n = int(num)
            if 1 <= n < 1000:
                # Create dot visualization
                dots = "•" * n
                # Wrap dots to 90 chars per line (viewport is 100 with padding)
                lines = []
                for i in range(0, len(dots), 90):
                    lines.append(dots[i:i+90])
                dot_display = "\n".join(lines)
                return f"{formatted}\n{dot_display}"

        return formatted

    def _is_emoji_string(self, text: str) -> bool:
        """Check if text consists only of emoji characters (high unicode)"""
        return bool(text) and all(ord(c) > 127 or c.isspace() for c in text)

    def _eval_emoji_math(self, text: str) -> str | None:
        """Evaluate emoji expressions like '3 * cat', 'cat times 3', 'apple + banana', 'cat*3 + 2'
        Also handles: 'apples' (plural -> 2), '2 apples', '3banana'
        Also handles already-evaluated emoji strings from parentheses."""
        text_lower = text.lower()
        text_original = text  # Keep original for emoji string detection

        # Split by + or "plus" to handle additions
        parts_lower = re.split(r'\s*(?:\+|plus)\s*', text_lower)
        parts_original = re.split(r'\s*(?:\+|plus)\s*', text_original)
        results = []
        has_emoji = False  # Track if we found at least one emoji

        for part, part_orig in zip(parts_lower, parts_original):
            part = part.strip()
            part_orig = part_orig.strip()
            if not part:
                continue

            # Try: emoji_string * number (for already-evaluated emojis like "🐱🐶 * 2")
            match = re.match(r'^(.+?)\s*(?:[\*x]|times)\s*(\d+)$', part_orig)
            if match:
                emoji_str, count = match.group(1).strip(), int(match.group(2))
                if self._is_emoji_string(emoji_str) and count <= 100:
                    results.append((emoji_str * count, None, count))
                    has_emoji = True
                    continue

            # Try: number * emoji_string (for "2 * 🐱🐶")
            match = re.match(r'^(\d+)\s*(?:[\*x]|times)\s*(.+)$', part_orig)
            if match:
                count, emoji_str = int(match.group(1)), match.group(2).strip()
                if self._is_emoji_string(emoji_str) and count <= 100:
                    results.append((emoji_str * count, None, count))
                    has_emoji = True
                    continue

            # Try: number * word, number x word, or number times word
            match = re.match(r'^(\d+)\s*(?:[\*x]|times)\s*(\w+)$', part)
            if match:
                count, name = int(match.group(1)), match.group(2)
                emoji = self._get_emoji_singular(name)
                if emoji and count <= 100:
                    results.append((emoji * count, name, count))
                    has_emoji = True
                    continue

            # Try: word * number, word x number, or word times number
            match = re.match(r'^(\w+)\s*(?:[\*x]|times)\s*(\d+)$', part)
            if match:
                name, count = match.group(1), int(match.group(2))
                emoji = self._get_emoji_singular(name)
                if emoji and count <= 100:
                    results.append((emoji * count, name, count))
                    has_emoji = True
                    continue

            # Try: "2 apples" or "2apples" or "3 banana" or "3banana" (number followed by word)
            match = re.match(r'^(\d+)\s*(\w+)$', part)
            if match:
                count, name = int(match.group(1)), match.group(2)
                emoji = self._get_emoji_singular(name)
                if emoji and count <= 100:
                    results.append((emoji * count, name, count))
                    has_emoji = True
                    continue

            # Try: bare plural word like "apples" -> 2 emojis
            if part.endswith('s') and len(part) > 2:
                singular = part[:-1]
                emoji = self.content.get_emoji(singular)
                if emoji:
                    results.append((emoji * 2, singular, 2))
                    has_emoji = True
                    continue

            # Try: just a word (single emoji)
            emoji = self.content.get_emoji(part)
            if emoji:
                results.append((emoji, part, 1))
                has_emoji = True
                continue

            # Try: already-evaluated emoji string (from parentheses)
            if self._is_emoji_string(part_orig):
                results.append((part_orig, None, 1))
                has_emoji = True
                continue

            # Try: just a number (include as-is in mixed expressions)
            if re.match(r'^\d+$', part):
                results.append((part, None, int(part)))
                continue

            # Part didn't match anything - not emoji math
            return None

        # Only return if we found at least one emoji
        if results and has_emoji:
            return ''.join(r[0] for r in results)

        return None

    def _get_emoji_singular(self, word: str) -> str | None:
        """Get emoji for a word, handling plurals by stripping 's' suffix"""
        emoji = self.content.get_emoji(word)
        if emoji:
            return emoji
        # Try singular form if word ends in 's'
        if word.endswith('s') and len(word) > 2:
            return self.content.get_emoji(word[:-1])
        return None

    def _substitute_emojis(self, text: str) -> str:
        """Substitute emoji words with emojis in non-math text (e.g., 'apple & orange')"""
        # Find all word boundaries and try to replace emoji words
        result = []
        i = 0
        text_lower = text.lower()

        while i < len(text):
            # Try to find a word starting at position i
            if text_lower[i].isalpha():
                # Find word end
                j = i
                while j < len(text) and text_lower[j].isalpha():
                    j += 1
                word = text_lower[i:j]

                # Try to get emoji for this word
                emoji = self.content.get_emoji(word)
                if emoji:
                    result.append(emoji)
                else:
                    # Keep original text (preserve case)
                    result.append(text[i:j])
                i = j
            else:
                result.append(text[i])
                i += 1

        return ''.join(result)

    def _describe_emoji_result(self, text: str, result: str) -> str:
        """Describe an emoji math result for speech, e.g. '3 apples and 2 bananas'"""
        text_lower = text.lower()
        parts = re.split(r'\s*(?:\+|plus)\s*', text_lower)
        descriptions = []

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Try: number * word, number x word, or number times word
            match = re.match(r'^(\d+)\s*(?:[\*x]|times)\s*(\w+)$', part)
            if match:
                count, name = int(match.group(1)), match.group(2)
                if self.content.get_emoji(name):
                    descriptions.append(f"{count} {name}s" if count != 1 else f"1 {name}")
                    continue

            # Try: word * number, word x number, or word times number
            match = re.match(r'^(\w+)\s*(?:[\*x]|times)\s*(\d+)$', part)
            if match:
                name, count = match.group(1), int(match.group(2))
                if self.content.get_emoji(name):
                    descriptions.append(f"{count} {name}s" if count != 1 else f"1 {name}")
                    continue

            # Just a word - don't say "1 cat", just say "cat"
            if self.content.get_emoji(part):
                descriptions.append(part)

        if len(descriptions) == 1:
            return descriptions[0]
        elif len(descriptions) == 2:
            return f"{descriptions[0]} and {descriptions[1]}"
        elif len(descriptions) > 2:
            return ", ".join(descriptions[:-1]) + f", and {descriptions[-1]}"
        return result

    def _eval_color_mixing(self, text: str) -> str | None:
        """
        Evaluate color mixing expressions like "red + blue" or "red + red + blue".

        Returns a special formatted string with COLOR_RESULT: prefix that triggers
        the color swatch display, or None if not a color expression.

        Format: COLOR_RESULT:result_hex:color_name:comp1_hex,comp2_hex,...
        """
        text_lower = text.lower().strip()

        # Check if this looks like a color expression (colors separated by +)
        # Split by + and "plus"
        parts = re.split(r'\s*(?:\+|plus)\s*', text_lower)
        parts = [p.strip() for p in parts if p.strip()]

        if not parts:
            return None

        # Collect colors and their counts (for weighted mixing)
        colors_to_mix = []
        for part in parts:
            color_hex = self.content.get_color(part)
            if color_hex:
                colors_to_mix.append(color_hex)
            else:
                # Not a valid color - not a pure color expression
                return None

        if not colors_to_mix:
            return None

        # Single color - just show that color
        if len(colors_to_mix) == 1:
            mixed_hex = colors_to_mix[0]
        else:
            # Mix the colors using paint-like mixing
            mixed_hex = mix_colors_paint(colors_to_mix)

        # Get unique component colors for display (deduplicated, preserving order)
        seen = set()
        unique_components = []
        for c in colors_to_mix:
            if c not in seen:
                seen.add(c)
                unique_components.append(c)

        # Return a special marker that includes hex color, name, and components
        color_name = get_color_name_approximation(mixed_hex)
        components_str = ",".join(unique_components)
        return f"COLOR_RESULT:{mixed_hex}:{color_name}:{components_str}"

    def _is_color_result(self, result: str) -> bool:
        """Check if a result is a color result"""
        return result.startswith("COLOR_RESULT:")

    def _parse_color_result(self, result: str) -> tuple[str, str, list[str]] | None:
        """Parse a color result, returns (hex_color, color_name, component_colors) or None"""
        if not self._is_color_result(result):
            return None
        parts = result.split(":", 3)
        if len(parts) >= 3:
            hex_color = parts[1]
            color_name = parts[2]
            components = parts[3].split(",") if len(parts) > 3 and parts[3] else []
            return (hex_color, color_name, components)
        return None
