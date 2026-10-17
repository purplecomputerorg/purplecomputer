import { features } from "../state";
import { h } from "./dom";
import type { View } from "./view";

export const putItOnPurple = () => h("ol", { class: "steps" },
  h("li", {}, "Download your file."),
  h("li", {}, "Copy it onto any USB drive. Your Purple Key works too."),
  h("li", {}, "Plug the drive into Purple and turn Purple on. That's it."),
);

export function installView(): View {
  return {
    title: "Putting it on Purple",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Purple has no internet, so your file goes in on a USB drive."),
      putItOnPurple(),
      h("p", {}, "Everything you made is there from the first screen. If the drive goes in while Purple is already on, restart Purple once."),
      h("h3", {}, "Sharing"),
      h("p", {}, "The file is yours to share. Email it to Grandma, or put it on a USB drive for a cousin. There is no place to upload it and nothing to sign up for."),
    ),
  };
}

export function formatView(): View {
  const tree = [
    "manifest.json                  id, name, version, type, format",
    "content/",
    "  emoji.json                   word -> emoji            Play room",
    "  synonyms.json                nickname -> word         Play room",
    "  rankings.txt                 one word per line        Play room autocomplete",
    "  letters/a.wav, slash.wav …   your voice, per key      Music room, Say Letters",
    "  voice/<phrase>.wav           your voice, per phrase   spoken instead of Purple's voice",
    "  pictures/<name>.json, .png   paint list and preview   Art room, Open",
    "  <instrument>/c1.wav … d7.wav one note per file        Music room",
    "  instruments/<name>.json      the slider numbers       re-rendered by Purple's own synth",
    ...(features.rooms ? ["  rooms/<name>.py              a room you made          room picker, family rooms"] : []),
    "  theme.json                   background and key rows  not read yet",
  ].join("\n");
  return {
    title: "What is in the file",
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
