import { describe, expect, it } from "vitest";
import { loadPyodide } from "pyodide";
import purpleSource from "../../purple_tui/roomkit/purple.py?raw";
import runnerSource from "../../purple_tui/roomkit/runner.py?raw";
import guest from "../src/rooms/guest.py?raw";
import { EXAMPLES, soundboardSource, triviaSource } from "../src/examples";
import { BLANK_BLOCKS, sourceFromBlocks } from "../src/blocks";

type Msg = Record<string, unknown>;
type Shape = [string, ...unknown[]];
const END = "end of the scripted events";

// Runs a room in a fresh Pyodide the way the worker does (runner.py behind the guest wall), with
// Purple replaced by a script of events after the start event. Returns every reply the room sent.
async function runRoom(source: string, events: Msg[], keep: Msg = {}): Promise<Msg[]> {
  const py = await loadPyodide({ indexURL: decodeURIComponent(new URL("../node_modules/pyodide/", import.meta.url).pathname) });
  py.FS.mkdirTree("/purple");
  py.FS.writeFile("/purple/runner.py", runnerSource);
  py.runPython("import sys; sys.path.insert(0, '/purple')");
  const replies: Msg[] = [];
  const start = { ev: "start", t: 0, api: 1, size: [240, 120], keep, lib: purpleSource, source };
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
const typed = (text: string) => [...text].map((c) => (c === " " ? { ev: "key", key: "space" } : { ev: "key", key: c.toLowerCase(), char: c }));
const enter = { ev: "key", key: "enter" };
const GREEN = "#5ec46a";

describe("family rooms in Studio's Python", () => {
  it("runs the Snake example: draws it, moves on ticks, and turns on an arrow key", async () => {
    const replies = await runRoom(example("snake"), [{ ev: "tick", t: 0.2 }, { ev: "key", key: "down", t: 0.3 }, { ev: "tick", t: 0.4 }]);
    expect(squares(replies[0])).toEqual([[12, 6, GREEN], [11, 6, GREEN], [10, 6, GREEN], [9, 6, GREEN]]);
    expect(replies[0].wake).toBeCloseTo(0.2);
    expect(squares(replies[1])).toEqual([[12, 6, GREEN], [11, 6, GREEN], [10, 6, GREEN], [13, 6, GREEN]]);
    expect(replies[2]).not.toHaveProperty("scene");
    expect(squares(replies[3])).toContainEqual([13, 7, GREEN]);
    expect(replies.at(-1)).toMatchObject({ error: { text: expect.stringContaining(END) } });
  }, 60_000);

  it("runs the trivia example: asks, takes a typed answer, and plays a note for a right one", async () => {
    const replies = await runRoom(example("dinosaur-trivia"), [...typed("Brachiosaurus "), enter]);
    expect(texts(replies[0])).toEqual(["🦕", "Which dinosaur had a very long neck?", "Your answer", "Answer → _"]);
    expect(replies[0].sounds).toEqual([["say", "Which dinosaur had a very long neck?"]]);
    expect(texts(replies[3])).toContain("Answer → Bra_");
    const answered = replies[typed("Brachiosaurus ").length + 1];
    expect(answered.sounds).toEqual([["note", "C5", "marimba"], ["say", "Yes!"], ["say", "Which dinosaur had tiny arms and big teeth?"]]);
  }, 60_000);

  it("keeps whatever a parent types in the trivia form as text, never code", async () => {
    const tricky = `it's "big" \\ \n"); import os; ("`;
    const source = triviaSource({ rows: [{ emoji: "🦕", question: tricky, answer: "yes" }, { emoji: "", question: "", answer: "skipped" }] });
    expect(source).not.toMatch(/^import os/m);
    const replies = await runRoom(source, [...typed("YES"), enter]);
    expect(texts(replies[0])).toContain(tricky);
    expect(replies.at(-2)!.sounds).toContainEqual(["note", "C5", "marimba"]);
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

  it("turns blocks into a room that runs", async () => {
    const source = sourceFromBlocks(BLANK_BLOCKS);
    expect(source).toBe("from purple import *\n\n\ndef on_key(key):\n    show(key)\n\n\nshow('👋')\n");
    const replies = await runRoom(source, [{ ev: "key", key: "q" }]);
    expect([texts(replies[0]), texts(replies[1])]).toEqual([["👋"], ["q"]]);
  }, 60_000);
});
