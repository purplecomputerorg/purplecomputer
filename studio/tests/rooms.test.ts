import { describe, expect, it } from "vitest";
import { loadPyodide } from "pyodide";
import purpleSource from "../../purple_tui/roomkit/purple.py?raw";
import runnerSource from "../../purple_tui/roomkit/runner.py?raw";
import guest from "../src/rooms/guest.py?raw";
import { EXAMPLES, TEMPLATES, quizSource, soundboardSource } from "../src/examples";
import { blankRules, rulesSource, type Rule } from "../src/rules";

type Msg = Record<string, unknown>;
type Shape = [string, ...unknown[]];
const END = "end of the scripted events";

// Runs a room in a fresh Pyodide the way the worker does (runner.py behind the guest wall), with
// Purple replaced by a script of events after the start event. Returns every reply the room sent.
async function runRoom(source: string, events: Msg[], keep: Msg = {}, files: Msg = {}): Promise<Msg[]> {
  const py = await loadPyodide({ indexURL: decodeURIComponent(new URL("../node_modules/pyodide/", import.meta.url).pathname) });
  py.FS.mkdirTree("/purple");
  py.FS.writeFile("/purple/runner.py", runnerSource);
  py.runPython("import sys; sys.path.insert(0, '/purple')");
  const replies: Msg[] = [];
  const start = { ev: "start", t: 0, api: 2, size: [240, 120], keep, lib: purpleSource, source, ...files };
  const queue = [start, ...events].map((e) => JSON.stringify(e));
  py.registerJsModule("room_channel", {
    send: (text: string) => replies.push(JSON.parse(text)),
    recv: () => {
      const next = queue.shift();
      if (next === undefined) throw new Error(END);
      return next;
    },
  });
  py.runPython(guest);
  return replies;
}

const example = (name: string) => EXAMPLES.find((e) => e.name === name)!.source;
const shapes = (r: Msg) => (r.scene ?? []) as Shape[];
const texts = (r: Msg) => shapes(r).filter((s) => s[0] === "text").map((s) => s[4]);
// Grid squares a reply drew: [column, row, color] for each square that isn't the background.
const squares = (r: Msg) => shapes(r).slice(1).filter((s) => s[0] === "rect").map((s) => [Math.floor((s[1] as number) / 10), Math.floor((s[2] as number) / 10), s[5]]);
const GREEN = "#5ec46a";

describe("family rooms in Studio's Python", () => {
  it("runs the Snake example: a square each arrow, flowers behind it, and nothing on its own", async () => {
    const replies = await runRoom(example("snake"), [{ ev: "key", key: "down" }, { ev: "key", key: "space" }, { ev: "key", key: "a" }]);
    expect(squares(replies[0])).toEqual([[12, 6, GREEN], [11, 6, GREEN], [10, 6, GREEN], [9, 6, GREEN]]);
    expect(replies[0].wake).toBeNull();
    expect(squares(replies[1])).toContainEqual([12, 7, GREEN]);
    expect(squares(replies[1])).not.toContainEqual([9, 6, GREEN]);
    expect(texts(replies[1])).toEqual(["🌼"]);
    expect(squares(replies[2])).toContainEqual([12, 8, GREEN]);
    expect(texts(replies[2]).sort()).toEqual(["🌸", "🌼"]);
    expect(replies[3]).not.toHaveProperty("scene");
    expect(replies.at(-1)).toMatchObject({ error: { text: expect.stringContaining(END) } });
  }, 60_000);

  it("runs the memory example: a card on each letter key, turned over by pressing it", async () => {
    const replies = await runRoom(example("memory"), [{ ev: "key", key: "q" }, { ev: "key", key: "m" }, { ev: "key", key: "w" }]);
    expect(texts(replies[0])).toEqual([..."QWERTYUIOASDFGHJKL", "🔴 Red's turn"]);
    const [q] = texts(replies[1]);
    expect(q).toMatch(/\p{Extended_Pictographic}/u);
    expect(replies[2]).not.toHaveProperty("scene");
    expect(texts(replies[3]).slice(0, 2)).not.toContain("W");
  }, 60_000);

  it("plays memory alone with a parent's own picture beside an emoji, and no turn line", async () => {
    const source = example("memory").replace(/^CARDS = .*$/m, 'CARDS = [picture("grandma"), "🐶"]').replace(/^PLAYERS = .*$/m, 'PLAYERS = [("🔴", "Red", "#e44444")]');
    const keys = ["q", "w", "e", "r"].map((key) => ({ ev: "key", key }));
    const replies = await runRoom(source, keys, {}, { images: { grandma: [300, 200] } });
    expect(texts(replies[0])).toEqual([..."QWER"]);
    expect(replies.slice(1).flatMap((r) => shapes(r).filter((s) => s[0] === "image").map((s) => s[5]))).toContain("grandma");
  }, 60_000);

  it("runs the beat maker: a beat on each key, its drum's picture when on, Space to play", async () => {
    const replies = await runRoom(example("beats"), [{ ev: "key", key: "q" }, { ev: "key", key: "space" }]);
    expect(texts(replies[0]).slice(4, 6)).toEqual(["1", "2"]);
    expect(texts(replies[1])).toContain("🐸");
    expect(texts(replies[1])).not.toContain("Q");
    expect(replies[2].wake).not.toBeNull();
  }, 60_000);

  it("runs the picture quiz: a wrong pick goes away, the right one moves on to the next question", async () => {
    const keys = ["1", "2", "3"].map((key) => ({ ev: "key", key }));
    const replies = await runRoom(quizSource(TEMPLATES.quiz.defaults()), [...keys, { ev: "key", key: "space" }, { ev: "tick", t: 2 }]);
    expect(texts(replies[0]).sort()).toEqual(["1", "2", "3", "Which one says moo?", "🐄", "🐑", "🐖"].sort());
    expect(replies[0].sounds).toEqual([["say", "Which one says moo?"]]);
    const picks = replies.slice(1, 4);
    const right = picks.findIndex((r) => (r.sounds as unknown[] | undefined)?.some((s) => JSON.stringify(s) === '["note","G5","marimba"]'));
    expect(picks[right].sounds).toEqual([["say", "cow"], ["note", "G5", "marimba"]]);
    for (const wrong of picks.slice(0, right)) {
      const [[, word]] = wrong.sounds as [string, string][];
      expect(texts(wrong)).not.toContain(word === "pig" ? "🐖" : "🐑");
      expect(wrong.sounds).toContainEqual(["note", "E3", "marimba"]);
    }
    for (const after of replies.slice(right + 2, 5)) expect(after.sounds).toBeUndefined();
    expect(texts(replies[5])).toContain("Which one can fly?");
  }, 60_000);

  it("draws a parent's own pictures in the quiz, and keeps what they type as text, never code", async () => {
    const tricky = `it's "big" \\ \n"); import os; ("`;
    const source = quizSource({ rows: [
      { question: tricky, emoji: "grandma", right: { emoji: "grandma", word: "Grandma" }, others: [{ emoji: "", word: "" }] },
      { question: "", emoji: "", right: { emoji: "🐄", word: "" }, others: [] },
    ] });
    expect(source).not.toMatch(/^import os/m);
    const replies = await runRoom(source, [{ ev: "key", key: "1" }], {}, { images: { grandma: [200, 300] } });
    expect(texts(replies[0])).toContain(tricky);
    expect(shapes(replies[0]).filter((s) => s[0] === "image").map((s) => s[5])).toEqual(["grandma", "grandma"]);
    expect(replies[1].sounds).toEqual([["say", "Grandma"], ["note", "G5", "marimba"]]);
  }, 60_000);

  it("runs a soundboard: each key's sound, the fallback, and the key itself when no picture", async () => {
    const source = soundboardSource({
      rows: [{ key: "C", emoji: "🐄", word: "cow's \"moo\"", note: "C4" }, { key: "space", emoji: "⭐", word: "", note: "" }, { key: "", emoji: "x", word: "x", note: "x" }],
      other: { emoji: "", word: "", note: "A4" },
    });
    const replies = await runRoom(source, ["c", "space", "z"].map((key) => ({ ev: "key", key })));
    expect(texts(replies[0])).toEqual(["🎹"]);
    expect([texts(replies[1]), replies[1].sounds]).toEqual([["🐄"], [["say", 'cow\'s "moo"'], ["note", "C4", "marimba"]]]);
    expect([texts(replies[2]), replies[2].sounds]).toEqual([["⭐"], undefined]);
    expect([texts(replies[3]), replies[3].sounds]).toEqual([["z"], [["note", "A4", "marimba"]]]);
  }, 60_000);

  it("plays a parent's own picture, voice in place of Purple's, and sound on a picture keyboard key", async () => {
    const source = soundboardSource({ rows: [{ key: "m", emoji: "cat", word: "kitty", voice: "kitty", note: "meow" }], other: { emoji: "", word: "", note: "" } });
    const replies = await runRoom(source, [{ ev: "key", key: "m" }], {}, { images: { cat: [100, 100] }, sounds: ["kitty", "meow"] });
    expect(shapes(replies[1]).filter((s) => s[0] === "image").map((s) => s[5])).toEqual(["cat"]);
    expect(replies[1].sounds).toEqual([["clip", "kitty"], ["clip", "meow"]]);
  }, 60_000);

  it("remembers what a room keeps, and hands it back next time", async () => {
    const replies = await runRoom("from purple import *\nkeep['visits'] = keep.get('visits', 0) + 1\nshow(keep['visits'])\n", [], { visits: 2 });
    expect([texts(replies[0]), replies[0].keep]).toEqual([["3"], { visits: 3 }]);
  }, 60_000);

  it("reports a syntax error with its line", async () => {
    expect(await runRoom("from purple import *\nshow('hi'\n", [])).toEqual([{ error: { text: expect.stringMatching(/^SyntaxError/), line: 2 } }]);
  }, 60_000);

  it("reports a mistake in on_key with the line it happened on", async () => {
    const replies = await runRoom("from purple import *\n\ndef on_key(key):\n    show(key)\n    show(nope)\n", [{ ev: "key", key: "a" }]);
    expect(replies.at(-1)).toEqual({ error: { text: "NameError: name 'nope' is not defined", line: 5 } });
  }, 60_000);

  it("keeps a room away from JavaScript", async () => {
    for (const mod of ["js", "pyodide.ffi", "pyodide_js", "room_channel"]) {
      const replies = await runRoom(`from purple import *\nshow("before")\nimport ${mod}\n`, []);
      expect(replies).toEqual([{ error: { text: `ImportError: Rooms can't use ${mod.split(".")[0]}`, line: 3 } }]);
    }
  }, 120_000);

  it("turns rules into a room that runs", async () => {
    const source = rulesSource(blankRules());
    expect(source).toBe('from purple import *\n\n# Made with rules in Purple Studio.\n\ndef on_key(key):\n    show(key)\n\n\nshow("👋")\n');
    const replies = await runRoom(source, [{ ev: "key", key: "q" }]);
    expect([texts(replies[0]), texts(replies[1])]).toEqual([["👋"], ["q"]]);
  }, 60_000);

  it("runs every kind of rule, keys first and any other key last", async () => {
    const rules: Rule[] = [
      { when: { kind: "other" }, actions: [{ kind: "write", text: 'it\'s "x"' }] },
      { when: { kind: "key", key: "c" }, actions: [{ kind: "show", thing: { kind: "text", value: "🐄" } }, { kind: "play", note: "C4", instrument: "marimba" }] },
      { when: { kind: "key", key: "space" }, actions: [{ kind: "put", thing: { kind: "pick", value: "🌼" }, x: 3, y: 4 }, { kind: "drum", name: "kick" }] },
      { when: { kind: "every", seconds: 2 }, actions: [{ kind: "background", color: "#173a2a" }] },
      { when: { kind: "start" }, actions: [{ kind: "say", text: "" }, { kind: "clear" }] },
    ];
    const source = rulesSource(rules);
    expect(source).toContain("import random");
    expect(source).toContain("every(2, every_1)");
    const replies = await runRoom(source, ["c", "space", "z"].map((key) => ({ ev: "key", key })));
    expect([texts(replies[1]), replies[1].sounds]).toEqual([["🐄"], [["note", "C4", "marimba"]]]);
    expect([texts(replies[2]).sort(), replies[2].sounds]).toEqual([["🌼", "🐄"], [["drum", "kick"]]]);
    expect(texts(replies[3])).toContain('it\'s "x"');
  }, 60_000);
});
