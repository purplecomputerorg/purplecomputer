"""Shared utilities for AI tool scripts (play_ai, doodle_ai)."""

import json
import os
import re
from pathlib import Path


def load_env_file():
    """Load environment variables from tools/.env if it exists."""
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())


def parse_json_robust(text: str) -> dict | list | None:
    """Parse JSON from text with fallbacks for common issues.

    Handles:
    - JSON inside markdown code blocks
    - Trailing commas
    - Truncated JSON (attempts to close brackets)
    - Comments (// style)
    """

    # Try to extract from markdown code block first
    code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if code_block_match:
        text = code_block_match.group(1)

    # Find the JSON object or array
    start_obj = text.find('{')
    start_arr = text.find('[')

    if start_obj < 0 and start_arr < 0:
        return None

    # Determine if we're looking for object or array
    if start_arr >= 0 and (start_obj < 0 or start_arr < start_obj):
        start = start_arr
        open_char, close_char = '[', ']'
    else:
        start = start_obj
        open_char, close_char = '{', '}'

    # Find matching end by counting brackets
    depth = 0
    end = start
    in_string = False
    escape_next = False

    for i, char in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if char == '\\' and in_string:
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if depth != 0:
        # Truncated JSON: try to close it
        json_text = text[start:end] if end > start else text[start:]
        json_text += close_char * depth
    else:
        json_text = text[start:end]

    # Clean up common issues
    # Remove trailing commas before ] or }
    json_text = re.sub(r',\s*([}\]])', r'\1', json_text)
    # Remove // comments (but not inside strings, simplified)
    json_text = re.sub(r'//[^\n]*\n', '\n', json_text)

    # Try to parse
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f"[JSON Parse] First attempt failed: {e}")
        print(f"[JSON Parse] Extracted text length: {len(json_text)}, depth was: {depth}")
        if hasattr(e, 'pos') and e.pos:
            context_start = max(0, e.pos - 50)
            context_end = min(len(json_text), e.pos + 50)
            print(f"[JSON Parse] Context around error: ...{json_text[context_start:context_end]}...")

    # Last resort: try to extract just the actions array
    actions_match = re.search(r'"actions"\s*:\s*(\[[\s\S]*?\])(?=\s*[,}]|$)', text)
    if actions_match:
        try:
            actions_text = actions_match.group(1)
            actions_text = re.sub(r',\s*([}\]])', r'\1', actions_text)
            actions = json.loads(actions_text)
            print(f"[JSON Parse] Fallback extraction got {len(actions)} actions")
            return {"actions": actions}
        except json.JSONDecodeError as e:
            print(f"[JSON Parse] Fallback also failed: {e}")

    return None
