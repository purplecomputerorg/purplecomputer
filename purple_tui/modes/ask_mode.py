"""
Ask Mode - Math and Emoji REPL for Kids

A simple evaluator for:
- Basic math: 2 + 2, 3 x 4, 10 - 5
- Word synonyms: times, plus, minus
- Emoji display: typing "cat" shows 🐱
- Emoji math: 3 * cat produces 🐱🐱🐱
- Word definitions: typing "what is cat" shows definition
- Sticky shift, caps lock big letter mode
- Speech output (Tab to toggle)
- History (up/down arrows)
- Emoji autocomplete (Space to accept)
"""

from textual.widgets import Static, Input
from textual.containers import Vertical, ScrollableContainer
from textual.app import ComposeResult
from textual import events
from textual.message import Message
import re

from ..content import get_content


class OutputLine(Static):
    """A single line of output in the REPL"""

    def __init__(self, text: str, is_input: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.is_input = is_input

    def render(self) -> str:
        if self.is_input:
            return f"[bold magenta]💜[/] {self.text}"
        else:
            return f"[bold cyan]✨[/] {self.text}"


class AskInput(Input):
    """
    Custom input widget with:
    - Emoji autocomplete (Space to accept)
    - Sticky shift
    - History (up/down arrows)
    - Big letter mode (caps lock)
    """

    class Submitted(Message):
        """Message sent when user presses Enter"""
        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(placeholder="Type here...", **kwargs)
        self.history: list[str] = []
        self.history_index: int = -1
        self.sticky_shift: bool = False
        self.big_letter_mode: bool = False
        self.autocomplete_word: str = ""
        self.autocomplete_emoji: str = ""

    def _check_autocomplete(self) -> None:
        """Check if current input should show autocomplete"""
        content = get_content()
        text = self.value.lower().strip()

        # Get last word being typed
        words = text.split()
        if not words:
            self.autocomplete_word = ""
            self.autocomplete_emoji = ""
            return

        last_word = words[-1]
        if len(last_word) < 2:
            self.autocomplete_word = ""
            self.autocomplete_emoji = ""
            return

        # Search for matches
        matches = content.search_emojis(last_word)
        if matches and matches[0][0] != last_word:
            self.autocomplete_word = matches[0][0]
            self.autocomplete_emoji = matches[0][1]
        else:
            self.autocomplete_word = ""
            self.autocomplete_emoji = ""

    def on_key(self, event: events.Key) -> None:
        """Handle special keys"""
        # Tab toggles speech
        if event.key == "tab":
            event.stop()
            event.prevent_default()
            app = self.app
            if hasattr(app, 'toggle_speech'):
                app.toggle_speech()
            return

        # Up arrow - history back
        if event.key == "up":
            event.stop()
            event.prevent_default()
            if self.history and self.history_index < len(self.history) - 1:
                self.history_index += 1
                self.value = self.history[-(self.history_index + 1)]
            return

        # Down arrow - history forward
        if event.key == "down":
            event.stop()
            event.prevent_default()
            if self.history_index > 0:
                self.history_index -= 1
                self.value = self.history[-(self.history_index + 1)]
            elif self.history_index == 0:
                self.history_index = -1
                self.value = ""
            return

        # Space - accept autocomplete if there's a suggestion
        if event.key == "space" and self.autocomplete_word:
            event.stop()
            event.prevent_default()
            # Replace last word with autocomplete
            words = self.value.split()
            if words:
                words[-1] = self.autocomplete_word
                self.value = " ".join(words) + " "
            self.autocomplete_word = ""
            self.autocomplete_emoji = ""
            return

        # Enter - submit
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            if self.value.strip():
                self.history.append(self.value)
                self.history_index = -1
                self.post_message(self.Submitted(self.value))
                self.value = ""
            self.autocomplete_word = ""
            self.autocomplete_emoji = ""
            return

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update autocomplete suggestions as user types"""
        self._check_autocomplete()

    @property
    def autocomplete_hint(self) -> str:
        """Get the autocomplete hint to display"""
        if self.autocomplete_word:
            return f"[dim]{self.autocomplete_word} {self.autocomplete_emoji} (space to accept)[/]"
        return ""


class AutocompleteHint(Static):
    """Shows autocomplete suggestion"""
    pass


class AskMode(Vertical):
    """
    Ask Mode - The main REPL interface for kids.
    """

    DEFAULT_CSS = """
    AskMode {
        width: 100%;
        height: 100%;
    }

    #output-scroll {
        width: 100%;
        height: 1fr;
        border: none;
        scrollbar-gutter: stable;
    }

    #autocomplete-hint {
        dock: bottom;
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }

    #ask-input {
        dock: bottom;
        width: 100%;
        height: 3;
        border: heavy $accent;
    }

    OutputLine {
        width: 100%;
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.evaluator = SimpleEvaluator()

    def compose(self) -> ComposeResult:
        yield ScrollableContainer(id="output-scroll")
        yield AutocompleteHint(id="autocomplete-hint")
        yield AskInput(id="ask-input")

    def on_mount(self) -> None:
        """Focus the input when mode loads"""
        self.query_one("#ask-input").focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update autocomplete hint display"""
        try:
            ask_input = self.query_one("#ask-input", AskInput)
            hint = self.query_one("#autocomplete-hint", AutocompleteHint)
            hint.update(ask_input.autocomplete_hint)
        except Exception:
            pass

    async def on_ask_input_submitted(self, event: AskInput.Submitted) -> None:
        """Handle input submission"""
        input_text = event.value
        scroll = self.query_one("#output-scroll")

        # Apply big letter mode if active
        ask_input = self.query_one("#ask-input", AskInput)
        display_input = input_text.upper() if ask_input.big_letter_mode else input_text

        # Add input line to output
        scroll.mount(OutputLine(display_input, is_input=True))

        # Evaluate and show result
        result = self.evaluator.evaluate(input_text)
        if result:
            display_result = result.upper() if ask_input.big_letter_mode else result
            scroll.mount(OutputLine(display_result, is_input=False))

        # Scroll to bottom
        scroll.scroll_end(animate=False)

        # Handle speech if enabled
        app = self.app
        if hasattr(app, 'speech_enabled') and app.speech_enabled:
            self._speak(input_text, result)

    def _speak(self, input_text: str, result: str) -> None:
        """Speak the input and result using Piper TTS"""
        from ..tts import speak

        # Check if result looks like math output
        try:
            float(result.replace(",", ""))
            text_to_speak = f"{input_text} equals {result}"
        except (ValueError, AttributeError):
            # Not math, just speak the input
            text_to_speak = input_text

        speak(text_to_speak)


class SimpleEvaluator:
    """
    Simple math and emoji evaluator for kids.

    Supports:
    - Basic arithmetic: +, -, *, /
    - Word synonyms: "times", "plus", "minus", "divided by"
    - x between numbers treated as multiplication
    - Emoji variables and emoji math
    - Word definitions: "what is X"
    """

    def __init__(self):
        self.content = get_content()

    def evaluate(self, text: str) -> str:
        """Evaluate the input and return a result string"""
        text = text.strip()
        if not text:
            return ""

        # Check for definition query: "what is X" or "whats X"
        definition = self._check_definition(text)
        if definition:
            return definition

        # Normalize input for math
        normalized = self._normalize(text)

        # Try to evaluate as math expression
        try:
            result = self._eval_math(normalized)
            if result is not None:
                return str(result)
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
        patterns = [
            r"^what\s+is\s+(?:a\s+)?(\w+)\??$",
            r"^whats\s+(?:a\s+)?(\w+)\??$",
            r"^define\s+(\w+)$",
        ]

        text_lower = text.lower().strip()
        for pattern in patterns:
            match = re.match(pattern, text_lower)
            if match:
                word = match.group(1)
                definition = self.content.get_definition(word)
                if definition:
                    emoji = self.content.get_emoji(word) or ""
                    return f"{emoji} {definition}" if emoji else definition
                else:
                    return f"I don't know what {word} means yet!"

        return None

    def _normalize(self, text: str) -> str:
        """Normalize text for evaluation"""
        # Replace word operators with symbols
        replacements = [
            (r'\btimes\b', '*'),
            (r'\bplus\b', '+'),
            (r'\bminus\b', '-'),
            (r'\bdivided\s+by\b', '/'),
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

    def _eval_emoji_math(self, text: str) -> str | None:
        """Evaluate emoji multiplication like '3 * cat' -> '🐱🐱🐱'"""
        # Pattern: number * emoji_name or emoji_name * number
        match = re.match(r'(\d+)\s*[\*x]\s*(\w+)', text.lower())
        if match:
            count, name = int(match.group(1)), match.group(2)
            emoji = self.content.get_emoji(name)
            if emoji and count <= 100:  # Limit to prevent abuse
                return emoji * count

        match = re.match(r'(\w+)\s*[\*x]\s*(\d+)', text.lower())
        if match:
            name, count = match.group(1), int(match.group(2))
            emoji = self.content.get_emoji(name)
            if emoji and count <= 100:
                return emoji * count

        # Addition of emojis: cat + dog
        match = re.match(r'(\w+)\s*\+\s*(\w+)', text.lower())
        if match:
            name1, name2 = match.group(1), match.group(2)
            emoji1 = self.content.get_emoji(name1)
            emoji2 = self.content.get_emoji(name2)
            if emoji1 and emoji2:
                return emoji1 + emoji2

        return None
