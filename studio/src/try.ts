// try.html: the live Purple alone, for purplecomputer.org to show in an iframe. Besides the height
// (src/embed.ts), the landing page hears the room Purple is in, when Purple is ready, and the room whose
// demo or code key was just pressed; it can ask for a room, type a line into the room Purple is in, or
// open a room's code line and run an example there, as the Try code key does.
// Nothing the family made in Studio is here.
import "./fonts";
import "./styles.css";
import type { Place, Room } from "./live/boot";
import { startEmojiPictures } from "./emoji";
import { embed } from "./embed";
import { KEY_EVENT } from "./keys";
import { h } from "./ui/dom";
import { createStage, keycaps, ROOMS } from "./ui/stage";

export type ToTry =
  | { type: "purple-try-room"; room: Room }
  | { type: "purple-try-type"; text: string }
  | { type: "purple-try-code"; room?: Room };

const START = new URLSearchParams(location.search).get("room") as Room | null;
const isRoom = (r: unknown): r is Room => ROOMS.some(([room]) => room === r);

const app = document.getElementById("app")!;
let ready = false;
// Rooms with a code line, and the keys in it that pick an example and run it: down steps into the
// example cards, right to the next one (Art's red square), Enter runs it.
const EXAMPLES: Partial<Record<Room, string[]>> = {
  art: ["down", "_", "right", "_", "enter"],
  music: ["down", "_", "enter"],
  blocks: ["down", "_", "enter"],
};

// The demo and code keys: under the rooms, with the phone keys, for a room that has them.
const demoKey = h("button", { class: "demo-key", type: "button", onclick: () => demo(stage.live.place.room) });
const codeLabel = h("span");
const codeKey = h("button", { class: "demo-key", type: "button", onclick: () => { stage.showKeys(["escape", "space"], 0); code(); } }, codeLabel, keycaps("Esc", "Space"));
const trayKeys = h("div", { class: "demo-keys", hidden: true }, demoKey, codeKey);
const moved = () => {
  const room = stage.live.place.room;
  const d = ready ? DEMOS[room] : undefined;
  demoKey.hidden = !d;
  demoKey.textContent = d ? `▶ ${d.label}` : "";
  codeKey.hidden = !ready || !EXAMPLES[room];
  codeLabel.textContent = stage.live.place.code ? "Close code" : "Try code";
  trayKeys.hidden = demoKey.hidden && codeKey.hidden;
  hint();
  tip();
  tell();
  codeWhenThere();
};
const stage = createStage({ stays: false, onMove: moved, trayKey: trayKeys, keyHints: true });
stage.live.onReady = () => { ready = true; moved(); };
stage.live.warmsRoomVoice = false;

// What to do in each room, handwritten on the screen once it's been clicked, until the next key.
const TYPE: Record<Room, string> = { art: "Type some letters!", music: "Press any keys!", play: "Type a word, then Enter!", blocks: "Type some letters!" };
let hinted: Room | null = null;
const hint = () => {
  const { room, menu } = stage.live.place;
  if (!ready || menu || room === hinted) return;
  hinted = room;
  stage.live.prompt(TYPE[room]);
};

// What mashing keys won't find, one at a time under the keyboard until its key is pressed; a phone can't hold a key.
// A held key's tip waits for what the hold does (Purple's place says), since a tap presses the same key.
type Tip = { text: string; key: string; hold?: keyof Place };
const TIPS: Record<Room | "letters", Tip[]> = {
  music: [
    { text: "Press Enter for a new instrument", key: "enter" },
    { text: "*Hold* Enter to record a loop", key: "enter", hold: "looping" },
    { text: "Press Tab to hear the letters", key: "tab" },
  ],
  letters: [
    { text: "Press Enter for letter sounds", key: "enter" },
    { text: "Press Tab to play music again", key: "tab" },
  ],
  art: [
    { text: "Press Tab to write letters", key: "tab" },
  ],
  play: [{ text: "Press Tab so Purple says it", key: "tab" }],
  blocks: [
    { text: "Press Tab to spin around", key: "tab" },
    { text: "Press Enter to build up high", key: "enter" },
  ],
};
const KEYS_BEFORE_TIP = 6;
const HOLDS = matchMedia("(pointer: fine)");
const told = new Set<Tip>();
let showing: Tip | undefined;
let [since, tipRoom, demoing] = [0, "", false];
const done = (t: Tip) => {
  told.add(t);
  since = 0;
};
const tip = () => {
  const place = stage.live.place;
  const { room, menu, code, letters } = place;
  if (room !== tipRoom) [since, tipRoom] = [0, room];
  if (showing?.hold && place[showing.hold]) done(showing);
  const next = ready && !menu && !code && since >= KEYS_BEFORE_TIP
    ? TIPS[letters ? "letters" : room].find((t) => !told.has(t) && (!t.hold || HOLDS.matches)) : undefined;
  if (next === showing) return;
  showing = next;
  stage.laptop.tip(next?.text ?? null, next?.key, !!next?.hold);
};
// Purple's voice is a big download: it starts with the first key, so a visitor who only looks never pays for it.
const saveData = (navigator as { connection?: { saveData?: boolean } }).connection?.saveData;
if (!saveData) addEventListener(KEY_EVENT, () => stage.live.startVoice(), { once: true });
addEventListener(KEY_EVENT, (e) => {
  if (demoing) return;
  since++;
  if (showing && !showing.hold && showing.key === (e as CustomEvent<string>).detail) done(showing);
  tip();
});

const repeat = (n: number, key: string): string[] => Array(Math.abs(n)).fill(key);
const line = (text: string): string[] => [...text.toLowerCase()].map((c) => c === " " ? "space" : c).concat("enter");
const TYPE_MS = 120;

// Keys that paint a picture from where the brush is: arrows over to each square, then its letter.
// A letter moves the brush one right, and up or down right after one goes from under the square it painted.
function paint(rows: string[]): string[] {
  const keys: string[] = [];
  let [cx, cy, stamped] = [0, 0, false];
  rows.forEach((row, y) => [...row].forEach((c, x) => {
    if (c === ".") return;
    if (y !== cy && stamped) cx--;
    keys.push(...repeat(y - cy, y > cy ? "down" : "up"), ...repeat(x - cx, x > cx ? "right" : "left"), c);
    [cx, cy, stamped] = [x + 1, y, true];
  }));
  return keys;
}

const HEART = [".ee...ee.", "errr.rrre", "rrrrrrrrr", "ttttttttt", ".ttttttt.", "..yyyyy..", "...uuu...", "....i...."];
// Art's brush starts in the top corner; until someone has painted, the heart goes in the middle.
let artUsed = false;
addEventListener(KEY_EVENT, () => { if (stage.live.place.room === "art") artUsed = true; });
// Play's demo types the next of these each time.
const LINES = ["cat * 5", "red + blue", "3 x 4 bananas", "say I love you"];
let lines = 0;

// Each room's demo: keys Purple gets on the laptop, ms apart ("_" waits a beat).
const DEMOS: Partial<Record<Room, { label: string; keys: () => string[]; ms: number }>> = {
  art: { label: "Paint a heart", keys: () => [...(artUsed ? [] : [...repeat(10, "down"), ...repeat(30, "right")]), ...paint(HEART)], ms: 35 },
  // Twinkle Twinkle Little Star, on the middle row's scale.
  music: { label: "Play a song", keys: () => "a a g g h h g _ f f d d s s a".split(" "), ms: 330 },
  play: { label: "Type something", keys: () => line(LINES[lines++ % LINES.length]), ms: TYPE_MS },
  // A pyramid: letters climb over the blocks under them, so each row back over the last goes a level up.
  blocks: { label: "Build a pyramid", keys: () => "down down down down left left left left right e r t y t r e left left d f g f d right right c v c left left b".split(" "), ms: 110 },
};

// What's playing; a new one, typing, or another room stops it.
let playing = 0;
stage.live.onTyped = () => playing++;
function play(keys: string[], ms: number, done: () => void) {
  const room = stage.live.place.room;
  const run = ++playing;
  const step = (i: number) => {
    if (run !== playing || stage.live.place.room !== room) return;
    if (i === keys.length) return done();
    demoing = true;
    if (keys[i] !== "_") stage.laptop.type(keys[i]);
    demoing = false;
    setTimeout(() => step(i + 1), ms);
  };
  step(0);
}

function demo(room: Room) {
  const d = DEMOS[room];
  if (!d || stage.live.place.room !== room) return;
  // Its keys are for the room itself, not the code line.
  if (stage.live.place.code) return code(() => demo(room));
  tell({ demoed: room });
  stage.live.demo();
  play(d.keys(), d.ms, () => stage.live.prompt("Your turn!"));
}

function code(after = () => {}) {
  const { room, code: open } = stage.live.place;
  if (!open) tell({ coded: room });
  stage.live.code(!open);
  play(open ? ["_"] : ["_", ...EXAMPLES[room] ?? []], 250, after);
}

// The room the landing page asked to code in (purple-try-code). Purple says which room it's in a moment
// after it gets there, so the code line opens on the next move that finds Purple ready in that room.
let codeIn: Room | null = null;
function codeWhenThere() {
  if (!codeIn || !ready || stage.live.place.room !== codeIn) return;
  codeIn = null;
  if (!stage.live.place.code) code();
}

const tell = embed(app, (data) => {
  const m = data as ToTry;
  if (m.type === "purple-try-room" && isRoom(m.room)) stage.live.show({ room: m.room });
  // Pressed on the laptop's keys, so they light up as Purple gets them.
  if (m.type === "purple-try-type") play(line(m.text), TYPE_MS, () => {});
  // The asked room if it has a code line, else this one if it does, else Art.
  if (m.type === "purple-try-code") {
    const here = stage.live.place.room;
    codeIn = isRoom(m.room) && EXAMPLES[m.room] ? m.room : EXAMPLES[here] ? here : "art";
    if (here !== codeIn) stage.live.show({ room: codeIn });
    codeWhenThere();
  }
}, () => ({ room: stage.live.place.room, ready }));

app.append(stage.element);
void startEmojiPictures();
stage.show({ live: { room: START && isRoom(START) ? START : "art" } });
