import { Recorder, decodeToClip, normalize, play, tidy, type Clip } from "../audio";
import { roomLine } from "../roomvoice";
import { speakable } from "../speakable";
import { isQuiet } from "../state";
import { filePicker, h } from "./dom";
import { staysHere } from "./privacy";

// said: the words Purple read, when the clip came from typing.
type OnClip = (clip: Clip, said?: string) => void;

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

export const MIC = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>';

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

// Purple's room voice reading words, kept as a clip like any recording.
async function purpleSays(text: string, say: (text: string) => void): Promise<Clip | null> {
  say("Getting Purple's voice ready…");
  if (!(await speakable(text))) return (say("Purple doesn't say some words. Try different ones."), null);
  const clip = await roomLine(text);
  say(clip ? "" : "Purple's voice didn't load. Try again in a moment.");
  return clip;
}

export interface SoundPick {
  clip?: Clip;
  said?: string;
  // What Purple says with the field left empty; without it, the field needs words.
  fallback?: string;
  placeholder: string;
  small?: boolean;
  onClip: OnClip;
  onClear?: () => void;
}

// One control for a sound: Purple's voice reading typed words, or the family's own recording. A new sound plays right away.
export function soundPicker(o: SoundPick): HTMLElement {
  const box = h("div", { class: "sound-picker" });
  const status = h("div", { class: "status" });
  const say = (text: string) => void (status.textContent = text);
  let mine = !!o.clip && !o.said;
  const got: OnClip = (clip, said) => { play(clip); o.onClip(clip, said); };
  const words = h("input", { type: "text", value: o.said ?? "", placeholder: o.placeholder, "aria-label": "Words for Purple to say", autocomplete: "off" });
  const read = async () => {
    const text = words.value.trim();
    if (text && text === o.said && o.clip) return play(o.clip);
    if (!text && !o.fallback) return say("Type the words first, then press Say it.");
    const clip = await purpleSays(text || o.fallback!, say);
    if (!clip) return;
    if (text) return got(clip, text);
    play(clip);
    if (o.said) o.onClear?.();
  };
  words.addEventListener("keydown", (e) => e.key === "Enter" && void read());
  const option = (to: boolean, label: string) => h("button", { type: "button", "aria-pressed": String(mine === to), onclick: () => { mine = to; say(""); draw(); } }, label);
  const draw = () => box.replaceChildren(
    h("span", { class: "seg" }, option(false, "🔊 Purple's voice"), option(true, "🎤 Your voice")),
    mine ? h("div", { class: "row" }, recordButton((c) => got(c), say, o.small), filePicker("audio/*", (f) => finish(f, (c) => got(c), say)),
      ...(o.clip && !o.said ? [hear(o.clip), o.onClear && h("button", { type: "button", class: "x", title: "Remove your recording", "aria-label": "Remove your recording", onclick: o.onClear }, "×")] : []))
      : h("div", { class: "type-it" }, words, h("button", { type: "button", class: "btn secondary", onclick: read }, "▶ Say it")),
    status);
  draw();
  return box;
}

export const hear = (clip: Clip) => (isQuiet(clip) ? h("span", { class: "dim small" }, "🔇 No sound")
  : h("button", { class: "btn secondary small", onclick: () => play(clip) }, "▶ Hear it"));

export const voiceStays = () => staysHere("Your recordings stay in your browser. Nobody else hears them unless you share your Purple Pack.");

// Words in the family's own voice, played in Purple's place: a microphone, or once recorded, hear it or go back to Purple's voice.
export function voiceButtons(recorded: boolean, on: { clip: (clip: Clip) => void; hear: () => void; clear: () => void }, say: (text: string) => void): HTMLElement[] {
  if (!recorded) return [recordButton(on.clip, say, true)];
  return [
    h("button", { class: "rec-mini", title: "Hear your recording", "aria-label": "Hear your recording", onclick: on.hear }, "▶"),
    h("button", { class: "x", title: "Use Purple's voice", "aria-label": "Use Purple's voice", onclick: on.clear }, "×"),
  ];
}
