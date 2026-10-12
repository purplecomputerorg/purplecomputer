import { packFilename } from "../pack";
import { h } from "./dom";
import type { View } from "./view";

export function installView(): View {
  const file = packFilename();
  return {
    title: "Putting it on Purple",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Purple has no internet, so a pack goes in on a USB drive."),
      h("ol", { class: "plain" },
        h("li", {}, "Copy ", h("span", { class: "mono" }, file), " onto any USB drive. Your Purple Key works too. More than one pack is fine."),
        h("li", {}, "Plug it into the Purple computer, then turn Purple on."),
      ),
      h("p", {}, "The new words, voices, pictures, and instruments are there from the first screen. If the drive goes in while Purple is already on, restart Purple once."),
      h("p", { class: "dim small" }, "If your kid runs Purple from the Purple Key, put the pack on the Key itself: Purple reads it again every time it starts. Purple only ever reads from a USB drive, and leaves everything else on it alone."),
      h("h3", {}, "From the parent menu's terminal"),
      h("p", {}, "On an installed Purple, a pack can also be put in by hand. Open the parent menu, then the terminal, plug in the drive, and run:"),
      h("pre", {}, h("code", {}, [
        "sudo mkdir -p /mnt/drive",
        "sudo mount /dev/sdb1 /mnt/drive",
        `python3 -m purple_tui.usb_updater /mnt/drive`,
        "sudo umount /mnt/drive",
      ].join("\n"))),
      h("p", { class: "dim small" }, "The drive is usually ", h("span", { class: "mono" }, "/dev/sdb1"), "; ", h("span", { class: "mono" }, "lsblk"), " lists what is plugged in. Packs land in ", h("span", { class: "mono" }, "~/.purple/packs/"), "; to take one out again, delete its folder there."),
      h("h3", {}, "Sharing"),
      h("p", {}, "The pack is a plain file. Email it to Grandma, or put it on a USB drive for a cousin. There is no place to upload it and nothing to sign up for."),
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
    "  rooms/<name>.py              a room you made          room picker, family rooms",
    "  theme.json                   background and key rows  not read yet",
  ].join("\n");
  return {
    title: "What is in the file",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "A pack is a compressed folder of JSON, text, sound, and images, plus your rooms, each one Python file. Purple checks each file before installing, and runs a room only as a guest in a box of its own."),
      h("pre", {}, h("code", {}, tree)),
      h("p", {}, "The third column is where each file shows up on Purple. The layout copies the folders Purple already uses for its own built-in sounds and words, and Purple's source repository documents it in ", h("span", { class: "mono" }, "studio/PACK_FORMAT.md"), " along with a small command-line tool that builds, checks, and installs packs without this page, for anyone who would rather write a pack by hand."),
    ),
  };
}
