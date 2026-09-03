import { clipToBuffer, detectPitch, play, renderClip, type Clip } from "../audio";
import { INSTRUMENTS, SAMPLE_PITCHES, noteFrequency, noteFromFrequency } from "../purple/sounds";
import { changed, draft, slug } from "../state";
import { clear, field, h } from "./dom";
import { clipRow, recordControl } from "./record";

const OCTAVES = [2, 3, 4, 5];
const NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

export function instrumentView(): HTMLElement {
  const nameIn = h("input", { type: "text", placeholder: "Kitchen pots", value: draft.instrument?.name ?? "" });
  const detail = h("div");
  const status = h("div", { class: "status" });

  const pitchSelect = h("select", { style: "width:auto" }, ...OCTAVES.flatMap((o) => NOTES.map((n) => h("option", { value: `${n}${o}` }, `${n}${o}`))));

  function render() {
    clear(detail);
    const inst = draft.instrument;
    if (!inst) return;
    const { note, octave, cents } = noteFromFrequency(inst.sourceFreq);
    pitchSelect.value = `${note}${octave}`;
    pitchSelect.onchange = () => {
      const m = pitchSelect.value.match(/^([A-G]#?)(\d)$/)!;
      inst.sourceFreq = noteFrequency(m[1], Number(m[2]));
      changed();
      render();
    };
    const tryNote = async (file: string) => {
      const p = SAMPLE_PITCHES.find((s) => s.file === file)!;
      play(await renderClip(clipToBuffer(inst.source), inst.source.rate, p.freq / inst.sourceFreq));
    };
    detail.append(
      clipRow(inst.source, `content/${inst.name}/…`, () => { draft.instrument = null; changed(); render(); }),
      h("p", { class: "dim small", style: "margin-top:16px" }, `This sounds like ${note}${octave}${cents ? ` (${cents > 0 ? "+" : ""}${cents} cents)` : ""}. If that is wrong, pick the note you played:`),
      h("div", { class: "row" }, pitchSelect, h("span", { class: "dim small" }, "Hear it as"), ...["c3", "g4", "c5", "e6"].map((f) => h("button", { class: "btn secondary small", onclick: () => tryNote(f) }, f.toUpperCase().replace("S", "#")))),
    );
  }

  const onClip = (clip: Clip) => {
    const name = slug(nameIn.value) || "my-instrument";
    if ((INSTRUMENTS as readonly string[]).includes(name)) {
      status.textContent = `Purple already has a ${name}. Give yours a different name.`;
      return;
    }
    const freq = detectPitch(clip);
    status.textContent = freq ? "" : "Studio could not tell which note that was. Pick it below.";
    draft.instrument = { name, source: clip, sourceFreq: freq ?? noteFrequency("C", 4) };
    changed();
    render();
  };
  nameIn.oninput = () => {
    if (draft.instrument) {
      draft.instrument.name = slug(nameIn.value) || "my-instrument";
      changed();
      render();
    }
  };
  render();

  return h(
    "section",
    {},
    h("h2", {}, "Your own instrument"),
    h("p", { class: "lead" }, "Play one clear note on anything: a glass, a pot, a guitar string, your voice. Studio tunes that one note into every key on the Music room grid."),
    h("div", { class: "card" }, field("What is it called", nameIn), recordControl(onClip), status, detail),
    h("div", { class: "note" }, h("strong", {}, "What Purple does with this today: "), `Purple plays its four instruments from folders of pre-made sound files, one per note, ${SAMPLE_PITCHES.length} files each. This pack writes yours in the same layout and naming. There is no synthesizer in Purple to change how an existing instrument sounds, so Studio does not offer that.`),
  );
}
