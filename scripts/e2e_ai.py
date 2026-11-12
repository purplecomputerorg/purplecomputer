#!/usr/bin/env python3
"""Two AI testers with one Purple Pack between them. A parent uses Purple Studio in headless Chromium
to make something for their kid and downloads it; the file goes onto a pretend USB drive into a headless
Purple, where it's added and checked (tests/canvas/pack_journey.py); a kid then plays with it. A judge
reads both testers' reports, the checks and the screenshots, and keeps only what's real, which goes to
docs/AI_UX_BUGS.md. Each real bug should become a test (just e2e-pack, test_studio_to_purple.py).

    just e2e-ai [--budget 10] [--goal "a quiz about our dog"] [--age 5] [--url URL]

The budget (USD) splits 40% parent, 50% kid, 10% judge. Needs ANTHROPIC_API_KEY (or .env).
Everything lands in $TMPDIR/purple-e2e-ai/<time>/: report.json, studio/ and purple/ screenshots."""

import argparse
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import anthropic  # noqa: E402

from ai_ux_config import append_findings_log, check_api_key, estimate_cost  # noqa: E402

TESTER_MODEL, JUDGE_MODEL = "claude-sonnet-5-5", "claude-opus-5-5"
SPLIT = {"parent": 0.4, "kid": 0.5}  # the rest is left for the judge's one call
FALLBACKS = {"betas": ["server-side-fallback-2026-07-01"]}


def tool(name: str, about: str, /, **props) -> dict:
    """A tool whose properties are all strings unless given as a schema; the ones without a default are required."""
    schema = {k: (v if isinstance(v, dict) else {"type": "string", "description": v}) for k, v in props.items()}
    return {"name": name, "description": about, "input_schema": {
        "type": "object", "properties": schema, "required": [k for k, v in schema.items() if "default" not in v]}}


SEVERITY = {"type": "string", "enum": ["low", "medium", "high"]}
REPORTS = [
    tool("report_bug", "Something is clearly broken: missing, wrong, stuck, crashed, or not what the page said would happen.",
         title="One line", severity=SEVERITY, description="What happened and what should have",
         steps={"type": "array", "items": {"type": "string"}, "description": "How to make it happen again"}),
    tool("report_confusion", "Somewhere a real person would get stuck, misunderstand, or give up, even if nothing is broken.",
         title="One line", severity=SEVERITY, what_i_tried="", what_happened="", what_i_expected=""),
    tool("done", "You're finished. Say in plain words what you made or did.", summary=""),
]
N = {"type": "integer", "description": "The thing's number from the latest list"}
PARENT_TOOLS = [
    tool("look", "A screenshot of the page and a numbered list of everything you can click or type in."),
    tool("click", "Click thing n.", n=N),
    tool("type", "Click into thing n and type text (replacing what's there).", n=N, text="",
         enter={"type": "boolean", "default": False, "description": "Press Enter after"}),
    tool("upload", "Choose a file from your computer for thing n (a file input or a Choose button).", n=N,
         file={"type": "string", "enum": ["photo"], "description": "photo: backyard.png, a photo from your phone"}),
    tool("key", "Press a key on the page, like Enter, Escape or Tab.", key=""),
    tool("scroll", "Scroll the page down (or up with a negative number).", dy={"type": "integer", "default": 600}),
    tool("wait", "Wait for something to finish, up to 10 seconds.", seconds={"type": "number", "default": 3}),
    *REPORTS,
]
KID_TOOLS = [
    tool("look", "See the screen."),
    tool("press", "Press one key: a letter or digit, or enter, escape, space, backspace, tab, up, down, left, right.",
         key="", hold_seconds={"type": "number", "default": 0, "description": "Hold the key down this long"}),
    tool("type", "Type some letters, one key after another.", text=""),
    *REPORTS,
]

PARENT = """You are the parent of a {age}-year-old, trying Purple Studio for the first time. Purple Computer is a
laptop for kids, and Studio is the website where parents make things for it. You are not technical and you
are a bit busy. What you want to make: {goal}

You have a photo on your computer (backyard.png) and a microphone. Look at the page, work out what to do the
way a real parent would, and make it. When it's ready, download your Purple Pack, then call done with what
you made in plain words. Report bugs and confusions as you meet them, each once. Don't report things just
because they're different from other websites; report what actually gets in your way."""

KID = """You are {age} years old, sitting at a Purple Computer: a laptop for kids with only a keyboard, no mouse.
Your parent just put something new on it for you and said: "{summary}"

Try to find it and play with it the way a {age}-year-old would. Esc shows the rooms you can go to.
Report a bug when something looks broken: a picture missing, the wrong word, a sound that should be there
and isn't, the screen stuck, or what your parent made not being there. Report a confusion when a kid your
age would get stuck. Call done when you've played with everything your parent made."""

JUDGE = """Two AI testers just used Purple Computer end to end: a parent in Purple Studio (the website) making a
Purple Pack, then a kid on the Purple it was added to. You get their reports, what Purple's own automatic
checks found in the pack, what each screen said while the pack was added, and screenshots.

Keep only findings that are real and worth a developer's time: the tester's misreading of a screenshot,
an AI's guess about what a kid or parent would feel with no evidence, and duplicates are not. Every failed
automatic check is real: keep it. Say where each finding lives: studio, purple, or between (the pack, the
USB drive, the handoff). Merge duplicates into one finding."""

VERDICT = {"type": "object", "additionalProperties": False, "required": ["findings"], "properties": {"findings": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
                               "required": ["keep", "title", "severity", "where", "description", "steps", "why"],
                               "properties": {"keep": {"type": "boolean"}, "title": {"type": "string"},
                                              "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                                              "where": {"type": "string", "enum": ["studio", "purple", "between"]},
                                              "description": {"type": "string"},
                                              "steps": {"type": "array", "items": {"type": "string"}},
                                              "why": {"type": "string"}}}}}}


def image(png: bytes | str) -> dict:
    data = png if isinstance(png, str) else base64.standard_b64encode(png).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}


def text(s: str) -> dict:
    return {"type": "text", "text": s}


class Tester:
    """One AI tester's loop: tool calls until it calls done or spends its budget."""

    def __init__(self, client, label: str, system: str, tools: list, budget: float):
        self.client, self.label, self.system, self.tools, self.budget = client, label, system, tools, budget
        self.messages, self.spent, self.summary = [], 0.0, None
        self.bugs, self.confusions, self.steps = [], [], []
        self.last_shot: Path | None = None

    def _call(self):
        return self.client.beta.messages.create(
            model=TESTER_MODEL, max_tokens=8000, system=self.system, tools=self.tools, messages=self.messages, **FALLBACKS,
            extra_body={"fallbacks": "default", "cache_control": {"type": "ephemeral"}, "output_config": {"effort": "medium"}})

    async def run(self, first: list, act, can_finish=lambda: None) -> None:
        self.messages.append({"role": "user", "content": first})
        while self.summary is None and self.spent < self.budget:
            resp = await asyncio.to_thread(self._call)
            u = resp.usage
            self.spent += estimate_cost(u.input_tokens, u.output_tokens, TESTER_MODEL,
                                        u.cache_creation_input_tokens or 0, u.cache_read_input_tokens or 0)
            self.messages.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in resp.content]})
            uses = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason == "refusal" or not uses:
                print(f"  {self.label}: stopped ({resp.stop_reason})")
                return
            results = [{"type": "tool_result", "tool_use_id": b.id, **await self._use(b.name, b.input, act, can_finish)} for b in uses]
            if self.spent > 0.8 * self.budget:
                results.append(text("You're almost out of time: wrap up, and call done."))
            self.messages.append({"role": "user", "content": results})

    async def _use(self, name: str, args: dict, act, can_finish) -> dict:
        self.steps.append({"tool": name, "input": args})
        print(f"  {self.label} ${self.spent:.2f}: {name} {json.dumps(args, ensure_ascii=False)[:100]}")
        if name in ("report_bug", "report_confusion"):
            found = {**args, "steps": args.get("steps", []), "screenshot": str(self.last_shot or "")}
            (self.bugs if name == "report_bug" else self.confusions).append(found)
            return {"content": [text("Noted.")]}
        if name == "done":
            why_not = can_finish()
            if why_not:
                return {"content": [text(why_not)], "is_error": True}
            self.summary = args.get("summary", "")
            return {"content": [text("Thanks.")]}
        try:
            return {"content": await act(name, args)}
        except Exception as e:  # the tester's mistake (a stale number, a bad key) is told back, not fatal
            return {"content": [text(f"That didn't work: {e}")], "is_error": True}

    def report(self) -> dict:
        return {"spent": round(self.spent, 4), "summary": self.summary, "bugs": self.bugs, "confusions": self.confusions, "steps": self.steps}


class Browser:
    """studio/scripts/browser-bridge.ts, one request and reply per line."""

    def __init__(self, out: Path, url: str | None):
        self.out = out
        cmd = [str(ROOT / "studio" / "node_modules" / ".bin" / "vite-node"), "scripts/browser-bridge.ts", str(out), *([url] if url else [])]
        self.proc = subprocess.Popen(cmd, cwd=ROOT / "studio", stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self._read()
        self.n, self.last_shot = 0, None

    def _read(self) -> dict:
        for line in self.proc.stdout:
            if line.startswith("@@"):
                return json.loads(line[2:])
        raise RuntimeError("Studio's browser stopped")

    def ask(self, op: str, **args) -> dict:
        self.proc.stdin.write(json.dumps({"op": op, **args}) + "\n")
        self.proc.stdin.flush()
        reply = self._read()
        if not reply.get("ok"):
            raise RuntimeError(reply.get("error"))
        return reply

    async def act(self, name: str, args: dict) -> list:
        reply = self.ask(name, **args)
        page = [text(f"Page: {reply['url']}\n" + "\n".join(reply["things"]) + (f"\nPage errors: {reply['errors']}" if reply["errors"] else ""))]
        if "shot" not in reply:
            return page
        self.n += 1
        shot = self.out / "studio" / f"{self.n:03}.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(base64.b64decode(reply["shot"]))
        self.last_shot = shot
        return [image(reply["shot"]), *page]

    def downloads(self) -> list[str]:
        return self.ask("downloads")["files"]

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(30)


async def parent_phase(client, args, out: Path, budget: float) -> tuple[Tester, Path | None]:
    print(f"parent: in Studio (up to ${budget:.2f})")
    browser = Browser(out, args.url)
    tester = Tester(client, "parent", PARENT.format(age=args.age, goal=args.goal), PARENT_TOOLS, budget)

    async def act(name, a):
        content = await browser.act(name, a)
        tester.last_shot = browser.last_shot
        return content
    try:
        first = await act("look", {})
        await tester.run([text("Studio is open in your browser."), *first], act,
                         lambda: None if browser.downloads() else "You haven't downloaded your Purple Pack yet.")
        packs = [Path(p) for p in browser.downloads() if p.endswith(".purplepack")]
    finally:
        browser.close()
    return tester, max(packs, key=lambda p: p.stat().st_mtime) if packs else None


async def kid_phase(client, args, out: Path, pack: Path, summary: str, budget: float) -> tuple[Tester, dict]:
    from purple_tui.canvas.harness import make_app, type_text
    from tests.canvas.pack_journey import check, deliver, isolate
    from tests.canvas.real_purple import replay
    isolate(out / "home")
    drive = out / "drive"
    drive.mkdir()
    shutil.copy2(pack, drive / pack.name)
    app = make_app()
    shots = out / "purple"
    screens = await deliver(app, drive, shots)
    checks = [c.__dict__ for c in await check(app, pack, shots)]
    app.action_switch_room(app.kid_rooms[0])
    print(f"kid: on Purple (up to ${budget:.2f}); the pack's checks: {sum(c['ok'] for c in checks)}/{len(checks)} ok")
    tester = Tester(client, "kid", KID.format(age=args.age, summary=summary or "I made you something!"), KID_TOOLS, budget)
    n = 0

    async def act(name, a):
        nonlocal n
        if name == "press":
            hold = float(a.get("hold_seconds") or 0)
            await replay(app, [(a["key"], hold) if hold else a["key"]])
        elif name == "type":
            await type_text(app, a["text"])
        await asyncio.sleep(0.4)
        n += 1
        tester.last_shot = shots / f"kid-{n:03}.png"
        app.screenshot(str(tester.last_shot))
        return [image(tester.last_shot.read_bytes())]
    try:
        await tester.run([text("Here's the screen."), *await act("look", {})], act)
    finally:
        for room in app._family_rooms.values():
            room._stop()
    return tester, {"screens": screens, "checks": checks}


def judge(client, parent: Tester, kid: Tester | None, purple: dict, pack: Path | None, known: list[str]) -> tuple[list, float]:
    """known: what's off because of how this run was set up, not because of Studio or Purple."""
    findings = [*parent.bugs, *parent.confusions, *((kid.bugs + kid.confusions) if kid else [])]
    shots = [f["screenshot"] for f in findings if f.get("screenshot")][:8]
    evidence = {
        "expected in this test setup, so not findings": known,
        "parent": {"what they made": parent.summary, "bugs": parent.bugs, "confusions": parent.confusions},
        "pack": str(pack) if pack else "The parent never downloaded a Purple Pack.",
        "purple checks": purple.get("checks", []), "screens while adding": purple.get("screens", []),
        "kid": {"bugs": kid.bugs, "confusions": kid.confusions, "summary": kid.summary} if kid else None,
    }
    content = [text(json.dumps(evidence, indent=1, ensure_ascii=False))]
    for s in shots:
        content += [text(f"Screenshot {s}:"), image(Path(s).read_bytes())]
    resp = client.beta.messages.create(
        model=JUDGE_MODEL, max_tokens=16000, system=JUDGE, messages=[{"role": "user", "content": content}], **FALLBACKS,
        extra_body={"fallbacks": "default", "output_config": {"effort": "high", "format": {"type": "json_schema", "schema": VERDICT}}})
    u = resp.usage
    spent = estimate_cost(u.input_tokens, u.output_tokens, JUDGE_MODEL)
    if resp.stop_reason == "refusal":
        return [], spent
    body = next(b.text for b in resp.content if b.type == "text")
    return json.loads(body)["findings"], spent


async def main_async(args) -> int:
    out = Path(os.environ.get("TMPDIR", "/tmp")) / "purple-e2e-ai" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    client = anthropic.Anthropic()
    known = []
    if not args.url and not (ROOT / "studio" / ".cache" / "purple.zip").exists():
        known.append("Studio's live Purple preview can't start (\"couldn't start in this browser\", pyodide wheel errors): "
                     "this checkout hasn't run just studio-bundle.")
        print(f"note: {known[-1]} Run it first to test the preview too.")
    parent, pack = await parent_phase(client, args, out, args.budget * SPLIT["parent"])
    kid, purple = None, {}
    if pack:
        kid, purple = await kid_phase(client, args, out, pack, parent.summary or "", args.budget * SPLIT["kid"])
    else:
        print("parent: no Purple Pack was downloaded, so there's nothing for the kid")
    findings, judged = judge(client, parent, kid, purple, pack, known)
    kept = [f for f in findings if f["keep"]]
    if kept:
        append_findings_log([{**f, "title": f"[{f['where']}] {f['title']}", "description": f"{f['description']}\n\n{f['why']}"} for f in kept],
                            [], "e2e-ai: Studio to Purple", f"{TESTER_MODEL}, judged by {JUDGE_MODEL}")
    spent = parent.spent + (kid.spent if kid else 0) + judged
    report = {"parent": parent.report(), "kid": kid.report() if kid else None, "purple": purple, "findings": findings, "spent": round(spent, 4)}
    (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"\n{len(kept)} real finding(s) of {len(findings)}" + (" (added to docs/AI_UX_BUGS.md)" if kept else ""))
    for f in kept:
        print(f"  [{f['severity']}] {f['where']}: {f['title']}")
    print(f"spent ${spent:.2f}; everything in {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--budget", type=float, default=10.0, help="USD for the whole run (default 10)")
    ap.add_argument("--goal", default="something personal for your kid: your family's words and a photo, and maybe a room to play in")
    ap.add_argument("--age", type=int, default=5)
    ap.add_argument("--url", help="a deployed Studio instead of this checkout's")
    args = ap.parse_args()
    if not check_api_key():
        print("Set ANTHROPIC_API_KEY in the environment or .env first.")
        return 1
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
