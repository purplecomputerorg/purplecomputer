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
from dataclasses import dataclass, field, replace
from pathlib import Path

ENGLISH = "en"
PACK_TYPE = "language"
# Off until a speaker reviews the packs: none load, so Purple is English and the parent menu has no Language rows.
ENABLED = False
_SLOT_RE = re.compile(r"\{(\d+)\}")
_CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")
_MEMO_LIMIT = 4096
# Spaces and an icon or symbol before the words ("💬 Play"), spaces after: kept around the translation.
_AFFIX_RE = re.compile(r"([^\w\[{]*)(.*?)(\s*)", re.S)
_TOKEN_RE = re.compile(r"\d[\d.,]*|[^\W\d_]+|\S")


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
    measures: dict = field(default_factory=dict)  # English word -> counting word (Mandarin 只, 条)
    speech: dict = field(default_factory=dict)    # how Play's spoken line is said: guides/languages.md
    _aliases: dict | None = field(default=None, repr=False, compare=False)

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


def _speech(meta) -> dict:
    """language.json "speech", keeping only what is well formed."""
    raw = meta if isinstance(meta, dict) else {}
    out = {k: {a: b for a, b in v.items() if isinstance(a, str) and isinstance(b, str)}
           for k in ("words", "numbers") if isinstance(v := raw.get(k), dict)}
    out |= {k: raw[k] for k in ("count", "measure") if isinstance(raw.get(k), str)}
    try:
        out.get("count", "").format(n="", word="", plural="", measure="")
        out["plural"] = [(re.compile(p), r) for p, r in raw.get("plural") or []]
    except (TypeError, ValueError, KeyError, IndexError, re.error):
        out.pop("count", None)
        out.pop("plural", None)
    return out


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
        lang.measures = {k.lower(): v[2] for k, v in words.items() if k.lower() in lang.words
                         and isinstance(v, list) and len(v) > 2 and isinstance(v[2], str)}
    lang.speech = _speech(meta.get("speech"))
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
    return replace(over, voice=over.voice or base.voice, font=over.font or base.font, strings=strings,
                   words=base.words | over.words, input=base.input | over.input, templates=_templates(strings),
                   blocked=base.blocked | over.blocked, measures=base.measures | over.measures,
                   speech=base.speech | over.speech, _aliases=None)


ENGLISH_LANGUAGE = Language(ENGLISH, "English", "English", Path())


_languages: dict | None = None
_interface: str | None = None
_second: str | None = None
_loaded_choice = False
_memo: dict = {}


def languages() -> dict:
    """Installed languages by code: the image's packs, then user packs, which win."""
    global _languages
    if not ENABLED:
        return {}
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
    if not ENABLED:
        return ENGLISH, None
    if not _loaded_choice:
        from .settings import get_language, get_second_language
        _interface, _second, _loaded_choice = get_language(), get_second_language(), True
    return _interface, _second


def interface_language() -> Language | None:
    """None when the interface is English (or its pack is gone)."""
    return languages().get(_choice()[0])


def second_language() -> Language | None:
    """English is a choice when the interface is another language; never the interface's own."""
    interface, second = _choice()
    if second == interface:
        return None
    return ENGLISH_LANGUAGE if second == ENGLISH else languages().get(second)


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
    content.reload_content()


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


def plural(lang: Language, word: str) -> str:
    """The pack's first plural rule that matches, on the first word ("estrellas de mar")."""
    head, sep, rest = word.partition(" ")
    rule = next(((p, r) for p, r in lang.speech.get("plural", []) if p.search(head)), None)
    return rule[0].sub(rule[1], head, count=1) + sep + rest if rule else word


def aliases(lang: Language) -> dict:
    """Typed form -> English word, so Play understands the language: the word, its
    unaccented spelling, its plurals, and the toneless reading."""
    if lang._aliases is None:
        out = {}
        for english, (word, reading) in lang.words.items():
            forms = {word.lower(), fold(word)}
            forms |= {plural(lang, f) for f in forms}
            if reading:
                forms.add(fold(reading).replace(" ", ""))
            for f in forms:
                out.setdefault(f, english)
        lang._aliases = out
    return lang._aliases


def english_word(word: str) -> str:
    """The English word Play reads a typed word in the parent's languages as, else the word."""
    w = word.lower()
    return next((a[w] for a in map(aliases, active_languages()) if w in a), w)


def echo(lang: Language, word: str) -> tuple | None:
    """(word, reading) in lang for a typed word, singular or plural; None when it only repeats it."""
    from .content import singularize
    english = english_word(word)
    hit = (english, "") if lang.code == ENGLISH else lang.words.get(english) or lang.words.get(singularize(english) or "")
    return hit if hit and hit[0].lower() != word.lower() else None


def _english(lang: Language, word: str) -> str | None:
    """The English word a token names in lang's words; lang's own spelling wins over English."""
    from .content import singularize
    w = word.lower()
    return aliases(lang).get(w) or next((e for e in (w, singularize(w)) if e in lang.words), None)


def _say_word(lang: Language, word: str) -> str:
    english = _english(lang, word)
    return word if english is None or word.lower() in aliases(lang) else lang.words[english][0]


def _say_count(lang: Language, n: str, english: str) -> str:
    word, speech = lang.words[english][0], lang.speech
    return speech.get("count", "{n} {word}").format(
        n=speech.get("numbers", {}).get(n, n), word=word, plural=word if n == "1" else plural(lang, word),
        measure=lang.measures.get(english, speech.get("measure", "")))


def spoken(lang: Language, line: str) -> str:
    """Play's English spoken line said in lang: its joining words, its words for things, and a
    number before a thing said its way. Anything else stays as typed, for lang's voice to read."""
    words, tokens, out, i = lang.speech.get("words", {}), _TOKEN_RE.findall(line), [], 0
    while i < len(tokens):
        tok, pair = tokens[i], " ".join(tokens[i:i + 2]).lower()
        if pair in words:
            out.append(words[pair])
            i += 1
        elif tok[0].isdigit() and (english := _english(lang, tokens[i + 1] if i + 1 < len(tokens) else "")):
            out.append(_say_count(lang, tok, english))
            i += 1
        else:
            out.append(words.get(tok.lower()) or _say_word(lang, tok))
        i += 1
    return " ".join(out)


def speech_item(text: str):
    """A Play line for tts.speak_many: in the interface language's voice when it has one."""
    lang = interface_language()
    return (spoken(lang, text), lang) if lang and lang.voice else text


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
