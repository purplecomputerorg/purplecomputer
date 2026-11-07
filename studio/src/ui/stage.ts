// The live Purple as people see it: the handwritten title, the pretend laptop with the real Purple
// inside, the room buttons under it, and on a phone a few big keys for the room it's in. Studio's
// pages show it beside the editor; try.html shows it alone, for purplecomputer.org to embed.
import { typingKeys } from "../keys";
import type { Room, RoomSetup } from "../live/boot";
import { h } from "./dom";
import { Laptop } from "./laptop";
import { liveScreen } from "./live";
import { staysHere } from "./privacy";

// What a page asks of the stage: the room to set Purple up in, its own few phone keys, and a caption.
export interface StagePage {
  live?: RoomSetup;
  keys?: () => string[];
  caption?: string;
}

export const ROOMS: [Room, string][] = [["art", "🎨 Art"], ["music", "🎵 Music"], ["play", "💬 Play"], ["blocks", "🧊 Blocks"]];
const TRAY: Record<Room, string[]> = { play: typingKeys("cat"), music: [..."asdfg"], art: ["q", "a", "z", "space"], blocks: ["q", "a", "z", "enter"] };
const ARROWS = ["left", "up", "down", "right"];

// stays: the line saying what's typed stays on the device (try.html leaves it to the page around it).
// onMove: Purple moved to another room, or opened or closed a menu.
export function createStage({ stays = true, onMove = () => {} }: { stays?: boolean; onMove?: () => void } = {}) {
  const live = liveScreen();
  let page: StagePage | null = null;
  // The laptop and the live Purple inside it stay put for the whole visit (moving an iframe reloads it).
  const engage = () => page?.live && live.engage();
  const laptop = new Laptop((key) => { if (page?.live) live.key(key); engage(); });
  laptop.screen.append(live.element);

  const roomButtons = h("div", { class: "room-buttons" });
  const phoneBar = h("div", { class: "phone-bar" }, roomButtons, laptop.tray, h("p", { class: "phone-hint" }, "Or tap the laptop to type with your phone's keyboard."));
  const caption = h("p", { class: "caption" });
  const element = h("aside", { class: "stage" }, h("div", { class: "stage-inner" },
    h("h3", {}, "This little computer is a real Purple Computer for you to try"), laptop.element, phoneBar, caption,
    stays ? staysHere("This Purple runs in your browser. What you type into it stays on your device.") : null));

  // The room buttons, and the few keys for the room Purple is in (or the arrows while a menu is open).
  function refresh() {
    const setup = page?.live;
    roomButtons.hidden = !setup;
    roomButtons.replaceChildren(...ROOMS.map(([room, label]) => h("button", {
      type: "button", "aria-pressed": String(live.place.room === room),
      onclick: () => { live.show(room === setup?.room ? setup : { room }); engage(); },
    }, label)));
    const { room, menu } = live.place;
    const keys = !setup ? [] : menu ? [...ARROWS, "enter"] : (room === setup.room && page?.keys?.()) || TRAY[room];
    laptop.paint(setup ? [...keys, "escape"] : keys);
  }
  live.onMove = () => { refresh(); onMove(); };

  function show(next: StagePage | null) {
    page = next;
    live.element.hidden = !next?.live;
    caption.textContent = next?.caption ?? "";
    if (next?.live) live.show(next.live);
    refresh();
  }

  return { element, live, laptop, show, refresh };
}
