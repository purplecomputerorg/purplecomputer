import { INSTRUMENTS } from "@sdk/purple/sounds";
import { BASES, BASE_NAMES, defaults, type BaseName } from "@sdk/purple/synth";
import { playGridKey } from "../sounds";
import { changed, draft, slug, type Instrument } from "../state";
import { field, h, pageKeys } from "./dom";
import { musicPreview } from "./facsimile";
import type { View } from "./view";

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
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Purple's Music room has four instruments. Start from one, change how it sounds, and it becomes a fifth."),
      h("div", { class: "card" }, field("What to call it", nameIn), status, h("div", { class: "bases" }, ...BASE_NAMES.map((b) =>
        h("button", { class: "base", onclick: () => start(b) }, h("b", {}, `Start from ${BASES[b].label}`), h("span", {}, BASES[b].blurb))))),
      draft.instruments.length ? h("p", { class: "dim small" }, "Yours so far: ", ...draft.instruments.flatMap((i, n) => [n ? ", " : "", h("a", { href: `#instruments/${encodeURIComponent(i.name)}` }, i.name)])) : null,
    ),
    preview: musicPreview(() => ({ instrument: "marimba", sayLetters: false })),
    previewTitle: "What your kid hears",
    caption: "Music: letter keys play notes, number keys play drums.",
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
        replayTimer = window.setTimeout(() => playGridKey(inst.name, lastKey), 140);
      };
      sliders.append(h("div", { class: "slider" }, h("span", { class: "lbl" }, spec.label), range, val));
    }
  }

  const preview = musicPreview(() => ({ instrument: inst.name, sayLetters: false }), (k) => (lastKey = k));
  const unlisten = pageKeys((k) => preview.press(k));

  const reset = () => {
    Object.assign(inst.params, defaults(inst.base));
    changed();
    location.hash = `#instruments/${encodeURIComponent(inst.name)}`;
  };
  const remove = () => {
    draft.instruments = draft.instruments.filter((i) => i !== inst);
    changed();
    location.hash = "#instruments";
  };

  return {
    title: inst.name,
    editor: h(
      "section",
      {},
      h("div", { class: "card" }, h("div", { class: "row between" }, h("div", { style: "flex:1;min-width:200px" }, field("Name", nameIn)), h("span", { class: "dim small" }, `Started from ${base.label}. ${base.blurb}`))),
      h("p", { class: "dim small" }, "Type on your keyboard to play it. Moving a slider plays the last note again."),
      h("div", { class: "card" }, sliders, h("div", { class: "row between", style: "margin-top:20px" }, h("button", { class: "linkbtn dim", onclick: reset }, `Back to ${base.label}'s numbers`), h("button", { class: "linkbtn dim", onclick: remove }, "Remove this instrument"))),
    ),
    preview,
    previewTitle: "What your kid hears",
    caption: `Music, playing ${inst.name}.`,
    cleanup: () => { unlisten(); clearTimeout(replayTimer); },
  };
}

const fmt = (v: number, unit?: string) => `${Number.isInteger(v) ? v : v.toFixed(v < 1 ? 3 : 2).replace(/\.?0+$/, "")}${unit ? " " + unit : ""}`;

export function instrumentsView(item: string | null): View {
  const inst = item ? draft.instruments.find((i) => i.name === item) : null;
  return inst ? editor(inst) : chooser();
}
