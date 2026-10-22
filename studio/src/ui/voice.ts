import type { Clip } from "../audio";
import { play } from "../audio";
import { GRID_ROWS, LETTER_KEYS, PERCUSSION_ROW } from "@sdk/purple/sounds";
import { changed, draft, isQuiet, putPhrase } from "../state";
import { h, pageKeys } from "./dom";
import { keyLabel, sticker } from "./stickers";
import { addAllBar, keepButton, tryBar } from "./trybar";
import { liveScreen } from "./live";
import { staysHere } from "./privacy";
import { recordControl } from "./record";
import type { View } from "./view";

// The keys a recording can go on, laid out like the keyboard.
const KEY_ROWS = [PERCUSSION_ROW, ...GRID_ROWS].map((row) => row.filter((k) => LETTER_KEYS.includes(k)));
const nextToRecord = () => KEY_ROWS.flat().find((k) => !(k in draft.letters));

const tabs = (which: "letters" | "phrases") => h("div", { class: "tabs", role: "tablist" },
  h("a", { class: "tab", href: "#voice", "aria-selected": String(which === "letters") }, "Letters and numbers"),
  h("a", { class: "tab", href: "#voice/phrases", "aria-selected": String(which === "phrases") }, "Phrases"));

const hear = (clip: Clip) => (isQuiet(clip) ? h("span", { class: "dim small" }, "🔇 No sound")
  : h("button", { class: "btn secondary small", onclick: () => play(clip) }, "▶ Hear it"));
const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? " is" : "s are"}`;

function lettersView(): View {
  let current = nextToRecord() ?? "1";
  const keys = h("div", { class: "keyboard" });
  const now = h("div", { class: "voice-key" });
  const prompt = h("p", { class: "voice-prompt" });
  const pending = h("div");
  const actions = h("div");

  const select = (k: string) => {
    current = k;
    render();
  };
  function render() {
    // A straight grid, like Purple's Music room: a dot on a key tried, a check on a key added.
    keys.replaceChildren(...KEY_ROWS.flat().map((k) => h("button", {
      class: ["vkey", draft.letters[k] && (draft.letters[k].kept ? "kept" : "tried"), k === current && "current"].filter(Boolean).join(" "),
      "aria-label": k, onclick: () => select(k),
    }, sticker(k))));
    now.replaceChildren(sticker(current));
    const letter = draft.letters[current];
    prompt.replaceChildren(letter ? h("span", {}, h("b", {}, keyLabel(current)), " has your recording. Record again to change it.") : h("span", {}, "What should ", h("b", {}, keyLabel(current)), " say?"));
    actions.replaceChildren(letter ? h("div", { class: "stack" }, hear(letter.clip), tryBar(letter, () => { delete draft.letters[current]; changed(); render(); })) : "");
    pending.replaceChildren(addAllBar(Object.values(draft.letters), (n) => plural(n, "recording"), render) ?? "");
  }
  const onClip = (clip: Clip) => {
    draft.letters[current] = { clip, kept: draft.letters[current]?.kept };
    current = nextToRecord() ?? current;
    changed();
    render();
  };
  // Typing a key anywhere on the page jumps to it, and Purple says it.
  const unlisten = pageKeys((k) => {
    if (!LETTER_KEYS.includes(k)) return;
    select(k);
    liveScreen().key(k);
  });
  render();

  return {
    title: "Voice",
    editor: h(
      "section",
      {},
      tabs("letters"),
      h("p", { class: "lead" }, "In the Music room's Say Letters, each key plays what you record for it. Its name, \"D is for Dad,\" a sneeze, a song: anything goes."),
      h("div", { class: "card voice-card" },
        keys,
        h("div", { class: "voice-now" }, now, h("div", { class: "stack" }, prompt, recordControl(onClip), actions))),
      pending,
      h("p", { class: "dim small" }, "Letters and numbers you skip say their own names in Purple's voice; the other keys stay quiet until you give them something. Type a key on your keyboard to jump to it."),
      voiceStays(),
    ),
    live: { room: "music", letters: true },
    keys: () => { const mine = Object.keys(draft.letters).slice(0, 5); return mine.length ? mine : [..."abcde"]; },
    previewTitle: "What your kid hears",
    caption: "Purple's Music room in Say Letters. Keys you recorded play what you said.",
    cleanup: unlisten,
  };
}

const voiceStays = () => staysHere("Your recordings stay in your browser. Nobody else hears them unless you share your Purple Pack.");

function phrasesView(): View {
  const list = h("div", { class: "stack" });
  const text = h("input", { type: "text", placeholder: "Good night, Maya", "aria-label": "Phrase" });
  const status = h("div", { class: "status" });

  function render() {
    list.replaceChildren(...draft.phrases.map((p, i) => h("div", { class: "phrase-row" },
      h("strong", {}, p.text), h("div", { class: "row" }, hear(p.clip), keepButton(p, render),
        h("button", { class: "remove", title: "Remove", "aria-label": `Remove ${p.text}`, onclick: () => { draft.phrases.splice(i, 1); changed(); render(); } }, "✕")))),
      addAllBar(draft.phrases, (n) => plural(n, "phrase"), render) ?? "");
  }
  const onClip = (clip: Clip) => {
    const t = text.value.trim();
    if (!t) return void (status.textContent = "Type the phrase first, so Purple knows when to play it.");
    status.textContent = "";
    putPhrase(t, clip);
    text.value = "";
    render();
  };
  const record = recordControl(onClip);
  text.addEventListener("keydown", (e) => e.key === "Enter" && text.value.trim() && record.querySelector("button")?.click());
  render();

  return {
    title: "Voice",
    editor: h(
      "section",
      {},
      tabs("phrases"),
      h("p", { class: "lead" }, "Purple reads things out loud in Play when a kid types ", h("span", { class: "mono" }, "say"), " first, like ", h("span", { class: "mono" }, "say good night"), ". Record a phrase and they hear you instead."),
      list,
      h("div", { class: "card" }, h("div", { class: "phrase-new" }, text, record), status),
      h("p", { class: "dim small" }, "Capitals and spacing don't matter. Anything you haven't recorded, Purple says in its own voice."),
      voiceStays(),
    ),
    live: { room: "play" },
    previewTitle: "What your kid hears",
    caption: "Purple's Play room. Type say and your phrase, then press Enter.",
  };
}

export function voiceView(item: string | null): View {
  return item === "phrases" ? phrasesView() : lettersView();
}
