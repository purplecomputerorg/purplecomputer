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
- Typo tolerance: long math expressions forgive accidental keystrokes
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
from ..keyboard import (
    SHIFT_MAP, DoubleTapDetector, KeyRepeatSuppressor,
    CharacterAction, NavigationAction, ControlAction, ShiftAction,
)
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

    # Arrow colors for dark and light themes
    ARROW_DARK = "#a888d0"
    ARROW_LIGHT = "#7a5a9e"

    def __init__(self, text: str, line_type: str = "ask", **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.line_type = line_type  # "ask" or "answer"
        if line_type == "ask":
            self.add_class("ask")

    def _get_arrow_color(self) -> str:
        """Get arrow color based on current theme."""
        try:
            is_dark = "dark" in self.app.theme
            return self.ARROW_DARK if is_dark else self.ARROW_LIGHT
        except Exception:
            return self.ARROW_DARK

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        if self.line_type == "ask":
            return f"[bold #c4a0e8]{caps('Ask:')}[/] {caps(self.text)}"
        else:
            # Add arrow to each line for multi-line results
            arrow_color = self._get_arrow_color()
            lines = self.text.split('\n')
            return '\n'.join(f"[{arrow_color}]  →[/] {caps(line)}" for line in lines)


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

    def __init__(self, hex_color: str, color_name: str, component_colors: list[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._hex_color = hex_color
        self._color_name = color_name
        self._component_colors = component_colors or []

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
        # Arrow color: light purple on dark, darker purple on light for visibility
        arrow_color = "#a888d0" if self._is_dark_theme() else "#7a5a9e"

        prefix = "  →  "
        prefix_style = Style(color=arrow_color, bgcolor=surface)

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
                        segments.append(Segment(" ", surface_style))  # space between

                # Arrow to result
                segments.append(Segment(" → ", Style(color=arrow_color, bgcolor=surface)))

            # Start of result swatch (top row). No name label
            result_style = Style(bgcolor=self._hex_color)
            segments.append(Segment(" " * self.SWATCH_WIDTH, result_style))

            return Strip(segments)

        # Lines 1-2: Continue the result swatch
        elif y < self.SWATCH_HEIGHT:
            segments = [Segment("     ", surface_style)]  # Spacing for alignment (no arrow)

            # Add spacing for component boxes if present
            if len(self._component_colors) > 1:
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

    BINDINGS = [
        ("tab", "toggle_speech", "Toggle speech"),
    ]

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
        self._double_tap = DoubleTapDetector(
            threshold=DOUBLE_TAP_TIME,
            allowed_keys=set(SHIFT_MAP.keys()),
        )
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
        # See handle_keyboard_action() in AskMode for the actual input handling.
        event.stop()
        event.prevent_default()

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
            return

        # If exact match exists (color, emoji, or plural), don't show autocomplete
        if content.is_valid_word(last_word):
            self.autocomplete_matches = []
            self.autocomplete_type = "emoji"
            self.autocomplete_index = 0
            return

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
        """
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
        return f"{hint}   [dim]{caps('← space')}[/]"


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

    async def handle_keyboard_action(self, action) -> None:
        """
        Handle keyboard actions from the main app's KeyboardStateMachine.

        This mode uses Textual's Input widget which needs special treatment.
        We handle some actions directly and forward others to the input.
        """
        ask_input = self.query_one("#ask-input", InlineInput)

        # Handle navigation (up/down for scrolling history, left/right ignored)
        if isinstance(action, NavigationAction):
            if action.direction == 'up':
                ask_input.action_scroll_up()
            elif action.direction == 'down':
                ask_input.action_scroll_down()
            # Left/right arrows are ignored (no cursor movement for kids)
            return

        # Handle control actions
        if isinstance(action, ControlAction):
            if action.action == 'space' and action.is_down:
                # Space: accept autocomplete if there's a suggestion
                if ask_input.autocomplete_matches:
                    selected_word = ask_input.autocomplete_matches[ask_input.autocomplete_index][0]
                    words = ask_input.value.split()
                    if words:
                        words[-1] = selected_word
                        ask_input.value = " ".join(words) + " "
                        ask_input.cursor_position = len(ask_input.value)
                    ask_input.autocomplete_matches = []
                    ask_input.autocomplete_index = 0
                    ask_input._double_tap.reset()
                else:
                    # Type a space (always at end)
                    ask_input.value += " "
                    ask_input.cursor_position = len(ask_input.value)
                    ask_input._check_autocomplete()
                return

            if action.action == 'enter' and action.is_down:
                if ask_input.value.strip():
                    ask_input.post_message(InlineInput.Submitted(ask_input.value))
                    ask_input.value = ""
                ask_input.autocomplete_matches = []
                ask_input.autocomplete_index = 0
                ask_input._double_tap.reset()
                return

            if action.action == 'backspace' and action.is_down:
                # Allow key repeats: held backspace erases like an eraser
                if ask_input.value:
                    # Always delete from end (simpler for kids, no cursor confusion)
                    ask_input.value = ask_input.value[:-1]
                    ask_input.cursor_position = len(ask_input.value)
                    ask_input._check_autocomplete()
                return

            if action.action == 'escape' and action.is_down and not action.is_repeat:
                # ESC tap clears the prompt (start over button)
                if ask_input.value:
                    ask_input.value = ""
                    ask_input.cursor_position = 0
                    ask_input.autocomplete_matches = []
                    ask_input.autocomplete_index = 0
                    ask_input._double_tap.reset()
                    ask_input._check_autocomplete()
                return

            if action.action == 'tab' and action.is_down:
                ask_input.action_toggle_speech()
                return

            return

        # Handle character input
        if isinstance(action, CharacterAction):
            # Skip key repeats for characters (debounce held keys)
            if action.is_repeat:
                return

            char = action.char

            # Double-tap for shifted characters
            if ask_input._double_tap.check(char):
                if ask_input.value:
                    ask_input.value = ask_input.value[:-1] + SHIFT_MAP[char]
                    ask_input.cursor_position = len(ask_input.value)
                return

            # Math operators: auto-space for readability and substitute display chars
            if char in ask_input.MATH_OPERATORS:
                display_char = ask_input.MATH_DISPLAY.get(char, char)
                value = ask_input.value

                # Add spaces around operator if there's a digit before (not for negative numbers)
                # But don't double-space if user already typed a space
                has_digit_before = value and value[-1].isdigit()
                has_space_before = value and value[-1] == ' '
                if has_digit_before:
                    insert = f" {display_char} "
                elif has_space_before:
                    insert = f"{display_char} "
                else:
                    insert = display_char

                ask_input.value = value + insert
                ask_input.cursor_position = len(ask_input.value)
                ask_input._check_autocomplete()
                return

            # Normal character (always append at end)
            ask_input.value += char
            ask_input.cursor_position = len(ask_input.value)
            ask_input._check_autocomplete()
            return

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

        # Check for speak prefix (e.g., "say", "talk"): triggers TTS for this line only
        force_speak = False
        eval_text = input_text
        words = input_text.split(None, 1)
        if words and words[0].lower() in SimpleEvaluator.SPEAK_PREFIXES:
            force_speak = True
            eval_text = words[1] if len(words) > 1 else ""

        # Add the "Ask:" line to history (without speak prefix)
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
                    # Single color: inline box; multiple: swatch
                    if len(components) <= 1:
                        color_box = f"[on {hex_color}]  [/]"
                        parts = [before_part, color_box, after_part]
                        display = " ".join(filter(None, parts))
                        scroll.mount(HistoryLine(display, line_type="answer"))
                    else:
                        # For multi-color with emoji, show two lines:
                        # Line 1: inputs in order (emoji + component boxes)
                        # Line 2: result (emoji + mixed color)
                        if other_part:
                            comp_boxes = " ".join(f"[on {c}]  [/]" for c in components)
                            result_box = f"[on {hex_color}]  [/]"
                            # Line 1: inputs in order
                            input_parts = [before_part, comp_boxes, after_part]
                            input_line = " ".join(filter(None, input_parts))
                            # Line 2: result
                            result_parts = [before_part, result_box, after_part]
                            result_line = " ".join(filter(None, result_parts))
                            display = f"{input_line}\n{result_line}"
                            scroll.mount(HistoryLine(display, line_type="answer"))
                        else:
                            scroll.mount(ColorResultLine(hex_color, color_name, components))
            else:
                scroll.mount(HistoryLine(result, line_type="answer"))

        # Scroll to bottom
        scroll.scroll_end(animate=False)

        # Handle speech (if TTS enabled or force_speak from say/talk prefix)
        try:
            indicator = self.query_one("#speech-indicator", SpeechIndicator)
            if force_speak or indicator.speech_on:
                self._speak(eval_text, result)
        except Exception:
            pass

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
        text = self._clean_mostly_math(text)

        # Track if original had parens (implies computation)
        had_parens = '(' in text

        # Handle parentheses first
        text = self._eval_parens(text)

        # Try text with embedded expression (e.g., "what is 2 + 3", "I have 5 apples")
        if result := self._eval_text_with_expr(text, had_parens):
            return result

        # Check if it's a + expression
        if re.search(self.PLUS_PATTERN, text.lower()):
            if result := self._eval_plus_expr(text):
                return self._maybe_add_label(result, had_parens)

        # Try multiplication: "3 * cat", "cat times 5", etc.
        if mult := self._eval_mult(text):
            return self._maybe_add_label(mult, had_parens)

        # Try pure math
        normalized = self._normalize_math(text)
        if (math_result := self._eval_math(normalized)) is not None:
            return self._format_number_with_dots(math_result)

        # Try single word lookup (emoji or color)
        if single := self._lookup(text.lower().strip()):
            return single

        # Try emoji substitution in text (e.g., "I love cat")
        subbed = self._substitute_emojis(text)
        result = subbed if subbed != text else text

        return self._maybe_add_label(result, had_parens)

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
            return self._format_number_with_dots(math_result)

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
            # If result is "N emoji", extract just the emojis for outer expression
            if m := re.match(r'^(\d+)\s+(.+)$', result):
                count, emoji_str = int(m.group(1)), m.group(2).strip()
                if self._is_emoji_str(emoji_str):
                    result = emoji_str * count
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
                # Merge with previous if same emoji type, space if different
                if result_parts and self._is_emoji_str(result_parts[-1]):
                    last_emoji = [ch for ch in result_parts[-1] if ord(ch) > 127][-1] if result_parts[-1] else None
                    if last_emoji == e:
                        result_parts[-1] += emoji_str  # Same type, no space
                    else:
                        result_parts[-1] += ' ' + emoji_str  # Different type, add space
                else:
                    result_parts.append(emoji_str)
            elif item_type == 'text':
                result_parts.append(value)

        if pending:
            result_parts.append(self._format_number_with_dots(pending))

        # Only return if we have colors or emojis (not just text/numbers which pure math can handle)
        if colors or any(t == 'emoji' for t, _ in items):
            result = ' '.join(result_parts) if result_parts else None
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
