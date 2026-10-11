// The real Purple on the right: one iframe (purple.html), started when Studio opens and kept for
// the whole visit, so it's usually ready before anyone looks. Until it is, a screenshot of the
// same room, taken from Purple itself, stands in.
import type { Place, Room, RoomSetup } from "../live/boot";
import type { FromFrame, ToFrame, View } from "../live/frame";
import { announceKey } from "../keys";
import { buildPack } from "../pack";
import { draft, pieces } from "../state";
import { h } from "./dom";
import { tryHint } from "./playable";

const poster = (room: string) => new URL(`purple/poster-${room}.png`, document.baseURI).href;
// Quiet time after the last edit before the pack is rebuilt and Purple restarts with it.
const SETTLE_MS = 700;
// On a phone Purple's screen is too small to read whole, so it shows a close-up: this much bigger,
// around the spot given here, or else the room's cursor (Art and Blocks follow theirs).
const ZOOM: Record<Room, { scale: number; at?: [number, number] }> = {
  play: { scale: 2, at: [0.33, 0.6] },
  music: { scale: 1.3, at: [0.5, 0.47] },
  art: { scale: 2 },
  blocks: { scale: 1.6 },
};
// The same test as the phone rules in styles.css.
export const PHONE = matchMedia("(max-width: 700px), (max-height: 500px) and (pointer: coarse)");
export const MOUSE = matchMedia("(pointer: fine)");
const clamp = (v: number, max: number) => Math.min(max, Math.max(0, v));

class LiveScreen {
  readonly element: HTMLElement;
  private frame = h("iframe", { class: "live-frame", src: "purple.html", title: "Purple", tabindex: -1 });
  private poster = h("img", { class: "live-poster", alt: "" });
  private status = h("span", {}, "Starting Purple");
  private hint = tryHint("button", "then use the keyboard, like on Purple");
  private zoomed = true;
  private zoomButton = h("button", { class: "zoom-toggle", type: "button", onclick: () => { this.zoomed = !this.zoomed; this.reframe(); this.engage(); } });
  // Set by Studio: Purple moved to another room, or opened or closed a menu.
  onMove = () => {};
  place: Place = { room: "play", menu: false, at: null };
  private ready = false;
  private setup: RoomSetup = { room: "play" };
  private timer = 0;
  private sent = "";
  // Messages wait for the frame's page to be listening; until then the iframe holds about:blank.
  private hello!: () => void;
  private listening = new Promise<void>((resolve) => (this.hello = resolve));

  constructor() {
    this.hint.onclick = () => this.focus();
    this.element = h("div", { class: "screen-wrap live" }, this.frame, this.poster, h("div", { class: "live-status" }, h("i"), this.status), this.hint, this.zoomButton);
    PHONE.addEventListener("change", () => this.reframe());
    this.reframe();
    addEventListener("message", (e: MessageEvent<FromFrame>) => e.source === this.frame.contentWindow && this.onMessage(e.data));
    void this.sync();
  }

  show(setup: RoomSetup): void {
    this.setup = setup;
    this.moved({ room: setup.room, menu: false, at: null });
    this.poster.src = poster(setup.room);
    if (this.ready) this.post({ type: "setup", setup });
  }

  // Any change to the draft: rebuild the pack once edits settle.
  changed(): void {
    clearTimeout(this.timer);
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
    // Rooms stay out: Purple runs them as a separate process, which a browser can't; the Rooms
    // page previews them itself.
    const live = { ...draft, rooms: [] };
    const key = JSON.stringify(live, (_, v) => (v instanceof Float32Array ? `${v.length}:${v[v.length >> 1]}` : v));
    if (key === this.sent) return;
    this.sent = key;
    const pack = pieces().length ? new Uint8Array(await (await buildPack(undefined, live)).arrayBuffer()) : null;
    this.post({ type: "load", pack, setup: this.setup });
  }

  private onMessage(m: FromFrame): void {
    if (m.type === "hello") this.hello();
    if (m.type === "status") this.status.textContent = m.text.replace(/…$/, "");
    if (m.type === "failed") { this.status.textContent = "Purple couldn't start here"; console.warn("Purple failed:", m.text); }
    if (m.type === "loaded" && !this.ready) {
      this.ready = true;
      this.element.classList.add("ready");
      this.post({ type: "setup", setup: this.setup });
    }
    if (m.type === "focus") this.element.classList.toggle("focused", m.on);
    if (m.type === "focus" && m.on) this.element.classList.add("tried");
    if (m.type === "keydown") announceKey(m.key);
    if (m.type === "place") this.moved(m.place);
  }

  private moved(place: Place): void {
    const same = place.room === this.place.room && place.menu === this.place.menu;
    this.place = place;
    this.reframe();
    if (!same) this.onMove();
  }

  // The whole screen, or on a phone the close-up; menus show whole, since they sit in the middle.
  private reframe(): void {
    const { room, menu, at } = this.place;
    const zoom = PHONE.matches && !menu ? ZOOM[room] : null;
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
