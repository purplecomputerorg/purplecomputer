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
// Until Purple is ready they show their labels, disabled, with a spinner.
const labelled = (onclick: () => void, ...after: Node[]) => {
  const label = h("span");
  return { label, key: h("button", { class: "demo-key", type: "button", onclick }, h("span", {}, h("i", { class: "spin" }), label), ...after) };
};
const demoKeys = [0, 1].map((i) => labelled(() => demo(stage.live.place.room, i)));
const codeKey = labelled(() => { stage.showKeys(["escape", "space"], 0); code(); }, keycaps("Esc", "Space"));
const spinKey = labelled(() => play(tour(), 130, () => {}), keycaps("Tab"));
const trayKeys = h("div", { class: "demo-keys", hidden: true }, ...demoKeys.map((d) => d.key), spinKey.key, codeKey.key);
const showKeys = () => {
  const room = stage.live.place.room;
  const ds = DEMOS[room] ?? [];
  demoKeys.forEach(({ key, label }, i) => {
    key.hidden = !ds[i];
    const d = ds[i];
    label.replaceChildren(...d ? [`${ready ? "▶ " : ""}${d.label}`, ...d.typed ? [" ", h("code", {}, d.typed)] : []] : []);
  });
  spinKey.key.hidden = room !== "blocks" || !!stage.live.place.code;
  spinKey.label.textContent = "Spin around";
  codeKey.key.hidden = !EXAMPLES[room];
  codeKey.label.textContent = stage.live.place.code ? "Close code" : "Try code";
  [...demoKeys, spinKey, codeKey].forEach(({ key }) => key.disabled = !ready);
  trayKeys.hidden = !ds.length && codeKey.key.hidden;
};
const moved = () => {
  showKeys();
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
    { text: "*Hold* Enter to loop your tune", key: "enter", hold: "looping" },
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
    { text: "Press an arrow to move, then type more", key: "right" },
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
// Row by row from the front, snaking, with as many letters in each column as it stands high: a keyboard
// row a level, from the bottom row up to the numbers. It starts from the floor's middle (Purple's demo puts the cursor there).
const LEVELS = "cfr";
const pyramid = (): string[] => {
  const n = LEVELS.length, size = 2 * n - 1, rows = [...Array(size).keys()];
  return [...repeat(n - 1, "left"), ...repeat(n - 1, "down"), ...rows.flatMap((row) => [
    ...rows.flatMap((i) => {
      const col = row % 2 ? size - 1 - i : i;
      return [...LEVELS.slice(0, n - Math.max(Math.abs(col - n + 1), Math.abs(row - n + 1))), ...(i < size - 1 ? [row % 2 ? "left" : "right"] : [])];
    }),
    ...(row < size - 1 ? ["up"] : []),
  ])];
};
// Blocks' camera, Tab held with the arrows, once around in quarters: rising to look down on the build,
// sweeping down low, staying low, then back up to the resting tilt at the front. Each token is a turn
// step, then a tilt step with u or d, so the view tilts while it turns instead of only spinning.
const TOUR = "ru ru ru r r rd rd rd rd r r r r r r ru r r r r";
const ARROW: Record<string, string> = { r: "right", u: "up", d: "down" };
const tour = (): string[] => TOUR.split(" ").flatMap((t) => [...t].map((c) => `tab+${ARROW[c]}`));
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

// Each room's demos: keys Purple gets on the laptop, ms apart ("_" waits a beat).
// typed: the line Purple gets, shown in code type after the label.
type Demo = { label: string; typed?: string; keys: () => string[]; ms: number; letters?: boolean };
const DEMOS: Partial<Record<Room, Demo[]>> = {
  art: [{ label: "Paint a heart", keys: () => [...(artUsed ? [] : [...repeat(10, "down"), ...repeat(30, "right")]), ...paint(HEART)], ms: 35 }],
  music: [
    // Twinkle Twinkle Little Star, on the middle row's scale.
    { label: "Play a song", keys: () => "a a g g h h g _ f f d d s s a".split(" "), ms: 330 },
    // In Letters saying sounds: c, a, t, then Space says the word they spell.
    { label: "Spell cat", keys: () => "_ c _ a _ t _ _ space".split(" "), ms: 500, letters: true },
  ],
  play: ["red + blue", "say cat + cat x 5"].map((typed) => ({ label: "Type", typed, keys: () => line(typed), ms: TYPE_MS })),
  blocks: [{ label: "Build a pyramid", keys: pyramid, ms: 70 }],
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

function demo(room: Room, i: number) {
  const d = DEMOS[room]?.[i];
  if (!d || stage.live.place.room !== room) return;
  // Its keys are for the room itself, not the code line.
  if (stage.live.place.code) return code(() => demo(room, i));
  tell({ demoed: room });
  stage.live.demo(d.letters);
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
showKeys();
