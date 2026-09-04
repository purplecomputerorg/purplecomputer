import { beforeAll, describe, expect, it } from "vitest";
import { loadPyodide, type PyodideInterface } from "pyodide";
import prelude from "../src/purple_prelude.py?raw";
import { bridge } from "../src/pybridge";
import { draft } from "../src/state";

// Pyodide runs in Node too, so the prelude and the bridge get a real Python interpreter here.
// Loading it takes a few seconds; every test shares one instance.
let py: PyodideInterface;

beforeAll(async () => {
  // Under Vite the module's own URL is rewritten, so point Pyodide at its files explicitly.
  py = await loadPyodide({ indexURL: decodeURIComponent(new URL("../node_modules/pyodide/", import.meta.url).pathname) });
  py.registerJsModule("purple_bridge", bridge);
  await py.runPythonAsync(prelude);
}, 120_000);

describe("the Python page's pack object", () => {
  it("adds words, synonyms, rankings, an instrument, and a room to the draft", async () => {
    await py.runPythonAsync(`
pack.word("tractor", "🚜")
pack.synonym("tracter", "tractor")
pack.rank("tractor", "cow")
pack.instrument("Kitchen Marimba", "marimba", wood=0.9)
pack.room("farm", "Farm",
    when_start(show("🐄"), say("farm")),
    when_key("c", show("🐄"), say("cow"), play("C4")),
    when_any_key(add(key()), if_(compare(">", var("n"), 2), [clear()], [change("n")])),
)
`);
    expect(draft.words).toEqual([{ word: "tractor", emoji: "🚜" }]);
    expect(draft.synonyms).toEqual([{ alias: "tracter", word: "tractor" }]);
    expect(draft.ranked).toEqual(["tractor", "cow"]);
    expect(draft.instruments[0]).toMatchObject({ name: "kitchen-marimba", base: "marimba", params: { wood: 0.9 } });
    expect(draft.rooms[0].program.rules[2]).toEqual({ when: { event: "any_key" }, do: [
      { do: "add", text: { key: true } },
      { do: "if", test: { compare: ">", a: { var: "n" }, b: 2 }, then: [{ do: "clear" }], else: [{ do: "change", var: "n", by: 1 }] },
    ] });
    expect(draft.rooms[0].blocks).toMatchObject({ blocks: { languageVersion: 0 } });
    expect(JSON.parse(String(await py.runPythonAsync("json.dumps(pack.summary())")))).toEqual({ words: 1, synonyms: 1, autocomplete_picks: 2, instruments: 1, rooms: 1 });
  });

  it("raises the same refusals Purple would", async () => {
    await expect(py.runPythonAsync(`pack.room("Bad Name", "x")`)).rejects.toThrow(/lowercase/);
    await expect(py.runPythonAsync(`pack.room("ok", "x", when_key("c", play("H9")))`)).rejects.toThrow(/note must look like/);
    await expect(py.runPythonAsync(`pack.instrument("x", "marimba", reverb=1)`)).rejects.toThrow(/no parameter reverb/);
  });
});
