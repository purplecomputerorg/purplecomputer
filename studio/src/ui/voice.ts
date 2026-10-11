import type { Clip } from "../audio";
import { play } from "../audio";
import { GRID_ROWS, LETTER_KEYS, PERCUSSION_ROW } from "@sdk/purple/sounds";
import { changed, draft } from "../state";
import { h, pageKeys } from "./dom";
import { sticker } from "./stickers";
import { liveScreen } from "./live";
import { recordControl } from "./record";
import type { View } from "./view";

// The keys that have a voice clip, laid out like the keyboard.
const KEY_ROWS = [PERCUSSION_ROW, ...GRID_ROWS].map((row) => row.filter((k) => LETTER_KEYS.includes(k)));

const tabs = (which: "letters" | "phrases") => h("div", { class: "tabs", role: "tablist" },
  h("a", { class: "tab", href: "#voice", "aria-selected": String(which === "letters") }, "Letters and numbers"),
  h("a", { class: "tab", href: "#voice/phrases", "aria-selected": String(which === "phrases") }, "Phrases"));

const clipActions = (clip: Clip, onRemove: () => void) => h("div", { class: "row" },
  h("button", { class: "btn secondary small", onclick: () => play(clip) }, "▶ Hear it"),
  h("button", { class: "linkbtn dim small", onclick: onRemove }, "Remove"));

function lettersView(): View {
  let current = LETTER_KEYS.find((k) => !(k in draft.letters)) ?? "a";
  const keys = h("div", { class: "keyboard" });
  const big = h("div", { class: "big-letter" });
  const count = h("p", { class: "dim" });
  const actions = h("div");

  const select = (k: string) => {
    current = k;
    render();
  };
  function render() {
    keys.replaceChildren(...KEY_ROWS.map((row) => h("div", { class: "r" }, ...row.map((k) =>
      h("button", { class: ["vkey", k in draft.letters && "done", k === current && "current"].filter(Boolean).join(" "), "aria-label": k, onclick: () => select(k) }, sticker(k))))));
    big.textContent = current;
    count.textContent = `${Object.keys(draft.letters).length} of ${LETTER_KEYS.length} recorded. Keys you skip keep Purple's voice.`;
    const clip = draft.letters[current];
    actions.replaceChildren(clip ? clipActions(clip, () => { delete draft.letters[current]; changed(); render(); }) : "");
  }
  const onClip = (clip: Clip) => {
    draft.letters[current] = clip;
    current = LETTER_KEYS.find((k) => !(k in draft.letters)) ?? current;
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
      h("p", { class: "lead" }, "In the Music room, every key can say its own name. Record yours: pick a key, press Record, say it, press Stop."),
      h("div", { class: "card voice-card" }, keys, h("div", { class: "voice-now" }, big, h("div", { class: "stack" }, recordControl(onClip), actions))),
      count,
      h("p", { class: "dim small" }, "Tip: type a key on your keyboard to jump to it. Studio moves to the next key after each recording."),
    ),
    live: { room: "music", letters: true },
    keys: () => { const mine = Object.keys(draft.letters).slice(0, 5); return mine.length ? mine : [..."abcde"]; },
    previewTitle: "What your kid hears",
    caption: "Purple's Music room, saying letters. Keys you recorded say them in your voice.",
    cleanup: unlisten,
  };
}

function phrasesView(): View {
  const list = h("div", { class: "stack" });
  const text = h("input", { type: "text", placeholder: "Good night, Maya", "aria-label": "Phrase" });
  const status = h("div", { class: "status" });

  function render() {
    list.replaceChildren(...draft.phrases.map((p, i) => h("div", { class: "phrase-row" },
      h("strong", {}, p.text), clipActions(p.clip, () => { draft.phrases.splice(i, 1); changed(); render(); }))));
  }
  const onClip = (clip: Clip) => {
    const t = text.value.trim();
    if (!t) return void (status.textContent = "Type the phrase first, so Purple knows when to play it.");
    status.textContent = "";
    draft.phrases = [...draft.phrases.filter((p) => p.text.toLowerCase() !== t.toLowerCase()), { text: t, clip }];
    text.value = "";
    changed();
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
    ),
    live: { room: "play" },
    previewTitle: "What your kid hears",
    caption: "Purple's Play room. Type say and your phrase, then press Enter.",
  };
}

export function voiceView(item: string | null): View {
  return item === "phrases" ? phrasesView() : lettersView();
}
