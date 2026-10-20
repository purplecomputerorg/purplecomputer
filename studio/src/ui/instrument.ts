import { INSTRUMENTS } from "@sdk/purple/sounds";
import { BASES, BASE_NAMES, defaults, type BaseName, type Params } from "@sdk/purple/synth";
import { playGridKey } from "../sounds";
import { changed, draft, freeName, isTheirs, titleOf, withSample, type Instrument } from "../state";
import { tryBar, yoursList } from "./trybar";
import { field, go, h, pageKeys } from "./dom";
import { liveScreen } from "./live";
import type { View } from "./view";

// Sounds to try first: Purple's four instruments with their sliders moved toward something familiar.
const SOUNDS: { title: string; blurb: string; base: BaseName; params: Params }[] = [
  { title: "Bells", blurb: "Long and ringing", base: "glockenspiel", params: { duration: 2.6, ring: 2.4, shimmer: 1.6 } },
  { title: "Music box", blurb: "Small and tinkly", base: "glockenspiel", params: { duration: 0.6, ring: 0.5, fundamental: 0.3, ping: 0.15 } },
  { title: "Harp", blurb: "Soft, slow plucks", base: "ukulele", params: { duration: 1.8, damping: 0.998, warmth: 0.3, softness: 5, pluck_pos: 0.4, body_mix: 0.15 } },
  { title: "Twangy guitar", blurb: "Bright and twangy", base: "ukulele", params: { warmth: 0.9, softness: 0, pluck_pos: 0.12, body_freq: 250, body_mix: 0.6 } },
  { title: "Xylophone", blurb: "Short, knocky wood", base: "marimba", params: { duration: 0.35, bar_decay: 9, wood: 1, sparkle: 0.2, tube: 0, mallet: 0.5 } },
  { title: "Soft marimba", blurb: "Round, with a long hum", base: "marimba", params: { duration: 1.5, attack_ms: 20, bar_decay: 1.5, wood: 0, sparkle: 0, tube: 0.6, tube_decay: 2, mallet: 0 } },
  { title: "Organ", blurb: "Big and steady", base: "accordion", params: { attack_ms: 40, detune: 0.5, harmonics: 14, rolloff: 1800, trem_rate: 6, trem_depth: 0.06 } },
  { title: "Harmonica", blurb: "Breathy, with a hand wobble", base: "accordion", params: { duration: 0.8, attack_ms: 50, detune: 0, harmonics: 14, rolloff: 2200, trem_rate: 5.5, trem_depth: 0.14, breath: 1, scoop: 40 } },
];

// Sounds made from the same Purple instrument share a color.
const SWATCH: Record<BaseName, string> = { glockenspiel: "#f2c94c", ukulele: "#e8875b", marimba: "#5fb3a1", accordion: "#7b8fe0" };

const taken = (n: string, except?: Instrument) => (INSTRUMENTS as readonly string[]).includes(n) || draft.instruments.some((i) => i !== except && i.name === n);

// Trying a sound replaces the last one tried, unless it was changed or added.
function tryOut(title: string, base: BaseName, params: Params) {
  const others = draft.instruments.filter(isTheirs);
  const name = freeName(title, (n) => (INSTRUMENTS as readonly string[]).includes(n) || others.some((i) => i.name === n));
  const n = name.match(/-(\d+)$/)?.[1];
  draft.instruments = withSample(draft.instruments, { name, title: n && !title.endsWith(n) ? `${title} ${n}` : title, base, params: { ...defaults(base), ...params } });
  changed();
  location.hash = `#instruments/${encodeURIComponent(name)}`;
}

function drop(inst: Instrument) {
  draft.instruments = draft.instruments.filter((i) => i !== inst);
  changed();
  go("#instruments");
}

function chooser(): View {
  return {
    title: "Instruments",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "A sound of your own for the Music room. Try one, change how it sounds, and add it to your Purple Pack when you like it."),
      yoursList(draft.instruments, (i) => ({ href: `#instruments/${encodeURIComponent(i.name)}`, title: titleOf(i), face: h("span", { class: "pick-swatch", style: `background:${SWATCH[i.base]}` }) }), drop),
      h("h3", {}, "Try a sound"),
      h("div", { class: "cards" }, ...SOUNDS.map((snd) =>
        h("button", { class: "pick", onclick: () => tryOut(snd.title, snd.base, snd.params) }, h("span", { class: "pick-swatch", style: `background:${SWATCH[snd.base]}` }), h("b", {}, snd.title), h("span", {}, snd.blurb)))),
      h("h3", {}, "Or a plain one from Purple"),
      h("div", { class: "row" }, ...BASE_NAMES.map((b) =>
        h("button", { class: "btn secondary small", onclick: () => tryOut(`My ${BASES[b].label.toLowerCase()}`, b, {}) }, BASES[b].label))),
    ),
    live: { room: "music" },
    previewTitle: "What your kid hears",
    caption: "Purple's Music room. Letter keys play notes, number keys play drums.",
  };
}

function editor(inst: Instrument): View {
  let lastKey = "q";
  let replayTimer = 0;
  const base = BASES[inst.base];

  const nameIn = h("input", { type: "text", value: titleOf(inst), maxLength: 24 });
  nameIn.onchange = () => {
    inst.title = nameIn.value.trim() || titleOf(inst);
    inst.sample = false;
    inst.name = freeName(inst.title, (n) => taken(n, inst));
    changed();
    location.hash = `#instruments/${encodeURIComponent(inst.name)}`;
  };

  const sliders = h("div", { class: "sliders" });
  const groups = [...new Set(base.params.map((s) => s.group))];
  for (const g of groups) {
    sliders.append(h("h3", {}, g));
    for (const spec of base.params.filter((s) => s.group === g)) {
      const pos = spec.scale?.toSlider(inst.params[spec.key]) ?? inst.params[spec.key];
      const val = h("span", { class: "val" }, fmt(pos, spec.unit));
      const range = h("input", { type: "range", min: spec.min, max: spec.max, step: spec.step, value: pos });
      range.oninput = () => {
        const s = Number(range.value);
        inst.params[spec.key] = spec.scale?.fromSlider(s) ?? s;
        inst.sample = false;
        val.textContent = fmt(s, spec.unit);
        changed();
        clearTimeout(replayTimer);
        replayTimer = window.setTimeout(() => playGridKey(inst.name, lastKey), 140);
      };
      sliders.append(h("div", { class: "slider" }, h("span", { class: "lbl" }, spec.label, h("small", {}, spec.hint)), range, val));
    }
  }

  // Typing on the page plays Purple's Music room, which has this instrument once edits settle.
  const unlisten = pageKeys((k) => {
    lastKey = k;
    liveScreen().key(k);
  });

  const reset = () => {
    Object.assign(inst.params, defaults(inst.base));
    changed();
    location.hash = `#instruments/${encodeURIComponent(inst.name)}`;
  };
  return {
    title: titleOf(inst),
    back: ["#instruments", "All instruments"],
    editor: h(
      "section",
      {},
      tryBar(inst, () => drop(inst)),
      h("div", { class: "card" }, field("Name", nameIn), h("p", { class: "dim small" }, `Made from Purple's ${base.label}.`)),
      h("div", { class: "card" }, h("p", { class: "dim small", style: "margin-top:0" }, "Type on your keyboard to play it. Moving a slider plays the last note again."), sliders, h("div", { class: "row between", style: "margin-top:20px" }, h("button", { class: "linkbtn dim", onclick: reset }, `Back to a plain ${base.label}`))),
    ),
    live: { room: "music", instrument: inst.name },
    previewTitle: "What your kid hears",
    caption: `Purple's Music room playing ${titleOf(inst)}. Moving a slider plays it in Purple Studio; Purple has the new sound a moment later.`,
    cleanup: () => { unlisten(); clearTimeout(replayTimer); },
  };
}

const num = (v: number) => `${Number.isInteger(v) ? v : v.toFixed(v < 1 ? 3 : 2).replace(/\.?0+$/, "")}`;
const fmt = (v: number, unit?: string) =>
  unit === "%" ? `${num(v * 100)}%` : unit === "×" ? `${num(v)}×` : `${num(v)}${unit ? " " + unit : ""}`;

export function instrumentsView(item: string | null): View {
  const inst = item ? draft.instruments.find((i) => i.name === item) : null;
  return inst ? editor(inst) : chooser();
}
