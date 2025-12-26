"""
Ask Mode: Math and Emoji REPL for Kids

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
from rich.highlighter import Highlighter
from rich.text import Text
import re

from ..content import get_content
from ..constants import (
    TOGGLE_DEBOUNCE, DOUBLE_TAP_TIME,
    ICON_VOLUME_ON, ICON_VOLUME_OFF,
)
from ..keyboard import SHIFT_MAP, DoubleTapDetector
from ..color_mixing import mix_colors_paint, get_color_name_approximation
from ..scrolling import scroll_widget


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
            # Add arrow to each line for multi-line results
            lines = self.text.split('\n')
            return '\n'.join(f"[#a888d0]  →[/] {line}" for line in lines)


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
        """Render each line of the color result (mixed colors only, 3x6 swatch without name)"""
        width = self.size.width
        if width <= 0:
            width = 40

        prefix = "  →  "
        prefix_style = Style(color="#a888d0")

        # Line 0: Show component colors and arrow to result
        if y == 0:
            segments = [Segment(prefix, prefix_style)]

            # Show component color boxes (only if multiple components)
            if len(self._component_colors) > 1:
                for i, comp_hex in enumerate(self._component_colors):
                    # Add small colored box for each component
                    comp_style = Style(bgcolor=comp_hex)
                    segments.append(Segment("  ", comp_style))  # 2-char wide box
                    if i < len(self._component_colors) - 1:
                        segments.append(Segment(" ", Style()))  # space between

                # Arrow to result
                segments.append(Segment(" → ", Style(color="#a888d0")))

            # Start of result swatch (top row). No name label
            result_style = Style(bgcolor=self._hex_color)
            segments.append(Segment(" " * self.SWATCH_WIDTH, result_style))

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

    BINDINGS = [
        ("tab", "toggle_speech", "Toggle speech"),
    ]

    def __init__(self, **kwargs):
        super().__init__(placeholder="", highlighter=ValidWordHighlighter(), **kwargs)
        self.autocomplete_matches: list[tuple[str, str]] = []  # [(word, emoji/hex), ...]
        self.autocomplete_type: str = "emoji"  # "emoji" or "color"
        self.autocomplete_index: int = 0
        self._double_tap = DoubleTapDetector(
            threshold=DOUBLE_TAP_TIME,
            allowed_keys=set(SHIFT_MAP.keys()),
        )

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
        """Handle all special keys before Input processes them"""
        import time

        key = event.key
        char = event.character

        # Up/Down arrows: scroll the history
        if key == "up":
            event.stop()
            event.prevent_default()
            self.action_scroll_up()
            return
        if key == "down":
            event.stop()
            event.prevent_default()
            self.action_scroll_down()
            return

        # Space: accept autocomplete if there's a suggestion
        if key == "space" and self.autocomplete_matches:
            event.stop()
            event.prevent_default()
            selected_word = self.autocomplete_matches[self.autocomplete_index][0]
            words = self.value.split()
            if words:
                words[-1] = selected_word
                self.value = " ".join(words) + " "
                self.cursor_position = len(self.value)
            self.autocomplete_matches = []
            self.autocomplete_index = 0
            self._double_tap.reset()
            return

        # Enter: submit
        if key == "enter":
            event.stop()
            event.prevent_default()
            if self.value.strip():
                self.post_message(self.Submitted(self.value))
                self.value = ""
            self.autocomplete_matches = []
            self.autocomplete_index = 0
            self._double_tap.reset()
            return

        # Double-tap for shifted characters
        if char and self._double_tap.check(char):
            event.stop()
            event.prevent_default()
            if self.value:
                self.value = self.value[:-1] + SHIFT_MAP[char]
                self.cursor_position = len(self.value)
            return

        # Let parent Input handle all other keys
        await super()._on_key(event)

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
        """Check if current input should show autocomplete for colors and/or emojis.

        Colors and emojis can both appear in expressions like "cat + red" or "red + blue",
        so we search both and combine results, prioritizing exact matches.
        """
        content = get_content()
        text = self.value.lower().strip()

        # Find the last word being typed (sequence of letters at the end)
        match = re.search(r'([a-z]+)$', text)
        last_word = match.group(1) if match else ""
        if len(last_word) < 2:
            self.autocomplete_matches = []
            self.autocomplete_type = "emoji"
            self.autocomplete_index = 0
            return

        # If exact match exists (color, emoji, or plural), don't show autocomplete
        if content.is_valid_word(last_word):
            self.autocomplete_matches = []
            self.autocomplete_type = "emoji"
            self.autocomplete_index = 0
            return

        # Search both colors and emojis
        color_matches = content.search_colors(last_word)
        emoji_matches = content.search_emojis(last_word)

        # Combine results: colors first (marked as color type), then emojis
        # We'll track the type in the tuple: (word, display_value, is_color)
        combined = []
        seen_words = set()

        # Add color matches (show hex as display value)
        for word, hex_code in color_matches:
            if word != last_word and word not in seen_words:
                combined.append((word, hex_code, True))
                seen_words.add(word)

        # Add emoji matches
        for word, emoji in emoji_matches:
            if word != last_word and word not in seen_words:
                combined.append((word, emoji, False))
                seen_words.add(word)

        # Limit to 5 total suggestions
        combined = combined[:5]

        if not combined:
            self.autocomplete_matches = []
            self.autocomplete_type = "emoji"
            self.autocomplete_index = 0
            return

        # Store matches as (word, display_value). The display logic will handle rendering
        # Use "mixed" type if we have both colors and emojis
        has_colors = any(is_color for _, _, is_color in combined)
        has_emojis = any(not is_color for _, _, is_color in combined)

        self.autocomplete_matches = [(word, display) for word, display, _ in combined]
        self.autocomplete_type = "mixed" if (has_colors and has_emojis) else ("color" if has_colors else "emoji")
        self.autocomplete_index = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update autocomplete suggestions as user types"""
        self._check_autocomplete()

    @property
    def autocomplete_hint(self) -> str:
        """Get the autocomplete hint to display. Shows up to 5 options.

        Handles colors (shown as colored blocks) and emojis in any combination.
        """
        if not self.autocomplete_matches:
            return ""

        # Show up to 5 matches
        shown = self.autocomplete_matches[:5]
        parts = []

        for word, display_value in shown:
            # Detect if this is a color (hex code starts with #) or emoji
            if display_value.startswith("#"):
                # Color: show colored block (color at full opacity, word dimmed)
                parts.append(f"[dim]{word}[/] [{display_value}]██[/]")
            else:
                # Emoji: show as-is (emoji visible, word dimmed)
                parts.append(f"[dim]{word}[/] {display_value}")

        hint = "   ".join(parts)
        return f"{hint}   [dim]← space[/]"


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
    """Shows whether speech is on/off. Tab to toggle."""

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

        # Update UI immediately. Call refresh before anything else
        self.refresh()

        # Debounce: only speak after delay if state actually changed
        self.set_timer(TOGGLE_DEBOUNCE, self._speak_if_changed)

        return self.speech_on


class AskMode(Vertical):
    """
    Ask Mode: IPython-style REPL interface for kids.
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
                    # Single color: inline box; multiple: swatch
                    if len(components) <= 1:
                        color_box = f"[on {hex_color}]  [/]"
                        parts = [before_part, color_box, after_part]
                        display = " ".join(filter(None, parts))
                        scroll.mount(HistoryLine(display, line_type="answer"))
                    else:
                        # For multi-color with emoji, show swatch then emoji on same line after
                        if other_part:
                            # Show inline: before + component boxes + result + after
                            comp_boxes = " ".join(f"[on {c}]  [/]" for c in components)
                            result_box = f"[on {hex_color}]  [/]"
                            parts = [before_part, comp_boxes, "→", result_box, after_part]
                            display = " ".join(filter(None, parts))
                            scroll.mount(HistoryLine(display, line_type="answer"))
                        else:
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
    Unified evaluator for math, emojis, and colors.

    Rules (permissive, intuitive for kids):
    - Split by + to get terms
    - Numbers: accumulate, attach to next emoji term
    - Emojis: collect and concatenate
    - Colors: collect and mix (even if non-colors in between)
    - Parens: evaluate inner first, result becomes a term
    """

    def __init__(self):
        self.content = get_content()

    def evaluate(self, text: str) -> str:
        """Evaluate input and return result string."""
        text = text.strip()
        if not text:
            return ""

        # Handle parentheses first
        text = self._eval_parens(text)

        # Check if it's a + expression
        if re.search(r'\+|(?<!\w)plus(?!\w)', text.lower()):
            if result := self._eval_plus_expr(text):
                return result

        # Try multiplication: "3 * cat", "cat times 5", etc.
        if mult := self._eval_mult(text):
            return mult

        # Try pure math
        normalized = self._normalize_math(text)
        if (math_result := self._eval_math(normalized)) is not None:
            return self._format_number_with_dots(math_result)

        # Try single word lookup (emoji or color)
        if single := self._lookup(text.lower().strip()):
            return single

        # Try emoji substitution in text (e.g., "I love cat")
        subbed = self._substitute_emojis(text)
        return subbed if subbed != text else text

    def _eval_parens(self, text: str) -> str:
        """Evaluate innermost parentheses first, recursively."""
        for _ in range(10):
            if not (match := re.search(r'\(([^()]+)\)', text)):
                break
            result = self.evaluate(match.group(1))
            # Strip dot visualization for use in outer expressions
            result = result.split('\n')[0]
            text = text[:match.start()] + result + text[match.end():]
        return text

    def _eval_plus_expr(self, text: str) -> str | None:
        """Evaluate + expression. Preserves order. Numbers attach to next emoji. Colors mix (at first color's position)."""
        parts = re.split(r'\s*(?:\+|(?<!\w)plus(?!\w))\s*', text.lower())
        colors = []  # Collect for mixing
        items = []   # (type, value) in original order: value is (emoji, count, word) for emoji
        pending = 0

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Color term (collect for mixing, placeholder at first position)
            if hexes := self._parse_color(part):
                colors.extend(hexes)
                if not any(t == 'color' for t, _ in items):
                    items.append(('color', None))
                continue

            # Emoji term (pending attaches here)
            if emoji_data := self._parse_emoji(part):
                emoji, count, word = emoji_data
                items.append(('emoji', (emoji, count + pending, word)))
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
            items.append(('text', self._substitute_emojis(part)))

        # Attach remaining pending to last emoji
        if pending:
            for i in range(len(items) - 1, -1, -1):
                if items[i][0] == 'emoji':
                    e, c, w = items[i][1]
                    items[i] = ('emoji', (e, c + pending, w))
                    pending = 0
                    break

        # Collect emoji info for label formatting
        emoji_items = [(e, c, w) for t, v in items if t == 'emoji' for e, c, w in [v]]
        # If single emoji type with count > 1, show label
        show_label = (len(emoji_items) == 1 and emoji_items[0][2] and emoji_items[0][1] > 1
                      and not colors and not any(t == 'text' for t, _ in items))

        # Build result in order, merging adjacent emojis
        result_parts = []
        for item_type, value in items:
            if item_type == 'color' and colors:
                mixed = mix_colors_paint(colors) if len(colors) > 1 else colors[0]
                name = get_color_name_approximation(mixed)
                result_parts.append(f"COLOR_RESULT:{mixed}:{name.replace(' ', '_')}:{','.join(colors)}")
            elif item_type == 'emoji':
                e, c, w = value
                emoji_str = e * c
                # Merge with previous if also emoji
                if result_parts and self._is_emoji_str(result_parts[-1]):
                    result_parts[-1] += emoji_str
                else:
                    result_parts.append(emoji_str)
            elif item_type == 'text':
                result_parts.append(value)

        if pending:
            result_parts.append(self._format_number_with_dots(pending))

        # Only return if we have colors or emojis (not just text/numbers which pure math can handle)
        if colors or any(t == 'emoji' for t, _ in items):
            result = ' '.join(result_parts) if result_parts else None
            # Add label line for single emoji type with count
            if show_label and result:
                e, c, w = emoji_items[0]
                word = w + 's' if c != 1 and not w.endswith('s') else w
                result = f"{c} {word}\n{result}"
            return result
        return None

    def _normalize_mult(self, text: str) -> str:
        """Normalize multiplication operators (x, times) to *."""
        result = re.sub(r'\btimes\b', '*', text, flags=re.IGNORECASE)
        result = re.sub(r'(?<=[\d\w])\s*\bx\b\s*(?=[\d\w])', ' * ', result, flags=re.IGNORECASE)
        return result

    def _format_emoji_label(self, emoji: str, count: int, word: str) -> str:
        """Format emoji with label: 'N words\\nemojis'."""
        label = word + 's' if count != 1 and not word.endswith('s') else word
        return f"{count} {label}\n{emoji * count}"

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
                if has_operator and w and c > 1:
                    return self._format_emoji_label(e, c, w)
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

        # Just a color name (handles plurals via _get_color)
        if h := self._get_color(term):
            return [h]

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

        # Bare plural
        if term.endswith('s') and len(term) > 2:
            word = term[:-1]
            if e := self.content.get_emoji(word):
                return (e, 2, word)

        # Single word
        if e := self._get_emoji(term):
            return (e, 1, term.rstrip('s') if term.endswith('s') else term)

        return None

    def _get_emoji(self, word: str) -> str | None:
        """Get emoji, handling plurals."""
        if e := self.content.get_emoji(word):
            return e
        if word.endswith('s') and len(word) > 2:
            return self.content.get_emoji(word[:-1])
        return None

    def _get_color(self, word: str) -> str | None:
        """Get color hex, handling plurals."""
        if h := self.content.get_color(word):
            return h
        if word.endswith('s') and len(word) > 2:
            return self.content.get_color(word[:-1])
        return None

    def _lookup(self, word: str) -> str | None:
        """Look up word as emoji or color box."""
        if e := self._get_emoji(word):
            return e
        if h := self._get_color(word):
            return f"[on {h}]  [/]"
        return None

    def _is_emoji_str(self, text: str) -> bool:
        """Check if text is emoji characters only."""
        return bool(text) and all(ord(c) > 127 or c.isspace() for c in text)

    def _normalize_math(self, text: str) -> str:
        """Normalize text for math evaluation."""
        result = text.lower()
        for pat, repl in [(r'times', '*'), (r'plus', '+'), (r'minus', '-'), (r'divided\s*by', '/')]:
            result = re.sub(pat, repl, result)
        return re.sub(r'(\d)\s*x\s*(\d)', r'\1*\2', result)

    def _eval_math(self, text: str) -> float | int | None:
        """Safely evaluate math expression."""
        if not re.match(r'^[\d\s\+\-\*\/\(\)\.]+$', text):
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

    def _format_number_with_dots(self, num: int | float) -> str:
        """Format number with dot visualization."""
        formatted = self._format_number(num)
        if isinstance(num, (int, float)) and (isinstance(num, int) or num.is_integer()):
            n = int(num)
            if 1 <= n < 1000:
                dots = "•" * n
                lines = [dots[i:i+90] for i in range(0, len(dots), 90)]
                return f"{formatted}\n" + "\n".join(lines)
        return formatted

    def _substitute_emojis(self, text: str) -> str:
        """Replace emoji words inline (e.g., 'I love cat' -> 'I 😍 🐱')."""
        result, i = [], 0
        while i < len(text):
            if text[i].isalpha():
                j = i
                while j < len(text) and text[j].isalpha():
                    j += 1
                word = text[i:j].lower()
                result.append(self.content.get_emoji(word) or text[i:j])
                i = j
            else:
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
