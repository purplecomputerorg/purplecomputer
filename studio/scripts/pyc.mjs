// Adds Pyodide's own bytecode for purple_tui to purple.zip (scripts/studio_bundle.py runs it), so the
// browser doesn't compile Purple's Python on every start. Unchecked hash-based .pyc in __pycache__: the
// zip doesn't keep file times, and the .py stays beside it (tracebacks, and rooms read roomkit's source).
// node scripts/pyc.mjs <purple.zip>
import { readFileSync, writeFileSync } from "node:fs";
import { loadPyodide } from "pyodide";

const zip = process.argv[2];
const py = await loadPyodide();
py.FS.writeFile("/purple.zip", readFileSync(zip));
py.runPython(`
import importlib.util, sys, zipfile
from importlib._bootstrap_external import _code_to_hash_pyc
old = zipfile.ZipFile("/purple.zip")
entries = [(i, old.read(i)) for i in old.infolist()]
with zipfile.ZipFile("/purple.zip", "w", zipfile.ZIP_DEFLATED) as out:
    for info, data in entries:
        out.writestr(info, data)
        folder, _, name = info.filename.rpartition("/")
        if info.filename.startswith("purple_tui/") and name.endswith(".py"):
            code = compile(data, info.filename, "exec", dont_inherit=True)
            pyc = _code_to_hash_pyc(code, importlib.util.source_hash(data), checked=False)
            out.writestr(f"{folder}/__pycache__/{name[:-3]}.{sys.implementation.cache_tag}.pyc", pyc)
`);
writeFileSync(zip, py.FS.readFile("/purple.zip"));
