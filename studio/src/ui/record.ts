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

// A Record button that turns into Stop while it listens. small: a round button that fits in a form's row.
export function recordButton(onClip: (clip: Clip) => void, say: (text: string) => void, small = false): HTMLButtonElement {
  const recorder = new Recorder();
  const [label, stop] = small ? ["●", "■"] : ["● Record", "■ Stop"];
  const button = h("button", { class: small ? "rec-mini" : "btn record", title: "Record a sound", "aria-label": "Record a sound" }, label);
  button.onclick = async () => {
    if (recorder.active) {
      button.textContent = label;
      button.classList.remove("recording");
      await finish(await recorder.stop(), onClip, say);
      return;
    }
    try {
      await recorder.start();
      button.textContent = stop;
      button.classList.add("recording");
      say("Recording. Press Stop when you're done.");
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
