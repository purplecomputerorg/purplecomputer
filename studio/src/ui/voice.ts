import type { Clip } from "../audio";
import { LETTER_KEYS, voiceClipFilename } from "../purple/sounds";
import { changed, draft } from "../state";
import { clear, field, h } from "./dom";
import { clipRow, recordControl } from "./record";

export function voiceView(): HTMLElement {
  let current = LETTER_KEYS.find((k) => !(k in draft.letters)) ?? "a";
  const keys = h("div", { class: "keys" });
  const big = h("div", { class: "big-letter" });
  const current_clip = h("div");

  function renderLetters() {
    clear(keys);
    for (const k of LETTER_KEYS) {
      const cls = ["key", k in draft.letters && "done", k === current && "current"].filter(Boolean).join(" ");
      keys.append(h("button", { class: cls, onclick: () => { current = k; renderLetters(); } }, k));
    }
    big.textContent = current;
    clear(current_clip);
    const clip = draft.letters[current];
    if (clip) {
      current_clip.append(clipRow(clip, `content/letters/${current}.wav`, () => {
        delete draft.letters[current];
        changed();
        renderLetters();
      }));
    }
  }

  const onLetter = (clip: Clip) => {
    draft.letters[current] = clip;
    changed();
    current = LETTER_KEYS[(LETTER_KEYS.indexOf(current) + 1) % LETTER_KEYS.length];
    renderLetters();
  };
  renderLetters();

  const phraseInput = h("input", { type: "text", placeholder: "Good morning, Maya" });
  const phraseName = h("span", { class: "mono" }, "content/voice/….wav");
  phraseInput.oninput = () => (phraseName.textContent = `content/voice/${voiceClipFilename(phraseInput.value || "…")}`);
  const phrases = h("div", { class: "stack" });

  function renderPhrases() {
    clear(phrases);
    draft.phrases.forEach((p, i) =>
      phrases.append(
        h("div", { class: "card quiet" }, h("p", {}, h("strong", {}, p.text)), clipRow(p.clip, `content/voice/${voiceClipFilename(p.text)}`, () => {
          draft.phrases.splice(i, 1);
          changed();
          renderPhrases();
        })),
      ),
    );
  }
  renderPhrases();

  const phraseStatus = h("div", { class: "status" });
  const onPhrase = (clip: Clip) => {
    const text = phraseInput.value.trim();
    if (!text) {
      phraseStatus.textContent = "Type the phrase first, so Purple knows when to play it.";
      return;
    }
    phraseStatus.textContent = "";
    draft.phrases = draft.phrases.filter((p) => p.text.toLowerCase() !== text.toLowerCase());
    draft.phrases.push({ text, clip });
    phraseInput.value = "";
    phraseInput.dispatchEvent(new Event("input"));
    changed();
    renderPhrases();
  };

  return h(
    "section",
    {},
    h("h2", {}, "Your own voice"),
    h("p", { class: "lead" }, "Purple says letters and numbers out loud in the Music room, and reads back what a kid types in Play. Those can be in a voice your kid knows."),
    h("h3", {}, "Letters and numbers"),
    h("p", { class: "dim small" }, "Pick a key, say its name, stop. Studio moves to the next one. Any you skip keep Purple's own voice."),
    h("div", { class: "card" }, keys, big, recordControl(onLetter), current_clip),
    h("h3", {}, "Phrases"),
    h("p", { class: "dim small" }, "When a kid types exactly this phrase in Play, Purple plays your recording instead of speaking it. Capitals and spacing do not matter."),
    h("div", { class: "card" }, field("The phrase, exactly as your kid would type it", phraseInput), h("p", { class: "dim small" }, "Saved as ", phraseName), recordControl(onPhrase), phraseStatus),
    phrases,
    h("div", { class: "note" }, h("strong", {}, "What Purple does with this today: "), "the Music room and the reader only look in Purple's own sound pack for these files. This pack puts yours in the same layout, one WAV per key at the same sample rate, so the change on Purple's side is to look in your pack too."),
  );
}
