import { features } from "../state";
import { h } from "./dom";
import type { View } from "./view";

export const putItOnPurple = () => h("ol", { class: "steps" },
  h("li", {}, "Download your Purple Pack."),
  h("li", {}, "Copy it onto your Purple Key, or any USB drive."),
  h("li", {}, "Plug the drive into Purple, on or off. When Purple shows your pack, choose Add."),
);

export function installView(): View {
  return {
    title: "Putting it on Purple",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Purple has no internet, so your Purple Pack goes in on a USB drive."),
      putItOnPurple(),
      h("p", {}, "Purple asks for the Parent PIN first if you've set one. Everything you made works right away, with no restart.",
        features.rooms ? " Rooms wait until you turn them on in the Parent Menu, under Family Rooms." : ""),
      h("p", {}, "If Purple starts from your Purple Key, keep your Purple Pack on the Key so it's there every time."),
      h("h3", {}, "Sharing"),
      h("p", {}, "Your Purple Pack is yours to share. Email it to Grandma, or put it on a USB drive for a cousin. There is no place to upload it and nothing to sign up for."),
    ),
  };
}

export function formatView(): View {
  const rows: [file: string, what: string, where?: string][] = [
    ["manifest.json", "id, name, version, type, format"],
    ["studio.json, studio/pictures/", "how Studio reopens it", "Purple never reads these"],
    ["content/", ""],
    ["  emoji.json", "word -> emoji", "Play room"],
    ["  synonyms.json", "nickname -> word", "Play room"],
    ["  meanings.json", "word -> what it is", "Play room, \"who is grandma\""],
    ["  rankings.txt", "one word per line", "Play room autocomplete"],
    ["  letters/a.wav, slash.wav …", "your voice, per key", "Music room, Say Letters"],
    ["  voice/<phrase>.wav", "your voice, per phrase", "spoken instead of Purple's voice"],
    ["  pictures/<name>.json, .png", "paint list and preview", "Art room, Open"],
    ["  <instrument>/c1.wav … d7.wav", "one note per file", "Music room"],
    ["  instruments/<name>.json", "the slider numbers", "re-rendered by Purple's own synth"],
    ...(features.rooms ? [
      ["  rooms/<name>.py", "a room you made", "room picker, family rooms"],
      ["  rooms/<name>.json", "the room's emoji", "room picker"],
      ["  rooms/purple.py", "the library rooms run on", "every family room"],
      ["  images/<name>.png", "a room's pictures", "rooms, and words shown as pictures"],
      ["  sounds/<name>.wav", "a room's sounds", "rooms"],
      ["  room-voice/<phrase>.wav", "a room's lines, spoken", "rooms"],
      ["  word-pictures.json", "word -> picture", "Play room"],
    ] satisfies typeof rows : []),
    ["  theme.json", "screen and key colors", "every room"],
  ];
  const tree = rows.map(([file, what, where]) => (file.padEnd(31) + what.padEnd(25) + (where ?? "")).trimEnd()).join("\n");
  return {
    title: "What is in a Purple Pack",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, features.rooms
        ? "A pack is a compressed folder of JSON, text, sound, and images, plus your rooms, each one Python file. Purple checks each file before installing, and runs a room only as a guest in a box of its own."
        : "A pack is a compressed folder of JSON, text, sound, and images. Purple checks each file before installing."),
      h("pre", {}, h("code", {}, tree)),
      h("p", {}, "The third column is where each file shows up on Purple. The layout copies the folders Purple already uses for its own built-in sounds and words, and Purple's source repository documents it in ", h("span", { class: "mono" }, "studio/PACK_FORMAT.md"), " along with a small command-line tool that builds, checks, and installs packs without this page, for anyone who would rather write a pack by hand."),
    ),
  };
}
