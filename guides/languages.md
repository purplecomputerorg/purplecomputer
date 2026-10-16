# Languages

Purple ships Spanish (`packs/lang-es`) and Mandarin Chinese, Simplified (`packs/lang-zh`), as language packs. A parent picks two things in the parent menu:

- **Language**: the interface (menus, hints, messages) in that language, and Play's voice: Play says its answers in it (see Speech).
- **Second Language**: Play shows and says that language's word next to the words a kid types (`dog` gives 🐶 and "🐶 perro" or "🐶 狗 gǒu"), and understands words typed in it (`perro`, `gou`, `狗`). When the Language isn't English, English is a choice here too.

Both languages' words type the same emoji and colors as their English. When a word is in both the Language and English (Spanish `papa` is potato, English `papa` is dad), the Language wins; a second language never takes an English word.

Canvas UI only. The Textual UI stays English.

Pack file format: `studio/PACK_FORMAT.md`. Code: `purple_tui/i18n.py`.

## Why strings are translated where they are drawn

The UI changes all the time, so the code never wraps strings in `t()`. `Gfx.text`, `Gfx.layout` and `draw_key_hint` look up the whole English string as drawn; a hit is replaced, a miss stays English. So:

- New UI works the day it lands, in English, until its strings are translated.
- Reworded English silently falls back to English. Nothing breaks and there are no version checks; a pack made for any version works on any other.
- f-strings become templates: `"{0} blocks left"` matches `"3 blocks left"`, and the value in a slot is itself looked up.
- What a kid typed must not be translated: pass `tr=False` (the text field and Play's history do).
- A label drawn in pieces (split around a keycap, or a `Name: value` menu row) is translated whole first, then split.

Keeping up: `just python scripts/i18n_strings.py` counts what each pack is missing, `-v` lists them with file and line, `<code> --json` prints them ready to fill. Translate with an LLM and have a speaker review. The extractor errs toward listing too much; an extra key is harmless because nothing draws it.

## Chinese

- **Font:** `NotoSansSC-Purple.ttf` in the pack, cut down to the 3,500 most common characters plus every character in the pack's files. Language pack fonts join the fallback chain (`gfx.FALLBACK_FACES`) at startup. Rebuild it after changing strings: `scripts/build_lang_zh.py --font-only`.
- **Wrapping:** `Gfx.layout` breaks between any two Chinese characters.
- **Typing:** Play shows the characters a typed pinyin run could be, words with a picture first; the number keys 1 to 9 pick one. The candidates come from `words.json` readings, then `input.json` (common words by frequency, built by `scripts/build_lang_zh.py`, with a blocklist so nothing crude is offered).
- **Speech:** text containing Chinese characters is spoken with the Mandarin voice automatically.

## Profanity

`speech_filter.filter_speech` checks each installed pack's `blocked.txt` before the English list, so a Spanish or Chinese word is silenced even when the kid's settings are English. The Chinese typing dictionary drops the same words (`scripts/build_lang_zh.py` reads `blocked.txt`, plus a wider list of things typing shouldn't offer). `tests/canvas/test_languages.py` checks that every Play word in every pack can still be said, which is how a collision like Spanish "fucsia" against the English list gets caught. To edit a list, decode it, change it, and encode it again (`base64 -d` / `base64`).

## Speech

Play works in English inside; only its spoken line is translated, by `i18n.spoken`, from the pack's `language.json` `speech` object:

- `words`: Play's English joining words (`plus`, `divided by`, `equals`, `what is`...) in the language.
- Known words become the pack's word; a word typed in the language stays as typed. Anything else (names, sentences) is left for the language's voice to read.
- A number before a thing is said with `count`, a template over `{n}`, `{word}`, `{plural}` and `{measure}`: Spanish `"{n} {plural}"` ("2 perros"), Mandarin `"{n}{measure}{word}"` ("两只狗"). `numbers` respells a number there (Mandarin 2 is 两).
- `plural`: `[regex, replacement]` rules tried in order on the first word ("estrellas de mar"); they also make the plural forms Play understands typed.
- `measure`: the default counting word; a word's own goes third in its `words.json` entry (`"dog": ["狗", "gǒu", "只"]`).

Numbers stay digits: each voice reads them in its own language.

Each pack names a Piper model (`es_MX-ald-medium`, `zh_CN-huayan-medium`, about 63 MB each, downloaded by the image build and `scripts/install_piper_voice.sh`). The speech worker loads a language's model on first use and keeps it. There is no flite fallback for other languages: no Piper means no speech in them. The Mandarin voice's tones come from espeak-ng's phonemizer; have a native speaker listen before relying on it.

## Adding a language

Copy `packs/lang-es`, change `language.json`, fill `strings.json` from the extractor and `words.json` from the emoji and color lists, and pick a Piper voice (bundle it in the pack as `content/<voice>.onnx` to deliver it without a new image). Build it with `just build-packs`-style tar and install it like any pack (`studio/PACK_FORMAT.md`, "Where packs live"); it takes effect at the next start.
