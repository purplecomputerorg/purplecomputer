import { parse, RoomError } from "@sdk/room";
import { MODEL, ROOM_SYSTEM, WORDS_SYSTEM, ask, extractJson, loadKey, storeKey } from "../llm";
import { changed, draft } from "../state";
import { clear, field, h } from "./dom";
import { addRoom } from "../pybridge";
import type { View } from "./view";

interface Suggestion { word: string; emoji: string; alias?: string }

export function helperView(): View {
  const keyIn = h("input", { type: "password", placeholder: "sk-ant-…", value: loadKey(), autocomplete: "off" });
  const remember = h("input", { type: "checkbox", checked: !!loadKey() });
  const persist = () => storeKey(remember.checked ? keyIn.value.trim() : null);
  keyIn.onchange = persist;
  remember.onchange = persist;
  const key = () => keyIn.value.trim();

  // Words ----------------------------------------------------------------------------
  const wordsIn = h("textarea", { rows: 3, placeholder: "Things our family says: Grandma's dog Biscuit, the red tractor, blueberry pancakes on Sundays" });
  const wordsStatus = h("div", { class: "status" });
  const picks = h("div", { class: "stack" });
  const addChecked = h("button", { class: "btn small", hidden: true }, "Add the checked ones");
  let suggestions: Suggestion[] = [];

  addChecked.onclick = () => {
    const boxes = [...picks.querySelectorAll<HTMLInputElement>("input[type=checkbox]")];
    boxes.forEach((box, i) => {
      if (!box.checked) return;
      const s = suggestions[i];
      if (s.alias) {
        draft.synonyms = [...draft.synonyms.filter((x) => x.alias !== s.alias), { alias: s.alias, word: s.word }];
      } else {
        draft.words = [...draft.words.filter((w) => w.word !== s.word), { word: s.word, emoji: s.emoji }];
      }
    });
    changed();
    wordsStatus.textContent = "Added. They are under Words now.";
    clear(picks);
    addChecked.hidden = true;
  };

  const suggestWords = async () => {
    if (!key()) { wordsStatus.textContent = "Paste an API key first."; return; }
    wordsStatus.textContent = "Asking…";
    try {
      const data = extractJson(await ask(key(), WORDS_SYSTEM, wordsIn.value.trim() || "everyday words a four year old likes")) as { words?: Suggestion[]; synonyms?: { alias: string; word: string }[] };
      const words = (data.words ?? []).filter((w) => w.word && w.emoji).map((w) => ({ word: w.word.toLowerCase().trim(), emoji: w.emoji }));
      const syns = (data.synonyms ?? []).filter((s) => s.alias && s.word).map((s) => ({ word: s.word.toLowerCase().trim(), emoji: "", alias: s.alias.toLowerCase().trim() }));
      suggestions = [...words, ...syns];
      clear(picks);
      for (const s of suggestions) {
        picks.append(h("label", { class: "row" }, h("input", { type: "checkbox", checked: true }),
          s.alias ? h("span", {}, h("b", {}, s.alias), h("span", { class: "dim" }, " → "), s.word) : h("span", {}, h("span", { class: "emoji-big" }, s.emoji), " ", h("b", {}, s.word))));
      }
      addChecked.hidden = !suggestions.length;
      wordsStatus.textContent = suggestions.length ? "Untick anything that does not fit." : "Nothing usable came back. Try again with more detail.";
    } catch (e) {
      wordsStatus.textContent = e instanceof Error ? e.message : String(e);
    }
  };

  // Rooms ----------------------------------------------------------------------------
  const roomIn = h("textarea", { rows: 3, placeholder: "A room where each letter is an animal that makes its sound, and the space bar plays a little tune" });
  const roomStatus = h("div", { class: "status" });
  const roomPreview = h("pre", { class: "small", hidden: true });
  const addTheRoom = h("button", { class: "btn small", hidden: true }, "Add this room");
  let pending: ReturnType<typeof parse> | null = null;

  addTheRoom.onclick = () => {
    if (!pending) return;
    const name = draft.rooms.some((r) => r.program.name === pending!.name) ? `${pending.name}-${draft.rooms.length + 1}` : pending.name;
    const room = addRoom({ ...pending, name });
    location.hash = `#rooms/${encodeURIComponent(room.program.name)}`;
  };

  const makeRoom = async () => {
    if (!key()) { roomStatus.textContent = "Paste an API key first."; return; }
    roomStatus.textContent = "Asking…";
    addTheRoom.hidden = true;
    roomPreview.hidden = true;
    try {
      const program = parse(extractJson(await ask(key(), ROOM_SYSTEM, roomIn.value.trim() || "a calm room about the ocean")));
      pending = program;
      roomPreview.textContent = JSON.stringify(program, null, 2);
      roomPreview.hidden = false;
      addTheRoom.hidden = false;
      roomStatus.textContent = `${program.title ?? program.name}: ${program.rules.length} rules. Purple checked it and would run it.`;
    } catch (e) {
      roomStatus.textContent = e instanceof RoomError ? `The reply was not a room Purple can run: ${e.message}. Try again.` : e instanceof Error ? e.message : String(e);
    }
  };

  return {
    title: "Helper",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "A blank box is the hardest part. If you have a Claude API key, this page uses it to draft a word list or a whole room from a sentence or two. Everything it makes lands in your pack as plain data you can see and change; Purple itself never talks to anything."),
      h("div", { class: "card" },
        field("Your Claude API key", keyIn),
        h("label", { class: "row small dim" }, remember, ` Remember it in this browser (it is stored on this computer only, and sent only to api.anthropic.com when you press a button below). Model: ${MODEL}.`)),
      h("h3", {}, "Words from a description"),
      h("div", { class: "card" }, wordsIn, h("div", { class: "row", style: "margin-top:10px" }, h("button", { class: "btn small", onclick: suggestWords }, "Suggest words"), wordsStatus), picks, h("p", { style: "margin-top:10px" }, addChecked)),
      h("h3", {}, "A room from a description"),
      h("div", { class: "card" }, roomIn, h("div", { class: "row", style: "margin-top:10px" }, h("button", { class: "btn small", onclick: makeRoom }, "Draft a room"), roomStatus), roomPreview, h("p", { style: "margin-top:10px" }, addTheRoom)),
      h("div", { class: "note" }, h("strong", {}, "What this costs and sends: "), "one request per button press, with the text in the box, to Anthropic under your key. Nothing from your photos, recordings, or the rest of the pack. Without a key this page does nothing, and the rest of Studio never needs one."),
    ),
    stage: () => null,
  };
}
