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
- Definitions: ?cat or cat? shows definition
- Speech output (Tab to toggle)
- History (up/down arrows)
- Emoji autocomplete (Space to accept)
"""

from textual.widgets import Static, Input
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.app import ComposeResult
from textual import events
from textual.message import Message
import re

from ..content import get_content
from ..constants import (
    TOGGLE_DEBOUNCE, DOUBLE_TAP_TIME,
    ICON_VOLUME_ON, ICON_VOLUME_OFF,
)


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

    # Map of unshifted -> shifted characters (double-tap to get shifted)
    SHIFT_MAP = {
        '1': '!', '2': '@', '3': '#', '4': '$', '5': '%',
        '6': '^', '7': '&', '8': '*', '9': '(', '0': ')',
        '-': '_', '=': '+', '[': '{', ']': '}', '\\': '|',
        ';': ':', "'": '"', ',': '<', '.': '>', '/': '?',
        '`': '~',
    }

    def __init__(self, **kwargs):
        super().__init__(placeholder="", **kwargs)
        self.autocomplete_matches: list[tuple[str, str]] = []  # [(word, emoji), ...]
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
        """Check if current input should show autocomplete"""
        content = get_content()
        text = self.value.lower().strip()

        # Get last word being typed
        words = text.split()
        if not words:
            self.autocomplete_matches = []
            self.autocomplete_index = 0
            return

        last_word = words[-1]
        # Strip ? from beginning/end for autocomplete
        clean_word = last_word.strip("?")
        if len(clean_word) < 2:
            self.autocomplete_matches = []
            self.autocomplete_index = 0
            return

        # Search for matches - get up to 5
        matches = content.search_emojis(clean_word)
        # Filter out exact match and limit to 5
        self.autocomplete_matches = [(w, e) for w, e in matches if w != clean_word][:5]
        self.autocomplete_index = 0

    def _update_caps_mode(self, char: str) -> None:
        """Track caps mode based on recent letter keypresses"""
        if char and char.isalpha():
            if not hasattr(self, '_recent_letters'):
                self._recent_letters = []
            self._recent_letters.append(char)
            self._recent_letters = self._recent_letters[-4:]
            if len(self._recent_letters) >= 4:
                new_caps = all(c.isupper() for c in self._recent_letters)
                if hasattr(self.app, 'caps_mode') and new_caps != self.app.caps_mode:
                    self.app.caps_mode = new_caps
                    if hasattr(self.app, '_refresh_caps_sensitive_widgets'):
                        self.app._refresh_caps_sensitive_widgets()

    async def _on_key(self, event: events.Key) -> None:
        """Handle special keys before parent Input processes them"""
        import time

        char = event.character

        # Track caps mode
        self._update_caps_mode(char)

        # Space - accept autocomplete if there's a suggestion
        if event.key == "space" and self.autocomplete_matches:
            event.stop()
            event.prevent_default()
            # Replace last word with selected autocomplete
            selected_word = self.autocomplete_matches[self.autocomplete_index][0]
            words = self.value.split()
            if words:
                # Preserve ? prefix/suffix if present
                last = words[-1]
                if last.startswith("?"):
                    words[-1] = "?" + selected_word
                elif last.endswith("?"):
                    words[-1] = selected_word + "?"
                else:
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
        if char and char in self.SHIFT_MAP:
            now = time.time()
            if self.last_char == char and (now - self.last_char_time) < DOUBLE_TAP_TIME:
                # Double-tap detected - replace last char with shifted version
                event.stop()
                event.prevent_default()
                # Remove last character and insert shifted
                if self.value:
                    self.value = self.value[:-1] + self.SHIFT_MAP[char]
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
        text = caps("Try: cat  •  2 + 2  •  cat times 3  •  apple?")
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
        from ..tts import speak, stop, init
        stop()  # Cancel any previous
        if self.speech_on != self._state_before_toggle:
            if self.speech_on:
                init()
            speak("talking on" if self.speech_on else "talking off")
        # Reset for next toggle sequence
        self._state_before_toggle = self.speech_on

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

    def on_click(self, event) -> None:
        """Always keep focus on input"""
        if self.display:
            event.stop()
            self.query_one("#ask-input").focus()

    def on_descendant_blur(self, event) -> None:
        """Re-focus input if it loses focus"""
        if self.display:
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

        # Make math expressions speakable
        def make_speakable(text: str) -> str:
            import re
            # Lowercase to avoid spelling out caps letter by letter
            text = text.lower()
            # Handle x between numbers (2x3, 2 x 3, etc.)
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

        # Check if result is emoji (contains high unicode chars)
        if result and any(ord(c) > 127 for c in result):
            # It's emoji - describe it for speech
            description = self.evaluator._describe_emoji_result(input_text, result)
            text_to_speak = f"{make_speakable(input_text)} equals {description}"
        # Check if result looks like math output
        elif result:
            try:
                float(result.replace(",", ""))
                text_to_speak = f"{make_speakable(input_text)} equals {result}"
            except (ValueError, AttributeError):
                # Not math, just speak the result if different from input
                if result.lower() != input_text.lower():
                    text_to_speak = result.lower()
                else:
                    text_to_speak = input_text.lower()
        else:
            text_to_speak = input_text.lower()

        speak(text_to_speak)


class SimpleEvaluator:
    """
    Simple math and emoji evaluator for kids.

    Supports:
    - Basic arithmetic: +, -, *, /
    - Word synonyms: "times", "plus", "minus", "divided by"
    - x between numbers treated as multiplication
    - Emoji variables and emoji math
    - Definitions: ?word or word? shows definition
    - Word definitions: "what is X"
    """

    def __init__(self):
        self.content = get_content()

    def _is_all_caps(self, text: str) -> bool:
        """Check if text is all caps (only considering letters, need more than 3)"""
        letters = [c for c in text if c.isalpha()]
        return len(letters) > 3 and all(c.isupper() for c in letters)

    def _maybe_uppercase(self, text: str, result: str) -> str:
        """Make result uppercase if input was all caps"""
        if self._is_all_caps(text):
            return result.upper()
        return result

    def evaluate(self, text: str) -> str:
        """Evaluate the input and return a result string"""
        text = text.strip()
        if not text:
            return ""

        # Check for definition query: ?word or word?
        definition = self._check_definition(text)
        if definition:
            return self._maybe_uppercase(text, definition)

        # Normalize input for math
        normalized = self._normalize(text)

        # Try to evaluate as math expression
        try:
            result = self._eval_math(normalized)
            if result is not None:
                return self._format_number(result)
        except Exception:
            pass

        # Try emoji lookup
        emoji = self.content.get_emoji(text.lower())
        if emoji:
            return emoji

        # Try emoji math (e.g., "3 * cat")
        emoji_result = self._eval_emoji_math(text)
        if emoji_result:
            return emoji_result

        # Just return the input as-is (string echo)
        return text

    def _check_definition(self, text: str) -> str | None:
        """Check if this is a definition query"""
        text_lower = text.lower().strip()

        # Pattern: ?word (at start)
        if text_lower.startswith("?"):
            word = text_lower[1:].strip().rstrip("?")
            if word:
                return self._get_definition_response(word)

        # "what is X" / "whats X" / "define X" patterns (with or without ?)
        patterns = [
            r"^what\s+is\s+(?:a\s+)?(\w+)\??$",
            r"^whats\s+(?:a\s+)?(\w+)\??$",
            r"^define\s+(\w+)\??$",
        ]

        for pattern in patterns:
            match = re.match(pattern, text_lower)
            if match:
                word = match.group(1)
                return self._get_definition_response(word)

        # Pattern: word? (at end) - simple single word with ?
        if text_lower.endswith("?"):
            word = text_lower.rstrip("?").strip()
            if word and " " not in word:
                return self._get_definition_response(word)

        return None

    def _get_definition_response(self, word: str) -> str:
        """Get definition response for a word"""
        definition = self.content.get_definition(word)
        if definition:
            emoji = self.content.get_emoji(word) or ""
            return f"{emoji} {definition}" if emoji else definition
        else:
            # Try to at least show the emoji
            emoji = self.content.get_emoji(word)
            if emoji:
                return f"{emoji} (no definition yet)"
            return f"I don't know what '{word}' means yet!"

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

    def _eval_emoji_math(self, text: str) -> str | None:
        """Evaluate emoji expressions like '3 * cat', 'cat times 3', 'apple + banana', 'cat*3 + 2'"""
        text_lower = text.lower()

        # Split by + or "plus" to handle additions
        parts = re.split(r'\s*(?:\+|plus)\s*', text_lower)
        results = []
        has_emoji = False  # Track if we found at least one emoji

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Try: number * word, number x word, or number times word
            match = re.match(r'^(\d+)\s*(?:[\*x]|times)\s*(\w+)$', part)
            if match:
                count, name = int(match.group(1)), match.group(2)
                emoji = self.content.get_emoji(name)
                if emoji and count <= 100:
                    results.append((emoji * count, name, count))
                    has_emoji = True
                    continue

            # Try: word * number, word x number, or word times number
            match = re.match(r'^(\w+)\s*(?:[\*x]|times)\s*(\d+)$', part)
            if match:
                name, count = match.group(1), int(match.group(2))
                emoji = self.content.get_emoji(name)
                if emoji and count <= 100:
                    results.append((emoji * count, name, count))
                    has_emoji = True
                    continue

            # Try: just a word (single emoji)
            emoji = self.content.get_emoji(part)
            if emoji:
                results.append((emoji, part, 1))
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

            # Just a word
            if self.content.get_emoji(part):
                descriptions.append(f"1 {part}")

        if len(descriptions) == 1:
            return descriptions[0]
        elif len(descriptions) == 2:
            return f"{descriptions[0]} and {descriptions[1]}"
        elif len(descriptions) > 2:
            return ", ".join(descriptions[:-1]) + f", and {descriptions[-1]}"
        return result
