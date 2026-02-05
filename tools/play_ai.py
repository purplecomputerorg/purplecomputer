#!/usr/bin/env python3
"""
AI-assisted Play Mode composition generator.

Uses Claude to generate PlayKeys sequences from natural language prompts.
Two-pass approach: generate, then self-review the grid visualization.

Usage:
    python tools/play_ai.py "smiley face that sounds like a nice tune"
    python tools/play_ai.py "heart" --no-review
    python tools/play_ai.py "rainstorm" --json
    python tools/play_ai.py "happy birthday" --install
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.play_constants import GRID_KEYS, ALL_KEYS, COLORS, NOTE_FREQUENCIES, PERCUSSION
from ai_utils import load_env_file, parse_json_robust


# Map grid key to (row, col) for spatial reasoning
KEY_TO_POS = {}
for r, row in enumerate(GRID_KEYS):
    for c, key in enumerate(row):
        KEY_TO_POS[key] = (r, c)
        KEY_TO_POS[key.lower()] = (r, c)

# Color names for display
COLOR_NAMES = {0: "purple", 1: "blue", 2: "red"}
COLOR_CHARS = {0: "P", 1: "B", 2: "R"}


def build_generate_prompt(goal: str) -> tuple[str, str]:
    """Build the system and user prompts for Pass 1 (generation).

    Returns (system_prompt, user_prompt).
    """
    # Build frequency descriptions for each row
    freq_desc_row1 = ", ".join(
        f"{k}={NOTE_FREQUENCIES[k]:.0f}Hz" for k in ['Q','W','E','R','T','Y','U','I','O','P']
    )
    freq_desc_row2 = ", ".join(
        f"{k}={NOTE_FREQUENCIES[k]:.0f}Hz"
        for k in ['A','S','D','F','G','H','J','K','L','semicolon']
    )
    freq_desc_row3 = ", ".join(
        f"{k}={NOTE_FREQUENCIES[k]:.0f}Hz"
        for k in ['Z','X','C','V','B','N','M','comma','period','slash']
    )

    # Build percussion descriptions
    perc_desc = ", ".join(f"{k}={v}" for k, v in PERCUSSION.items())

    system = f"""You are a composer and visual artist for Purple Computer's Play Mode.

Play Mode is a 10x4 grid mapped to the QWERTY keyboard. Each key press plays a sound AND cycles the key's color. Your job is to create compositions that look good AND sound good.

## The Grid (coordinates: col 0-9, row 0-3)

```
Col:  0    1    2    3    4    5    6    7    8    9
Row 0: 1    2    3    4    5    6    7    8    9    0    (Percussion)
Row 1: Q    W    E    R    T    Y    U    I    O    P    (High marimba)
Row 2: A    S    D    F    G    H    J    K    L    ;    (Mid marimba)
Row 3: Z    X    C    V    B    N    M    ,    .    /    (Low marimba)
```

## Sounds

Row 0 (numbers) are percussion: {perc_desc}
Row 1 (Q-P) are high marimba: {freq_desc_row1}
Row 2 (A-;) are mid marimba: {freq_desc_row2}
Row 3 (Z-/) are low marimba: {freq_desc_row3}

Notes go left-to-right = ascending pitch. Rows go top-to-bottom = descending octave (row 1 is highest, row 3 is lowest).

## Color Cycling

Each key press cycles the color:
- 1 press = purple (#da77f2)
- 2 presses = blue (#4dabf7)
- 3 presses = red (#ff6b6b)
- 4 presses = back to off (default)

Colors PERSIST. To make a key purple, press it once. To make it blue, press it twice. To make it red, press it three times. To leave it off, don't press it (or press it exactly 4 times).

IMPORTANT: Every press also plays a sound. So pressing a key 3 times for red plays the sound 3 times. Design sequences where repeated presses sound intentional (like rhythmic repetition), not accidental.

## Symmetry

The grid center axis is between columns 4 and 5. For symmetric shapes, mirror across this axis:
- Col 0 mirrors col 9
- Col 1 mirrors col 8
- Col 2 mirrors col 7
- Col 3 mirrors col 6
- Col 4 mirrors col 5

## Musical Tips

- Adjacent keys in a row form a scale (left-to-right = ascending)
- Playing across rows gives octave jumps
- Use None (rest) in sequences for rhythmic pauses
- Chords: use lists like ["q", "p"] to play simultaneous keys
- Percussion (row 0) adds rhythm without affecting melodic flow
- Higher seconds_between for dramatic moments, lower for energetic parts

## Reference Patterns

Smiley face:
```
. . . P . P . . . .    <- eyes at col 3,5 (purple, 1 press)
. . . . B . . . . .    <- nose at col 4 (blue, 2 presses)
. . R . . . R . . .    <- smile corners at col 2,6 (red, 3 presses)
. . R R R R R . . .    <- smile bottom at col 2-6 (red, 3 presses)
```

Heart:
```
. P P . . . P P . .    <- top bumps at col 1-2, 6-7
P P P P . P P P P .    <- wide part (adjusted for grid)
. P P P P P P P . .    <- middle
. . P P P P P . . .    <- narrowing
. . . P P P . . . .    <- bottom
```
(Note: the grid only has 4 rows, so simplify shapes to fit)

Heart (4 rows):
```
. R . R . R . R . .
R R R R . R R R R .
. R R R R R R R . .
. . . R R R . . . .
```

## Output Format

Return a JSON object with:
- "title": short title for the composition
- "grid_plan": a 4x10 array of strings showing your intended final color state. Use "." for off, "P" for purple (1 press), "B" for blue (2 presses), "R" for red (3 presses).
- "sections": array of sections, each with:
  - "comment": description of what this section does (e.g., "Eyes (purple)")
  - "keys": list of key presses. Each item is a lowercase key string, a list of keys for a chord, or null for a rest. IMPORTANT: for keys that need multiple presses for color, repeat the key (e.g., ["t", "t"] for blue T).
  - "seconds_between": seconds between each key press
  - "pause_after": seconds to pause after this section (0.2-1.0)

Example for a smiley:
```json
{{
  "title": "Smiley Face",
  "grid_plan": [
    [".", ".", ".", "P", ".", "P", ".", ".", ".", "."],
    [".", ".", ".", ".", "B", ".", ".", ".", ".", "."],
    [".", ".", "R", ".", ".", ".", "R", ".", ".", "."],
    [".", ".", "R", "R", "R", "R", "R", ".", ".", "."]
  ],
  "sections": [
    {{
      "comment": "Eyes (purple, 1 press each)",
      "keys": ["4", null, "6"],
      "seconds_between": 0.67,
      "pause_after": 0.4
    }},
    {{
      "comment": "Nose (blue, 2 presses)",
      "keys": ["t", "t"],
      "seconds_between": 0.5,
      "pause_after": 0.4
    }},
    {{
      "comment": "Smile corners (red, 3 presses each)",
      "keys": ["d", "d", "d", null, "j", "j", "j"],
      "seconds_between": 0.33,
      "pause_after": 0.3
    }},
    {{
      "comment": "Smile bottom (red, 3 presses each)",
      "keys": ["c", "c", "c", "v", "v", "v", "b", "b", "b", "n", "n", "n", "m", "m", "m"],
      "seconds_between": 0.25,
      "pause_after": 0.8
    }}
  ]
}}
```

Key name reference (use lowercase in sequences):
- Row 0: 1 2 3 4 5 6 7 8 9 0
- Row 1: q w e r t y u i o p
- Row 2: a s d f g h j k l ;
- Row 3: z x c v b n m , . /
"""

    user = f'Create a Play Mode composition for: "{goal}"'

    return system, user


def build_review_prompt(sections: list[dict], grid_text: str) -> tuple[str, str]:
    """Build the system and user prompts for Pass 2 (review).

    Returns (system_prompt, user_prompt).
    """
    system = """You are reviewing a Play Mode composition for Purple Computer. You will see the computed grid visualization showing what the composition actually produces. Check for:

1. Symmetry issues (if the shape should be symmetric)
2. Missing or extra colored keys
3. Keys that cycle to the wrong color (e.g., pressed 5 times wraps to 1 press = purple instead of off)
4. Visual clarity (does the shape read well on a 10x4 grid?)

If the composition looks correct, return it unchanged. If there are issues, fix them and return the corrected version in the same JSON format.

Return a JSON object with the same structure: title, grid_plan, and sections."""

    # Rebuild section descriptions for the review
    sections_json = json.dumps(sections, indent=2)

    user = f"""Here is what the composition produces on the 10x4 grid:

{grid_text}

And here are the sections that generated it:
{sections_json}

Review the grid. Does it look correct? Are there symmetry issues, wrong colors, or clarity problems? Return the (possibly corrected) composition as JSON."""

    return system, user


def call_api(system: str, user: str, api_key: str) -> str:
    """Call the Claude API and return the response text."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    return response.content[0].text


def normalize_key(key: str) -> str | None:
    """Normalize a key string to the canonical form used in ALL_KEYS.

    Returns None if the key is not valid.
    """
    if not isinstance(key, str):
        return None
    upper = key.upper()
    if upper in ALL_KEYS:
        return upper
    # Handle special key names
    if key == ';' or upper == ';':
        return ';'
    return None


def compute_grid(sections: list[dict]) -> tuple[dict[str, int], str]:
    """Count presses per key across all sections, compute final color state.

    Returns (color_map, grid_text) where:
    - color_map maps uppercase key -> color index (0=purple, 1=blue, 2=red, -1=off)
    - grid_text is a formatted text grid for display
    """
    press_counts: dict[str, int] = {}

    for section in sections:
        for item in section.get("keys", []):
            if item is None:
                continue
            if isinstance(item, list):
                keys = item
            else:
                keys = [item]
            for k in keys:
                norm = normalize_key(k)
                if norm:
                    press_counts[norm] = press_counts.get(norm, 0) + 1

    # Compute final color state
    color_map: dict[str, int] = {}
    warnings = []
    for key, count in press_counts.items():
        color_idx = (count - 1) % len(COLORS)
        if COLORS[color_idx] is None:
            color_map[key] = -1
        else:
            color_map[key] = color_idx
        if count >= 4:
            effective = count % len(COLORS)
            if effective == 0:
                warnings.append(f"  Warning: {key} pressed {count}x, cycles back to OFF")
            else:
                warnings.append(f"  Warning: {key} pressed {count}x, wraps to {COLOR_NAMES.get(effective - 1, '?')}")

    # Build text grid
    lines = []
    lines.append("Final color state (P=purple, B=blue, R=red, .=off):")
    lines.append("")

    # Header with column numbers
    header = "  " + "  ".join(str(c) for c in range(10))
    lines.append(header)

    for r, row in enumerate(GRID_KEYS):
        # Color line
        color_line = "  "
        for c, key in enumerate(row):
            idx = color_map.get(key, -1)
            char = COLOR_CHARS.get(idx, ".")
            color_line += f"{char}  "
        lines.append(color_line.rstrip())

        # Key label line
        key_line = "  "
        for c, key in enumerate(row):
            display = key if len(key) == 1 else key[0]
            key_line += f"{display}  "
        lines.append(key_line.rstrip())

    if warnings:
        lines.append("")
        for w in warnings:
            lines.append(w)

    return color_map, "\n".join(lines)


def sections_to_code(sections: list[dict]) -> str:
    """Convert sections to Python PlayKeys code."""
    code_lines = []

    for section in sections:
        comment = section.get("comment", "")
        if comment:
            code_lines.append(f'    Comment("=== {comment} ==="),')

        keys = section.get("keys", [])
        secs = section.get("seconds_between", 0.5)
        pause = section.get("pause_after", 0.5)

        # Convert keys to PlayKeys sequence format
        sequence_items = []
        for item in keys:
            if item is None:
                sequence_items.append("None")
            elif isinstance(item, list):
                inner = ", ".join(f"'{k}'" for k in item)
                sequence_items.append(f"[{inner}]")
            else:
                sequence_items.append(f"'{item}'")

        sequence_str = ", ".join(sequence_items)
        code_lines.append(f"    PlayKeys(")
        code_lines.append(f"        sequence=[{sequence_str}],")
        code_lines.append(f"        seconds_between={secs},")
        code_lines.append(f"        pause_after={pause},")
        code_lines.append(f"    ),")
        code_lines.append("")

    return "\n".join(code_lines)


def validate_sections(sections: list[dict]) -> list[dict]:
    """Validate and clean sections. Warn about invalid keys."""
    valid_keys_lower = {k.lower() for k in ALL_KEYS}

    cleaned = []
    for section in sections:
        clean_keys = []
        for item in section.get("keys", []):
            if item is None:
                clean_keys.append(None)
            elif isinstance(item, list):
                valid_chord = [k for k in item if k.lower() in valid_keys_lower or k in valid_keys_lower]
                if valid_chord:
                    clean_keys.append(valid_chord)
                else:
                    print(f"  Warning: dropped invalid chord {item}")
            elif isinstance(item, str):
                if item.lower() in valid_keys_lower or item in valid_keys_lower:
                    clean_keys.append(item)
                else:
                    print(f"  Warning: dropped invalid key '{item}'")
            else:
                print(f"  Warning: dropped unknown item {item}")

        cleaned.append({
            "comment": section.get("comment", ""),
            "keys": clean_keys,
            "seconds_between": section.get("seconds_between", 0.5),
            "pause_after": section.get("pause_after", 0.5),
        })

    return cleaned


def main():
    parser = argparse.ArgumentParser(
        description="Generate Play Mode compositions from natural language using Claude AI."
    )
    parser.add_argument("goal", help="What to create (e.g., 'smiley face', 'rainstorm', 'ascending melody')")
    parser.add_argument("--no-review", action="store_true", help="Skip the review pass (Pass 2)")
    parser.add_argument("--json", action="store_true", help="Print raw JSON output")
    parser.add_argument("--save", metavar="NAME",
                        help="Save as a named demo segment (e.g., --save smiley)")
    args = parser.parse_args()

    # Load API key
    load_env_file()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set.")
        print("Set it in tools/.env or as an environment variable.")
        sys.exit(1)

    # Pass 1: Generate
    print(f'Generating composition for: "{args.goal}"')
    print()

    system, user = build_generate_prompt(args.goal)
    print("[Pass 1] Calling Claude API...")
    response_text = call_api(system, user, api_key)

    data = parse_json_robust(response_text)
    if not data or not isinstance(data, dict):
        print("Error: could not parse API response as JSON.")
        print("Raw response:")
        print(response_text)
        sys.exit(1)

    title = data.get("title", "Untitled")
    sections = data.get("sections", [])

    if not sections:
        print("Error: no sections in response.")
        print("Raw response:")
        print(response_text)
        sys.exit(1)

    print(f'  Title: "{title}"')
    print(f"  Sections: {len(sections)}")

    # Validate keys
    sections = validate_sections(sections)

    # Compute grid visualization
    color_map, grid_text = compute_grid(sections)
    print()
    print(grid_text)
    print()

    # Pass 2: Review (unless --no-review)
    if not args.no_review:
        print("[Pass 2] Sending grid to Claude for review...")
        review_system, review_user = build_review_prompt(sections, grid_text)
        review_text = call_api(review_system, review_user, api_key)

        review_data = parse_json_robust(review_text)
        if review_data and isinstance(review_data, dict):
            review_sections = review_data.get("sections", [])
            if review_sections:
                review_sections = validate_sections(review_sections)
                # Check if anything changed
                old_json = json.dumps(sections, sort_keys=True)
                new_json = json.dumps(review_sections, sort_keys=True)
                if old_json != new_json:
                    print("  Review made corrections.")
                    sections = review_sections
                    title = review_data.get("title", title)
                    color_map, grid_text = compute_grid(sections)
                    print()
                    print(grid_text)
                    print()
                else:
                    print("  Review confirmed: no changes needed.")
            else:
                print("  Review returned no sections, keeping original.")
        else:
            print("  Could not parse review response, keeping original.")
        print()

    # Output
    if args.json:
        output = {
            "title": title,
            "sections": sections,
        }
        print(json.dumps(output, indent=2))
    else:
        # Print PlayKeys code
        code = sections_to_code(sections)
        print("--- PlayKeys Code ---")
        print()
        print(code)

        if args.save:
            from ai_utils import append_to_demo_json
            segments_dir = Path(__file__).parent.parent / "purple_tui" / "demo" / "segments"
            segments_dir.mkdir(parents=True, exist_ok=True)
            segment_path = segments_dir / f"{args.save}.py"
            content = f'''"""AI-generated Play Mode composition: {title}

Generated by: python tools/play_ai.py "{args.goal}" --save {args.save}
"""

from ..script import PlayKeys, Comment, Pause, SwitchMode

SEGMENT = [
    SwitchMode("play"),
    Pause(0.3),

{code}
    Pause(2.0),
    Comment("AI-generated composition complete!"),
]
'''
            segment_path.write_text(content)
            append_to_demo_json(args.save)
            print(f"Saved segment: {segment_path}")
            print(f"Added to demo.json")


if __name__ == "__main__":
    main()
