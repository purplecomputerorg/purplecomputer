import type { Clip } from "../audio";
import { LETTER_KEYS, voiceClipFilename } from "../purple/sounds";
import { changed, draft } from "../state";
import { clear, field, h } from "./dom";
import { musicFrame, playFrame } from "./facsimile";
import { clipRow, recordControl } from "./record";
import type { View } from "./view";

export function voiceView(): View {
  let current = LETTER_KEYS.find((k) => !(k in draft.letters)) ?? "a";
  let lastPhrase: string | null = draft.phrases.at(-1)?.text ?? null;
  const keys = h("div", { class: "keys" });
  const big = h("div", { class: "big-letter" });
  const currentClip = h("div");

  function renderLetters() {
    clear(keys);
    for (const k of LETTER_KEYS) {
      const cls = ["key", k in draft.letters && "done", k === current && "current"].filter(Boolean).join(" ");
      keys.append(h("button", { class: cls, onclick: () => { current = k; renderLetters(); changed(); } }, k));
    }
    big.textContent = current;
    clear(currentClip);
    const clip = draft.letters[current];
    if (clip) currentClip.append(clipRow(clip, `content/letters/${current}.wav`, () => { delete draft.letters[current]; changed(); renderLetters(); }));
  }
  const onLetter = (clip: Clip) => {
    draft.letters[current] = clip;
    current = LETTER_KEYS[(LETTER_KEYS.indexOf(current) + 1) % LETTER_KEYS.length];
    changed();
    renderLetters();
  };
  renderLetters();

  const phraseIn = h("input", { type: "text", placeholder: "Good morning, Maya" });
  const phraseName = h("span", { class: "mono" }, "content/voice/….wav");
  phraseIn.oninput = () => (phraseName.textContent = `content/voice/${voiceClipFilename(phraseIn.value || "…")}`);
  const phrases = h("div", { class: "stack" });
  function renderPhrases() {
    clear(phrases);
    draft.phrases.forEach((p, i) =>
      phrases.append(h("div", { class: "card" }, h("p", {}, h("strong", {}, p.text)), clipRow(p.clip, `content/voice/${voiceClipFilename(p.text)}`, () => { draft.phrases.splice(i, 1); changed(); renderPhrases(); }))));
  }
  renderPhrases();
  const phraseStatus = h("div", { class: "status" });
  const onPhrase = (clip: Clip) => {
    const text = phraseIn.value.trim();
    if (!text) {
      phraseStatus.textContent = "Type the phrase first, so Purple knows when to play it.";
      return;
    }
    phraseStatus.textContent = "";
    draft.phrases = draft.phrases.filter((p) => p.text.toLowerCase() !== text.toLowerCase());
    draft.phrases.push({ text, clip });
    lastPhrase = text;
    phraseIn.value = "";
    phraseIn.dispatchEvent(new Event("input"));
    changed();
    renderPhrases();
  };

  return {
    title: "Voice",
    path: "content/letters/<key>.wav  ·  content/voice/<phrase>.wav",
    tag: "real",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Purple says letters and numbers out loud in the Music room, and reads back what a kid types in Play. Those can be in a voice your kid knows."),
      h("h3", {}, "Letters and numbers"),
      h("p", { class: "dim small" }, "Pick a key, say its name, stop. Studio moves to the next one. Any you skip keep Purple's own voice."),
      h("div", { class: "card" }, keys, big, recordControl(onLetter), currentClip),
      h("h3", {}, "Phrases"),
      h("p", { class: "dim small" }, "When a kid types exactly this phrase in Play, Purple plays your recording instead of speaking it. Capitals and spacing do not matter."),
      h("div", { class: "card" }, field("The phrase, exactly as your kid would type it", phraseIn), h("p", { class: "dim small" }, "Saved as ", phraseName), recordControl(onPhrase), phraseStatus),
      phrases,
      h("div", { class: "note" }, h("strong", {}, "What Purple does with this: "), "the Music room's Say Letters mode plays your clip for any key you recorded and Purple's own clip for the rest. A phrase you record is what Purple says instead of its built-in voice whenever it would say exactly those words."),
    ),
    stage: () => (lastPhrase ? playFrame([{ ask: lastPhrase, answer: `♪ ${lastPhrase}` }]) : musicFrame({ instrument: "Marimba", sayLetters: true, activeKey: current })),
    stageTitle: "What your kid hears",
    caption: lastPhrase ? "Play, reading a phrase back in your recording." : "The Music room in Say Letters mode: each key says its name.",
  };
}
