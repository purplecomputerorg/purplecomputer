#!/usr/bin/env python3
"""Autonomous AI UX bug hunter for Purple Computer.

Runs a budget-aware loop: an orchestrator (Sonnet) reviews what's been tested,
plans targeted missions, and dispatches test sessions with the right model and
focus area. Tracks actual API cost (not estimates) so budget decisions stay
accurate even if pricing assumptions drift.

State persists in .ai_ux_hunt/ so history survives reboots (unlike /tmp).
Bugs still go to AI_UX_BUGS.md.

Usage:
    just hunt                    # default $10 budget
    just hunt --budget 5.00      # custom budget
    just hunt --resume           # continue a previous hunt
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai_ux_config import DEFAULT_MODEL, estimate_cost, MODEL_PRICING  # noqa: E402

# Set environment before app imports (same as ai_ux_test.py)
os.environ["PURPLE_NO_EVDEV"] = "1"
os.environ["PURPLE_DEV_MODE"] = "1"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
os.environ.setdefault("ORT_LOGGING_LEVEL", "3")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import io

_real_stdout = sys.__stdout__
_real_stderr = sys.__stderr__
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_ux_test import run_agent  # noqa: E402
sys.stdout = _real_stdout
sys.stderr = _real_stderr

try:
    import anthropic
except ImportError:
    print("pip install anthropic", file=sys.stderr)
    sys.exit(1)

# ANSI colors
BOLD = "\033[1m"
DIM = "\033[2m"
PURPLE = "\033[35m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
RESET = "\033[0m"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
HUNT_DIR = REPO_ROOT / ".ai_ux_hunt"
STATE_PATH = HUNT_DIR / "hunt_state.json"
SESSIONS_DIR = HUNT_DIR / "sessions"
BUG_LOG_PATH = REPO_ROOT / "AI_UX_BUGS.md"

ORCHESTRATOR_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


def _default_state(budget: float) -> dict:
    return {
        "budget": budget,
        "actual_cost_total": 0.0,
        "orchestrator_cost_total": 0.0,
        "sessions": [],
        "known_bugs": [],
        "known_confusions": [],
        "coverage_notes": [],
        "started": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
    }


def load_state(budget: float | None = None) -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            state = json.load(f)
        if budget is not None:
            state["budget"] = budget
        return state
    return _default_state(budget or 10.0)


def save_state(state: dict):
    HUNT_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = datetime.now().isoformat()
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Orchestrator: ask Sonnet to plan the next mission
# ---------------------------------------------------------------------------

ORCHESTRATOR_SYSTEM = """\
You are a test strategist for Purple Computer, a kids' app (ages 4-7) with three rooms: Play (math/typing), Music (notes), Art (drawing/turtle). Each room has a code panel (REPL).

Your job: given a budget, what's been tested, and what's been found, plan the SINGLE most valuable next test session. You want to find NEW bugs AND UX confusions (places where a kid or parent would feel lost, not know what to do, or misunderstand the UI).

Think about:
- What areas/interactions haven't been tested yet?
- What edge cases might be hiding bugs?
- Where might the UX be confusing for a 5-year-old or a non-technical parent?
- Are there dead ends, missing affordances, or unclear next steps?
- Where did previous sessions see "almost-bugs" or unexpected behavior worth deeper investigation?
- Cheap models (Haiku) for broad sweeps and crash testing; expensive models (Opus) for subtle UX/confusion issues.
- Alternate between bug-hunting and confusion-hunting missions. Both matter equally.

Respond with ONLY a JSON object (no markdown fencing):
{
  "model": "claude-haiku-4-5-20251001" | "claude-sonnet-4-6" | "claude-opus-4-6",
  "room": "play" | "music" | "art",
  "max_steps": 10-60,
  "mission": "Specific test instructions for the agent. Be concrete: what to type, what to try, what to look for. Tell the agent whether to focus on finding bugs, confusions, or both.",
  "rationale": "Why this mission, briefly."
}

Budget rules:
- Haiku: ~$0.003/step. Use for crash testing, key mashing, broad sweeps.
- Sonnet: ~$0.010/step. Use for methodical feature testing.
- Opus: ~$0.050/step. Use for subtle UX evaluation, logic bugs, confusing flows.
- Leave at least $0.50 as a buffer. Don't plan sessions that would exceed the remaining budget.
- If remaining budget is under $1.00, use Haiku with fewer steps.
- Vary rooms and approaches across sessions. Don't repeat the same area twice in a row unless investigating a lead."""


def _build_orchestrator_prompt(state: dict) -> str:
    remaining = state["budget"] - state["actual_cost_total"] - state["orchestrator_cost_total"]
    session_count = len(state["sessions"])

    parts = [f"Budget: ${state['budget']:.2f} total, ${remaining:.2f} remaining after {session_count} sessions."]

    if state["known_bugs"]:
        parts.append("\nKnown bugs (already found, don't re-test these):")
        for bug in state["known_bugs"]:
            parts.append(f"  - [{bug.get('severity', '?')}] {bug.get('title', '?')}")

    if state.get("known_confusions"):
        parts.append("\nKnown UX confusions (already found, don't re-report these):")
        for c in state["known_confusions"]:
            parts.append(f"  - [{c.get('severity', '?')}] {c.get('title', '?')}")

    if state["sessions"]:
        parts.append("\nPrevious sessions (most recent first):")
        for s in reversed(state["sessions"][-10:]):
            model_short = s.get("model", "?").split("-")[1] if "-" in s.get("model", "") else s.get("model", "?")
            bugs_found = s.get("bug_count", 0)
            confusions_found = s.get("confusion_count", 0)
            cost = s.get("actual_cost", 0)
            room = s.get("room", "?")
            steps = s.get("steps_used", "?")
            mission_preview = (s.get("mission", "") or s.get("persona", ""))[:100]
            findings = f"{bugs_found} bugs, {confusions_found} confusions"
            parts.append(f"  - {model_short}, {room}, {steps} steps, ${cost:.3f}, {findings}: {mission_preview}")

    if state["coverage_notes"]:
        parts.append("\nCoverage notes from previous sessions:")
        for note in state["coverage_notes"][-15:]:
            parts.append(f"  - {note}")

    if remaining < 1.0:
        parts.append(f"\nWARNING: Only ${remaining:.2f} left. Use Haiku, keep steps low.")

    return "\n".join(parts)


def _extract_text(response) -> str:
    text = "".join(b.text for b in response.content if hasattr(b, "text")).strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = "\n".join(text.split("\n")[:-1])
    return text.strip()


def _try_parse_json(text: str):
    try:
        return json.loads(text), None
    except json.JSONDecodeError as e:
        # Fallback: escape literal newlines/tabs inside string values.
        repaired = re.sub(
            r'"((?:[^"\\]|\\.)*)"',
            lambda m: '"' + m.group(1).replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + '"',
            text,
            flags=re.DOTALL,
        )
        try:
            return json.loads(repaired), None
        except json.JSONDecodeError:
            return None, str(e)


def plan_next_session(state: dict, max_attempts: int = 3) -> dict | None:
    """Ask the orchestrator to plan the next test session. Returns mission dict or None if done."""
    remaining = state["budget"] - state["actual_cost_total"] - state["orchestrator_cost_total"]
    if remaining < 0.10:
        return None

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": _build_orchestrator_prompt(state)}]
    plan = None
    last_err = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.messages.create(
                model=ORCHESTRATOR_MODEL,
                max_tokens=500,
                system=ORCHESTRATOR_SYSTEM,
                messages=messages,
            )
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            print(f"  {YELLOW}Orchestrator API error (attempt {attempt}/{max_attempts}): {e}{RESET}")
            time.sleep(2 * attempt)
            continue

        state["orchestrator_cost_total"] += estimate_cost(
            response.usage.input_tokens, response.usage.output_tokens, ORCHESTRATOR_MODEL
        )

        text = _extract_text(response)
        plan, last_err = _try_parse_json(text)
        if plan is not None:
            break

        print(f"  {YELLOW}Invalid JSON (attempt {attempt}/{max_attempts}): {last_err}{RESET}")
        print(f"  {DIM}{text[:200]}{RESET}")
        messages.append({"role": "assistant", "content": text})
        messages.append({
            "role": "user",
            "content": f"That wasn't valid JSON ({last_err}). Respond with ONLY a valid JSON object. Escape newlines inside strings as \\n.",
        })

    if plan is None:
        print(f"  {RED}Orchestrator failed to produce valid JSON after {max_attempts} attempts.{RESET}")
        return None

    # Validate and cap cost
    max_steps = min(plan.get("max_steps", 20), 80)
    model = plan.get("model", DEFAULT_MODEL)
    estimated_session_cost = estimate_cost(3000 * max_steps, 250 * max_steps, model)

    if estimated_session_cost > remaining - 0.10:
        # Scale down steps to fit budget
        safe_budget = remaining - 0.10
        inp_rate, out_rate = MODEL_PRICING.get(model, (3.0, 15.0))
        cost_per_step = (3000 / 1e6 * inp_rate) + (250 / 1e6 * out_rate)
        max_steps = max(5, int(safe_budget / cost_per_step))
        plan["max_steps"] = max_steps

    plan["max_steps"] = max_steps
    return plan


# ---------------------------------------------------------------------------
# Session summary: extract coverage notes from action log
# ---------------------------------------------------------------------------


def _summarize_session(report: dict) -> list[str]:
    """Extract short coverage notes from a session's action log."""
    notes = []
    rooms_visited = set()
    actions_by_type = {}

    for entry in report.get("action_log", []):
        tool = entry.get("tool", "")
        inp = entry.get("input", {})

        if tool == "switch_room":
            rooms_visited.add(inp.get("room", "?"))
        actions_by_type[tool] = actions_by_type.get(tool, 0) + 1

        if tool == "type_text":
            text = inp.get("text", "")
            if text:
                notes.append(f"Typed '{text[:40]}' in {report.get('start_room', '?')}")
        elif tool == "toggle_code_panel":
            notes.append(f"Toggled code panel in {report.get('start_room', '?')}")

    room = report.get("start_room", "?")
    model_short = report.get("model", "?").rsplit("-", 1)[0].split("-")[-1]
    steps = report.get("steps", 0)
    bugs = report.get("bug_count", 0)
    confusions = report.get("confusion_count", 0)

    summary = f"{model_short}: {room} room, {steps} steps, {bugs} bugs, {confusions} confusions"
    if rooms_visited:
        summary += f", visited {', '.join(sorted(rooms_visited))}"

    action_summary = ", ".join(f"{v}x {k}" for k, v in sorted(actions_by_type.items()) if k != "done")
    if action_summary:
        summary += f" ({action_summary})"

    return [summary] + notes[:5]


# ---------------------------------------------------------------------------
# Main hunt loop
# ---------------------------------------------------------------------------


async def run_hunt(budget: float = 10.0, resume: bool = False):
    state = load_state(budget if not resume else None)
    if not resume:
        state = _default_state(budget)
    save_state(state)

    remaining = budget - state["actual_cost_total"] - state["orchestrator_cost_total"]
    session_num = len(state["sessions"])

    print()
    print(f"  {PURPLE}{BOLD}AI UX Bug Hunt{RESET}")
    print(f"  {DIM}Autonomous bug hunting with budget-aware orchestration{RESET}")
    print()
    print(f"  Budget:    ${state['budget']:.2f}")
    print(f"  Spent:     ${state['actual_cost_total'] + state['orchestrator_cost_total']:.2f}")
    print(f"  Remaining: ${remaining:.2f}")
    print(f"  Sessions:  {session_num} completed")
    print(f"  Bugs:      {len(state['known_bugs'])} found so far")
    print(f"  Confusions: {len(state.get('known_confusions', []))} found so far")
    print()

    while True:
        remaining = state["budget"] - state["actual_cost_total"] - state["orchestrator_cost_total"]
        session_num = len(state["sessions"]) + 1

        if remaining < 0.10:
            print(f"  {YELLOW}Budget exhausted (${remaining:.2f} remaining). Stopping.{RESET}")
            break

        # Plan next session
        print(f"  {CYAN}{'=' * 50}{RESET}")
        print(f"  {BOLD}Session #{session_num}{RESET} (${remaining:.2f} remaining)")
        print(f"  {DIM}Planning next mission...{RESET}")

        plan = plan_next_session(state)
        if plan is None:
            state["planning_failures"] = state.get("planning_failures", 0) + 1
            save_state(state)
            if state["planning_failures"] >= 5:
                print(f"  {RED}5 consecutive planning failures. Stopping.{RESET}")
                break
            print(f"  {YELLOW}Planning failed ({state['planning_failures']}/5). Retrying in 30s...{RESET}")
            time.sleep(30)
            continue
        state["planning_failures"] = 0

        save_state(state)  # save orchestrator cost

        model = plan.get("model", DEFAULT_MODEL)
        room = plan.get("room", "play")
        max_steps = plan.get("max_steps", 20)
        mission = plan.get("mission", "Explore freely and look for bugs.")
        rationale = plan.get("rationale", "")

        model_short = model.split("-")[1] if "-" in model else model
        est_cost = estimate_cost(3000 * max_steps, 250 * max_steps, model)

        print()
        print(f"  {BOLD}Plan:{RESET} {model_short}, {room}, {max_steps} steps (~${est_cost:.2f})")
        print(f"  {BOLD}Why:{RESET}  {rationale[:100]}")
        print(f"  {BOLD}Mission:{RESET}")
        for line in mission.split(". "):
            line = line.strip()
            if line:
                print(f"    {DIM}{line}.{RESET}")
        print()

        # Run the session
        session_dir = SESSIONS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{session_num:03d}"
        known_titles = [b.get("title", "") for b in state["known_bugs"]]
        known_titles += [c.get("title", "") for c in state.get("known_confusions", [])]

        try:
            report = await run_agent(
                persona_name="hunt",
                room=room,
                max_steps=max_steps,
                model=model,
                mission=mission,
                log_dir=session_dir,
                known_bugs=known_titles if known_titles else None,
            )
        except Exception as e:
            print(f"  {RED}Session crashed: {e}{RESET}")
            report = {"actual_cost": 0, "bugs": [], "bug_count": 0, "steps": 0, "action_log": []}

        # Update state with actual cost
        actual_cost = report.get("actual_cost", 0)
        state["actual_cost_total"] += actual_cost

        # Record session
        session_record = {
            "session_num": session_num,
            "model": model,
            "room": room,
            "max_steps": max_steps,
            "steps_used": report.get("steps", 0),
            "mission": mission,
            "rationale": rationale,
            "bug_count": report.get("bug_count", 0),
            "confusion_count": report.get("confusion_count", 0),
            "actual_cost": actual_cost,
            "estimated_cost": est_cost,
            "timestamp": datetime.now().isoformat(),
        }
        state["sessions"].append(session_record)

        # Track new bugs and confusions
        for bug in report.get("bugs", []):
            state["known_bugs"].append({
                "title": bug.get("title", ""),
                "severity": bug.get("severity", "medium"),
                "session": session_num,
            })
        for confusion in report.get("confusions", []):
            state.setdefault("known_confusions", []).append({
                "title": confusion.get("title", ""),
                "severity": confusion.get("severity", "minor"),
                "session": session_num,
            })

        # Add coverage notes
        coverage = _summarize_session(report)
        state["coverage_notes"].extend(coverage)
        # Keep coverage notes from growing unbounded
        if len(state["coverage_notes"]) > 50:
            state["coverage_notes"] = state["coverage_notes"][-40:]

        save_state(state)

        # Print session result
        total_spent = state["actual_cost_total"] + state["orchestrator_cost_total"]
        remaining = state["budget"] - total_spent
        cost_drift = actual_cost - est_cost if est_cost > 0 else 0

        print()
        print(f"  {BOLD}Session #{session_num} result:{RESET}")
        print(f"    Cost: ${actual_cost:.3f} (est ${est_cost:.3f}, drift {'+' if cost_drift >= 0 else ''}{cost_drift:.3f})")
        print(f"    Findings: {report.get('bug_count', 0)} bugs, {report.get('confusion_count', 0)} confusions")
        print(f"    Total spent: ${total_spent:.2f} / ${state['budget']:.2f} (${remaining:.2f} left)")
        print()

    # Final summary
    total_spent = state["actual_cost_total"] + state["orchestrator_cost_total"]
    print()
    print(f"  {PURPLE}{BOLD}Hunt Complete{RESET}")
    confusions = state.get("known_confusions", [])
    print(f"  Sessions:       {len(state['sessions'])}")
    print(f"  Bugs:           {len(state['known_bugs'])}")
    print(f"  Confusions:     {len(confusions)}")
    print(f"  Total spent:    ${total_spent:.2f} / ${state['budget']:.2f}")
    print(f"  Orchestrator:   ${state['orchestrator_cost_total']:.2f}")
    print(f"  Test sessions:  ${state['actual_cost_total']:.2f}")

    if state["known_bugs"]:
        print()
        print(f"  {BOLD}Bugs found:{RESET}")
        for bug in state["known_bugs"]:
            print(f"    [{bug.get('severity', '?').upper()}] {bug.get('title', '?')} (session #{bug.get('session', '?')})")

    if confusions:
        print()
        print(f"  {BOLD}Confusions found:{RESET}")
        for c in confusions:
            print(f"    [{c.get('severity', '?').upper()}] {c.get('title', '?')} (session #{c.get('session', '?')})")

    print(f"\n  State: {STATE_PATH}")
    print(f"  Findings log: {BUG_LOG_PATH}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def check_api_key():
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


def main():
    parser = argparse.ArgumentParser(description="Autonomous AI UX bug hunter")
    parser.add_argument("--budget", type=float, default=10.0,
                        help="Total budget in USD (default: $10.00)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume a previous hunt (keep existing state, add budget if specified)")
    args = parser.parse_args()

    if not check_api_key():
        print(f"  {RED}No ANTHROPIC_API_KEY found. Set it in your environment or .env{RESET}")
        sys.exit(1)

    try:
        asyncio.run(run_hunt(budget=args.budget, resume=args.resume))
    except KeyboardInterrupt:
        print(f"\n  {YELLOW}Interrupted. State saved to {STATE_PATH}{RESET}")
        print(f"  {DIM}Resume with: just hunt --resume{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
