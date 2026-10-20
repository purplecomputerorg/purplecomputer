import { buildPack, packFilename } from "../pack";
import type { Picture } from "../photo";
import { addAll, changed, countOf, draft, pieces, titleOf, tryingPieces, type Count, type Instrument, type Keepable, type Phrase, type RoomDraft, type RoomFile, type SynonymEntry, type WordEntry } from "../state";
import { miniScreen } from "./colors";
import { field, h } from "./dom";
import { SWATCH } from "./instrument";
import { putItOnPurple } from "./install";
import { clearEverythingButton, openPackButton } from "./packfile";
import { staysHere } from "./privacy";
import { ICONS } from "./rooms";
import { sticker } from "./stickers";
import type { View } from "./view";

const chip = (face: Node | string, text: string) =>
  h("span", { class: "pack-item" }, typeof face === "string" ? h("span", { class: "pack-icon" }, face) : face, h("span", {}, text));

// Each thing as it shows on its own page: a picture's photo, a word's emoji, a key's sticker.
const FACES: Record<string, (item: Keepable) => Node> = {
  pictures: (i) => chip(h("img", { src: (i as Picture).sourceUrl, alt: "" }), titleOf(i as Picture)),
  letter_recordings: (i) => chip(sticker(Object.keys(draft.letters).find((k) => draft.letters[k] === i) ?? "?"), "🎤"),
  phrases: (i) => chip("🎤", `“${(i as Phrase).text}”`),
  words: (i) => chip((i as WordEntry).emoji, (i as WordEntry).word),
  autocomplete_picks: (i) => chip("⭐", (i as Keepable & { word: string }).word),
  synonyms: (i) => chip("↪", `${(i as SynonymEntry).alias} means ${(i as SynonymEntry).word}`),
  instruments: (i) => chip(h("span", { class: "pick-swatch", style: `background:${SWATCH[(i as Instrument).base]}` }), titleOf(i as Instrument)),
  rooms: (i) => { const r = i as RoomDraft; return chip(r.made ? ICONS[r.made.kind] : "🐍", titleOf(r)); },
  room_files: (i) => chip((i as RoomFile).kind === "images" ? "🖼️" : "🔊", (i as RoomFile).name),
  colors: () => chip(h("span", { class: "pack-colors" }, miniScreen(draft.theme!), ...["q", "a", "z"].map((k) => sticker(k))), "Screen and key colors"),
};

const groups = (list: Count[]) => list.map((p) => h("div", { class: "pack-group" },
  h("a", { class: "pack-heading", href: `#${p.section}` }, countOf(p)),
  h("div", { class: "pack-items" }, ...p.items.map(FACES[p.id]))));

export function downloadView(): View {
  const nameIn = h("input", { type: "text", value: draft.name, oninput: () => { draft.name = nameIn.value; changed(); } });
  const summary = h("div");
  const trying = h("div");
  const leftOut = h("p", { class: "dim small" });
  const status = h("div", { class: "status" });
  const button = h("button", { class: "btn logo" }, "Download my Purple Pack");

  function render() {
    const list = pieces();
    summary.replaceChildren(...(list.length ? groups(list) : [h("p", { class: "dim" }, "Nothing added yet. Try something, then press Add to my Purple Pack.")]));
    button.disabled = !list.length;
    const left = tryingPieces();
    const n = left.reduce((sum, p) => sum + p.count, 0);
    leftOut.textContent = n ? `This leaves out the ${n === 1 ? "change" : `${n} changes`} you haven't added.` : "";
    trying.replaceChildren(...(n ? [h("div", { class: "card unadded" },
      h("h3", {}, n === 1 ? "You have a change you haven't added" : `You have ${n} changes you haven't added`),
      h("p", {}, "You tried these but didn't press Add, so they won't be in your Purple Pack."),
      ...groups(left),
      h("button", { class: "btn", onclick: () => { addAll(); changed(); render(); } }, n === 1 ? "Add it to my Purple Pack" : "Add them all to my Purple Pack"))] : []));
  }
  render();

  button.onclick = async () => {
    button.disabled = true;
    try {
      const blob = await buildPack((msg) => (status.textContent = `${msg}…`));
      const a = h("a", { href: URL.createObjectURL(blob), download: packFilename() });
      a.click();
      URL.revokeObjectURL(a.href);
      status.textContent = `Downloaded ${packFilename()}.`;
    } catch (e) {
      status.textContent = `Something went wrong while packing. (Technical: ${e instanceof Error ? e.message : String(e)})`;
    }
    button.disabled = false;
  };

  return {
    title: "Your Purple Pack",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Everything you added goes into your Purple Pack."),
      staysHere("Your Purple Pack is made in your browser and saved to your downloads. No copy goes anywhere else."),
      trying,
      h("div", { class: "card" }, h("h3", { style: "margin-top:0" }, "In your Purple Pack"), summary),
      field("File name", h("div", { class: "row", style: "flex-wrap:nowrap" }, nameIn, h("span", { class: "mono dim" }, ".purplepack"))),
      h("div", { class: "row", style: "margin-top:22px" }, button),
      leftOut,
      status,
      h("h3", {}, "Then put it on Purple"),
      putItOnPurple(),
      h("p", { class: "dim small" }, "To change it later, ", openPackButton("open your Purple Pack"), " here, change what you like, and download it again. Or ", clearEverythingButton(), " to start fresh."),
    ),
  };
}
