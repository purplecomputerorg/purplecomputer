import { Recorder, decodeToClip, normalize, tidy, type Clip } from "../audio";
import { filePicker, h } from "./dom";

// Every clip, recorded or chosen, passes through the same tidy and normalize; say tells the family how it went.
async function finish(blob: Blob, onClip: (clip: Clip) => void, say: (text: string) => void) {
  say("Listening back…");
  try {
    const clip = normalize(tidy(await decodeToClip(blob)));
    if (clip.samples.length === 0) return say("That was silent. Try again a little closer to the microphone.");
    say("");
    onClip(clip);
  } catch {
    say("That file could not be read as audio.");
  }
}

const MIC = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>';

// A Record button that turns into Stop while it listens. small: a round microphone button that fits in a form's row.
export function recordButton(onClip: (clip: Clip) => void, say: (text: string) => void, small = false): HTMLButtonElement {
  const recorder = new Recorder();
  const button = h("button", { class: small ? "rec-mini" : "btn record", title: "Record a sound", "aria-label": "Record a sound" });
  const show = (on: boolean) => {
    if (small) button.innerHTML = on ? "■" : MIC;
    else button.textContent = on ? "■ Stop" : "● Record";
    button.classList.toggle("recording", on);
  };
  show(false);
  button.onclick = async () => {
    if (recorder.active) {
      show(false);
      await finish(await recorder.stop(), onClip, say);
      return;
    }
    try {
      await recorder.start();
      show(true);
      say("Recording. Press the button again when you're done.");
    } catch {
      say("The microphone is not available. You can choose a file instead.");
    }
  };
  return button;
}

// One shared record-or-choose-a-file control.
export function recordControl(onClip: (clip: Clip) => void): HTMLElement {
  const status = h("div", { class: "status" });
  const say = (text: string) => void (status.textContent = text);
  return h("div", { class: "stack" }, h("div", { class: "row" }, recordButton(onClip, say), filePicker("audio/*", (f) => finish(f, onClip, say))), status);
}

// Words in the family's own voice, played in Purple's place: a microphone, or once recorded, hear it or go back to Purple's voice.
export function voiceButtons(recorded: boolean, on: { clip: (clip: Clip) => void; hear: () => void; clear: () => void }, say: (text: string) => void): HTMLElement[] {
  if (!recorded) return [recordButton(on.clip, say, true)];
  return [
    h("button", { class: "rec-mini", title: "Hear your recording", "aria-label": "Hear your recording", onclick: on.hear }, "▶"),
    h("button", { class: "x", title: "Use Purple's voice", "aria-label": "Use Purple's voice", onclick: on.clear }, "×"),
  ];
}
