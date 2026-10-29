import { describe, expect, it } from "vitest";
import { loadPyodide } from "pyodide";
import purpleSource from "../../purple_tui/roomkit/purple.py?raw";
import runnerSource from "../../purple_tui/roomkit/runner.py?raw";
import guest from "../src/rooms/guest.py?raw";
import { BLANK_ROOMS, EXAMPLES, TEMPLATES, quizSource, soundboardSource } from "../src/examples";
import { blankRules, rulesSource, type Rule } from "../src/rules";
import { applyKnobs, BLOCK_STARTERS, blocksSource, build, WHOLE_ROOM_BLOCKS } from "../src/blocks";
import { readKnobs } from "../src/knobs";

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
  it("runs the Snake example: it crawls a square each tick to the key pressed, which lights up in its sticker color, turning the head that color too, and plays its note", async () => {
    const ticks = [1, 2, 3, 4].map((t) => ({ ev: "tick", t }));
    const replies = await runRoom(example("snake"), [{ ev: "key", key: "h" }, ...ticks]);
    expect(squares(replies[0])).toEqual(expect.arrayContaining([[11, 9, GREEN], [10, 9, GREEN]]));
    expect(texts(replies[0])).toEqual(expect.arrayContaining(["1", "Q", "H", "/"]));
    expect(replies[0].wake).not.toBeNull();
    expect(squares(replies[5])).toEqual(expect.arrayContaining([[12, 6, "#DFBF1F"], [12, 7, GREEN]]));
    const head = (r: Msg) => (shapes(r).find((s) => s[0] === "image")?.[5] as { palette: Record<string, string> }).palette.S;
    expect([head(replies[0]), head(replies[5])]).toEqual([GREEN, "#DFBF1F"]);
    expect(replies[5].sounds).toEqual([["note", "C5", "glockenspiel"]]);
    expect(replies.at(-1)).toMatchObject({ error: { text: expect.stringContaining(END) } });
  }, 60_000);

  it("walks the explore example from map to map through the doors with the same number", async () => {
    const world = 'WORLD = {"a": ["TTTT", "TY1T", "TTTT"], "b": ["RRRR", "R1*R", "RRRR"]}';
    const source = example("explore").replace(/^WORLD = \{[\s\S]*?^\}$/m, world);
    const replies = await runRoom(source, [{ ev: "key", key: "right" }, { ev: "key", key: "right" }, { ev: "key", key: "up" }]);
    expect(texts(replies[0])).toEqual(expect.arrayContaining(["🌳", "🚪", "⭐ 0 of 1"]));
    expect(texts(replies[1])).toEqual(expect.arrayContaining(["🪨", "⭐", "⭐ 0 of 1"]));
    expect(texts(replies[1])).not.toContain("🌳");
    expect(texts(replies[2])).toContain("⭐ All the stars! The house is open.");
    expect(texts(replies[2])).not.toContain("⭐");
  }, 60_000);

  it("runs the memory example: a card on each letter key, turned over by pressing it, and players taking turns", async () => {
    const keys = ["2", "q", "m", "w"].map((key) => ({ ev: "key", key }));
    const replies = await runRoom(example("memory"), keys);
    expect(texts(replies[0])).toEqual([..."QWERTYUIOASDFGHJKL", "🔴  Press 1 to 6 for players"]);
    expect(texts(replies[1])).toContain("🔴 🔵  Press 1 to 6 for players");
    const [q] = texts(replies[2]);
    expect(q).toMatch(/\p{Extended_Pictographic}/u);
    expect(texts(replies[2])).toContain("🔴's turn");
    expect(replies[3]).not.toHaveProperty("scene");
    expect(texts(replies[4]).slice(0, 2)).not.toContain("W");
  }, 60_000);

  it("plays memory alone by default with a parent's own picture beside an emoji, and no turn line", async () => {
    const source = example("memory").replace(/^CARDS = .*$/m, 'CARDS = [picture("grandma"), "🐶"]');
    const keys = ["q", "w", "e", "r"].map((key) => ({ ev: "key", key }));
    const replies = await runRoom(source, keys, {}, { images: { grandma: [300, 200] } });
    expect(texts(replies[0])).toEqual([..."QWER", "🔴  Press 1 to 6 for players"]);
    expect(texts(replies[1]).filter((t) => t.includes("turn"))).toEqual([]);
    expect(replies.slice(1).flatMap((r) => shapes(r).filter((s) => s[0] === "image").map((s) => s[5]))).toContain("grandma");
  }, 60_000);

  it("runs the beat maker: a beat on each key, its drum's picture with the letter as a corner badge when on, Space to play", async () => {
    const replies = await runRoom(example("beats"), [{ ev: "key", key: "q" }, { ev: "key", key: "space" }]);
    expect(texts(replies[0]).slice(4, 6)).toEqual(["1", "2"]);
    expect(texts(replies[1])).toContain("🐸");
    const text = (t: string) => shapes(replies[1]).find((s) => s[0] === "text" && s[4] === t)!;
    expect(text("Q")[3]).toBeLessThan(text("E")[3] as number);
    expect(text("Q")[6]).toMatchObject({ box: "surface" });
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

  it("opens a story on its cover, and a key starts it with Purple saying the page", async () => {
    const replies = await runRoom(example("story"), [{ ev: "key", key: "a" }, { ev: "key", key: "1" }]);
    expect([texts(replies[0]), replies[0].sounds]).toEqual([["📖", "Mia and the map", "Press any key to start"], [["say", "Mia and the map"]]]);
    expect(replies[1].sounds).toEqual([["say", expect.stringMatching(/^Mia finds a map/)]]);
    expect(replies[2].sounds).toEqual([["note", "G4", "marimba"], ["say", expect.stringMatching(/^In the forest/)]]);
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

  const starter = (label: string) => BLOCK_STARTERS.find((s) => s.label === label)!.workspace();

  it("runs the light-the-keys blocks: a key lights its square in its sticker color and plays its column's note", async () => {
    const replies = await runRoom(blocksSource(starter("Light the keys")), [{ ev: "key", key: "q" }, { ev: "key", key: "space" }]);
    expect(texts(replies[0])).toEqual(expect.arrayContaining(["1", "Q", "/"]));
    expect(replies[1].sounds).toEqual([["note", "C4", "marimba"]]);
    expect(squares(replies[1]).filter(([, , c]) => c !== "tile")).toHaveLength(1);
    expect(replies[2]).not.toHaveProperty("sounds");
  }, 60_000);

  it("offers the same starters in blocks as in Python, and each one's blocks play like its Python", async () => {
    expect(BLOCK_STARTERS.map((s) => s.label)).toEqual(BLANK_ROOMS.map((r) => r.label));
    const keys = ["left", "q", "1", "space", "a"].map((key) => ({ ev: "key", key }));
    for (const r of BLANK_ROOMS) {
      const [python, blocks] = await Promise.all([runRoom(r.source, keys), runRoom(blocksSource(starter(r.label)), keys)]);
      expect(blocks, r.label).toEqual(python);
    }
  }, 120_000);

  it("meets the player from blocks: walls stop it, it walks onto a star, and a falling thing lands on it", async () => {
    const { b, on, thing, text, num, square, score, workspace } = build;
    const room = workspace(["found"],
      on("purple_on_start", {}, {},
        b("purple_wall", {}, { THING: thing("🌳") }),
        b("purple_put", { SIZE: "1" }, { THING: thing("🌳"), SQUARE: square(0, 1) }),
        b("purple_put", { SIZE: "1" }, { THING: thing("⭐"), SQUARE: square(1, 0) }),
        b("purple_put", { SIZE: "1" }, { THING: thing("🍎"), SQUARE: square(1, 5) }),
        b("purple_player_put", {}, { THING: thing("🦊"), SQUARE: square(0, 0) })),
      on("purple_on_key", { WHICH: "arrow" }, {}, b("purple_player_move", { WAY: "key" })),
      on("purple_every", {}, { SECONDS: num(1) }, b("purple_move_all", { WAY: "up" }, { THING: thing("🍎") })),
      on("purple_on_meet", {}, { THING: thing("⭐") }, b("purple_change", { VAR: { id: "found" } }, { BY: num(1) }),
        b("purple_status", {}, { TEXT: b("purple_join", {}, { A: text("found "), B: score("found") }) })),
      on("purple_on_meet", {}, { THING: thing("🍎") }, b("purple_say", {}, { TEXT: text("yum") })));
    const ticks = [1, 2, 3, 4, 5].map((t) => ({ ev: "tick", t }));
    const replies = await runRoom(blocksSource(room), [{ ev: "key", key: "down" }, { ev: "key", key: "right" }, ...ticks]);
    expect(replies[1]).not.toHaveProperty("scene");
    expect(texts(replies[2])).toContain("found 1");
    expect(texts(replies[2])).not.toContain("⭐");
    expect(replies.slice(3).map((r) => r.sounds).filter(Boolean)).toEqual([[["say", "yum"]]]);
    expect(texts(replies.at(-2)!)).not.toContain("🍎");
  }, 60_000);

  it("pictures the Rooms page's whole room in blocks as the same Python shown beside it", () => {
    expect(blocksSource(WHOLE_ROOM_BLOCKS())).toBe('from purple import *\n\n\ndef on_key(key):\n    grid.set(grid.random_empty(), "🐶")\n    drum("bongo")\n    say(key)\n');
  });

  it("writes a knob's new value back into its setting block", () => {
    const { b, on, thing, num, square, workspace, settingOf } = build;
    const room = workspace([], settingOf("FRUIT", "What falls.", thing("🍎")), settingOf("BASKET", "What catches it.", thing("🧺")),
      settingOf("SPEED", "Seconds a square.", num(0.5)), on("purple_on_start", {}, {}, b("purple_put", { SIZE: "1" }, { THING: thing("🍎"), SQUARE: square(1, 1) })));
    const knobs = readKnobs(blocksSource(room));
    expect(knobs.map((k) => k.name)).toEqual(["FRUIT", "BASKET", "SPEED"]);
    knobs[0].value = { t: "str", v: "🍌" };
    knobs[1].value = { t: "picture", v: "grandma" };
    knobs[2].value = { t: "num", v: 0.3 };
    applyKnobs(room, knobs);
    const source = blocksSource(room);
    expect(source).toContain('FRUIT = "🍌"\n');
    expect(source).toContain('BASKET = picture("grandma")\n');
    expect(source).toContain("SPEED = 0.3\n");
  });
});
