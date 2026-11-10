// try.html: the live Purple alone, for purplecomputer.org to show in an iframe. Besides the height
// (src/embed.ts), the landing page hears the room Purple is in and when Purple is ready; it can ask
// for a room, or type a line into the room Purple is in. Nothing the family made in Studio is here.
import "./fonts";
import "./styles.css";
import type { Room } from "./live/boot";
import { startEmojiPictures } from "./emoji";
import { embed } from "./embed";
import { createStage, ROOMS } from "./ui/stage";

export type ToTry = { type: "purple-try-room"; room: Room } | { type: "purple-try-type"; text: string };

const START = new URLSearchParams(location.search).get("room") as Room | null;
const isRoom = (r: unknown): r is Room => ROOMS.some(([room]) => room === r);

const app = document.getElementById("app")!;
let ready = false;
const stage = createStage({ stays: false, onMove: () => { hint(); tell(); } });
stage.live.onReady = () => { ready = true; hint(); tell(); };

// What to do in each room, handwritten on the screen once it's been clicked, until the next key.
const TYPE: Record<Room, string> = { art: "Type some letters!", music: "Press any keys!", play: "Type a word, then Enter!", blocks: "Type some letters!" };
let hinted: Room | null = null;
const hint = () => {
  const { room, menu } = stage.live.place;
  if (!ready || menu || room === hinted) return;
  hinted = room;
  stage.live.prompt(TYPE[room]);
};

const tell = embed(app, (data) => {
  const m = data as ToTry;
  if (m.type === "purple-try-room" && isRoom(m.room)) stage.live.show({ room: m.room });
  // Pressed on the laptop's keys, so they light up as Purple gets them.
  if (m.type === "purple-try-type") for (const c of [...m.text.toLowerCase(), "\n"]) stage.laptop.type(c === " " ? "space" : c === "\n" ? "enter" : c);
}, () => ({ room: stage.live.place.room, ready }));

app.append(stage.element);
void startEmojiPictures();
stage.show({ live: { room: START && isRoom(START) ? START : "art" } });
