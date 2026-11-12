#!/usr/bin/env python3
"""Two AI testers with one Purple Pack between them. A parent uses Purple Studio in headless Chromium
to make something for their kid and downloads it; the file goes onto a pretend USB drive into a headless
Purple, where it's added (by a script, or by the parent in a handoff scenario) and checked
(tests/canvas/pack_journey.py); a kid then plays with it. A judge reads the testers' reports, the checks
and the screenshots, and keeps only what's real, which goes to docs/AI_UX_BUGS.md. Each real bug should
become a test (just e2e-pack, test_studio_to_purple.py).

    just e2e-ai [--budget 10] [--goal "a quiz about our dog"] [--age 5] [--url URL]
    just e2e-ai --scenario breaker [--budget 1.5]     # one of scripts/e2e_ai_scenarios.py
    just e2e-ai-sweep [--budget 10]                   # many scenarios, then one write-up of what to fix

The budget (USD) splits 50% parent, 40% Purple (the kid, and the parent adding the pack in a handoff
scenario), 10% judge. Needs ANTHROPIC_API_KEY (or .env).
Everything lands in $TMPDIR/purple-e2e-ai/<time>/: report.json, studio/ and purple/ screenshots."""

import argparse
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import anthropic  # noqa: E402

from ai_ux_config import append_findings_log, check_api_key, estimate_cost  # noqa: E402
from e2e_ai_scenarios import BY_NAME, OPUS, SONNET, Scenario  # noqa: E402

JUDGE_MODEL = OPUS
KID_MODEL = SONNET  # the kid only looks and presses keys, which Sonnet does fine at a fraction of the price
SPLIT = {"parent": 0.5, "purple": 0.4}  # the rest is left for the judge's one call
HANDOFF_SHARE = 0.3  # of Purple's share, for the parent adding the pack
KEEP_SHOTS = 8  # screenshots a tester still sees; older ones become a line of text, so long sessions stay sharp and cheap
FALLBACKS = {"betas": ["server-side-fallback-2026-07-01"]}
# A headless Purple on a dev machine must never reach these, whatever an AI presses in the grown-up menu.
FORBIDDEN = {"sudo", "systemctl", "reboot", "poweroff", "shutdown", "xrandr", "purple-reboot"}


def tool(name: str, about: str, /, **props) -> dict:
    """A tool whose properties are all strings unless given as a schema; the ones without a default are required."""
    schema = {k: (v if isinstance(v, dict) else {"type": "string", "description": v}) for k, v in props.items()}
    return {"name": name, "description": about, "input_schema": {
        "type": "object", "properties": schema, "required": [k for k, v in schema.items() if "default" not in v]}}


SEVERITY = {"type": "string", "enum": ["low", "medium", "high"]}
REPORTS = [
    tool("report_bug", "Something is clearly broken: missing, wrong, stuck, crashed, lost, or not what the page said would happen.",
         title="One line", severity=SEVERITY, description="What happened and what should have",
         steps={"type": "array", "items": {"type": "string"}, "description": "How to make it happen again"}),
    tool("report_confusion", "Somewhere a real person would get stuck, misunderstand, or give up, even if nothing is broken.",
         title="One line", severity=SEVERITY, what_i_tried="", what_happened="", what_i_expected=""),
    tool("done", "You're finished. Say in plain words what you made or did, and what you meant to but couldn't.", summary=""),
]
N = {"type": "integer", "description": "The thing's number from the latest list"}
PARENT_TOOLS = [
    tool("look", "A screenshot of the page and a numbered list of everything you can click or type in. Other tools only give the list "
         "and what the page says, so look whenever you want to see what changed."),
    tool("click", "Click thing n.", n=N),
    tool("type", "Click into thing n and type text (replacing what's there).", n=N, text="",
         enter={"type": "boolean", "default": False, "description": "Press Enter after"}),
    tool("upload", "Choose a file from your computer for thing n (a file input or a Choose button).", n=N,
         file={"type": "string", "enum": ["photo", "voice", "pack"],
               "description": "photo: backyard.png, a photo from your phone. voice: grandma.wav, a voice memo Grandma sent you. "
                              "pack: the Purple Pack you downloaded last"}),
    tool("select", "Pick an option in dropdown n (a select), by the option's words.", n=N, option=""),
    tool("key", "Press a key on the page: Enter, Escape, Tab, Backspace, Space, ArrowUp/Down/Left/Right, Home, End, "
         "a letter, or a combination like Control+Home.", key=""),
    tool("scroll", "Scroll the page down (or up with a negative number).", dy={"type": "integer", "default": 600}),
    tool("wait", "Wait for something to finish, up to 10 seconds.", seconds={"type": "number", "default": 3}),
    tool("reload", "Reload the page, as if you closed the tab and came back."),
    tool("back", "The browser's back button."),
    *REPORTS,
]
PURPLE_TOOLS = [
    tool("look", "See the screen."),
    tool("press", "Press one key: a letter or digit, or enter, escape, space, backspace, tab, up, down, left, right.",
         key="", hold_seconds={"type": "number", "default": 0, "description": "Hold the key down this long"}),
    tool("type", "Type some letters, one key after another.", text=""),
    *REPORTS,
]

FAIR = """Report bugs and confusions the moment you meet them, each once, with what you expected instead. Don't
report things just because they're different from what you're used to, and don't guess about what you can't
see. When something looks off but you aren't sure it's wrong (a picture smaller than you expected, a word
missing), report it as a confusion and say you're unsure; don't only mention it when you call done. You have
plenty of time: there's no prize for finishing fast, and the more you really try, the better."""

PARENT = """You are the parent of a {age}-year-old, trying Purple Studio for the first time. Purple Computer is a
laptop for kids, and Studio is the website where parents make things for it.

{parent}

What you want to make: {goal}

You have a photo on your computer (backyard.png), a voice memo Grandma sent you (grandma.wav), and a microphone. Look at the page and work out what to do
the way a real parent would. The little Purple preview restarts for a moment after each change you make: a
dark cover with "Updating Purple Computer" fades over it, and keys typed then are lost. That's expected, so
wait for it to clear (the wait tool) before typing into the preview, and don't report the cover itself. When it's ready, download your Purple Pack, then call done. """ + FAIR

HANDOFF = """{who}

The Purple Pack ("{summary}") is on a USB drive you just plugged into the kid's Purple Computer: a laptop for
kids with only a keyboard, no mouse. The card that came with it says: to add things from a USB drive, plug
it in and follow the screen; hold Esc for a couple of seconds for the grown-up menu.

Get what's on the drive onto Purple and ready for the kid, then look around the grown-up menu for anything
about it. Call done when the kid could use it. """ + FAIR
PARENT_ADDS = "You are the parent of a {age}-year-old. You made this Purple Pack in Purple Studio.\n\n{parent}"

KID = """You are {age} years old, sitting at a Purple Computer: a laptop for kids with only a keyboard, no mouse.
Your parent just put something new on it for you and said: "{summary}"

{kid}

Esc shows the rooms you can go to. Report a bug when something looks broken: a picture missing, the wrong
word, the screen stuck, or what your parent made not being there. You can't hear, so only report a sound
when the screen shows something should be playing. Report a confusion when a kid your age would get stuck.
Call done when you've played with everything. """ + FAIR

ALREADY = """

Other testers already reported these, so don't spend time finding or reporting them again:
{titles}"""

NUDGE = ("You still have plenty of time. Look back at what you set out to do: is there anything you haven't tried, "
         "or something worth checking again? Do that first, then call done.")

JUDGE = """AI testers just used Purple Computer end to end: a parent in Purple Studio (the website) making a Purple
Pack, sometimes the parent adding it on Purple, then a kid on that Purple. Each played a persona described in
the evidence. You get their reports, what Purple's own automatic checks found, what Purple's screens said
while the pack was added, the pack's files, Studio's browser errors, and screenshots.

Keep only findings that are real and worth a developer's time. Not real: a tester misreading a screenshot,
an AI's guess about what a kid or parent would feel with no evidence on screen, a tester looking in the wrong
place, a missing sound (the testers can't hear), and duplicates. Real: every failed automatic check, every
browser error that comes from Studio's own code, and anything the screenshots show broken. A persona that
breaks things on purpose finds real bugs when Studio or Purple mishandles what it typed. A confusion is real
when the screenshot shows the cause (unclear words, something hidden or cut off), not when the tester was
just slow. Say where each finding lives: studio, purple, or between (the pack, the USB drive, the handoff).
Merge duplicates into one finding, and list the screenshot paths that show it."""

VERDICT = {"type": "object", "additionalProperties": False, "required": ["findings"], "properties": {"findings": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
                               "required": ["keep", "title", "severity", "where", "description", "steps", "why", "screenshots"],
                               "properties": {"keep": {"type": "boolean"}, "title": {"type": "string"},
                                              "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                                              "where": {"type": "string", "enum": ["studio", "purple", "between"]},
                                              "description": {"type": "string"},
                                              "steps": {"type": "array", "items": {"type": "string"}},
                                              "why": {"type": "string"},
                                              "screenshots": {"type": "array", "items": {"type": "string"}}}}}}}


def image(png: bytes | str) -> dict:
    data = png if isinstance(png, str) else base64.standard_b64encode(png).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}


def text(s: str) -> dict:
    return {"type": "text", "text": s}


def without_images(blocks: list) -> list:
    return [text("(an older screenshot)") if b.get("type") == "image" else
            {**b, "content": without_images(b["content"])} if b.get("type") == "tool_result" and isinstance(b.get("content"), list) else b
            for b in blocks]


class Tester:
    """One AI tester's loop: tool calls until it calls done or spends its budget."""

    def __init__(self, client, label: str, system: str, tools: list, budget: float, model: str = SONNET):
        self.client, self.label, self.system, self.tools, self.budget, self.model = client, label, system, tools, budget, model
        self.messages, self.spent, self.summary, self.nudged, self.last_words = [], 0.0, None, False, ""
        self.bugs, self.confusions, self.steps, self.errors = [], [], [], []
        self.last_shot: Path | None = None

    def _call(self):
        return self.client.beta.messages.create(
            model=self.model, max_tokens=8000, system=self.system, tools=self.tools, messages=self.messages, **FALLBACKS,
            extra_body={"fallbacks": "default", "cache_control": {"type": "ephemeral"}, "output_config": {"effort": "medium"}})

    def _forget_old_shots(self):
        """Drops old screenshots in batches, so the prompt cache only starts over now and then."""
        users = [m for m in self.messages if m["role"] == "user"]
        if sum(json.dumps(m["content"]).count('"type": "image"') for m in users) > 2 * KEEP_SHOTS:
            for m in users[:-KEEP_SHOTS]:
                m["content"] = without_images(m["content"])

    async def run(self, first: list, act, can_finish=lambda: None) -> None:
        self.messages.append({"role": "user", "content": first})
        while self.summary is None and self.spent < self.budget:
            self._forget_old_shots()
            resp = await asyncio.to_thread(self._call)
            u = resp.usage
            self.spent += estimate_cost(u.input_tokens, u.output_tokens, self.model,
                                        u.cache_creation_input_tokens or 0, u.cache_read_input_tokens or 0)
            self.messages.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in resp.content]})
            uses = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason == "refusal" or not uses:
                print(f"  {self.label}: stopped ({resp.stop_reason})")
                return
            results = [{"type": "tool_result", "tool_use_id": b.id, **await self._use(b.name, b.input, act, can_finish)} for b in uses]
            if self.spent > 0.8 * self.budget:
                why_not = can_finish()
                results.append(text("You're almost out of time: " + (f"{why_not} Do that now, then call done." if why_not else "wrap up, and call done.")))
            self.messages.append({"role": "user", "content": results})

    def _finish(self, args: dict, can_finish) -> dict:
        self.last_words = args.get("summary", "")
        why_not = can_finish()
        if not why_not and not self.nudged and self.spent < 0.5 * self.budget:
            self.nudged, why_not = True, NUDGE
        if why_not:
            return {"content": [text(why_not)], "is_error": True}
        self.summary = args.get("summary", "")
        return {"content": [text("Thanks.")]}

    async def _use(self, name: str, args: dict, act, can_finish) -> dict:
        self.steps.append({"tool": name, "input": args})
        print(f"  {self.label} ${self.spent:.2f}: {name} {json.dumps(args, ensure_ascii=False)[:100]}")
        if name in ("report_bug", "report_confusion"):
            found = {**args, "steps": args.get("steps", []), "screenshot": str(self.last_shot or "")}
            (self.bugs if name == "report_bug" else self.confusions).append(found)
            return {"content": [text("Noted.")]}
        if name == "done":
            return self._finish(args, can_finish)
        try:
            return {"content": await act(name, args)}
        except Exception as e:  # the tester's mistake (a stale number, a bad key) or a real crash: told back, and shown to the judge
            self.errors.append({"step": len(self.steps), "tool": name, "input": args, "error": f"{type(e).__name__}: {e}"})
            return {"content": [text(f"That didn't work: {e}")], "is_error": True}

    def report(self) -> dict:
        return {"spent": round(self.spent, 4), "summary": self.summary or self.last_words, "bugs": self.bugs, "confusions": self.confusions,
                "errors": self.errors, "steps": self.steps}


class Browser:
    """studio/scripts/browser-bridge.ts, one request and reply per line."""

    def __init__(self, out: Path, url: str | None, viewport: str = ""):
        self.out, self.errors = out, []
        cmd = [str(ROOT / "studio" / "node_modules" / ".bin" / "vite-node"), "scripts/browser-bridge.ts", str(out), *([url] if url else [])]
        env = {**os.environ, **({"E2E_VIEWPORT": viewport} if viewport else {})}
        self.proc = subprocess.Popen(cmd, cwd=ROOT / "studio", stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env)
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
        self.errors += reply.get("errors") or []
        if not reply.get("ok"):
            raise RuntimeError(reply.get("error"))
        return reply

    async def act(self, name: str, args: dict) -> list:
        reply = self.ask(name, **args)
        said = "".join(f"\nThe page says: {s}" for s in reply.get("says", []))
        page = [text(f"Page: {reply['url']}\n" + "\n".join(reply["things"]) + said + (f"\nPage errors: {reply['errors']}" if reply["errors"] else ""))]
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


def guard_subprocesses() -> None:
    real = subprocess.Popen

    class Guarded(real):
        def __init__(self, args, *a, **kw):
            words = (args if isinstance(args, str) else " ".join(map(str, args))).split()
            if any(Path(w).name in FORBIDDEN for w in words[:2]):
                raise PermissionError(f"e2e-ai: not running {' '.join(words[:3])} on this machine")
            super().__init__(args, *a, **kw)
    subprocess.Popen = Guarded


@dataclass
class Run:
    """What one scenario has done so far, filled in as it goes, so a crash still leaves a report and the real spend."""
    testers: dict = field(default_factory=lambda: dict.fromkeys(("parent in studio", "parent on purple", "kid")))
    page_errors: list = field(default_factory=list)
    purple: dict = field(default_factory=dict)
    pack: Path | None = None
    crash: str | None = None
    known: list = field(default_factory=list)  # titles earlier runs in this sweep already found

    def tester(self, who: str, client, sc: Scenario, system: str, tools: list, budget: float) -> Tester:
        if self.known:
            system += ALREADY.format(titles="\n".join(f"- {t}" for t in self.known))
        self.testers[who] = Tester(client, who, system, tools, budget, KID_MODEL if who == "kid" else sc.model)
        return self.testers[who]

    @property
    def spent(self) -> float:
        return sum(t.spent for t in self.testers.values() if t)


async def parent_phase(client, sc: Scenario, args, out: Path, budget: float, run: Run) -> None:
    print(f"parent: in Studio (up to ${budget:.2f})")
    browser = Browser(out, args.url, sc.viewport)
    browser.errors = run.page_errors
    tester = run.tester("parent in studio", client, sc, PARENT.format(age=sc.age, goal=sc.goal, parent=sc.parent), PARENT_TOOLS, budget)

    async def act(name, a):
        content = await browser.act(name, a)
        tester.last_shot = browser.last_shot
        return content
    try:
        first = await act("look", {})
        await tester.run([text("Studio is open in your browser."), *first], act,
                         lambda: None if browser.downloads() else "You haven't downloaded your Purple Pack yet.")
        packs = [Path(p) for p in browser.downloads() if p.endswith(".purplepack")]
        run.pack = max(packs, key=lambda p: p.stat().st_mtime) if packs else None
    finally:
        browser.close()


def purple_act(app, shots: Path, tester: Tester, prefix: str, screens: list):
    """A tester's keys on the headless Purple; each answer is a screenshot, and each new screen's words are kept."""
    from tests.canvas.pack_journey import said
    from tests.canvas.real_purple import replay
    from purple_tui.canvas.harness import type_text
    n = 0

    async def act(name, a):
        nonlocal n
        if name == "press":
            hold = float(a.get("hold_seconds") or 0)
            await replay(app, [(a["key"], hold) if hold else a["key"]])
        elif name == "type":
            await type_text(app, a["text"])
        await asyncio.sleep(0.4)
        if app.top is not None and (not screens or screens[-1] != said(app.top)):
            screens.append(said(app.top))
        n += 1
        tester.last_shot = shots / f"{prefix}-{n:03}.png"
        app.screenshot(str(tester.last_shot))
        return [image(tester.last_shot.read_bytes())]
    return act


async def handoff(client, sc: Scenario, app, drive: Path, summary: str, shots: Path, budget: float, run: Run) -> None:
    from purple_tui import pack_arrivals
    from purple_tui.usb_updater import update_from
    print(f"parent: adding the pack on Purple (up to ${budget:.2f})")
    update_from(drive, pack_arrivals.WAITING_DIR)
    app._check_pack_arrivals()
    tester = run.tester("parent on purple", client, sc, HANDOFF.format(summary=summary, who=sc.adder or PARENT_ADDS.format(age=sc.age, parent=sc.parent)), PURPLE_TOOLS, budget)
    act = purple_act(app, shots, tester, "handoff", run.purple["screens"])
    await tester.run([text("Here's the screen, right after you plugged in the USB drive."), *await act("look", {})], act)
    for _ in range(6):
        if app.top is None:
            break
        app.top.close()


async def purple_phase(client, sc: Scenario, out: Path, summary: str, budget: float, run: Run) -> None:
    from purple_tui import settings
    from purple_tui.canvas.harness import make_app
    from tests.canvas.pack_journey import check, deliver, isolate, read_pack
    guard_subprocesses()
    isolate(out / "home")
    drive = out / "drive"
    drive.mkdir()
    shutil.copy2(run.pack, drive / run.pack.name)
    app = make_app()
    shots = out / "purple"
    shots.mkdir(parents=True, exist_ok=True)
    run.purple.update(screens=[], added_by="the parent, by hand" if sc.handoff else "a script saying yes to everything")
    if sc.handoff:
        await handoff(client, sc, app, drive, summary, shots, budget * HANDOFF_SHARE, run)
        budget -= run.testers["parent on purple"].spent
    else:
        run.purple["screens"] = await deliver(app, drive, shots)
    manifest = json.loads(read_pack(run.pack)["manifest.json"])
    added = manifest["id"] in settings.get_packs_added()
    run.purple["checks"] = ([c.__dict__ for c in await check(app, run.pack, shots)] if added else
                            [{"ok": False, "what": f'"{manifest["name"]}" was never added to Purple'}])
    checks = run.purple["checks"]
    app.action_switch_room(app.kid_rooms[0])
    print(f"kid: on Purple (up to ${budget:.2f}); the pack's checks: {sum(c['ok'] for c in checks)}/{len(checks)} ok")
    kid = run.tester("kid", client, sc, KID.format(age=sc.age, summary=summary or "I made you something!", kid=sc.kid), PURPLE_TOOLS, budget)
    act = purple_act(app, shots, kid, "kid", run.purple["screens"])
    try:
        await kid.run([text("Here's the screen."), *await act("look", {})], act)
    finally:
        for room in app._family_rooms.values():
            room._stop()


def judge(client, sc: Scenario, run: Run, known: list[str]) -> tuple[list, float]:
    """known: what's off because of how this run was set up, not because of Studio or Purple."""
    from tests.canvas.pack_journey import read_pack
    found = [f for t in run.testers.values() if t for f in t.bugs + t.confusions]
    shots = list(dict.fromkeys(f["screenshot"] for f in found if f.get("screenshot")))[:12]
    evidence = {
        "expected in this test setup, so not findings": known,
        "scenario": {"name": sc.name, "parent persona": sc.parent, "who adds the pack on Purple": sc.adder or "the parent", "goal": sc.goal, "kid persona": sc.kid, "age": sc.age,
                     "studio window": sc.viewport or "1280x900"},
        **{who: {"summary": t.summary or t.last_words, "steps taken": len(t.steps), "bugs": t.bugs, "confusions": t.confusions,
                 "errors when it acted (its own mistakes, or Studio or Purple crashing)": t.errors[:20]}
           for who, t in run.testers.items() if t},
        "pack": sorted(read_pack(run.pack)) if run.pack else "The parent never downloaded a Purple Pack.",
        "studio browser errors": list(dict.fromkeys(run.page_errors))[:30],
        "how the pack got on Purple": run.purple.get("added_by"),
        "purple checks": run.purple.get("checks", []), "purple screens seen": run.purple.get("screens", []),
        "the run crashed (a test harness bug, or Studio or Purple crashing)": run.crash[-3000:] if run.crash else None,
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


async def play(client, sc: Scenario, args, out: Path, budget: float, run: Run) -> None:
    await parent_phase(client, sc, args, out, budget * SPLIT["parent"], run)
    if not run.pack:
        print("parent: no Purple Pack was downloaded, so there's nothing for the kid")
        return
    summary = run.testers["parent in studio"].summary or ""
    await purple_phase(client, sc, out, summary, budget * SPLIT["purple"], run)


async def main_async(sc: Scenario, args) -> int:
    out = Path(args.out) if args.out else Path(os.environ.get("TMPDIR", "/tmp")) / "purple-e2e-ai" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic()
    known = []
    if not args.url and not (ROOT / "studio" / ".cache" / "purple.zip").exists():
        known.append("Studio's live Purple preview can't start (\"couldn't start in this browser\", pyodide wheel errors): "
                     "this checkout hasn't run just studio-bundle.")
        print(f"note: {known[-1]} Run it first to test the preview too.")
    budget = args.budget or sc.budget
    print(f"scenario {sc.name}: ${budget:.2f}, {sc.model}")
    run = Run(known=json.loads(Path(args.known).read_text()) if args.known else [])
    try:
        await play(client, sc, args, out, budget, run)
    except Exception:
        run.crash = traceback.format_exc()
        print(run.crash)
    found = any(t and (t.bugs or t.confusions) for t in run.testers.values()) or run.crash and run.spent
    findings, judged = judge(client, sc, run, known) if found else ([], 0.0)
    kept = [f for f in findings if f["keep"]]
    if kept and not args.no_log:
        append_findings_log([{**f, "title": f"[{f['where']}] {f['title']}", "description": f"{f['description']}\n\n{f['why']}"} for f in kept],
                            [], f"e2e-ai: {sc.name}", f"{sc.model}, judged by {JUDGE_MODEL}")
    spent = run.spent + judged
    report = {"scenario": asdict(sc), "budget": budget, **{k: t.report() if t else None for k, t in run.testers.items()},
              "purple": run.purple, "studio browser errors": run.page_errors, "crashed": run.crash,
              "findings": findings, "spent": round(spent, 4)}
    (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"\n{len(kept)} real finding(s) of {len(findings)}" + (" (added to docs/AI_UX_BUGS.md)" if kept and not args.no_log else ""))
    for f in kept:
        print(f"  [{f['severity']}] {f['where']}: {f['title']}")
    print(f"spent ${spent:.2f}; everything in {out}")
    return 1 if run.crash else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--scenario", choices=sorted(BY_NAME), help="a persona pair from scripts/e2e_ai_scenarios.py")
    ap.add_argument("--budget", type=float, help="USD for the whole run (default 10, or the scenario's)")
    ap.add_argument("--goal", default="something personal for your kid: your family's words and a photo, and a room to play in")
    ap.add_argument("--age", type=int, default=5)
    ap.add_argument("--url", help="a deployed Studio instead of this checkout's")
    ap.add_argument("--out", help="where this run's files go (default $TMPDIR/purple-e2e-ai/<time>)")
    ap.add_argument("--known", help="a JSON list of finding titles already reported, so testers skip them")
    ap.add_argument("--no-log", action="store_true", help="leave docs/AI_UX_BUGS.md alone (the sweep writes its own report)")
    args = ap.parse_args()
    if not check_api_key():
        print("Set ANTHROPIC_API_KEY in the environment or .env first.")
        return 1
    sc = BY_NAME[args.scenario] if args.scenario else Scenario(
        "custom", parent="You are not technical and you are a bit busy.", goal=args.goal, age=args.age, budget=10.0,
        kid=f"Try to find it and play with it the way a {args.age}-year-old would.")
    if why := sc.skip_reason():
        print(f"not running {sc.name}: {why}")
        return 1
    return asyncio.run(main_async(sc, args))


if __name__ == "__main__":
    sys.exit(main())
