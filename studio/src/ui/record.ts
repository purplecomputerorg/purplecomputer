import { Recorder, decodeToClip, normalize, tidy, type Clip } from "../audio";
import { filePicker, h } from "./dom";

// One shared record-or-choose-a-file control. Every clip passes through the same tidy and normalize.
export function recordControl(onClip: (clip: Clip) => void): HTMLElement {
  const recorder = new Recorder();
  const status = h("div", { class: "status" });
  const button = h("button", { class: "btn record" }, "● Record");

  const finish = async (blob: Blob) => {
    status.textContent = "Listening back…";
    try {
      const clip = normalize(tidy(await decodeToClip(blob)));
      if (clip.samples.length === 0) {
        status.textContent = "That was silent. Try again a little closer to the microphone.";
        return;
      }
      status.textContent = "";
      onClip(clip);
    } catch {
      status.textContent = "That file could not be read as audio.";
    }
  };

  button.onclick = async () => {
    if (recorder.active) {
      button.textContent = "● Record";
      button.classList.remove("recording");
      await finish(await recorder.stop());
      return;
    }
    try {
      await recorder.start();
      button.textContent = "■ Stop";
      button.classList.add("recording");
      status.textContent = "Recording. Press Stop when you're done.";
    } catch {
      status.textContent = "The microphone is not available. You can choose a file instead.";
    }
  };

  return h("div", { class: "stack" }, h("div", { class: "row" }, button, filePicker("audio/*", finish)), status);
}
