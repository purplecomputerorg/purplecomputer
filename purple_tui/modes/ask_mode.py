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

    def __init__(self, **kwargs):
        super().__init__(placeholder="", **kwargs)
        self.autocomplete_matches: list[tuple[str, str]] = []  # [(word, emoji), ...]
        self.autocomplete_index: int = 0

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

    async def _on_key(self, event: events.Key) -> None:
        """Handle special keys before parent Input processes them"""
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
            return

        # Let parent handle other keys
        await super()._on_key(event)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update autocomplete suggestions as user types"""
        self._check_autocomplete()

    @property
    def autocomplete_hint(self) -> str:
        """Get the autocomplete hint to display - shows multiple options"""
        if not self.autocomplete_matches:
            return ""

        # Build hint showing all matches
        parts = []
        for word, emoji in self.autocomplete_matches:
            parts.append(f"{word} {emoji}")

        hint = "  •  ".join(parts)
        return f"  [dim]{hint} (space)[/]"


class InputPrompt(Static):
    """Shows 'Ask:' prompt with input area"""

    def render(self) -> str:
        return "[bold #c4a0e8]Ask:[/]"


class AutocompleteHint(Static):
    """Shows autocomplete suggestion and help hints"""
    pass


class SpeechIndicator(Static):
    """Shows whether speech is on/off - Tab to toggle"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.speech_on = False

    def render(self) -> str:
        if self.speech_on:
            return "[bold green]🔊 Tab: speech ON[/]"
        else:
            return "[dim]🔇 Tab: speech off[/]"

    def toggle(self) -> bool:
        self.speech_on = not self.speech_on
        # Pre-initialize TTS when turned on
        if self.speech_on:
            from ..tts import init
            init()
        self.refresh()
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
            yield Static("[dim]Try: apple?  •  2 + 2  •  cat[/]", id="example-hint")

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
            result = text
            # Handle x between numbers (2x3, 2 x 3, etc.)
            result = re.sub(r'(\d)\s*x\s*(\d)', r'\1 times \2', result, flags=re.IGNORECASE)
            return (result
                .replace("×", " times ")
                .replace("*", " times ")
                .replace("÷", " divided by ")
                .replace("/", " divided by ")
                .replace("+", " plus ")
                .replace("−", " minus ")
                .replace("-", " minus ")
                .replace("=", " equals ")
            )

        # Check if result looks like math output
        try:
            float(result.replace(",", ""))
            text_to_speak = f"{make_speakable(input_text)} equals {result}"
        except (ValueError, AttributeError):
            # Not math, just speak the result if different from input
            if result and result != input_text:
                text_to_speak = result
            else:
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
    - Definitions: ?word or word? shows definition
    - Word definitions: "what is X"
    """

    def __init__(self):
        self.content = get_content()

    def evaluate(self, text: str) -> str:
        """Evaluate the input and return a result string"""
        text = text.strip()
        if not text:
            return ""

        # Check for definition query: ?word or word?
        definition = self._check_definition(text)
        if definition:
            return definition

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
