#!/usr/bin/env python3
"""List the interface strings a language pack hasn't translated yet.

Every string literal in the canvas UI that could be drawn is a candidate; an
f-string becomes a template with {0}, {1}... where its values go. Extra keys
in a pack are harmless (nothing draws them), so this errs toward listing too
much. Guide: guides/languages.md.

    just python scripts/i18n_strings.py              # missing counts per pack
    just python scripts/i18n_strings.py zh --json    # zh's missing strings as a JSON object to fill in
"""

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [ROOT / "purple_tui" / "canvas", ROOT / "purple_tui" / "hints.py", ROOT / "purple_tui" / "tts.py"]
SKIP_FILES = {"gfx.py", "kms.py", "sdl_input.py", "frame_stats.py"}  # nothing here is drawn as words
# Kid-facing examples to type, which only make sense in English.
SKIP_NAMES = {"PLAY_IDEAS", "ART_IDEAS", "BLOCKS_IDEAS", "MUSIC_IDEAS", "IDEAS"}
_CODE_RE = re.compile(r"^[a-z0-9_\-./:#%*+=<>\\]*$|^[A-Z0-9_]+$|^#[0-9a-fA-F]{3,8}$|^\W*$|2>&1|\.(ttf|json|wav|onnx|flitevox|log)\b")
_SKIP_CALLS = {"getattr", "setattr", "hasattr", "startswith", "endswith", "split", "join", "get", "pop", "index",
               "re.compile", "compile", "match", "search", "sub", "findall", "finditer", "fullmatch", "open",
               "environ.get", "getenv", "_dbg", "_log", "log", "heartbeat", "boot_log", "print", "Path", "run",
               "Popen", "check_output", "font", "image", "struct.pack", "struct.unpack", "encode", "decode",
               "format", "strftime", "rgb", "mix", "hexcolor", "isinstance", "set_clip", "push_timer"}


def _call_name(node) -> str:
    f = node.func
    if isinstance(f, ast.Attribute) and "log" in f.attr.lower() or isinstance(f, ast.Name) and "log" in f.id.lower():
        return "_log"
    if isinstance(f, ast.Attribute):
        base = f.value.id + "." if isinstance(f.value, ast.Name) else ""
        return base + f.attr if base + f.attr in _SKIP_CALLS else f.attr
    return f.id if isinstance(f, ast.Name) else ""


def _template(node: ast.JoinedStr) -> str:
    out, n = [], 0
    for v in node.values:
        if isinstance(v, ast.Constant):
            out.append(str(v.value))
        else:
            out.append(f"{{{n}}}")
            n += 1
    return "".join(out)


def _shown(text: str) -> bool:
    text = text.strip()
    if not text or _CODE_RE.match(text) or "\n    " in text:
        return False
    letters = re.sub(r"\{\d+\}|\[[^\]]*\]|\{[^}]*\}", "", text)
    return bool(re.search(r"[A-Za-z]{2}", letters)) and not re.fullmatch(r"[a-z]+(_[a-z0-9]+)+", text)


class _Collector(ast.NodeVisitor):
    def __init__(self):
        self.found: dict = {}
        self.skip: set = set()

    def _add(self, text, where):
        if _shown(text):
            self.found.setdefault(text, where)

    def visit_Module(self, node):
        self._mark_docstrings(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self._mark_docstrings(node)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_ClassDef = visit_FunctionDef

    def _mark_docstrings(self, node):
        body = getattr(node, "body", [])
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            self.skip.add(id(body[0].value))

    def visit_Assign(self, node):
        if any(isinstance(t, ast.Name) and t.id in SKIP_NAMES for t in node.targets):
            return
        self.generic_visit(node)

    def visit_Call(self, node):
        if _call_name(node) in _SKIP_CALLS:
            return
        self.generic_visit(node)

    def visit_Subscript(self, node):
        self.visit(node.value)  # a key like d["menu-x"] is never drawn

    def visit_Compare(self, node):
        return  # == "escape" compares to a key name

    def visit_Dict(self, node):
        for v in node.values:
            self.visit(v)

    def visit_JoinedStr(self, node):
        self._add(_template(node), self.where(node))
        for v in node.values:
            if isinstance(v, ast.FormattedValue):
                self.visit(v.value)

    def visit_Constant(self, node):
        if isinstance(node.value, str) and id(node) not in self.skip:
            self._add(node.value, self.where(node))

    def where(self, node):
        return f"{self.path}:{node.lineno}"


def interface_strings() -> dict:
    """text -> first file:line it appears at."""
    files = []
    for src in SOURCES:
        files += sorted(p for p in src.rglob("*.py") if p.name not in SKIP_FILES) if src.is_dir() else [src]
    c = _Collector()
    for path in files:
        c.path = str(path.relative_to(ROOT))
        c.visit(ast.parse(path.read_text(), str(path)))
    return c.found


def main(argv):
    sys.path.insert(0, str(ROOT))
    from purple_tui import i18n
    wanted = interface_strings()
    langs = i18n.languages()
    codes = [a for a in argv if not a.startswith("-")] or sorted(langs)
    for code in codes:
        lang = langs.get(code)
        have = lang.strings if lang else {}
        missing = {k: "" for k in wanted if k not in have}
        if "--json" in argv:
            print(json.dumps(missing, ensure_ascii=False, indent=2))
        else:
            print(f"{code}: {len(wanted) - len(missing)} of {len(wanted)} translated, {len(missing)} missing")
            if "-v" in argv:
                for k in missing:
                    print(f"  {wanted[k]}  {k!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
