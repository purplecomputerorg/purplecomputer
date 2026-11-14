#!/usr/bin/env python3
"""Spends a budget on e2e-ai scenarios (scripts/e2e_ai_scenarios.py), a few at a time, then has Opus turn every
real finding into one ranked list of what to fix, written for an LLM to pick up: docs/E2E_AI_FIXES.md.

    just e2e-ai-sweep [--budget 10] [--parallel 3] [--only breaker,grandparent] [--each 0.4] [--url URL]

A scenario starts only when its budget still fits, so the total never passes --budget. Scenarios that finish
under budget leave room for the next. Once every scenario has run, the ones that found the most real bugs per
dollar run again (up to 3 times each), since the same personas find different things each time. Each run is
told what earlier runs already found, so it doesn't pay to find it again."""

import argparse
import asyncio
import json
import os
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import anthropic  # noqa: E402

from ai_ux_config import BUG_LOG_PATH, check_api_key, estimate_cost  # noqa: E402
from e2e_ai_scenarios import OPUS, SCENARIOS  # noqa: E402

PORT = 5199
SYNTH_RESERVE = 0.8  # kept back for the write-up
SMALLEST = 0.5  # a scenario with less than this can't get far enough to be worth it
ROUNDS = 3
FIXES = ROOT / "docs" / "E2E_AI_FIXES.md"

SYNTH = """You turn an automated end-to-end test sweep of Purple Computer into the one document a developer (most
likely an LLM coding agent with this repo checked out) reads to fix what it found.

Purple Computer is a laptop for kids 3 to 10. Purple Studio (studio/, a TypeScript website) is where parents
make a Purple Pack (photos, words, recorded voices, instruments, colors, little game rooms) and download it;
the pack goes onto a USB drive and into Purple (purple_tui/, Python, the canvas UI under purple_tui/canvas/).
In each scenario AI testers played a parent persona in Studio, sometimes the parent adding the pack on
Purple, and a kid persona on Purple; a judge then kept only real findings. You get every scenario's kept
findings with screenshots, what each tester said they did, the repo's file list, and docs/AI_UX_BUGS.md
(what's already known).

Write Markdown, starting at a level-2 heading (the title and scenario table are added for you):

## How to use this
A few lines for the agent: verify each issue's repro before changing code (an AI tester can be wrong), read
CLAUDE.md first, and add a test for each
real bug (tests/canvas/, studio tests, or tests/canvas/test_studio_to_purple.py for pack round trips).

## Fix these
Real bugs, most severe first. Merge the same problem seen in several scenarios into one issue (more
scenarios is more evidence). For each, a level-3 heading "N. [high|medium|low] [studio|purple|between] title",
then: **What happens**, **Expected**, **Repro** (numbered steps), **Seen in** (scenarios), **Screenshots**
(the paths given, as-is), **Where to look** (likely files from the file list, marked as a guess, and why),
**Confidence** (high/medium/low, and what would raise it).

## Decide these
Confusions and design questions where a person must choose, not a coder: what tripped testers up, the
evidence, and the options. Keep it short.

## Already known
Findings that match something in docs/AI_UX_BUGS.md that isn't struck through, one line each.

## Coverage
What the sweep exercised well and what it never reached (from the testers' summaries), so the next sweep
can aim there.

Be concrete and plain. Don't pad, don't invent repro steps the evidence doesn't support, and leave out
anything you can't tie to evidence."""


def studio_server() -> subprocess.Popen:
    proc = subprocess.Popen([str(ROOT / "studio" / "node_modules" / ".bin" / "vite"), "--port", str(PORT), "--strictPort", "--logLevel", "error"],
                            cwd=ROOT / "studio")
    insecure = ssl._create_unverified_context()
    for _ in range(120):
        try:
            urllib.request.urlopen(f"https://localhost:{PORT}/", context=insecure, timeout=2)
            return proc
        except OSError:
            if proc.poll() is not None:
                raise RuntimeError(f"Studio's dev server exited (is port {PORT} taken?)")
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError("Studio's dev server didn't start")


def kept(report: dict) -> list[dict]:
    return [f for f in report.get("findings", []) if f.get("keep")]


async def run_one(sc, budget: float, out: Path, url: str, known: list[str]) -> dict:
    out.mkdir(parents=True)
    (out / "known.json").write_text(json.dumps(known, ensure_ascii=False))
    cmd = [sys.executable, str(ROOT / "scripts" / "e2e_ai.py"), "--scenario", sc.name, "--budget", f"{budget:.2f}",
           "--url", url, "--out", str(out), "--no-log", "--known", str(out / "known.json")]
    with open(out / "log.txt", "w") as log:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT,
                                                    env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1"})
        await proc.wait()
    report = out / "report.json"
    if report.exists():
        return json.loads(report.read_text())
    return {"spent": budget, "crashed": f"exit {proc.returncode} before writing a report", "findings": []}


async def sweep(args, out: Path, url: str) -> list[dict]:
    pool = [s for s in SCENARIOS if not args.only or s.name in args.only]
    for s in [s for s in pool if s.skip_reason()]:
        print(f"skip {s.name}: {s.skip_reason()}")
        pool.remove(s)
    spendable = args.budget - SYNTH_RESERVE
    done, running = [], {}

    def spent() -> float:
        return sum(d["report"]["spent"] for d in done)

    def held() -> float:
        return sum(b for _, b in running.values())

    def per_dollar(name: str) -> float:
        reports = [d["report"] for d in done if d["name"] == name]
        return sum(len(kept(r)) for r in reports) / max(sum(r["spent"] for r in reports), 0.01)

    def next_up():
        """Every scenario once, in order; then whichever finished one found the most per dollar, again."""
        busy = {sc.name for (_, sc), _ in running.values()}
        runs = Counter(d["name"] for d in done) + Counter(busy)
        if fresh := [s for s in pool if not runs[s.name]]:
            return fresh[0]
        again = [s for s in pool if s.name not in busy and runs[s.name] < ROUNDS and per_dollar(s.name) > 0]
        return max(again, key=lambda s: per_dollar(s.name), default=None)

    def finished(task):
        (r, sc), budget = running.pop(task)
        report = task.result()
        done.append({"round": r, "name": sc.name, "dir": out / f"{r}-{sc.name}", "report": report})
        print(f"  done {sc.name} (round {r}): ${report['spent']:.2f} of ${budget:.2f}, {len(kept(report))} real finding(s)"
              + (f"  CRASHED, see {out / f'{r}-{sc.name}' / 'log.txt'}" if report.get("crashed") else "")
              + f"; ${spent():.2f} spent, ${held():.2f} held for running scenarios")

    while True:
        while len(running) < args.parallel and (sc := next_up()):
            left = spendable - spent() - held()
            budget = min(sc.budget, args.each or left, left)
            if budget < min(SMALLEST, args.each or SMALLEST):
                break
            r = 1 + sum(d["name"] == sc.name for d in done)
            known = [f["title"] for d in done for f in kept(d["report"])]
            task = asyncio.create_task(run_one(sc, budget, out / f"{r}-{sc.name}", url, known))
            running[task] = ((r, sc), budget)
            print(f"start {sc.name} (round {r}, {sc.model}): up to ${budget:.2f}")
        if not running:
            return done
        for task in (await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED))[0]:
            finished(task)


def gather(done: list[dict], shots: Path) -> list[dict]:
    """Each scenario's kept findings, with their screenshots copied next to the write-up under stable names."""
    shots.mkdir(exist_ok=True)
    runs = []
    for d in done:
        rep, tag = d["report"], f"{d['round']}-{d['name']}"
        found = []
        for f in kept(rep):
            paths = []
            for s in f.get("screenshots", []):
                src = Path(s)
                if src.exists():
                    dst = shots / f"{tag}-{src.parent.name}-{src.name}"
                    shutil.copy2(src, dst)
                    paths.append(str(dst))
            found.append({**f, "screenshots": paths})
        runs.append({"scenario": tag, "spent": rep.get("spent"), "crashed": rep.get("crashed"),
                     "what testers did": {k: (rep.get(k) or {}).get("summary") for k in ("parent in studio", "parent on purple", "kid")},
                     "purple checks failed": [c["what"] for c in (rep.get("purple") or {}).get("checks", []) if not c["ok"]],
                     "findings": found})
    return runs


def file_list() -> str:
    files = subprocess.run(["git", "ls-files", "studio/src", "studio/sdk", "purple_tui", "packs", "tests/canvas"],
                           cwd=ROOT, capture_output=True, text=True).stdout.split()
    return "\n".join(f for f in files if f.endswith((".py", ".ts", ".css", ".html")))


def write_up(client, runs: list[dict]) -> tuple[str, float]:
    from e2e_ai import image, text
    found = [f for r in runs for f in r["findings"]]
    order = {"high": 0, "medium": 1, "low": 2}
    shots = list(dict.fromkeys(s for f in sorted(found, key=lambda f: order[f["severity"]]) for s in f["screenshots"]))[:24]
    content = [text("Scenarios:\n" + json.dumps(runs, indent=1, ensure_ascii=False)),
               text("docs/AI_UX_BUGS.md:\n" + (BUG_LOG_PATH.read_text() if BUG_LOG_PATH.exists() else "(none)")),
               text("Repo files:\n" + file_list())]
    for s in shots:
        content += [text(f"Screenshot {s}:"), image(Path(s).read_bytes())]
    with client.beta.messages.stream(
            model=OPUS, max_tokens=32000, system=SYNTH, messages=[{"role": "user", "content": content}],
            betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default", "output_config": {"effort": "high"}}) as stream:
        resp = stream.get_final_message()
    u = resp.usage
    return "".join(b.text for b in resp.content if b.type == "text"), estimate_cost(u.input_tokens, u.output_tokens, OPUS)


def header(runs: list[dict], out: Path, spent: float) -> str:
    rows = "\n".join(f"| {r['scenario']} | ${r['spent']:.2f} | {len(r['findings'])}{' (crashed)' if r['crashed'] else ''} |" for r in runs)
    return (f"# What the e2e-ai sweep found ({datetime.now():%Y-%m-%d %H:%M})\n\n"
            f"`just e2e-ai-sweep` spent ${spent:.2f} on {len(runs)} scenarios (personas: `scripts/e2e_ai_scenarios.py`). "
            f"Every run's screenshots, logs and report.json are in `{out}`.\n\n"
            f"| Scenario | Spent | Real findings |\n|---|---|---|\n{rows}\n\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--budget", type=float, default=10.0, help="USD for everything, write-up included (default 10)")
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--only", type=lambda s: s.split(","), help="comma-separated scenario names")
    ap.add_argument("--each", type=float, help="cap every scenario at this many USD (a cheap trial run)")
    ap.add_argument("--url", help="a deployed Studio instead of this checkout's")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    if not check_api_key():
        print("Set ANTHROPIC_API_KEY in the environment or .env first.")
        return 1
    out = Path(os.environ.get("TMPDIR", "/tmp")) / "purple-e2e-ai" / f"sweep-{datetime.now():%Y%m%d-%H%M%S}"
    out.mkdir(parents=True)
    print(f"sweep: ${args.budget:.2f}, {args.parallel} at a time; everything in {out}")
    server = None if args.url else studio_server()
    try:
        done = asyncio.run(sweep(args, out, args.url or f"https://localhost:{PORT}/"))
    finally:
        if server:
            server.terminate()
    if all(d["report"].get("crashed") for d in done):
        print("nothing to write up: " + ("every scenario crashed" if done else "no scenario fit in the budget"))
        return 1
    runs = gather(done, out / "shots")
    tested = sum(d["report"]["spent"] for d in done)
    print(f"\nwriting it up ({sum(len(r['findings']) for r in runs)} real findings from {len(runs)} scenarios)")
    body, synth = write_up(anthropic.Anthropic(), runs)
    doc = header(runs, out, tested + synth) + body.strip() + "\n"
    (out / "FIXES.md").write_text(doc)
    FIXES.write_text(doc)
    print(f"spent ${tested + synth:.2f}; the write-up is {FIXES.relative_to(ROOT)} (and {out / 'FIXES.md'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
