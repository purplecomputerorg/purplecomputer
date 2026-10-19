// The real Purple on the right: one iframe (purple.html), started when Studio opens and kept for
// the whole visit, so it's usually ready before anyone looks. Until it is, and while it restarts
// with an edit, a quiet message covers it, since it can't take keys then.
import type { ArtPicture } from "@sdk/purple/art";
import type { Place, Room, RoomSetup } from "../live/boot";
import type { FromFrame, ToFrame, View } from "../live/frame";
import { KEY_EVENT, announceKey } from "../keys";
import { buildPack } from "../pack";
import { draft } from "../state";
import { h } from "./dom";

// Covers Purple while it isn't getting keys. Once someone has played with it (the screen marked
// "tried"), it shrinks to a small reminder, since they already know how.
function tryHint(hint: string): HTMLElement {
  return h("button", { class: "playable-hint", type: "button" },
    h("strong", {}, "Click to try it"), h("span", {}, hint), h("em", {}, "Click to type here"));
}

// Why a family room stopped, as Purple's FamilyRoom put it.
export interface RoomProblem { text: string; line: number | null }

// Quiet time after the last edit before the pack is rebuilt and Purple picks it up.
const SETTLE_MS = 150;
// A close-up of Purple's screen: this much bigger, around the spot given here, or else the room's
// cursor (Art and Blocks follow theirs). A phone starts in it, since the whole screen is too small
// to read there; a computer starts on the whole screen and can zoom in.
const ZOOM: Record<Room, { scale: number; at?: [number, number] }> = {
  play: { scale: 2, at: [0.33, 0.6] },
  music: { scale: 1.3, at: [0.5, 0.47] },
  art: { scale: 2 },
  blocks: { scale: 1.6 },
};
// The same test as the phone rules in styles.css.
export const PHONE = matchMedia("(max-width: 700px), (max-height: 500px) and (pointer: coarse)");
const MOUSE = matchMedia("(pointer: fine)");
const clamp = (v: number, max: number) => Math.min(max, Math.max(0, v));

class LiveScreen {
  readonly element: HTMLElement;
  private frame = h("iframe", { class: "live-frame", src: "purple.html", title: "Purple", tabindex: -1 });
  private status = h("span", {}, "Loading Purple Computer in your browser");
  private hint = tryHint("then use the keyboard, like on Purple");
  private voiceNote = h("div", { class: "voice-loading", hidden: true });
  // An edit on its way: Purple still plays meanwhile, with what it had.
  private updating = h("div", { class: "live-updating", hidden: true }, "Updating Purple");
  private note = h("div", { class: "screen-note", hidden: true });
  private zoomed = PHONE.matches;
  private zoomButton = h("button", { class: "zoom-toggle", type: "button", onclick: () => { this.zoomed = !this.zoomed; this.reframe(); this.engage(); } });
  // Set by Studio: Purple moved to another room, or opened or closed a menu.
  onMove = () => {};
  // Set by the Rooms page: a family room's print() output, and why one stopped.
  onPrint = (_text: string) => {};
  onProblem = (_p: RoomProblem) => {};
  // Set by the Pictures page: Art switched between painting and writing letters.
  onWriting = (_on: boolean) => {};
  place: Place = { room: "art", menu: false, at: null, writing: false };
  private pictureWaits: ((p: ArtPicture) => void)[] = [];
  private ready = false;
  private setup: RoomSetup = { room: "art" };
  private timer = 0;
  private sent = "";
  // Messages wait for the frame's page to be listening; until then the iframe holds about:blank.
  private hello!: () => void;
  private listening = new Promise<void>((resolve) => (this.hello = resolve));

  constructor() {
    this.hint.onclick = () => this.focus();
    this.element = h("div", { class: "screen-wrap live" }, this.frame, h("div", { class: "live-status" }, h("i"), this.status), this.hint, this.zoomButton, this.voiceNote, this.updating, this.note);
    PHONE.addEventListener("change", () => { this.zoomed = PHONE.matches; this.reframe(); });
    this.reframe();
    addEventListener("message", (e: MessageEvent<FromFrame>) => e.source === this.frame.contentWindow && this.onMessage(e.data));
    addEventListener(KEY_EVENT, () => (this.note.hidden = true));
    void this.sync();
  }

  // A handwritten note on the screen saying what to do, until the next key.
  prompt(text: string | null): void {
    this.note.textContent = text;
    this.note.hidden = !text;
  }

  show(setup: RoomSetup): void {
    this.setup = setup;
    this.moved({ room: setup.room, menu: false, at: null, writing: setup.room === "art" && !!setup.letters });
    if (this.ready) this.post({ type: "setup", setup });
  }

  // What's on Purple's Art canvas, painting and letters, once Purple gets to it.
  picture(): Promise<ArtPicture> {
    return new Promise((resolve) => {
      this.pictureWaits.push(resolve);
      this.post({ type: "picture" });
    });
  }

  // Any change to the draft: rebuild the pack once edits settle. Purple keeps taking keys unless
  // the new pack makes it start again.
  changed(): void {
    clearTimeout(this.timer);
    this.updating.hidden = false;
    this.timer = window.setTimeout(() => void this.sync(), SETTLE_MS);
  }

  key(key: string): void {
    if (!this.ready) return;
    this.post({ type: "key", char: key });
    announceKey(key);
  }

  focus(): void {
    this.frame.focus();
    this.post({ type: "focus" });
  }

  // Someone used the demo (a key, a room, the zoom): on a computer, send their typing to Purple
  // too. A phone keeps its own keyboard's focus.
  engage(): void {
    if (MOUSE.matches) this.focus();
  }

  private async sync(): Promise<void> {
    // The room being tried opens straight on the screen (RoomSetup.family), so the Esc menu lists
    // only the added ones, as Open does pictures.
    const live = { ...draft, rooms: draft.rooms.filter((r) => r.kept), pictures: draft.pictures.filter((p) => p.kept) };
    const key = JSON.stringify(live, (_, v) => (v instanceof Float32Array ? `${v.length}:${v[v.length >> 1]}` : v));
    if (key === this.sent) return void (this.updating.hidden = true);
    this.sent = key;
    const pack = new Uint8Array(await (await buildPack(undefined, live, true)).arrayBuffer());
    this.post({ type: "load", pack, setup: this.setup });
  }

  private onMessage(m: FromFrame): void {
    if (m.type === "hello") this.hello();
    if (m.type === "failed") { this.status.textContent = "Purple Computer couldn't start in this browser"; this.element.classList.add("failed"); console.warn("Purple failed:", m.text); }
    if (m.type === "restarting") this.busy(true);
    if (m.type === "loaded") { this.busy(false); this.updating.hidden = true; }
    if (m.type === "loaded" && !this.ready) {
      this.ready = true;
      this.element.classList.add("ready");
      this.post({ type: "setup", setup: this.setup });
    }
    if (m.type === "focus") this.element.classList.toggle("focused", m.on);
    if (m.type === "focus" && m.on) this.element.classList.add("tried");
    if (m.type === "voice") { this.voiceNote.textContent = m.text; this.voiceNote.hidden = !m.text; }
    if (m.type === "keydown") announceKey(m.key);
    if (m.type === "place") this.moved(m.place);
    if (m.type === "picture") this.pictureWaits.shift()?.(m.picture);
    if (m.type === "print") this.onPrint(m.text);
    if (m.type === "problem") this.onProblem({ text: m.text, line: m.line });
  }

  private busy(on: boolean): void {
    if (this.ready) this.status.textContent = "Updating Purple Computer";
    this.element.classList.toggle("busy", on);
  }

  private moved(place: Place): void {
    const same = place.room === this.place.room && place.menu === this.place.menu;
    const switched = place.writing !== this.place.writing;
    this.place = place;
    this.reframe();
    if (!same) this.onMove();
    if (switched) this.onWriting(place.writing);
  }

  // The whole screen or the close-up; menus and pictures show whole.
  private reframe(): void {
    const { room, menu, at } = this.place;
    const zoom = !menu && !(room === "art" && this.setup.picture) ? ZOOM[room] : null;
    this.zoomButton.hidden = !zoom;
    this.zoomButton.textContent = this.zoomed ? "Whole screen" : "Zoom in";
    const size = zoom && this.zoomed ? 1 / zoom.scale : 1;
    const [x, y] = zoom?.at ?? at ?? [0.5, 0.5];
    const view: View = [clamp(x - size / 2, 1 - size), clamp(y - size / 2, 1 - size), size, size];
    this.post({ type: "view", view });
  }

  private post(m: ToFrame): void {
    void this.listening.then(() => this.frame.contentWindow?.postMessage(m, location.origin));
  }
}

let screen: LiveScreen | null = null;

// Started once, at Studio's first paint, and shared by every page that shows Purple.
export function liveScreen(): LiveScreen {
  screen ??= new LiveScreen();
  return screen;
}
