"""Languages: interface translation and the second language in Play.

A language is a pack whose manifest type is "language" (studio/PACK_FORMAT.md).
Interface strings are looked up by their English text when they are drawn, so
a string a pack lacks stays English and new UI never needs a pack update to
keep working. Design: guides/languages.md.
"""

import base64
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

ENGLISH = "en"
PACK_TYPE = "language"
_SLOT_RE = re.compile(r"\{(\d+)\}")
_CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")
_MEMO_LIMIT = 4096
# Spaces and an icon or symbol before the words ("💬 Play"), spaces after: kept around the translation.
_AFFIX_RE = re.compile(r"([^\w\[{]*)(.*?)(\s*)", re.S)


@dataclass
class Language:
    code: str
    name: str                      # in the language itself: "Español"
    english_name: str
    content: Path
    voice: str | None = None       # Piper model name
    font: Path | None = None       # covers the script when the bundled faces don't
    strings: dict = field(default_factory=dict)
    words: dict = field(default_factory=dict)     # English word -> (word, reading)
    input: dict = field(default_factory=dict)     # toneless pinyin -> [characters, ...]
    templates: list = field(default_factory=list)  # (regex, translation)
    blocked: frozenset = frozenset()                # never spoken, in any language setting

    def lookup(self, text: str) -> str | None:
        hit = self.strings.get(text)
        if hit is not None:
            return hit
        for pattern, out in self.templates:
            m = pattern.fullmatch(text)
            if m:
                return _SLOT_RE.sub(lambda s: self._slot(m.group(int(s.group(1)) + 1)), out)
        return None

    def _slot(self, value: str) -> str:
        return self.lookup(value) or value


def _read(path: Path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _template(key: str):
    """'{0} blocks left' -> a regex capturing slots {0}, {1}... in order, or None for
    plain text or text that is nothing but slots."""
    parts = _SLOT_RE.split(key)
    if len(parts) == 1 or not "".join(parts[::2]).strip() or [int(p) for p in parts[1::2]] != list(range(len(parts) // 2)):
        return None
    return re.compile("".join(re.escape(p) if i % 2 == 0 else "(.*?)" for i, p in enumerate(parts)))


def _templates(strings: dict) -> list:
    return [(t, v) for k, v in strings.items() if (t := _template(k))]


def _word_entry(value):
    if isinstance(value, str) and value:
        return value, ""
    if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
        return value[0], value[1] if len(value) > 1 else ""
    return None


def load_language(pack_dir: Path) -> Language | None:
    from .content import read_manifest
    manifest = read_manifest(pack_dir)
    content = pack_dir / "content"
    meta = _read(content / "language.json") if manifest and manifest.get("type") == PACK_TYPE else None
    if not isinstance(meta, dict) or not isinstance(meta.get("code"), str) or meta["code"] == ENGLISH:
        return None
    font = content / meta["font"] if isinstance(meta.get("font"), str) else None
    lang = Language(meta["code"], str(meta.get("name") or meta["code"]), str(meta.get("english_name") or meta["code"]),
                    content, meta.get("voice") if isinstance(meta.get("voice"), str) else None,
                    font if font and font.is_file() else None)
    strings = _read(content / "strings.json")
    if isinstance(strings, dict):
        lang.strings = {k: v for k, v in strings.items() if isinstance(k, str) and isinstance(v, str) and v}
        lang.templates = _templates(lang.strings)
    words = _read(content / "words.json")
    if isinstance(words, dict):
        lang.words = {k.lower(): e for k, v in words.items() if isinstance(k, str) and (e := _word_entry(v))}
    entries = _read(content / "input.json")
    if isinstance(entries, dict):
        lang.input = {k: v for k, v in entries.items() if isinstance(k, str) and isinstance(v, list)}
    lang.blocked = read_blocked(content / "blocked.txt")
    return lang


def read_blocked(path: Path) -> frozenset:
    """Words never spoken: base64 of one word per line, so the repo holds no plaintext profanity."""
    try:
        text = base64.b64decode(path.read_bytes()).decode("utf-8")
    except (OSError, ValueError):
        return frozenset()
    return frozenset(w.strip().lower() for w in text.splitlines() if w.strip())


def _merge(base: Language, over: Language) -> Language:
    """A later pack of the same language adds to it: a family's fixes win, the rest stays.
    Blocked words only ever add up."""
    strings = base.strings | over.strings
    return Language(over.code, over.name, over.english_name, over.content, over.voice or base.voice,
                    over.font or base.font, strings, base.words | over.words, base.input | over.input,
                    _templates(strings), base.blocked | over.blocked)


_languages: dict | None = None
_interface: str | None = None
_second: str | None = None
_loaded_choice = False
_memo: dict = {}


def languages() -> dict:
    """Installed languages by code: the image's packs, then user packs, which win."""
    global _languages
    if _languages is None:
        from .content import _pack_dirs
        found = {}
        for packs in (Path(__file__).parent.parent / "packs", Path.home() / ".purple" / "packs"):
            for d in _pack_dirs(packs):
                if lang := load_language(d):
                    found[lang.code] = _merge(found[lang.code], lang) if lang.code in found else lang
        _languages = found
    return _languages


def _choice():
    global _interface, _second, _loaded_choice
    if not _loaded_choice:
        from .settings import get_language, get_second_language
        _interface, _second, _loaded_choice = get_language(), get_second_language(), True
    return _interface, _second


def interface_language() -> Language | None:
    """None when the interface is English (or its pack is gone)."""
    return languages().get(_choice()[0])


def second_language() -> Language | None:
    return languages().get(_choice()[1])


def active_languages() -> list:
    return [lang for lang in (interface_language(), second_language()) if lang]


def set_languages(interface: str, second: str | None) -> None:
    """Persist both choices and drop everything derived from the old ones."""
    global _interface, _second, _loaded_choice
    from . import content
    from .settings import set_language, set_second_language
    set_language(interface)
    set_second_language(second)
    _interface, _second, _loaded_choice = interface, second, True
    _memo.clear()
    if content._content is not None:  # rebuilt in place: rooms hold on to it
        content._content.__init__(content._content.packs_dir)
        content._content.load_all()


def reload() -> None:
    """After a pack install: rescan language packs."""
    global _languages
    _languages = None
    _memo.clear()


def translate(text: str) -> str:
    """Interface text in the parent's language; English when there is no translation."""
    lang = interface_language()
    if lang is None or not text:
        return text
    hit = _memo.get(text)
    if hit is None:
        lead, core, tail = _AFFIX_RE.fullmatch(text).groups()
        found = lang.lookup(text)
        if found is None and core and core != text:
            found = lang.lookup(core)
            found = None if found is None else lead + found + tail
        hit = text if found is None else found
        if len(_memo) >= _MEMO_LIMIT:
            _memo.clear()
        _memo[text] = hit
    return hit


def fonts() -> list:
    """(face name, path) for every installed language that brings a font."""
    return [(f"lang-{lang.code}", lang.font) for lang in languages().values() if lang.font]


def has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def speech_language(text: str) -> Language | None:
    """The language to speak text in when the caller didn't say: Chinese characters pick a
    language whose input covers them, anything else is English."""
    if not has_cjk(text):
        return None
    return next((lang for lang in languages().values() if lang.input), None)


def fold(word: str) -> str:
    """Lowercase without accents: what a kid types for "ratón" or "lǜ"."""
    return "".join(c for c in unicodedata.normalize("NFD", word.lower()) if unicodedata.category(c) != "Mn")


def aliases(lang: Language) -> dict:
    """Typed form -> English word, so Play understands the language: the word, its
    unaccented spelling, plurals for alphabetic words, and the toneless reading."""
    out = {}
    for english, (word, reading) in lang.words.items():
        forms = {word.lower(), fold(word)}
        if not has_cjk(word):
            forms |= {f + ("es" if f[-1] not in "aeiou" else "s") for f in set(forms)}
        if reading:
            forms.add(fold(reading).replace(" ", ""))
        for f in forms:
            out.setdefault(f, english)
    return out


def echo(lang: Language, english: str) -> tuple | None:
    """(word, reading) for an English word in the second language, singular or plural."""
    from .content import singularize
    english = english.lower()
    return lang.words.get(english) or lang.words.get(singularize(english) or "")


def candidates(lang: Language, typed: str, limit: int = 9) -> list:
    """Characters for a typed pinyin run: words with a picture first, then the input list
    by how common they are."""
    key = typed.lower()
    if not key or not lang.input:
        return []
    out = [w for w, r in lang.words.values() if r and fold(r).replace(" ", "") == key]
    for w in lang.input.get(key, []):
        if w not in out:
            out.append(w)
    return out[:limit]
