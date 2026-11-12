import type { Clip } from "../audio";
import { GRID_ROWS, LETTER_KEYS, PERCUSSION_ROW } from "@sdk/purple/sounds";
import { changed, draft, whileShown } from "../state";
import { h, seg } from "./dom";
import { keyLabel, sticker } from "./stickers";
import { tryBar } from "./trybar";
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
  const picker = h("div");

  const select = (k: string) => {
    current = k;
    render();
  };
  // A straight grid, like Purple's Music room: a check on a key in the Purple Pack, a dot on one left out.
  const paintKeys = () => keys.replaceChildren(...KEY_ROWS.flat().map((k) => h("button", {
    class: ["vkey", draft.letters[k] && (draft.letters[k].kept ? "kept" : "left-out"), k === current && "current"].filter(Boolean).join(" "),
    "aria-label": k, onclick: () => select(k),
  }, sticker(k))));
  whileShown(keys, paintKeys);
  function render() {
    paintKeys();
    now.replaceChildren(sticker(current));
    const letter = draft.letters[current];
    const name = h("b", {}, keyLabel(current));
    prompt.replaceChildren("What should ", name, " say?");
    const clear = () => { delete draft.letters[current]; changed(); render(); };
    // Picking one plays the key in Purple, so it's heard the way the kid will hear it.
    const plays = (after: boolean) => () => { letter!.after = after; changed(); render(); liveScreen().keyAfterEdits(current); };
    const order = (after: boolean, words: string): Parameters<typeof seg>[0] => [h("span", {}, words, sticker(current)), after === !!letter!.after, plays(after)];
    picker.replaceChildren(soundPicker({ clip: letter?.clip, said: letter?.said, placeholder: "Hi sweetie, it's Grandma!", onClip, onClear: clear }),
      ...(letter ? [h("div", { class: "letter-order" }, seg(order(true, "After"), order(false, "Instead of"))), tryBar(letter)] : []));
  }
  // A new sound plays after Purple says the key; a changed one keeps its choice.
  const onClip = (clip: Clip, said?: string) => {
    const was = draft.letters[current];
    draft.letters[current] = { clip, said, kept: was?.kept ?? true, after: was ? !!was.after : true };
    changed();
    render();
  };
  // A key typed on the page or in Purple jumps to it, and Purple says it.
  const unlisten = liveScreen().followKeys((k) => LETTER_KEYS.includes(k) && select(k));
  render();

  return {
    title: "Letters",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "In the Music room, switch to ", h("b", {}, "Letters"), " and each key plays what you give it: \"D is for Dad,\" Grandma saying hi, a sneeze, a song, or words for Purple to say."),
      h("div", { class: "card voice-card" },
        keys,
        h("div", { class: "voice-now" }, now, h("div", { class: "stack" }, prompt, picker))),
      h("p", { class: "dim small" }, "Keys you skip play Purple's own: letters and numbers say their names, and ; , . / make silly sounds. Type a key on your keyboard to jump to it and hear it."),
      voiceStays(),
    ),
    live: { room: "music", letters: true },
    keys: () => { const mine = Object.keys(draft.letters).slice(0, 5); return mine.length ? mine : [..."abcde"]; },
    caption: "Purple's Music room, switched to Letters. Keys you gave a sound play it.",
    cleanup: unlisten,
  };
}
