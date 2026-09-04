import { play } from "../audio";
import { KEY_COLORS } from "../purple/art";
import { GRID_ROWS, INSTRUMENTS, PERCUSSION_ROW, SAMPLE_PITCHES, noteFrequency, pitchFor } from "../purple/sounds";
import { BASES, BASE_NAMES, SYNTH_RATE, defaults, renderNote, type BaseName } from "../purple/synth";
import { changed, draft, slug, type Instrument } from "../state";
import { field, h } from "./dom";
import { musicFrame } from "./facsimile";
import type { View } from "./view";

const NOTE_CACHE = new Map<string, Float32Array>();

function playKey(inst: Instrument, key: string): void {
  const row = GRID_ROWS.findIndex((r) => r.includes(key));
  if (row < 0) return;
  const { note, octave } = pitchFor(row, GRID_ROWS[row].indexOf(key));
  const id = `${inst.base}|${JSON.stringify(inst.params)}|${note}${octave}`;
  let samples = NOTE_CACHE.get(id);
  if (!samples) {
    if (NOTE_CACHE.size > 200) NOTE_CACHE.clear();
    samples = renderNote(inst.base, inst.params, noteFrequency(note, octave));
    NOTE_CACHE.set(id, samples);
  }
  play({ samples, rate: SYNTH_RATE });
}

function chooser(): View {
  const nameIn = h("input", { type: "text", placeholder: "Kitchen marimba" });
  const status = h("div", { class: "status" });
  const start = (base: BaseName) => {
    const name = slug(nameIn.value) || `my-${base}`;
    if ((INSTRUMENTS as readonly string[]).includes(name) || draft.instruments.some((i) => i.name === name)) {
      status.textContent = `There is already a ${name}. Pick another name.`;
      return;
    }
    draft.instruments.push({ name, base, params: defaults(base) });
    changed();
    location.hash = `#instruments/${encodeURIComponent(name)}`;
  };
  return {
    title: "Instruments",
    path: "content/<name>/c1.wav … d7.wav",
    tag: "real",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Purple's four instruments are made from math: a few equations for a bar, a string, a reed, a bell. Start from one and move its numbers."),
      h("div", { class: "card" }, field("What to call it", nameIn), status, h("div", { class: "bases" }, ...BASE_NAMES.map((b) =>
        h("button", { class: "base", onclick: () => start(b) }, h("b", {}, `Start from ${BASES[b].label}`), h("span", {}, BASES[b].blurb))))),
      draft.instruments.length ? h("p", { class: "dim small" }, "Yours so far: ", ...draft.instruments.flatMap((i, n) => [n ? ", " : "", h("a", { href: `#instruments/${encodeURIComponent(i.name)}` }, i.name)])) : null,
      h("div", { class: "note" }, h("strong", {}, "What Purple does with this: "), `the Music room adds it after Purple's four, so Enter cycles to it and the code panel can choose it by name. Studio renders it into ${SAMPLE_PITCHES.length} note files, one per pitch the grid can reach, using the same math Purple's own instruments were made with, and saves your slider numbers next to them so Purple can re-render it itself.`),
    ),
    stage: () => musicFrame({ instrument: "Marimba" }),
    stageTitle: "What your kid hears",
    caption: "The Music room. Letter rows play notes, the number row plays percussion. Enter cycles instruments.",
  };
}

function editor(inst: Instrument): View {
  let lastKey = "q";
  let replayTimer = 0;
  const base = BASES[inst.base];

  const nameIn = h("input", { type: "text", value: inst.name });
  nameIn.onchange = () => {
    const name = slug(nameIn.value) || inst.name;
    if (draft.instruments.some((i) => i !== inst && i.name === name) || (INSTRUMENTS as readonly string[]).includes(name)) {
      nameIn.value = inst.name;
      return;
    }
    inst.name = name;
    changed();
    location.hash = `#instruments/${encodeURIComponent(name)}`;
  };

  const sliders = h("div", { class: "sliders" });
  const groups = [...new Set(base.params.map((s) => s.group))];
  for (const g of groups) {
    sliders.append(h("h3", {}, g));
    for (const spec of base.params.filter((s) => s.group === g)) {
      const val = h("span", { class: "val" }, fmt(inst.params[spec.key], spec.unit));
      const range = h("input", { type: "range", min: spec.min, max: spec.max, step: spec.step, value: inst.params[spec.key] });
      range.oninput = () => {
        inst.params[spec.key] = Number(range.value);
        val.textContent = fmt(inst.params[spec.key], spec.unit);
        changed();
        clearTimeout(replayTimer);
        replayTimer = window.setTimeout(() => playKey(inst, lastKey), 140);
      };
      sliders.append(h("div", { class: "slider" }, h("span", { class: "lbl" }, spec.label), range, val));
    }
  }

  const grid = h("div", { class: "grid" });
  const keyButtons = new Map<string, HTMLButtonElement>();
  const press = (k: string) => {
    keyButtons.get(lastKey)?.classList.remove("on");
    lastKey = k;
    keyButtons.get(k)?.classList.add("on");
    playKey(inst, k);
    changed();
  };
  grid.append(h("div", { class: "r" }, ...PERCUSSION_ROW.map((k) => h("button", { class: "k perc", disabled: true, title: "Percussion is shared by every instrument" }, k))));
  for (const row of GRID_ROWS) {
    grid.append(h("div", { class: "r" }, ...row.map((k) => {
      const b = h("button", { class: "k", style: `border-bottom-color:${KEY_COLORS[k]}`, onclick: () => press(k) }, k === "/" ? "÷" : k);
      keyButtons.set(k, b);
      return b;
    })));
  }
  keyButtons.get(lastKey)?.classList.add("on");

  const onKey = (e: KeyboardEvent) => {
    if ((e.target as HTMLElement).tagName === "INPUT" && (e.target as HTMLInputElement).type === "text") return;
    if (keyButtons.has(e.key) && !e.repeat) press(e.key);
  };
  document.addEventListener("keydown", onKey);

  const reset = () => {
    Object.assign(inst.params, defaults(inst.base));
    changed();
    location.hash = `#instruments/${encodeURIComponent(inst.name)}`;
  };
  const remove = () => {
    draft.instruments = draft.instruments.filter((i) => i !== inst);
    NOTE_CACHE.clear();
    changed();
    location.hash = "#instruments";
  };

  return {
    title: inst.name,
    path: `content/${inst.name}/c1.wav … d7.wav  ·  content/instruments/${inst.name}.json`,
    tag: "real",
    editor: h(
      "section",
      {},
      h("div", { class: "card" }, h("div", { class: "row between" }, h("div", { style: "flex:1;min-width:200px" }, field("Name", nameIn)), h("span", { class: "dim small" }, `Started from ${base.label}. ${base.blurb}`))),
      h("div", { class: "card" }, h("p", { class: "dim small" }, "Click a key, or type on your keyboard. Sliding a control replays the last key."), grid),
      h("div", { class: "card" }, sliders, h("div", { class: "row between", style: "margin-top:20px" }, h("button", { class: "linkbtn dim", onclick: reset }, `Back to ${base.label}'s numbers`), h("button", { class: "linkbtn dim", onclick: remove }, "Remove this instrument"))),
    ),
    stage: () => musicFrame({ instrument: inst.name, activeKey: lastKey }),
    stageTitle: "What your kid hears",
    caption: `The Music room with ${inst.name} chosen. Each key plays one of the ${SAMPLE_PITCHES.length} rendered notes.`,
    cleanup: () => { document.removeEventListener("keydown", onKey); clearTimeout(replayTimer); },
  };
}

const fmt = (v: number, unit?: string) => `${Number.isInteger(v) ? v : v.toFixed(v < 1 ? 3 : 2).replace(/\.?0+$/, "")}${unit ? " " + unit : ""}`;

export function instrumentsView(item: string | null): View {
  const inst = item ? draft.instruments.find((i) => i.name === item) : null;
  return inst ? editor(inst) : chooser();
}
