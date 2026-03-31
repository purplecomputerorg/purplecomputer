# AI UX Testing

Automated exploratory testing where a Claude agent pretends to be a kid (or parent) using Purple Computer, presses keys, observes the screen, and reports bugs.

## Quick Start

```bash
# 1. Set up API key (one time)
cp .env.example .env
# Edit .env with your Anthropic API key

# 2. Run
just ux
```

The interactive menu walks you through persona, room, steps, and model.

## How It Works

The agent runs in a loop:

1. App launches headlessly via Textual's `run_test()` (no display needed)
2. Agent sees the initial screen state (included in first message)
3. Agent decides what to do next (press keys, switch rooms, open code panel)
4. Every action automatically returns the updated screen text
5. If something looks wrong, agent files a bug report
6. Repeat until max steps or agent calls `done`

Bugs are logged to `AI_UX_BUGS.md` in the repo root (accumulates across sessions).

The agent has two levels of input:

- **High-level:** `press_key`, `type_text` use `_execute_dev_command` (same as `just preview`)
- **Raw evdev:** `raw_key` injects `RawKeyEvent` into `_handle_raw_key_event`, testing the full keyboard pipeline (shift, sticky shift, hold-or-tap, caps lock, key repeat)

## Personas

| Name | Age | What it tests |
|------|-----|---------------|
| `explorer` | 5 | General exploration, all rooms, random key presses |
| `keymash` | 4 | Crash resistance: rapid raw key events, multiple keys held |
| `methodical` | 7 | Happy paths: typing math, drawing shapes, playing notes |
| `coder` | 8 | Code panel: REPL commands, syntax errors, empty input |
| `parent` | adult | Confusing UX, jargon, dead ends, unclear next steps |
| `shift` | 6 | Physical shift, sticky shift, caps lock via raw evdev |

## CLI Options

Skip the interactive menu:

```bash
just python scripts/ai_ux_test.py --persona keymash --room art --max-steps 20
just python scripts/ai_ux_test.py --persona coder --model claude-sonnet-4-6
```

## Output

Each session writes to `/tmp/purple_ux_test/<timestamp>_<persona>/`:

- `report.json`: bugs found, full action log, token usage
- `step_NNN.svg` / `step_NNN.png`: screenshots (only when the agent uses the screenshot tool)

Live console output shows each action and per-step token usage:

```
  [tokens: 1,234 in / 89 out | total: 1,234 in]
  [1] type_text('5+3')
  [1] press_key(enter)
  [tokens: 2,100 in / 102 out | total: 3,334 in]
  [2] *** BUG: Answer text overlaps prompt ***
  [2] switch_room(art)
```

Bugs are also appended to `AI_UX_BUGS.md` in the repo root with repro steps, grouped by session.

## Configuration

Edit `scripts/ai_ux_config.py`:

```python
DEFAULT_MAX_STEPS = 10      # steps per session (each step = one API call)
DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # cheapest; switch to sonnet/opus for deeper testing
```

## Cost

Rough estimates per session (varies with step count and screen content):

| Model | 10 steps | 50 steps |
|-------|----------|----------|
| Haiku 4.5 | ~$0.02 | ~$0.10 |
| Sonnet 4.6 | ~$0.10 | ~$0.50 |
| Opus 4.6 | ~$0.50 | ~$2.50 |

## Observation

Every action tool automatically returns the current screen as plain text (~500 chars, extracted from Textual's SVG export). The agent does not need to explicitly observe.

The `screenshot` tool renders an 800px-wide PNG (~14KB) for checking colors, layout, or alignment. The agent is prompted to use it sparingly since images cost more tokens.

## Adding Personas

Add an entry to the `PERSONAS` dict in `scripts/ai_ux_test.py`. The value is a system prompt fragment describing who the agent is and how it should behave. Mention specific tools (like `raw_key`) if the persona should use low-level input.

## Adding Tools

Add a tool definition to the `TOOLS` list and a handler in `execute_tool()`. The `AppHarness` class wraps all app interaction. Existing tools:

- `press_key`, `type_text`: character-level input (auto-returns screen)
- `raw_key`: evdev-level input with down/up/repeat (auto-returns screen)
- `switch_room`, `toggle_code_panel`: navigation (auto-returns screen)
- `screenshot`: PNG observation (use sparingly)
- `report_bug`, `done`: session control

## Troubleshooting

**529 Overloaded errors:** The script retries with exponential backoff (up to 5 retries, 1-17s waits). If a model is persistently overloaded, switch to a different one in `ai_ux_config.py` or pick another from the interactive menu.

**No rsvg-convert:** PNG screenshots require `rsvg-convert`. On NixOS it's pulled via `nix-shell -p librsvg` automatically. Text observation works without it.

**Empty screen text:** The SVG text extraction parses `<text>` elements from Textual's SVG export. If the app's rendering changes significantly, the regex in `AppHarness._svg_to_text()` may need updating.

## Files

```
scripts/
  ai_ux_config.py    # shared constants (DEFAULT_MAX_STEPS, DEFAULT_MODEL)
  ai_ux_runner.py    # interactive launcher (just ux)
  ai_ux_test.py      # agent engine, tools, personas, harness
.env.example         # template for API key
AI_UX_BUGS.md        # accumulated bug reports (auto-appended by test runs)
```

## Cost Optimization

The agent uses several techniques to minimize API costs:

- **Auto-attached screen text:** Every action returns the screen, eliminating separate observe calls
- **History trimming:** Old screen observations are summarized, old screenshots replaced with `[screenshot taken]`
- **Low max_tokens (300):** Agent only needs to call tools, not write prose
- **No commentary:** System prompt instructs agent to only use tools, not narrate
- **Initial screen in first message:** No wasted turn for initial observation
