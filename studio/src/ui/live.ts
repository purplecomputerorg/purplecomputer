// The real Purple on the right: one iframe (purple.html), started when Studio opens and kept for
// the whole visit, so it's usually ready before anyone looks. Until it is, a screenshot of the
// same room, taken from Purple itself, stands in.
import type { RoomSetup } from "../live/boot";
import type { FromFrame, ToFrame } from "../live/frame";
import { buildPack } from "../pack";
import { draft, pieces } from "../state";
import { h } from "./dom";

const EXPAND_ICON = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>`;
declare global { interface Navigator { keyboard?: { lock(keys: string[]): Promise<void>; unlock(): void } } }

const poster = (room: string) => new URL(`purple/poster-${room}.png`, document.baseURI).href;
// Quiet time after the last edit before the pack is rebuilt and Purple restarts with it.
const SETTLE_MS = 700;

class LiveScreen {
  readonly element: HTMLElement;
  private frame = h("iframe", { class: "live-frame", src: "purple.html", title: "Purple", tabindex: -1 });
  private poster = h("img", { class: "live-poster", alt: "" });
  private status = h("span", {}, "Starting Purple");
  private hint = h("button", { class: "playable-hint", type: "button" }, h("strong", {}, "Click to try it"), h("span", {}, "then use the keyboard, like on Purple"));
  private ready = false;
  private setup: RoomSetup = { room: "play" };
  private timer = 0;
  private sent = "";
  // Messages wait for the frame's page to be listening; until then the iframe holds about:blank.
  private hello!: () => void;
  private listening = new Promise<void>((resolve) => (this.hello = resolve));

  constructor() {
    const full = h("button", { class: "screen-full", title: "Full screen", "aria-label": "Full screen" });
    full.innerHTML = EXPAND_ICON;
    full.onclick = () => this.fullscreen();
    this.hint.onclick = () => this.focus();
    this.element = h("div", { class: "screen-wrap live" }, this.frame, this.poster, h("div", { class: "live-status" }, h("i"), this.status), this.hint, full);
    addEventListener("message", (e: MessageEvent<FromFrame>) => e.source === this.frame.contentWindow && this.onMessage(e.data));
    document.addEventListener("fullscreenchange", () => !document.fullscreenElement && navigator.keyboard?.unlock());
    void this.sync();
  }

  show(setup: RoomSetup): void {
    this.setup = setup;
    this.poster.src = poster(setup.room);
    if (this.ready) this.post({ type: "setup", setup });
  }

  // Any change to the draft: rebuild the pack once edits settle.
  changed(): void {
    clearTimeout(this.timer);
    this.timer = window.setTimeout(() => void this.sync(), SETTLE_MS);
  }

  key(char: string): void {
    if (this.ready) this.post({ type: "key", char });
  }

  focus(): void {
    this.frame.focus();
    this.post({ type: "focus" });
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
  }

  private post(m: ToFrame): void {
    void this.listening.then(() => this.frame.contentWindow?.postMessage(m, location.origin));
  }

  private fullscreen(): void {
    if (document.fullscreenElement) return void document.exitFullscreen();
    // Keyboard lock keeps Esc for Purple's room picker instead of leaving full screen (Chrome).
    void this.element.requestFullscreen?.().then(() => { void navigator.keyboard?.lock(["Escape"]); this.focus(); });
  }
}

let screen: LiveScreen | null = null;

// Started once, at Studio's first paint, and shared by every page that shows Purple.
export function liveScreen(): LiveScreen {
  screen ??= new LiveScreen();
  return screen;
}
