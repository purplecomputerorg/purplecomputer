import { Recorder, decodeToClip, normalize, play, tidy, type Clip } from "../audio";
import { filePicker, h, seconds } from "./dom";

// One shared record-or-choose-a-file control. Every clip passes through the same tidy and normalize.
export function recordControl(onClip: (clip: Clip) => void): HTMLElement {
  const recorder = new Recorder();
  const status = h("div", { class: "status" });
  const button = h("button", { class: "btn" }, "Record");

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
      button.textContent = "Record";
      button.classList.remove("recording");
      await finish(await recorder.stop());
      return;
    }
    try {
      await recorder.start();
      button.textContent = "Stop";
      button.classList.add("recording");
      status.textContent = "Recording. Press Stop when you are done.";
    } catch {
      status.textContent = "The microphone is not available. You can choose a file instead.";
    }
  };

  return h("div", { class: "stack" }, h("div", { class: "row" }, button, filePicker("audio/*", finish)), status);
}

export function drawWave(canvas: HTMLCanvasElement, clip: Clip): void {
  const ctx = canvas.getContext("2d")!;
  const { width, height } = canvas;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#9b59d0";
  const step = Math.max(1, Math.floor(clip.samples.length / width));
  for (let x = 0; x < width; x++) {
    let peak = 0;
    for (let i = x * step; i < (x + 1) * step && i < clip.samples.length; i++) peak = Math.max(peak, Math.abs(clip.samples[i]));
    const hgt = Math.max(1, peak * height);
    ctx.fillRect(x, (height - hgt) / 2, 1, hgt);
  }
}

export function clipRow(clip: Clip, filename: string, onRemove: () => void): HTMLElement {
  const canvas = h("canvas", { class: "wave", width: 600, height: 48 });
  requestAnimationFrame(() => drawWave(canvas, clip));
  return h(
    "div",
    { class: "stack" },
    canvas,
    h(
      "div",
      { class: "row between" },
      h("div", { class: "row" }, h("button", { class: "btn secondary small", onclick: () => play(clip) }, "Play"), h("span", { class: "mono" }, filename), h("span", { class: "dim small" }, seconds(clip.samples.length / clip.rate))),
      h("button", { class: "linkbtn dim", onclick: onRemove }, "Remove"),
    ),
  );
}
