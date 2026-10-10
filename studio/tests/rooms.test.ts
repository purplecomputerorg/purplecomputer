import { describe, expect, it } from "vitest";
import { loadPyodide } from "pyodide";
import purpleSource from "../../purple_tui/roomkit/purple.py?raw";
import guest from "../src/rooms/guest.py?raw";
import { EXAMPLES, soundboardSource, triviaSource } from "../src/examples";
import { BLANK_BLOCKS, sourceFromBlocks } from "../src/blocks";

type Msg = Record<string, unknown>;
const END = "end of the scripted events";

// Runs a room in a fresh Pyodide the way the worker does (purple.py, then the guest wall), with the
// page side replaced by a script of events. Returns every message the room sent.
async function runRoom(source: string, events: Msg[]): Promise<Msg[]> {
  const py = await loadPyodide({ indexURL: decodeURIComponent(new URL("../node_modules/pyodide/", import.meta.url).pathname) });
  py.FS.mkdirTree("/purple");
  py.FS.writeFile("/purple/purple.py", purpleSource);
  py.runPython("import sys; sys.path.insert(0, '/purple')");
  const sent: Msg[] = [];
  const queue = events.map((e) => JSON.stringify(e));
  py.registerJsModule("room_channel", {
    send: (text: string) => sent.push(JSON.parse(text)),
    recv: () => {
      const next = queue.shift();
      if (next === undefined) throw new Error(END);
      return next;
    },
  });
  py.runPython(guest);
  py.globals.set("ROOM_SOURCE", source);
  py.runPython("purple.run(ROOM_SOURCE)");
  return sent;
}

const example = (name: string) => EXAMPLES.find((e) => e.name === name)!.source;
const cells = (sent: Msg[]) => sent.filter((m) => m.cmd === "cell").map((m) => [m.x, m.y, m.thing]);
const GREEN = "#5ec46a";

describe("family rooms in Studio's Python", () => {
  it("runs the Snake example: draws it, moves on ticks, and turns on an arrow key", async () => {
    const tick = { ev: "tick", id: 1 };
    const sent = await runRoom(example("snake"), [tick, tick, { ev: "key", key: "down" }, tick]);
    expect(cells(sent).slice(0, 4)).toEqual([[12, 6, GREEN], [11, 6, GREEN], [10, 6, GREEN], [9, 6, GREEN]]);
    expect(sent).toContainEqual({ cmd: "every", id: 1, seconds: 0.2 });
    expect(cells(sent).slice(4)).toEqual([[9, 6, null], [13, 6, GREEN], [10, 6, null], [14, 6, GREEN], [11, 6, null], [14, 7, GREEN]]);
    expect(sent.filter((m) => m.cmd === "done")).toHaveLength(5);
    expect(sent.at(-1)).toMatchObject({ cmd: "error", text: expect.stringContaining(END) });
  }, 60_000);

  it("runs the trivia example: asks, and plays a note for a right answer", async () => {
    const sent = await runRoom(example("dinosaur-trivia"), [{ ev: "answer", text: "Brachiosaurus " }, { ev: "answer", text: "stegosaurus" }]);
    expect(sent.slice(0, 5)).toEqual([
      { cmd: "clear" }, { cmd: "show", text: "🦕" }, { cmd: "write", text: "Which dinosaur had a very long neck?" },
      { cmd: "say", text: "Which dinosaur had a very long neck?" }, { cmd: "ask", prompt: "Your answer" },
    ]);
    expect(sent).toContainEqual({ cmd: "play", note: "C5", instrument: "marimba" });
    expect(sent).toContainEqual({ cmd: "say", text: "Good try! It was t rex." });
  }, 60_000);

  it("keeps whatever a parent types in the trivia form as text, never code", async () => {
    const tricky = `it's "big" \\ \n"); import os; ("`;
    const source = triviaSource({ rows: [{ emoji: "🦕", question: tricky, answer: tricky }, { emoji: "", question: "", answer: "skipped" }] });
    expect(source).not.toMatch(/^import os/m);
    const sent = await runRoom(source, [{ ev: "answer", text: `  ${tricky.toUpperCase()} ` }]);
    expect(sent).toContainEqual({ cmd: "write", text: tricky });
    expect(sent).toContainEqual({ cmd: "play", note: "C5", instrument: "marimba" });
    expect(sent.filter((m) => m.cmd === "ask")).toHaveLength(1);
    expect(sent.find((m) => m.cmd === "error")?.text).toContain(END);
  }, 60_000);

  it("runs a soundboard: each key's sound, the fallback, and the key itself when no picture", async () => {
    const source = soundboardSource({
      rows: [{ key: "C", emoji: "🐄", word: "cow's \"moo\"", note: "C4" }, { key: "space", emoji: "⭐", word: "", note: "" }, { key: "", emoji: "x", word: "x", note: "x" }],
      other: { emoji: "", word: "", note: "A4" },
    });
    const sent = await runRoom(source, ["c", "space", "z"].map((key) => ({ ev: "key", key })));
    expect(sent.filter((m) => m.cmd !== "done").slice(0, 7)).toEqual([
      { cmd: "show", text: "🎹" },
      { cmd: "show", text: "🐄" }, { cmd: "say", text: 'cow\'s "moo"' }, { cmd: "play", note: "C4", instrument: "marimba" },
      { cmd: "show", text: "⭐" },
      { cmd: "show", text: "z" }, { cmd: "play", note: "A4", instrument: "marimba" },
    ]);
  }, 60_000);

  it("reports a syntax error with its line", async () => {
    expect(await runRoom("from purple import *\nshow('hi'\n", [])).toEqual([{ cmd: "error", text: expect.stringMatching(/^SyntaxError/), line: 2 }]);
  }, 60_000);

  it("reports a mistake in on_key with the line it happened on", async () => {
    const sent = await runRoom("from purple import *\n\ndef on_key(key):\n    show(key)\n    show(nope)\n", [{ ev: "key", key: "a" }]);
    expect(sent).toEqual([{ cmd: "done" }, { cmd: "show", text: "a" }, { cmd: "error", text: "NameError: name 'nope' is not defined", line: 5 }]);
  }, 60_000);

  it("keeps a room away from JavaScript", async () => {
    for (const mod of ["js", "pyodide.ffi", "pyodide_js", "room_channel"]) {
      const sent = await runRoom(`from purple import *\nshow("before")\nimport ${mod}\n`, []);
      expect(sent).toEqual([{ cmd: "show", text: "before" }, { cmd: "error", text: `ImportError: Rooms can't use ${mod.split(".")[0]}`, line: 3 }]);
    }
  }, 120_000);

  it("turns blocks into a room that runs", async () => {
    const source = sourceFromBlocks(BLANK_BLOCKS);
    expect(source).toBe("from purple import *\n\n\ndef on_key(key):\n    show(key)\n\n\nshow('👋')\n");
    const sent = await runRoom(source, [{ ev: "key", key: "q" }]);
    expect(sent.slice(0, 4)).toEqual([{ cmd: "show", text: "👋" }, { cmd: "done" }, { cmd: "show", text: "q" }, { cmd: "done" }]);
  }, 60_000);
});
