import type { Clip } from "../audio";
import { GRID_ROWS, LETTER_KEYS, PERCUSSION_ROW } from "@sdk/purple/sounds";
import { changed, draft } from "../state";
import { h, pageKeys } from "./dom";
import { keyLabel, sticker } from "./stickers";
import { addAllBar, plural, tryBar } from "./trybar";
import { liveScreen } from "./live";
import { soundPicker, voiceStays } from "./record";
import type { View } from "./view";

// The keys a sound can go on, laid out like the keyboard.
const KEY_ROWS = [PERCUSSION_ROW, ...GRID_ROWS].map((row) => row.filter((k) => LETTER_KEYS.includes(k)));
const nextToGive = () => KEY_ROWS.flat().find((k) => !(k in draft.letters));

export function keysView(): View {
  let current = nextToGive() ?? "1";
  const keys = h("div", { class: "keyboard" });
  const now = h("div", { class: "voice-key" });
  const prompt = h("p", { class: "voice-prompt" });
  const pending = h("div");
  const picker = h("div");

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
    const name = h("b", {}, keyLabel(current));
    prompt.replaceChildren("What should ", name, " say?");
    const clear = () => { delete draft.letters[current]; changed(); render(); };
    picker.replaceChildren(soundPicker({ clip: letter?.clip, said: letter?.said, placeholder: "Hi sweetie, it's Grandma!", onClip, onClear: clear }),
      letter ? tryBar(letter, clear) : "");
    pending.replaceChildren(addAllBar(Object.values(draft.letters), (n) => plural(n, "letter"), render) ?? "");
  }
  const onClip = (clip: Clip, said?: string) => {
    draft.letters[current] = { clip, said, kept: draft.letters[current]?.kept };
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
    title: "Letters",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "In the Music room's Say Letters, each key plays what you give it. Record its name in your voice, \"D is for Dad,\" a sneeze, a song, or type words for Purple to say."),
      h("div", { class: "card voice-card" },
        keys,
        h("div", { class: "voice-now" }, now, h("div", { class: "stack" }, prompt, picker))),
      pending,
      h("p", { class: "dim small" }, "Letters and numbers you skip say their own names in Purple's voice; the other keys stay quiet until you give them something. Type a key on your keyboard to jump to it."),
      voiceStays(),
    ),
    live: { room: "music", letters: true },
    keys: () => { const mine = Object.keys(draft.letters).slice(0, 5); return mine.length ? mine : [..."abcde"]; },
    previewTitle: "What your kid hears",
    caption: "Purple's Music room in Say Letters. Keys you gave a sound play it.",
    cleanup: unlisten,
  };
}
