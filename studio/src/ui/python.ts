// A Python console over the pack, for parents who would rather write than click. Pyodide runs
// Python in the browser; a small bridge lets it change the draft, and every room it makes goes
// through the same check Purple applies.
import prelude from "../purple_prelude.py?raw";
import { bridge } from "../pybridge";
import { clear, h } from "./dom";
import type { View } from "./view";

interface Pyodide {
  runPythonAsync(code: string): Promise<unknown>;
  registerJsModule(name: string, module: object): void;
  setStdout(options: { batched: (text: string) => void }): void;
  setStderr(options: { batched: (text: string) => void }): void;
}
declare global { interface Window { loadPyodide?: (options: { indexURL: string }) => Promise<Pyodide> } }

const EXAMPLE = `pack.word("tractor", "🚜")
pack.synonym("tracter", "tractor")
pack.rank("tractor")

pack.room("hello", """
from purple import *

show("👋")

def on_key(key):
    show(key)
    play("C4")
""")
print(pack)`;

let pyodide: Promise<Pyodide> | null = null;

function loadRuntime(onStatus: (s: string) => void): Promise<Pyodide> {
  pyodide ??= (async () => {
    onStatus("Loading Python (about 10 MB, once per visit)…");
    const base = new URL("pyodide/", document.baseURI).href;
    await new Promise<void>((resolve, reject) => {
      const s = h("script", { src: `${base}pyodide.js` });
      s.onload = () => resolve();
      s.onerror = () => reject(new Error("Could not load Pyodide. Is the dev server running from studio/?"));
      document.head.append(s);
    });
    const py = await window.loadPyodide!({ indexURL: base });
    py.registerJsModule("purple_bridge", bridge);
    await py.runPythonAsync(prelude);
    onStatus("Ready.");
    return py;
  })();
  return pyodide;
}

export function pythonView(): View {
  const code = h("textarea", { rows: 14, class: "code", spellcheck: false }, EXAMPLE);
  const out = h("pre", { class: "console" });
  const status = h("div", { class: "status" });
  const run = async () => {
    status.textContent = "Running…";
    clear(out);
    try {
      const py = await loadRuntime((s) => (status.textContent = s));
      py.setStdout({ batched: (t) => (out.textContent += t + "\n") });
      py.setStderr({ batched: (t) => (out.textContent += t + "\n") });
      await py.runPythonAsync(code.value);
      status.textContent = "Done. Changes are in the pack.";
    } catch (e) {
      out.textContent += (e instanceof Error ? e.message : String(e)) + "\n";
      status.textContent = "That did not run. The message above is Python's.";
    }
  };
  code.addEventListener("keydown", (e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run(); });

  return {
    title: "Python",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "The same pack, from Python. A ", h("span", { class: "mono" }, "pack"), " object adds words, synonyms, instruments, and rooms. It runs right here in the browser and changes the pack on the left as it goes."),
      h("div", { class: "card" }, code, h("div", { class: "row", style: "margin-top:10px" }, h("button", { class: "btn small", onclick: run }, "Run"), h("span", { class: "dim small" }, "or Ctrl+Enter"), status), out),
      h("h3", {}, "What you can call"),
      h("pre", { class: "small" }, prelude.split('"""')[1].trim()),
      h("p", { class: "dim small" }, "A room is its own Python file; see the ", h("a", { href: "#guide" }, "Room guide"), " for what it can call, and the Rooms page to try one."),
      h("div", { class: "note" }, h("strong", {}, "What this is not: "), "a way to change Purple itself. This page fills in the pack; only the rooms in it run on Purple, each in a box of its own. The Python runtime is Pyodide, loaded from this site the first time you press Run."),
    ),
    stage: () => null,
  };
}
