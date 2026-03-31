#!/usr/bin/env python3
"""AI-driven UX testing for Purple Computer.

Launches the app headlessly, then lets a Claude agent explore it as a simulated
kid user. The agent can press keys (high-level or raw evdev), observe the screen
(as cheap plain text or optional PNG), and report bugs.

Usage:
    just python scripts/ai_ux_test.py                          # default: curious 5yo
    just python scripts/ai_ux_test.py --persona keymash        # 4yo key masher
    just python scripts/ai_ux_test.py --persona methodical     # 7yo careful typist
    just python scripts/ai_ux_test.py --persona coder          # kid exploring code panel
    just python scripts/ai_ux_test.py --persona parent         # parent figuring it out
    just python scripts/ai_ux_test.py --max-steps 30           # limit iterations
    just python scripts/ai_ux_test.py --room art               # start in art room

Set ANTHROPIC_API_KEY in environment (or .env).
"""

import argparse
import asyncio
import base64
import json
import os
import re
import subprocess
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai_ux_config import DEFAULT_MAX_STEPS, DEFAULT_MODEL, estimate_cost  # noqa: E402

# Set environment before any app imports
os.environ["PURPLE_NO_EVDEV"] = "1"
os.environ["PURPLE_DEV_MODE"] = "1"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
os.environ.setdefault("ORT_LOGGING_LEVEL", "3")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

# Suppress noisy imports
import io

_real_stdout = sys.__stdout__
_real_stderr = sys.__stderr__
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from purple_tui.purple_tui import PurpleApp  # noqa: E402
from purple_tui.constants import ROOM_PLAY, ROOM_MUSIC, ROOM_ART  # noqa: E402
from purple_tui.input import RawKeyEvent, KeyCode  # noqa: E402

sys.stdout = _real_stdout
sys.stderr = _real_stderr

try:
    import anthropic
except ImportError:
    print("pip install anthropic", file=sys.stderr)
    sys.exit(1)

# ANSI colors for terminal output
DIM = "\033[2m"
RESET = "\033[0m"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOM_MAP = {"play": ROOM_PLAY[0], "music": ROOM_MUSIC[0], "art": ROOM_ART[0]}

# Map friendly key names to KeyCode values for raw evdev injection
NAME_TO_KEYCODE: dict[str, int] = {}
for attr in dir(KeyCode):
    if attr.startswith("KEY_"):
        NAME_TO_KEYCODE[attr[4:].lower()] = getattr(KeyCode, attr)
# Add single-char shortcuts: "a" -> KEY_A, "1" -> KEY_1, etc.
_CHAR_TO_KEYCODE = {
    **{chr(c): getattr(KeyCode, f"KEY_{chr(c).upper()}") for c in range(ord("a"), ord("z") + 1)},
    **{str(i): getattr(KeyCode, f"KEY_{i}") for i in range(10)},
    " ": KeyCode.KEY_SPACE,
    "-": KeyCode.KEY_MINUS,
    "=": KeyCode.KEY_EQUAL,
    "[": KeyCode.KEY_LEFTBRACE,
    "]": KeyCode.KEY_RIGHTBRACE,
    ";": KeyCode.KEY_SEMICOLON,
    "'": KeyCode.KEY_APOSTROPHE,
    "\\": KeyCode.KEY_BACKSLASH,
    ",": KeyCode.KEY_COMMA,
    ".": KeyCode.KEY_DOT,
    "/": KeyCode.KEY_SLASH,
    "`": KeyCode.KEY_GRAVE,
}
NAME_TO_KEYCODE.update(_CHAR_TO_KEYCODE)

# ---------------------------------------------------------------------------
# Tool definitions for Claude
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "press_key",
        "description": "Press a key. Letters a-z, digits 0-9, or: enter, tab, space, up, down, left, right, escape, backspace, delete. Screen text is returned automatically.",
        "input_schema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
    },
    {
        "name": "type_text",
        "description": "Type a string character by character. Screen text is returned automatically.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "raw_key",
        "description": "Raw evdev key event. For hold/release testing: shift, sticky shift, capslock, space-hold, key mashing. Keys: a-z, 0-9, space, enter, leftshift, rightshift, capslock, up/down/left/right, escape, backspace, tab.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "is_down": {"type": "boolean", "description": "true=press, false=release"},
                "is_repeat": {"type": "boolean"},
            },
            "required": ["key", "is_down"],
        },
    },
    {
        "name": "screenshot",
        "description": "PNG screenshot showing colors and layout. Use only when visual details matter.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "switch_room",
        "description": "Switch room. Screen text is returned automatically.",
        "input_schema": {
            "type": "object",
            "properties": {"room": {"type": "string", "enum": ["play", "music", "art"]}},
            "required": ["room"],
        },
    },
    {
        "name": "toggle_code_panel",
        "description": "Open/close the code panel (REPL) in Art or Music room. Not available in Play.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "report_bug",
        "description": "Report unexpected behavior or confusing UX.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                "steps": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "description", "severity", "steps"],
        },
    },
    {
        "name": "done",
        "description": "End the session.",
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    },
]

# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------

PERSONAS = {
    "explorer": (
        "You are a curious 5-year-old using Purple Computer for the first time. "
        "You can barely read. You press keys to see what happens. You get excited "
        "and try things quickly. Sometimes you mash keys. You explore all three "
        "rooms (play, music, art)."
    ),
    "keymash": (
        "You are a 4-year-old who can't read at all. You slam keys randomly and "
        "rapidly. Use raw_key to send rapid key-down events without always releasing. "
        "Press multiple keys at once. Mash the keyboard like a toddler would. Try "
        "pressing shift, caps lock, arrows, and letters all jumbled together. The "
        "app should never crash or show confusing errors."
    ),
    "methodical": (
        "You are a 7-year-old who can read simple words. You carefully explore each "
        "room. In Play, you try typing math problems (2+3, 10-4) and pressing enter. "
        "You read the prompts and try to follow them. In Art, you use arrow keys to "
        "draw shapes. In Music, you try pressing letter keys to play notes."
    ),
    "coder": (
        "You are an 8-year-old who has seen someone code before. Focus on the code "
        "panel. Open it (toggle_code_panel or hold space with raw_key) in each room. "
        "Try typing code commands. In Art, try 'forward 50', 'right 90', 'color red'. "
        "In Music, try typing note sequences. Test what happens with syntax errors "
        "and empty submissions."
    ),
    "parent": (
        "You are a non-technical parent trying to understand what this app does. "
        "You methodically try each room. You look for anything confusing, any "
        "jargon a parent wouldn't understand, any dead ends where it's not clear "
        "what to do next. You are evaluating whether to let your kid use this."
    ),
    "shift": (
        "You are a 6-year-old testing capitalization. Use raw_key to: hold leftshift "
        "then press letters (physical shift), double-tap leftshift quickly (sticky "
        "shift), press capslock to toggle caps, and try combinations. Verify that "
        "uppercase letters appear correctly. Test in Play mode typing words, and in "
        "Art code panel typing commands."
    ),
}

# ---------------------------------------------------------------------------
# App wrapper
# ---------------------------------------------------------------------------


class AppHarness:
    """Wraps PurpleApp for headless agent interaction."""

    def __init__(self):
        self.app: PurpleApp | None = None
        self.pilot = None
        self._time = time.monotonic()  # virtual clock for raw events
        self._log_dir: Path | None = None
        self._step = 0
        self._bugs: list[dict] = []

    async def start(self, room: str = "play"):
        self.app = PurpleApp()
        ctx = self.app.run_test(size=(146, 38))
        self.pilot = await ctx.__aenter__()
        self._ctx = ctx
        await self.pilot.pause()
        await asyncio.sleep(0.5)
        await self.pilot.pause()

        if room != "play":
            room_id = ROOM_MAP.get(room, ROOM_PLAY[0])
            self.app.action_switch_room(room_id)
            await self.pilot.pause()
            await asyncio.sleep(0.3)
            await self.pilot.pause()

    async def stop(self):
        if self._ctx:
            await self._ctx.__aexit__(None, None, None)

    def _advance_time(self, ms: float = 10) -> float:
        """Advance virtual clock and return timestamp."""
        self._time += ms / 1000.0
        return self._time

    async def press_key(self, key: str) -> str:
        await self.app._execute_dev_command({"action": "key", "value": key})
        await self.pilot.pause()
        return f"Pressed '{key}'"

    async def type_text(self, text: str) -> str:
        for char in text:
            await self.app._execute_dev_command({"action": "key", "value": char})
            await asyncio.sleep(0.03)
        await self.pilot.pause()
        return f"Typed '{text}' ({len(text)} chars)"

    async def raw_key(self, key: str, is_down: bool, is_repeat: bool = False) -> str:
        keycode = NAME_TO_KEYCODE.get(key.lower())
        if keycode is None:
            return f"Unknown key '{key}'. Valid: {', '.join(sorted(NAME_TO_KEYCODE.keys())[:20])}..."
        event = RawKeyEvent(
            keycode=keycode,
            is_down=is_down,
            timestamp=self._advance_time(10 if not is_repeat else 33),
            is_repeat=is_repeat,
        )
        await self.app._handle_raw_key_event(event)
        await self.pilot.pause()
        direction = "down" if is_down else "up"
        if is_repeat:
            direction = "repeat"
        return f"Raw {key} {direction}"

    @staticmethod
    def _svg_to_text(svg: str) -> str:
        """Extract readable text from Textual SVG screenshot."""
        entries = re.findall(
            r'<text[^>]*\bx="([\d.]+)"[^>]*\by="([\d.]+)"[^>]*>(.*?)</text>',
            svg, re.DOTALL,
        )
        if not entries:
            entries = re.findall(
                r'<text[^>]*\by="([\d.]+)"[^>]*\bx="([\d.]+)"[^>]*>(.*?)</text>',
                svg, re.DOTALL,
            )
            entries = [(x, y, c) for y, x, c in entries]

        rows: dict[int, list[tuple[float, str]]] = {}
        for x_str, y_str, content in entries:
            y = round(float(y_str))
            x = float(x_str)
            content = content.replace("&#160;", "\u00a0")
            content = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), content)
            content = re.sub(r"<[^>]+>", "", content)
            if y not in rows:
                rows[y] = []
            rows[y].append((x, content))

        lines = []
        for y in sorted(rows.keys()):
            parts = sorted(rows[y], key=lambda p: p[0])
            line = "".join(p[1] for p in parts)
            lines.append(line.rstrip())

        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)

    def observe_screen(self) -> str:
        """Extract plain text from SVG export. ~500 chars, very token-cheap."""
        svg = self.app.export_screenshot()
        return self._svg_to_text(svg)

    def _svg_to_png(self, svg_path: str, png_path: str) -> bool:
        """Convert SVG to a small PNG (800px wide, ~14KB)."""
        rsvg = shutil.which("rsvg-convert")
        if rsvg:
            try:
                subprocess.run(
                    [rsvg, "-w", "800", "-o", png_path, svg_path],
                    check=True, capture_output=True,
                )
                return True
            except subprocess.CalledProcessError:
                pass
        try:
            subprocess.run(
                ["nix-shell", "-p", "librsvg", "--run",
                 f"rsvg-convert -w 800 -o {png_path} {svg_path}"],
                check=True, capture_output=True, timeout=30,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return False

    async def screenshot(self) -> tuple[str | None, str]:
        """Take an 800px-wide PNG screenshot (~14KB), return (base64_png, path)."""
        if not self._log_dir:
            return None, "No log directory"
        svg_path = str(self._log_dir / f"step_{self._step:03d}.svg")
        png_path = str(self._log_dir / f"step_{self._step:03d}.png")
        self.app.save_screenshot(svg_path)

        if self._svg_to_png(svg_path, png_path):
            with open(png_path, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            return data, png_path
        return None, svg_path

    async def switch_room(self, room: str) -> str:
        room_id = ROOM_MAP.get(room)
        if not room_id:
            return f"Unknown room '{room}'. Options: play, music, art"
        self.app.action_switch_room(room_id)
        await self.pilot.pause()
        await asyncio.sleep(0.3)
        await self.pilot.pause()
        return f"Switched to {room}"

    async def toggle_code_panel(self) -> str:
        from purple_tui.constants import ROOM_PLAY
        if self.app.active_room == ROOM_PLAY[0]:
            return "Code panel not available in Play room"
        self.app._open_repl_panel()
        self.app._open_code_panel_in_room(self.app.active_room)
        await asyncio.sleep(0.3)
        await self.pilot.pause()
        return "Toggled code panel"

    async def wait(self, seconds: float) -> str:
        seconds = min(seconds, 5.0)
        await asyncio.sleep(seconds)
        await self.pilot.pause()
        return f"Waited {seconds}s"


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------


async def execute_tool(harness: AppHarness, name: str, input_data: dict) -> list[dict]:
    """Execute a tool call and return content blocks for the tool result.

    Action tools auto-attach the current screen text so the agent doesn't
    need a separate observe_screen call (saves ~50% of API calls).
    """
    harness._step += 1

    def with_screen(msg: str) -> list[dict]:
        """Return action result + current screen text."""
        screen = harness.observe_screen()
        return [{"type": "text", "text": f"{msg}\n\nScreen:\n{screen}"}]

    if name == "press_key":
        msg = await harness.press_key(input_data.get("key", ""))
        return with_screen(msg)

    elif name == "type_text":
        msg = await harness.type_text(input_data.get("text", ""))
        return with_screen(msg)

    elif name == "raw_key":
        key = input_data.get("key")
        is_down = input_data.get("is_down")
        if not key or is_down is None:
            return [{"type": "text", "text": f"raw_key requires 'key' and 'is_down', got: {input_data}"}]
        msg = await harness.raw_key(key, is_down, input_data.get("is_repeat", False))
        return with_screen(msg)

    elif name == "screenshot":
        b64, path = await harness.screenshot()
        if b64:
            return [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
            ]
        return [{"type": "text", "text": f"Screenshot (SVG only): {path}"}]

    elif name == "switch_room":
        msg = await harness.switch_room(input_data["room"])
        return with_screen(msg)

    elif name == "toggle_code_panel":
        msg = await harness.toggle_code_panel()
        return with_screen(msg)

    elif name == "report_bug":
        bug = {
            "step": harness._step,
            "title": input_data.get("title", "Untitled"),
            "description": input_data.get("description", ""),
            "severity": input_data.get("severity", "medium"),
            "steps": input_data.get("steps", []),
            "timestamp": datetime.now().isoformat(),
        }
        harness._bugs.append(bug)
        return [{"type": "text", "text": f"Bug #{len(harness._bugs)} recorded: {bug['title']}"}]

    elif name == "done":
        return [{"type": "text", "text": "Session complete."}]

    return [{"type": "text", "text": f"Unknown tool: {name}"}]


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


SYSTEM_PROMPT = """\
Test Purple Computer, an app for kids 4-7 with three rooms: Play (math/typing), Music (notes), Art (drawing/turtle). Each room has a code panel (REPL) via toggle_code_panel.

Every action tool returns the screen text automatically. Only use screenshot when you need to check colors or visual layout.

Screen text is extracted from SVG and has known limitations:
- Color swatches appear as empty space or block characters (▅▄██). This is normal, not a bug.
- "Hold Space: close code" in the bottom bar is expected when the code panel is active.
- Use screenshot to verify visual issues before reporting them as bugs.

Do NOT generate commentary or narration. Only use tools and report_bug. Call done when finished.

{persona}"""


async def run_agent(
    persona_name: str = "explorer",
    room: str = "play",
    max_steps: int = DEFAULT_MAX_STEPS,
    model: str = DEFAULT_MODEL,
):
    log_dir = Path(f"/tmp/purple_ux_test/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{persona_name}")
    log_dir.mkdir(parents=True, exist_ok=True)

    persona_text = PERSONAS.get(persona_name, PERSONAS["explorer"])
    system = SYSTEM_PROMPT.format(persona=persona_text)

    print(f"Starting AI UX test: persona={persona_name}, room={room}, max_steps={max_steps}")
    print(f"Logs: {log_dir}")
    print()

    harness = AppHarness()
    harness._log_dir = log_dir
    await harness.start(room)

    client = anthropic.Anthropic()
    initial_screen = harness.observe_screen()
    messages: list[dict] = [
        {"role": "user", "content": f"App is running. Initial screen:\n{initial_screen}"}
    ]

    action_log = []
    total_input_tokens = 0
    total_output_tokens = 0

    def trim_history():
        """Keep history lean: summarize old observations, drop old images.

        Keeps the first message (start prompt) and the last HISTORY_KEEP
        turns. For older turns, replaces screen text and images with
        short summaries so the agent remembers what it did but we don't
        pay to resend full screen dumps.
        """
        HISTORY_KEEP = 6  # keep last 6 messages (3 turns) in full detail

        if len(messages) <= HISTORY_KEEP + 1:
            return

        for msg in messages[1:-HISTORY_KEEP]:
            if msg["role"] != "user" or not isinstance(msg.get("content"), list):
                continue
            for result in msg["content"]:
                if result.get("type") != "tool_result":
                    continue
                content = result.get("content", [])
                if not isinstance(content, list):
                    continue
                trimmed = []
                for block in content:
                    if block.get("type") == "image":
                        trimmed.append({"type": "text", "text": "[screenshot taken]"})
                    elif block.get("type") == "text" and len(block.get("text", "")) > 200:
                        # Long text is a screen observation, summarize
                        text = block["text"]
                        # Keep first and last line as context
                        lines = text.split("\n")
                        if len(lines) > 4:
                            preview = f"{lines[0]}... ({len(lines)} lines) ...{lines[-1]}"
                        else:
                            preview = text[:150]
                        trimmed.append({"type": "text", "text": f"[screen: {preview}]"})
                    else:
                        trimmed.append(block)
                result["content"] = trimmed

    def api_call_with_retry(max_retries=5):
        """Call the API with exponential backoff on overload errors."""
        for attempt in range(max_retries):
            try:
                return client.messages.create(
                    model=model,
                    max_tokens=300,
                    system=system,
                    tools=TOOLS,
                    messages=messages,
                )
            except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
                is_overload = isinstance(e, anthropic.APIStatusError) and e.status_code == 529
                is_server = isinstance(e, anthropic.APIStatusError) and e.status_code >= 500
                is_rate = isinstance(e, anthropic.RateLimitError)
                is_conn = isinstance(e, anthropic.APIConnectionError)
                if not (is_overload or is_server or is_rate or is_conn):
                    raise
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt + (1 if is_overload or is_server else 5)
                label = "overloaded" if is_overload else "rate limited" if is_rate else "server error" if is_server else "connection error"
                print(f"  {DIM}API {label} ({e.status_code if hasattr(e, 'status_code') else 'N/A'}), retrying in {wait}s...{RESET}")
                time.sleep(wait)

    try:
        for step in range(max_steps):
            trim_history()
            response = api_call_with_retry()
            step_in = response.usage.input_tokens
            step_out = response.usage.output_tokens
            total_input_tokens += step_in
            total_output_tokens += step_out
            cost_so_far = estimate_cost(total_input_tokens, total_output_tokens, model)
            print(f"  {DIM}[tokens: {step_in:,} in / {step_out:,} out | ${cost_so_far:.4f}]{RESET}")

            messages.append({"role": "assistant", "content": response.content})

            # Process tool calls
            tool_results = []
            done = False

            for block in response.content:
                if block.type == "text" and block.text.strip():
                    print(f"  [{step+1}] {block.text[:120]}")
                elif block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    log_entry = {"step": step + 1, "tool": tool_name, "input": tool_input}

                    result_content = await execute_tool(harness, tool_name, tool_input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_content,
                    })

                    # Print compact summary
                    summary = tool_name
                    if tool_name == "press_key":
                        summary = f"press_key({tool_input.get('key', '?')})"
                    elif tool_name == "type_text":
                        summary = f"type_text('{tool_input.get('text', '')[:20]}')"
                    elif tool_name == "raw_key":
                        d = "v" if tool_input.get("is_down") else "^"
                        summary = f"raw_key({tool_input.get('key', '?')}{d})"
                    elif tool_name == "switch_room":
                        summary = f"switch_room({tool_input.get('room', '?')})"
                    elif tool_name == "report_bug":
                        summary = f"BUG: {tool_input.get('title', '?')}"
                        print(f"  [{step+1}] *** {summary} ***")
                    elif tool_name == "screenshot":
                        summary = "screenshot"
                    elif tool_name == "done":
                        done = True
                        summary = f"done: {tool_input.get('summary', '')[:80]}"

                    if tool_name != "report_bug":
                        print(f"  [{step+1}] {summary}")

                    log_entry["result_text"] = " | ".join(
                        b["text"] for b in result_content if b.get("type") == "text"
                    )
                    action_log.append(log_entry)

            if done or not tool_results:
                break

            messages.append({"role": "user", "content": tool_results})

    finally:
        await harness.stop()

        # Always write report, even on crash
        report = {
            "persona": persona_name,
            "start_room": room,
            "model": model,
            "steps": len(action_log),
            "max_steps": max_steps,
            "bugs": harness._bugs,
            "bug_count": len(harness._bugs),
            "tokens": {"input": total_input_tokens, "output": total_output_tokens},
            "action_log": action_log,
        }

        report_path = log_dir / "report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        if harness._bugs:
            _append_bug_log(harness._bugs, persona_name, model)

        print()
        print(f"Session complete: {len(action_log)} actions, {len(harness._bugs)} bugs found")
        total_cost = estimate_cost(total_input_tokens, total_output_tokens, model)
        print(f"Tokens: {total_input_tokens:,} in / {total_output_tokens:,} out (${total_cost:.4f})")
        if harness._bugs:
            print()
            print("Bugs found:")
            for i, bug in enumerate(harness._bugs, 1):
                print(f"  {i}. [{bug['severity']}] {bug['title']}")
                print(f"     {bug['description'][:100]}")
        print(f"\nFull report: {report_path}")

    return report


BUG_LOG_PATH = Path(__file__).resolve().parent.parent / "AI_UX_BUGS.md"


def _append_bug_log(bugs: list[dict], persona: str, model: str):
    """Append bugs to the repo-level markdown bug log."""
    date = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Create file with header if it doesn't exist
    if not BUG_LOG_PATH.exists():
        BUG_LOG_PATH.write_text(
            "# AI UX Test Bugs\n\n"
            "Bugs discovered by automated AI UX testing (`just ux`). "
            "Mark fixed bugs with ~~strikethrough~~ or delete them.\n\n"
        )

    lines = []
    lines.append(f"## {date} ({persona}, {model})\n\n")
    for bug in bugs:
        severity = bug["severity"].upper()
        lines.append(f"### [{severity}] {bug['title']}\n\n")
        lines.append(f"{bug['description']}\n\n")
        if bug.get("steps"):
            lines.append("**Repro:**\n")
            for i, step in enumerate(bug["steps"], 1):
                lines.append(f"{i}. {step}\n")
            lines.append("\n")

    with open(BUG_LOG_PATH, "a") as f:
        f.writelines(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="AI-driven UX testing for Purple Computer")
    parser.add_argument("--persona", default="explorer", choices=list(PERSONAS.keys()),
                        help="Testing persona (default: explorer)")
    parser.add_argument("--room", default="play", choices=["play", "music", "art"],
                        help="Starting room (default: play)")
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS,
                        help=f"Max agent iterations (default: {DEFAULT_MAX_STEPS})")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Claude model to use (default: {DEFAULT_MODEL})")
    args = parser.parse_args()

    asyncio.run(run_agent(
        persona_name=args.persona,
        room=args.room,
        max_steps=args.max_steps,
        model=args.model,
    ))


if __name__ == "__main__":
    main()
