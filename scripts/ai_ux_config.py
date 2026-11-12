"""Shared config for AI UX testing scripts."""

import os
from datetime import datetime
from pathlib import Path

DEFAULT_MAX_STEPS = 10
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
REPO_ROOT = Path(__file__).resolve().parent.parent
BUG_LOG_PATH = REPO_ROOT / "docs" / "AI_UX_BUGS.md"

# Pricing per million tokens (input, output) - from platform.claude.com/docs/en/about-claude/pricing
MODEL_PRICING = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
# Fallback for unknown models
DEFAULT_PRICING = (3.00, 15.00)


def estimate_cost(input_tokens: int, output_tokens: int, model: str, cache_write: int = 0, cache_read: int = 0) -> float:
    """Estimate USD cost from token counts and model; cache writes cost 1.25x input, reads 0.1x."""
    inp_rate, out_rate = MODEL_PRICING.get(model, DEFAULT_PRICING)
    return ((input_tokens + cache_write * 1.25 + cache_read * 0.1) * inp_rate + output_tokens * out_rate) / 1_000_000


def check_api_key() -> bool:
    """ANTHROPIC_API_KEY from the environment, or from the repo's .env."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith("ANTHROPIC_API_KEY="):
                    key = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                    if key:
                        os.environ["ANTHROPIC_API_KEY"] = key
                        return True
    return False


def append_findings_log(bugs: list[dict], confusions: list[dict], persona: str, model: str):
    """Append bugs and confusions to the repo-level markdown log."""
    date = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not BUG_LOG_PATH.exists():
        BUG_LOG_PATH.write_text(
            "# AI UX Test Findings\n\n"
            "Bugs and UX confusions discovered by automated AI UX testing (`just ux`). "
            "Mark resolved items with ~~strikethrough~~ or delete them.\n\n"
        )

    lines = [f"## {date} ({persona}, {model})\n\n"]
    for bug in bugs:
        lines.append(f"### [{bug['severity'].upper()}] {bug['title']}\n\n")
        lines.append(f"{bug['description']}\n\n")
        if bug.get("steps"):
            lines.append("**Repro:**\n")
            lines += [f"{i}. {step}\n" for i, step in enumerate(bug["steps"], 1)]
            lines.append("\n")
    for confusion in confusions:
        lines.append(f"### [CONFUSION: {confusion['severity'].upper()}] {confusion['title']}\n\n")
        lines.append(f"**Tried:** {confusion['what_i_tried']}\n\n")
        lines.append(f"**What happened:** {confusion['what_happened']}\n\n")
        lines.append(f"**Expected:** {confusion['what_i_expected']}\n\n")

    with open(BUG_LOG_PATH, "a") as f:
        f.writelines(lines)
