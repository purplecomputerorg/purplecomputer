// try.html: the live Purple alone, for purplecomputer.org to show in an iframe. The landing page
// says hello, and from then on hears this page's height, the room Purple is in, and when Purple is
// ready; it can ask for a room, or type a line into the room Purple is in. Nothing the family made
// in Studio is here.
import "./fonts";
import "./styles.css";
import type { Room } from "./live/boot";
import { startEmojiPictures } from "./emoji";
import { createStage, ROOMS } from "./ui/stage";

export type FromTry = { type: "purple-try"; height: number; room: Room; ready: boolean };
export type ToTry =
  | { type: "purple-try-hello" }
  | { type: "purple-try-room"; room: Room }
  | { type: "purple-try-type"; text: string };

// purplecomputer.org, its Vercel previews, and its dev server.
const EMBEDDER = /^(https:\/\/(www\.)?purplecomputer\.org|https:\/\/landing-[a-z0-9-]+-tavinathanson\.vercel\.app|http:\/\/(localhost|simba):3002)$/;
const START = new URLSearchParams(location.search).get("room") as Room | null;
const isRoom = (r: unknown): r is Room => ROOMS.some(([room]) => room === r);

const app = document.getElementById("app")!;
let parentOrigin: string | null = null;
let ready = false;
const stage = createStage({ stays: false, onMove: () => tell() });
stage.live.onReady = () => { ready = true; tell(); };

function tell(): void {
  if (!parentOrigin) return;
  const m: FromTry = { type: "purple-try", height: Math.max(app.scrollHeight, Math.ceil(app.getBoundingClientRect().height)), room: stage.live.place.room, ready };
  parent.postMessage(m, parentOrigin);
}

addEventListener("message", (e: MessageEvent<ToTry>) => {
  if (!EMBEDDER.test(e.origin) || !e.data?.type) return;
  parentOrigin = e.origin;
  const m = e.data;
  if (m.type === "purple-try-room" && isRoom(m.room)) stage.live.show({ room: m.room });
  // Pressed on the laptop's keys, so they light up as Purple gets them.
  if (m.type === "purple-try-type") for (const c of [...m.text.toLowerCase(), "\n"]) stage.laptop.type(c === " " ? "space" : c === "\n" ? "enter" : c);
  tell();
});

app.append(stage.element);
void startEmojiPictures();
stage.show({ live: { room: START && isRoom(START) ? START : "art" } });
// The stage's own height, not the window's, so the frame can shrink to fit as well as grow.
new ResizeObserver(() => tell()).observe(app);
