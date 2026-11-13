// The real Purple on the right: one iframe (purple.html), started when Studio opens and kept for
// the whole visit, so it's usually ready before anyone looks. Until it is, and while it restarts
// with an edit, a quiet message covers it, since it can't take keys then.
import { buildEntries } from "@sdk/pack";
import type { Place, Room, RoomSetup } from "../live/boot";
import type { FromFrame, ToFrame, View } from "../live/frame";
import { onHush, stopPreviews } from "../audio";
import { roomIcon } from "../examples";
import { KEY_EVENT, MODIFIER_EVENT, announceKey } from "../keys";
import { manifest, packChanges, packSpec, type Sent } from "../pack";
import { onRoomVoice, roomReady, roomVoiceVersion, warmRoomVoice } from "../roomvoice";
import { draft, type RoomDraft } from "../state";
import { h, pageKeys } from "./dom";
import { trace } from "../live/trace";

// Covers Purple while it isn't getting keys. Once someone has played with it (the screen marked
// "tried"), it shrinks to a small reminder, since they already know how.
function tryHint(hint: string): HTMLElement {
  return h("button", { class: "playable-hint", type: "button" },
    h("strong", {}, "Click to try it"), h("span", {}, hint), h("em", {}, "Click to type here"), h("small", {}, "Esc picks a room"));
}

// Why a family room stopped, as Purple's FamilyRoom put it.
export interface RoomProblem { text: string; line: number | null }

// Quiet time after the last edit before the pack is rebuilt and Purple picks it up.
const SETTLE_MS = 150;
// How long a click on Purple shows that it only takes keys.
const NUDGE_MS = 2500;
// A click this soon after Purple took the keys is the rest of the one that opened it.
const SETTLE_CLICK_MS = 1000;
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
// Just arrived in a room, before Purple has said where it is.
const arrived = (room: Room): Place => ({ room, menu: false, code: false, at: null });

class LiveScreen {
  readonly element: HTMLElement;
  // autoplay: so Purple can make sounds even when Studio's own page is embedded in another site's.
  private frame = h("iframe", { class: "live-frame", src: "purple.html", title: "Purple", tabindex: -1, allow: "autoplay" });
  private status = h("span", {}, "Loading Purple Computer in your browser");
  private hint = tryHint("then it's keyboard only, on purpose");
  private voiceNote = h("div", { class: "voice-loading", hidden: true });
  // An edit on its way: Purple still plays meanwhile, with what it had.
  private updating = h("div", { class: "live-updating", hidden: true }, "Updating Purple");
  private note = h("div", { class: "screen-note", hidden: true });
  private prompted: string | null = null;
  private nudging = 0;
  private focusedAt = 0;
  private zoomed = PHONE.matches;
  private zoomButton = h("button", { class: "zoom-toggle", type: "button", onclick: () => { this.zoomed = !this.zoomed; this.reframe(); this.engage(); } });
  // Set by Studio: Purple moved to another room, or opened or closed a menu.
  onMove = () => {};
  // Set by try.html: Purple is up and taking keys for the first time; someone typed on their own keyboard.
  onReady = () => {};
  onTyped = () => {};
  // Cleared by try.html, which has no family rooms to speak in the room voice.
  warmsRoomVoice = true;
  // Set by the Rooms page: a family room's print() output, and why one stopped.
  onPrint = (_text: string) => {};
  onProblem = (_p: RoomProblem) => {};
  place: Place = arrived("art");
  // The room asked for that Purple hasn't opened yet (its room button looks busy); onOpening hears it change.
  opening: Room | null = null;
  onOpening = () => {};
  private ready = false;
  private setup: RoomSetup = { room: "art" };
  private timer = 0;
  private sent = "";
  // Which show() is current: a room still waiting on its lines gives way to the next one.
  private entering = 0;
  // The room Purple was last asked for by the current show(); the screen stays covered until Purple says it's there after that setup.
  private wanted: Room | null = null;
  // What Purple has now, so the next pack sends only what changed.
  private last: Sent = { id: "", files: new Map() };
  private syncing = Promise.resolve();
  // The rooms in the last pack sent, as they were then.
  private packed: RoomDraft[] = [];
  // Messages wait for the frame's page to be listening; until then the iframe holds about:blank.
  private hello!: () => void;
  // Questions for Purple's Python, by id, each with what it answers when Purple can't run.
  private asking = new Map<number, { resolve: (value: unknown) => void; fallback: unknown }>();
  private nextAsk = 0;
  private listening = new Promise<void>((resolve) => (this.hello = resolve));

  constructor() {
    this.hint.onclick = () => this.focus();
    this.element = h("div", { class: "screen-wrap live" }, this.frame, h("div", { class: "live-status" }, h("i"), this.status), this.hint, this.zoomButton, this.voiceNote, this.updating, this.note);
    PHONE.addEventListener("change", () => { this.zoomed = PHONE.matches; this.reframe(); });
    this.reframe();
    addEventListener("message", (e: MessageEvent<FromFrame>) => {
      // Not e.source: once Purple runs, Safari stops giving the frame's window for its messages.
      if (e.origin !== location.origin || !e.data?.type) return;
      if (e.data.type !== "status") trace("[studio] got", e.data.type);
      this.onMessage(e.data);
    });
    addEventListener(KEY_EVENT, () => { this.prompt(null); stopPreviews(); });
    onHush(() => this.ready && this.post({ type: "hush" }));
    onRoomVoice(() => this.queueSync());
    this.queueSync();
  }

  // Words as Purple would say them, run through Purple's own speech filter. Nothing passes if Purple can't run.
  filter(text: string): Promise<string> {
    return this.ask((id) => ({ type: "filter", id, text }), "");
  }

  // Why a room's Python can't run as written; null when it can, or when Purple can't tell.
  check(source: string, names: string[]): Promise<RoomProblem | null> {
    return this.ask<[string, number | null] | null>((id) => ({ type: "check", id, source, names }), null)
      .then((p) => p && { text: p[0], line: p[1] });
  }

  private ask<T>(message: (id: number) => ToFrame, fallback: T): Promise<T> {
    const id = ++this.nextAsk;
    return new Promise((resolve) => {
      this.asking.set(id, { resolve: resolve as (value: unknown) => void, fallback });
      this.post(message(id));
    });
  }

  private answered(id: number, value: unknown): void {
    this.asking.get(id)?.resolve(value);
    this.asking.delete(id);
  }

  // A handwritten note on the screen saying what to do, until the next key.
  prompt(text: string | null): void {
    this.prompted = text;
    this.showNote(text);
  }

  // A click on Purple says why nothing happened, then puts back the note it covered.
  private nudge(): void {
    if (performance.now() - this.focusedAt < SETTLE_CLICK_MS) return;
    this.showNote("Keyboard only, on purpose!");
    this.nudging = window.setTimeout(() => this.showNote(this.prompted), NUDGE_MS);
  }

  private showNote(text: string | null): void {
    clearTimeout(this.nudging);
    this.note.textContent = text;
    this.note.hidden = !text;
  }

  show(setup: RoomSetup): void {
    this.setup = setup;
    this.queueSync();
    this.wanted = null;
    this.opening = setup.room;
    if (this.ready) this.status.textContent = "Opening the room";
    else this.moved(arrived(setup.room));
    this.element.classList.add("entering");
    void this.enter();
  }

  // A family room waits for its lines in the room voice, and for Purple to have them, so it never says one in another voice first.
  private async enter(): Promise<void> {
    const turn = ++this.entering;
    const room = draft.rooms.find((r) => r.name === this.setup.family?.name);
    if (room) {
      await roomReady(room, (text) => turn === this.entering && (this.status.textContent = text));
      this.queueSync();
      await this.syncing;
    }
    if (turn !== this.entering || !this.ready) return;
    this.wanted = this.setup.room;
    this.post({ type: "setup", setup: this.withRooms() });
  }

  private voiceLoading(text: string | null): void {
    this.voiceNote.textContent = text;
    this.voiceNote.hidden = !text;
  }

  // Any change to the draft: rebuild the pack once edits settle. Purple keeps taking keys unless
  // the new pack makes it start again.
  changed(): void {
    clearTimeout(this.timer);
    this.timer = window.setTimeout(() => this.queueSync(), SETTLE_MS);
  }

  key(key: string): void {
    if (!this.ready) return;
    this.post({ type: "key", char: key });
    announceKey(key);
  }

  // Purple's voice, downloaded now instead of when Purple first speaks.
  startVoice(): void {
    this.post({ type: "voice" });
  }

  // A key right after the edit that's settling, so Purple plays it with the change: the frame runs messages in order.
  keyAfterEdits(key: string): void {
    clearTimeout(this.timer);
    this.queueSync();
    void this.syncing.then(() => this.key(key));
  }

  // Opens the room's code line, or closes it, without the Esc menu.
  code(on: boolean): void {
    if (this.ready) this.post({ type: "code", on });
  }

  // The room in its demo's mode, before the demo's keys.
  demo(): void {
    if (this.ready) this.post({ type: "demo" });
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

  // Typing on the page plays Purple and hands it the keyboard, so Enter and Esc work from then on.
  // onKey hears every key Purple gets, however it got there.
  followKeys(onKey: (key: string) => void): () => void {
    const off = pageKeys((k) => { this.key(k); this.engage(); });
    const heard = (e: Event) => onKey((e as CustomEvent<string>).detail);
    addEventListener(KEY_EVENT, heard);
    return () => { off(); removeEventListener(KEY_EVENT, heard); };
  }

  // One at a time, so each one's changes are against what Purple last got.
  private queueSync(): void {
    this.syncing = this.syncing.then(() => this.sync()).catch((err) => console.warn("[studio] Purple's pack:", err));
  }

  // A family room goes with the rest of the family's rooms not in the pack, so the Esc menu lists
  // them all; the pack has only the added ones, so trying rooms doesn't start Purple again.
  private withRooms(): RoomSetup {
    const { family } = this.setup;
    return family ? { ...this.setup, family: { ...family, rooms: draft.rooms.filter((r) => !r.kept).map((r) => [r.name, r.source, roomIcon(r)]) } } : this.setup;
  }

  private async sync(): Promise<void> {
    // Open lists only the added pictures. The room open in its editor stays in the pack as it was, since
    // a pack with changed rooms starts Purple again; the editor plays its own copy over it.
    const open = this.setup.family?.name;
    const rooms = [...draft.rooms.filter((r) => r.kept && r.name !== open), ...this.packed.filter((r) => r.name === open)];
    this.packed = rooms.map((r) => ({ ...r }));
    const live = { ...draft, rooms, pictures: draft.pictures.filter((p) => p.kept) };
    const key = JSON.stringify([live, roomVoiceVersion()], (_, v) => (v instanceof Float32Array ? `${v.length}:${v[v.length >> 1]}` : v));
    if (key === this.sent) return;
    this.sent = key;
    this.updating.hidden = false;
    const spec = await packSpec(live, true);
    const entries = await buildEntries(spec);
    const id = manifest(spec).id;
    const pack = packChanges(id, entries, this.last);
    this.last = { id, files: new Map(entries.map((e) => [e.path, e.data])) };
    if (!pack.files.length && !pack.removed.length) return void (this.updating.hidden = true);
    // New lines in the room voice are found as they're said, so the room carries on instead of starting over.
    const voiceOnly = [...pack.files.map(([path]) => path), ...pack.removed].every((path) => path.startsWith("content/room-voice/"));
    this.post({ type: "load", pack, setup: voiceOnly ? null : this.withRooms() });
  }

  private onMessage(m: FromFrame): void {
    if (m.type === "hello") this.hello();
    if (m.type === "failed") this.last.id = "";  // the next pack goes whole, since this one may not have landed
    if (m.type === "failed") [...this.asking].forEach(([id, a]) => this.answered(id, a.fallback));
    if (m.type === "answer") this.answered(m.id, m.value);
    if (m.type === "failed") this.opened();
    if (m.type === "failed") { this.status.textContent = "Purple Computer couldn't start in this browser"; this.element.classList.add("failed"); console.warn("Purple failed:", m.text); }
    if (m.type === "restarting") this.busy(true);
    if (m.type === "loaded") { this.busy(false); this.updating.hidden = true; }
    if (m.type === "loaded" && !this.ready) {
      this.ready = true;
      this.element.classList.add("ready");
      if (this.warmsRoomVoice) warmRoomVoice();
      void this.enter();
      this.onReady();
    }
    if (m.type === "focus") this.element.classList.toggle("focused", m.on);
    if (m.type === "focus" && m.on) this.element.classList.add("tried");
    if (m.type === "focus" && m.on) this.focusedAt = performance.now();
    if (m.type === "voice") this.voiceLoading(m.text);
    if (m.type === "keydown") { announceKey(m.key); this.onTyped(); }
    if (m.type === "modifier") dispatchEvent(new CustomEvent(MODIFIER_EVENT, { detail: m.key }));
    if (m.type === "click") this.nudge();
    if (m.type === "place" && this.ready) this.moved(m.place);  // before then, the room asked for stands
    if (m.type === "place" && m.place.setup && m.place.room === this.wanted) { this.element.classList.remove("entering"); this.opened(); }
    if (m.type === "print") this.onPrint(m.text);
    if (m.type === "problem") this.onProblem({ text: m.text, line: m.line });
  }

  private opened(): void {
    this.opening = null;
    this.onOpening();
  }

  private busy(on: boolean): void {
    if (this.ready) this.status.textContent = "Updating Purple Computer";
    this.element.classList.toggle("busy", on);
  }

  private moved(place: Place): void {
    const same = place.room === this.place.room && place.menu === this.place.menu && place.code === this.place.code;
    this.place = place;
    this.reframe();
    if (!same) this.onMove();
  }

  // The whole screen or the close-up; a menu's close-up is its middle.
  private reframe(): void {
    const { room, menu, at } = this.place;
    const zoom = ZOOM[room];
    this.zoomButton.textContent = this.zoomed ? "Whole screen" : "Zoom in";
    const size = this.zoomed ? 1 / zoom.scale : 1;
    const [x, y] = (menu ? null : zoom.at ?? at) ?? [0.5, 0.5];
    const view: View = [clamp(x - size / 2, 1 - size), clamp(y - size / 2, 1 - size), size, size];
    this.post({ type: "view", view });
  }

  private post(m: ToFrame): void {
    void this.listening.then(() => (trace("[studio] sends", m.type), this.frame.contentWindow?.postMessage(m, location.origin)));
  }
}

let screen: LiveScreen | null = null;

// Started once, at Studio's first paint, and shared by every page that shows Purple.
export function liveScreen(): LiveScreen {
  screen ??= new LiveScreen();
  return screen;
}
