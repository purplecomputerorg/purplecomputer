import { PACK_FORMATS, type PackSkipped } from "@sdk/pack";
import { roomIcon } from "../examples";
import { buildPack, packFilename } from "../pack";
import type { Picture } from "../photo";
import { changed, countOf, draft, isQuiet, keep, notInPieces, phraseFor, pieces, titleOf, type Count, type Instrument, type Keepable, type Phrase, type RoomDraft, type RoomFile, type SynonymEntry, type WordEntry } from "../state";
import { miniScreen } from "./colors";
import { field, h } from "./dom";
import { SWATCH } from "./instrument";
import { putItOnPurple } from "./install";
import { pictureOr } from "./roomfiles";
import { clearEverythingButton, openPackButton } from "./packfile";
import { staysHere } from "./privacy";
import { sticker } from "./stickers";
import type { View } from "./view";

const chip = (face: Node | string, text: string) =>
  h("span", { class: "pack-item" }, typeof face === "string" ? h("span", { class: "pack-icon" }, face) : face, h("span", {}, text));

// Each thing as it shows on its own page: a picture's photo, a word's emoji, a key's sticker.
const FACES: Record<string, (item: Keepable) => Node> = {
  pictures: (i) => chip(h("img", { src: (i as Picture).sourceUrl, alt: "" }), titleOf(i as Picture)),
  letter_recordings: (i) => chip(sticker(Object.keys(draft.letters).find((k) => draft.letters[k] === i) ?? "?"), "🎤"),
  phrases: (i) => chip(isQuiet((i as Phrase).clip) ? "🔇" : "🎤", `“${(i as Phrase).text}”`),
  said: (i) => chip("🔊", `${(i as Phrase).text}: “${(i as Phrase).said}”`),
  words: (i) => chip(pictureOr((i as WordEntry).emoji), (i as WordEntry).word + voiceMark(phraseFor((i as WordEntry).word))),
  autocomplete_picks: (i) => chip("⭐", (i as Keepable & { word: string }).word),
  synonyms: (i) => chip("↪", `${(i as SynonymEntry).alias} means ${(i as SynonymEntry).word}`),
  instruments: (i) => chip(h("span", { class: "pick-swatch", style: `background:${SWATCH[(i as Instrument).base]}` }), titleOf(i as Instrument)),
  rooms: (i) => { const r = i as RoomDraft; return chip(roomIcon(r), titleOf(r)); },
  room_files: (i) => chip((i as RoomFile).kind === "images" ? "🖼️" : "🔊", (i as RoomFile).name),
  colors: () => chip(h("span", { class: "pack-colors" }, miniScreen(draft.theme!), ...["q", "a", "z"].map((k) => sticker(k))), "Screen and key colors"),
};

const voiceMark = (p?: Phrase) => (!p ? "" : p.said ? " 🔊" : isQuiet(p.clip) ? " 🔇" : " 🎤");

// A word's voice rides on the word's own chip, so each word is listed once.
function onePerWord(list: Count[]): Count[] {
  const voiced = new Set(list.find((p) => p.id === "words")?.items.map((w) => phraseFor((w as WordEntry).word)));
  return list.map((p) => (p.id === "phrases" || p.id === "said" ? { ...p, items: p.items.filter((i) => !voiced.has(i as Phrase)) } : p))
    .map((p) => ({ ...p, count: p.items.length })).filter((p) => p.count > 0);
}

const longDate = (date: string) => new Date(`${date}T12:00`).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });

// Older Purples refuse a pack newer than they read, or open it without some parts: one date covers both.
function newestNeeded(format: number, skipped: PackSkipped[]): string | null {
  const dates = [format > 1 ? PACK_FORMATS.find((f) => f.format === format)?.date : undefined, ...skipped.map((s) => s.date)];
  return dates.filter((d): d is string => !!d).sort().pop() ?? null;
}

const willItRun = (date: string) => h("details", { class: "will-it-run" },
  h("summary", {}, "Will my Purple run this?"),
  h("p", {}, `Yes, if your Purple was downloaded on ${longDate(date)} or later. If it's older, download Purple again first, or some of this won't show up.`));

// add: an Add button on each one.
const groups = (list: Count[], add?: (item: Keepable) => void) => onePerWord(list).map((p) => {
  const href = `#${p.section}`;
  return h("div", { class: "pack-group" },
    h("a", { class: "pack-heading", href }, countOf(p)),
    h("div", { class: "pack-items" }, ...p.items.map((i) => {
      const face = h("a", { class: "pack-link", href }, FACES[p.id](i));
      return add ? h("span", { class: "pack-add" }, face, h("button", { class: "btn secondary small", onclick: () => add(i) }, "Add")) : face;
    })));
});

export function downloadView(): View {
  const nameIn = h("input", { type: "text", value: draft.name, oninput: () => { draft.name = nameIn.value; changed(); } });
  const summary = h("div");
  const others = h("div");
  const status = h("div", { class: "status" });
  const button = h("button", { class: "btn logo" }, "Download my Purple Pack");
  const steps = putItOnPurple();

  function render() {
    const list = pieces();
    summary.replaceChildren(...(list.length ? groups(list) : [h("p", { class: "dim" }, "Nothing in it yet.")]));
    button.disabled = !list.length;
    const add = (i: Keepable) => { keep(i, true); render(); };
    const out = notInPieces();
    others.replaceChildren(...(out.length ? [h("div", { class: "card not-in" }, h("h3", {}, "Not in your Purple Pack"), ...groups(out, add))] : []));
  }
  render();

  const download = async () => {
    if (button.disabled) return;
    button.disabled = true;
    try {
      const { blob, format, skipped } = await buildPack((msg) => (status.textContent = `${msg}…`));
      const a = h("a", { href: URL.createObjectURL(blob), download: packFilename() });
      a.click();
      URL.revokeObjectURL(a.href);
      const since = newestNeeded(format, skipped);
      status.replaceChildren(h("p", {}, `Saved to your Downloads as ${packFilename()}. Next: copy it to your Purple Key or a USB drive.`),
        ...(since ? [willItRun(since)] : []));
      steps.firstElementChild!.replaceChildren("✓ Downloaded your Purple Pack.");
    } catch (e) {
      status.textContent = `Something went wrong while packing. (Technical: ${e instanceof Error ? e.message : String(e)})`;
    }
    button.disabled = false;
  };
  button.onclick = download;

  return {
    title: "Your Purple Pack",
    download,
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Everything you added goes into your Purple Pack."),
      staysHere("Your Purple Pack is made in your browser and saved to your downloads. No copy goes anywhere else."),
      h("div", { class: "card in-pack" }, h("h3", {}, "✓ In your Purple Pack"), summary),
      others,
      field("File name", h("div", { class: "row", style: "flex-wrap:nowrap" }, nameIn, h("span", { class: "mono dim" }, ".purplepack"))),
      h("p", { class: "dim small" }, "Purple lists your packs by this name, so pick one you'll know later, like Grandma's voice."),
      h("div", { class: "row", style: "margin-top:22px" }, button),
      status,
      h("h3", {}, "Then put it on Purple"),
      steps,
      h("p", { class: "dim small" }, "To change it later, ", openPackButton("open your Purple Pack"), " here, change what you like, and download it again. Or ", clearEverythingButton(), " to start fresh."),
    ),
  };
}
