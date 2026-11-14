// Swaps purplecomputer's Python in purple.zip for Pyodide's own bytecode (scripts/studio_bundle.py runs it), so
// the browser downloads less and doesn't compile Purple on every start. roomkit keeps its .py, since rooms
// read its source, with an unchecked hash-based .pyc in __pycache__ (the zip doesn't keep file times).
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
with zipfile.ZipFile("/purple.zip", "w") as out:
    for info, data in entries:
        folder, _, name = info.filename.rpartition("/")
        if not (info.filename.startswith("purplecomputer/") and name.endswith(".py")):
            out.writestr(info, data)
            continue
        code = compile(data, info.filename, "exec", dont_inherit=True)
        pyc = _code_to_hash_pyc(code, importlib.util.source_hash(data), checked=False)
        if info.filename.startswith("purplecomputer/roomkit/"):
            out.writestr(info, data)
            out.writestr(f"{folder}/__pycache__/{name[:-3]}.{sys.implementation.cache_tag}.pyc", pyc)
        else:
            out.writestr(f"{folder}/{name}c", pyc)
`);
writeFileSync(zip, py.FS.readFile("/purple.zip"));
